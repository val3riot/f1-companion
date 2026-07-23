from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from .cache import AsyncTTLCache
from .config import settings
from .rate_limit import SlidingWindowRateLimiter


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latest_by_driver(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for row in rows:
        driver_number = row.get("driver_number")
        if driver_number is None:
            continue
        current = latest.get(driver_number)
        if current is None or row.get("date", "") > current.get("date", ""):
            latest[driver_number] = row
    return list(latest.values())


def laps_completed_by(
    laps: list[dict[str, Any]], cursor: datetime
) -> list[dict[str, Any]]:
    rows = []
    for lap in laps:
        date_start = lap.get("date_start")
        if not isinstance(date_start, str):
            continue
        try:
            lap_start = parse_date(date_start)
        except ValueError:
            continue
        lap_duration = lap.get("lap_duration")
        if isinstance(lap_duration, (int, float)):
            lap_finish = lap_start + timedelta(seconds=lap_duration)
        else:
            lap_finish = lap_start
        if lap_finish <= cursor:
            rows.append(lap)
    return rows


def best_laps(laps: list[dict[str, Any]]) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
]:
    best_lap = min(
        laps,
        key=lambda lap: lap["lap_duration"],
        default=None,
    )
    best_laps_by_driver: dict[int, dict[str, Any]] = {}
    for lap in laps:
        driver_number = lap.get("driver_number")
        if driver_number is None:
            continue
        current = best_laps_by_driver.get(driver_number)
        if current is None or lap["lap_duration"] < current["lap_duration"]:
            best_laps_by_driver[driver_number] = lap
    return best_lap, sorted(
        best_laps_by_driver.values(),
        key=lambda lap: lap["lap_duration"],
    )


class OpenF1Client:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.openf1_base_url,
            timeout=httpx.Timeout(25),
            headers={"User-Agent": "f1-companion/0.1"},
        )
        self._limiter = SlidingWindowRateLimiter(
            settings.requests_per_second,
            settings.requests_per_minute,
        )
        self._cache = AsyncTTLCache()

    async def close(self) -> None:
        await self._http.aclose()

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        ttl: int | None = None,
        empty_on_not_found: bool = False,
    ) -> list[dict[str, Any]]:
        clean_params = {
            key: value
            for key, value in (params or {}).items()
            if value is not None
        }
        cache_key = f"{endpoint}?{urlencode(sorted(clean_params.items()))}"

        async def fetch() -> list[dict[str, Any]]:
            await self._limiter.acquire()
            response = await self._http.get(f"/{endpoint}", params=clean_params)
            if empty_on_not_found and response.status_code == 404:
                return []
            response.raise_for_status()
            return response.json()

        return await self._cache.get_or_set(
            cache_key,
            fetch,
            ttl if ttl is not None else settings.cache_ttl_seconds,
        )

    async def snapshot(
        self, session_key: int, requested_at: datetime | None
    ) -> dict[str, Any]:
        sessions = await self.get(
            "sessions", {"session_key": session_key}, ttl=3600
        )
        if not sessions:
            raise ValueError("Sessione non trovata")

        session = sessions[0]
        now = datetime.now(timezone.utc)
        start = parse_date(session["date_start"])
        end = parse_date(session["date_end"])
        is_live_window = start - timedelta(minutes=30) <= now <= end + timedelta(
            minutes=30
        )

        # Sequential calls keep behavior predictable under the free global quota.
        drivers = await self.get(
            "drivers", {"session_key": session_key}, ttl=3600
        )
        results = await self.get(
            "session_result", {"session_key": session_key}, ttl=300
        )
        laps = await self.get(
            "laps", {"session_key": session_key}, ttl=300
        )

        valid_laps = [
            lap
            for lap in laps
            if isinstance(lap.get("lap_duration"), (int, float))
            and not lap.get("is_pit_out_lap", False)
        ]
        cursor = requested_at or min(now, end)
        if requested_at is None and now > end:
            winner = next(
                (
                    result
                    for result in results
                    if result.get("position") == 1
                    and isinstance(result.get("duration"), (int, float))
                ),
                None,
            )
            lap_finishes = [
                parse_date(lap["date_start"])
                + timedelta(seconds=lap["lap_duration"])
                for lap in valid_laps
                if lap.get("date_start")
            ]
            if winner and session.get("session_type") == "Race":
                cursor = start + timedelta(seconds=winner["duration"])
            elif lap_finishes:
                cursor = max(lap_finishes)

        cursor = max(start, min(cursor, end))
        visible_laps = laps_completed_by(valid_laps, cursor)
        if not visible_laps and requested_at is None and cursor >= end:
            visible_laps = valid_laps
        best_lap, driver_best_laps = best_laps(visible_laps)
        short_from = cursor - timedelta(seconds=12)
        timing_from = cursor - timedelta(minutes=5)
        iso_cursor = cursor.isoformat()
        common_short = {
            "session_key": session_key,
            "date>=": short_from.isoformat(),
            "date<=": iso_cursor,
        }
        common_timing = {
            "session_key": session_key,
            "date>=": timing_from.isoformat(),
            "date<=": iso_cursor,
        }

        positions = await self.get(
            "position", common_timing, ttl=20, empty_on_not_found=True
        )
        intervals = await self.get(
            "intervals", common_timing, ttl=20, empty_on_not_found=True
        )
        locations = await self.get(
            "location", common_short, ttl=10, empty_on_not_found=True
        )
        telemetry = await self.get(
            "car_data", common_short, ttl=10, empty_on_not_found=True
        )
        weather = await self.get(
            "weather", common_timing, ttl=60, empty_on_not_found=True
        )

        return {
            "session": session,
            "cursor": iso_cursor,
            "is_live_window": is_live_window,
            "drivers": drivers,
            "results": results,
            "positions": latest_by_driver(positions),
            "intervals": latest_by_driver(intervals),
            "locations": latest_by_driver(locations),
            "telemetry": latest_by_driver(telemetry),
            "weather": weather[-1] if weather else None,
            "best_lap": best_lap,
            "best_laps": driver_best_laps,
        }
