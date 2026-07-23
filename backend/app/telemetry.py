import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import statistics
from typing import Any

from .config import settings


class TelemetryUnavailable(RuntimeError):
    pass


def _number(value: Any) -> float | None:
    try:
        if value is None or value != value:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def linear_slope(values: list[tuple[float, float]]) -> float | None:
    if len(values) < 3:
        return None
    xs = [item[0] for item in values]
    ys = [item[1] for item in values]
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)
    ) / denominator


def corner_class(min_speed: float) -> str:
    if min_speed < 140:
        return "slow"
    if min_speed < 210:
        return "medium"
    return "fast"


def downsample_trace(
    rows: list[tuple[float, float, float, float]],
    max_points: int = 240,
) -> list[list[float]]:
    if not rows:
        return []
    if len(rows) <= max_points:
        selected = rows
    else:
        indexes = {
            round(index * (len(rows) - 1) / (max_points - 1))
            for index in range(max_points)
        }
        selected = [rows[index] for index in sorted(indexes)]
    return [
        [
            round(distance, 1),
            round(speed, 1),
            round(throttle, 1),
            round(brake, 1),
        ]
        for distance, speed, throttle, brake in selected
    ]


def lap_time_seconds(row: Any) -> float | None:
    try:
        value = row.get("LapTime")
    except AttributeError:
        value = None
    if value is None or value != value:
        return None
    try:
        return float(value.total_seconds())
    except AttributeError:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def lap_number_value(row: Any) -> int | None:
    try:
        value = row.get("LapNumber")
    except AttributeError:
        value = None
    number = _number(value)
    return int(number) if number is not None else None


def lap_options(rows: list[Any]) -> list[dict[str, Any]]:
    options = []
    for row in rows:
        number = lap_number_value(row)
        seconds = lap_time_seconds(row)
        if number is None or seconds is None:
            continue
        try:
            compound = str(row.get("Compound", ""))
            stint = _number(row.get("Stint"))
        except AttributeError:
            compound = ""
            stint = None
        options.append(
            {
                "lap_number": number,
                "lap_time": round(seconds, 3),
                "compound": compound,
                "stint": int(stint) if stint is not None else None,
            }
        )
    return sorted(options, key=lambda item: item["lap_number"])


def downsample_xy(
    rows: list[tuple[float, float]],
    max_points: int = 520,
) -> list[list[float]]:
    if not rows:
        return []
    if len(rows) <= max_points:
        selected = rows
    else:
        indexes = {
            round(index * (len(rows) - 1) / (max_points - 1))
            for index in range(max_points)
        }
        selected = [rows[index] for index in sorted(indexes)]
    return [[round(x, 1), round(y, 1)] for x, y in selected]


def circuit_corners(corners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for corner in corners:
        x = _number(corner.get("X"))
        y = _number(corner.get("Y"))
        if x is None or y is None:
            continue
        number = _number(corner.get("Number"))
        distance = _number(corner.get("Distance"))
        result.append(
            {
                "number": int(number) if number is not None else 0,
                "letter": str(corner.get("Letter", "")),
                "distance": round(distance, 1)
                if distance is not None
                else None,
                "x": round(x, 1),
                "y": round(y, 1),
            }
        )
    return result


def empty_circuit_map(
    corners: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "trace": [],
        "corners": circuit_corners(corners),
    }


def add_trace_to_circuit_map(
    circuit_map: dict[str, Any],
    telemetry: Any,
) -> None:
    if (
        circuit_map["trace"]
        or telemetry is None
        or telemetry.empty
        or not {"X", "Y"}.issubset(telemetry.columns)
    ):
        return
    circuit_map["trace"] = downsample_xy(
        [
            (float(row["X"]), float(row["Y"]))
            for _, row in telemetry[["X", "Y"]]
            .dropna()
            .iterrows()
        ]
    )


class FastF1Service:
    def __init__(self) -> None:
        self._configured = False

    def _library(self):
        try:
            import fastf1
        except ImportError as exc:
            raise TelemetryUnavailable(
                "FastF1 non è installato nel backend"
            ) from exc

        if not self._configured:
            cache_dir = Path(settings.fastf1_cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            fastf1.Cache.enable_cache(str(cache_dir))
            self._configured = True
        return fastf1

    async def event_schedule(self, year: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._event_schedule, year)

    def _event_schedule(self, year: int) -> list[dict[str, Any]]:
        fastf1 = self._library()
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        events: list[dict[str, Any]] = []
        for _, event in schedule.iterrows():
            events.append(
                {
                    "round": int(event["RoundNumber"]),
                    "name": str(event["EventName"]),
                    "country": str(event["Country"]),
                    "location": str(event["Location"]),
                    "date": event["EventDate"].isoformat(),
                }
            )
        return events

    async def post_race(
        self,
        year: int,
        round_number: int,
        telemetry_session: str = "race",
        lap_mode: str = "best",
        lap_number: int | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._post_race,
            year,
            round_number,
            telemetry_session,
            lap_mode,
            lap_number,
        )

    async def available_sessions(
        self,
        year: int,
        round_number: int,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._available_sessions, year, round_number
        )

    def _available_sessions(
        self,
        year: int,
        round_number: int,
    ) -> list[dict[str, Any]]:
        fastf1 = self._library()
        session_map = {
            "Practice 1": ("fp1", "FP1", timedelta(minutes=90)),
            "Practice 2": ("fp2", "FP2", timedelta(minutes=90)),
            "Practice 3": ("fp3", "FP3", timedelta(minutes=90)),
            "Sprint Qualifying": (
                "sprint_qualifying",
                "Sprint qualifying",
                timedelta(minutes=90),
            ),
            "Sprint Shootout": (
                "sprint_qualifying",
                "Sprint qualifying",
                timedelta(minutes=90),
            ),
            "Sprint": ("sprint", "Sprint", timedelta(minutes=75)),
            "Qualifying": ("qualifying", "Qualifica", timedelta(minutes=90)),
            "Race": ("race", "Gara", timedelta(hours=3)),
        }
        try:
            event = fastf1.get_event(year, round_number)
        except Exception as exc:
            raise TelemetryUnavailable(
                "Programma sessioni non disponibile"
            ) from exc

        sessions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index in range(1, 6):
            try:
                session_name = str(event.get(f"Session{index}", ""))
                session_date = event.get(f"Session{index}Date")
            except AttributeError:
                session_name = str(event[f"Session{index}"])
                session_date = event[f"Session{index}Date"]
            if not session_name or session_name not in session_map:
                continue
            value, label, duration = session_map[session_name]
            if value in seen:
                continue
            try:
                if hasattr(session_date, "to_pydatetime"):
                    session_start = session_date.to_pydatetime()
                else:
                    session_start = session_date
                if session_start is None or session_start != session_start:
                    continue
            except Exception:
                continue
            now = (
                datetime.now(session_start.tzinfo)
                if session_start.tzinfo is not None
                else datetime.now()
            )
            if session_start + duration > now:
                continue
            seen.add(value)
            sessions.append(
                {
                    "value": value,
                    "label": label,
                    "name": session_name,
                    "date": session_start.isoformat(),
                }
            )
        return sessions

    async def circuit_layout(
        self,
        year: int,
        round_number: int,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._circuit_layout, year, round_number
        )

    def _circuit_layout(
        self,
        year: int,
        round_number: int,
    ) -> dict[str, Any]:
        fastf1 = self._library()
        try:
            session = fastf1.get_session(year, round_number, "R")
            session.load(
                laps=True,
                telemetry=True,
                weather=False,
                messages=False,
            )
        except Exception as exc:
            raise TelemetryUnavailable(
                "Layout FastF1 non disponibile per questa edizione"
            ) from exc

        try:
            circuit_info = session.get_circuit_info()
            corners = (
                circuit_info.corners.to_dict("records")
                if circuit_info is not None
                else []
            )
        except Exception:
            corners = []
        circuit_map = empty_circuit_map(corners, f"FastF1 {year} Race")

        try:
            driver_codes = session.laps["Driver"].dropna().unique()
        except Exception as exc:
            raise TelemetryUnavailable(
                "Layout FastF1 non disponibile per questa edizione"
            ) from exc

        for driver_code in driver_codes:
            try:
                laps = session.laps.pick_drivers(driver_code)
                quick = laps.pick_accurate().pick_wo_box().pick_quicklaps()
                if quick.empty:
                    continue
                add_trace_to_circuit_map(
                    circuit_map,
                    quick.pick_fastest().get_telemetry(),
                )
            except Exception:
                continue
            if circuit_map["trace"]:
                break

        if not circuit_map["trace"]:
            raise TelemetryUnavailable(
                "Layout FastF1 non disponibile per questa edizione"
            )

        return {
            "event": {
                "year": year,
                "round": round_number,
                "name": str(session.event["EventName"]),
                "location": str(session.event["Location"]),
                "date": session.date.isoformat(),
            },
            "circuit_map": circuit_map,
        }

    def _post_race(
        self,
        year: int,
        round_number: int,
        telemetry_session: str = "race",
        lap_mode: str = "best",
        lap_number: int | None = None,
    ) -> dict[str, Any]:
        fastf1 = self._library()
        session_codes = {
            "fp1": "FP1",
            "fp2": "FP2",
            "fp3": "FP3",
            "sprint_qualifying": "SQ",
            "sprint": "S",
            "qualifying": "Q",
            "race": "R",
        }
        session_labels = {
            "fp1": "Practice 1",
            "fp2": "Practice 2",
            "fp3": "Practice 3",
            "sprint_qualifying": "Sprint Qualifying",
            "sprint": "Sprint",
            "qualifying": "Qualifying",
            "race": "Race",
        }
        session_code = session_codes.get(telemetry_session, "R")
        try:
            session = fastf1.get_session(year, round_number, session_code)
            session.load(
                laps=True,
                telemetry=True,
                weather=True,
                messages=False,
            )
        except Exception as exc:
            raise TelemetryUnavailable(
                "Telemetria della sessione non disponibile"
            ) from exc
        try:
            session_laps = session.laps
        except Exception as exc:
            raise TelemetryUnavailable(
                "Telemetria della sessione non disponibile"
            ) from exc
        if session_laps.empty:
            raise TelemetryUnavailable(
                "Telemetria della sessione non disponibile"
            )

        try:
            circuit_info = session.get_circuit_info()
        except Exception:
            circuit_info = None
        corners = (
            circuit_info.corners.to_dict("records")
            if circuit_info is not None
            else []
        )
        circuit_map = empty_circuit_map(
            corners,
            (
                f"FastF1 {year} "
                f"{session_labels.get(telemetry_session, session_code)}"
            ),
        )
        try:
            event_name = str(session.event["EventName"])
            event_location = str(session.event["Location"])
        except Exception:
            event_name = f"Round {round_number}"
            event_location = ""
        try:
            event_date = session.date.isoformat()
        except Exception:
            event_date = f"{year}-01-01T00:00:00"
        drivers: list[dict[str, Any]] = []
        session_lap_numbers: set[int] = set()
        for driver_code in session_laps["Driver"].dropna().unique():
            driver_laps = session_laps.pick_drivers(driver_code)
            accurate = driver_laps.pick_accurate().pick_wo_box()
            quick = accurate.pick_quicklaps()
            timed_laps = [
                row
                for _, row in accurate.iterrows()
                if lap_time_seconds(row) is not None
                and lap_number_value(row) is not None
            ]
            if not timed_laps:
                continue

            lap_times = [
                lap_time_seconds(row)
                for _, row in (quick if not quick.empty else accurate).iterrows()
            ]
            lap_times = [
                seconds
                for seconds in lap_times
                if seconds is not None
            ]
            if not lap_times:
                lap_times = [
                    seconds
                    for seconds in (lap_time_seconds(row) for row in timed_laps)
                    if seconds is not None
                ]
            available_laps = lap_options(timed_laps)
            session_lap_numbers.update(item["lap_number"] for item in available_laps)
            representative = None
            selected_mode = "best"
            if lap_mode == "number" and lap_number is not None:
                try:
                    requested = accurate[accurate["LapNumber"] == float(lap_number)]
                    requested = requested[requested["LapTime"].notna()]
                    if not requested.empty:
                        representative = requested.iloc[0]
                        selected_mode = "number"
                except Exception:
                    representative = None
            if representative is None:
                representative = (
                    quick.pick_fastest()
                    if not quick.empty
                    else accurate.pick_fastest()
                )
            try:
                telemetry = (
                    representative.get_telemetry()
                    if representative is not None
                    else None
                )
            except Exception:
                telemetry = None

            corner_metrics = {"slow": [], "medium": [], "fast": []}
            if telemetry is not None and not telemetry.empty and corners:
                distance_max = float(telemetry["Distance"].max())
                for corner in corners:
                    distance = _number(corner.get("Distance"))
                    if distance is None or distance > distance_max:
                        continue
                    window = telemetry[
                        (telemetry["Distance"] >= distance - 80)
                        & (telemetry["Distance"] <= distance + 80)
                    ]
                    if window.empty:
                        continue
                    minimum = float(window["Speed"].min())
                    corner_metrics[corner_class(minimum)].append(
                        {
                            "number": int(corner.get("Number", 0)),
                            "letter": str(corner.get("Letter", "")),
                            "min_speed": round(minimum, 1),
                            "avg_speed": round(float(window["Speed"].mean()), 1),
                        }
                    )

            stints: list[dict[str, Any]] = []
            for stint_number, stint_laps in accurate.groupby("Stint"):
                timed = [
                    (
                        float(row["LapNumber"]),
                        row["LapTime"].total_seconds(),
                    )
                    for _, row in stint_laps.iterrows()
                    if row.get("LapTime") is not None
                    and row["LapTime"] == row["LapTime"]
                ]
                if len(timed) < 3:
                    continue
                stints.append(
                    {
                        "stint": int(stint_number),
                        "compound": str(stint_laps.iloc[0]["Compound"]),
                        "laps": len(timed),
                        "median_lap": round(
                            statistics.median(item[1] for item in timed), 3
                        ),
                        "pace_trend_seconds_per_lap": (
                            round(slope, 4)
                            if (slope := linear_slope(timed)) is not None
                            else None
                        ),
                    }
                )

            try:
                result = session.get_driver(driver_code)
            except Exception:
                result = {}
            team = str(
                result.get(
                    "TeamName",
                    (
                        representative.get("Team", "")
                        if representative is not None
                        else ""
                    ),
                )
            )
            metrics = {
                kind: {
                    "corners": len(values),
                    "average_min_speed": round(
                        statistics.mean(item["min_speed"] for item in values), 1
                    )
                    if values
                    else None,
                    "average_speed": round(
                        statistics.mean(item["avg_speed"] for item in values), 1
                    )
                    if values
                    else None,
                }
                for kind, values in corner_metrics.items()
            }
            trace: list[list[float]] = []
            if telemetry is not None and not telemetry.empty:
                add_trace_to_circuit_map(circuit_map, telemetry)
                trace = downsample_trace(
                    [
                        (
                            float(row["Distance"]),
                            float(row["Speed"]),
                            float(row["Throttle"]),
                            100.0 if bool(row["Brake"]) else 0.0,
                        )
                        for _, row in telemetry[
                            ["Distance", "Speed", "Throttle", "Brake"]
                        ]
                        .dropna()
                        .iterrows()
                    ]
                )

            drivers.append(
                {
                    "driver": str(driver_code),
                    "full_name": str(result.get("FullName", driver_code)),
                    "team": team,
                    "position": int(result["Position"])
                    if _number(result.get("Position")) is not None
                    else None,
                    "race_pace": round(statistics.median(lap_times), 3),
                    "best_lap": round(min(lap_times), 3),
                    "telemetry_lap": round(lap_time_seconds(representative), 3)
                    if representative is not None
                    and lap_time_seconds(representative) is not None
                    else None,
                    "telemetry_lap_number": lap_number_value(representative)
                    if representative is not None
                    else None,
                    "telemetry_lap_mode": selected_mode,
                    "requested_lap_number": lap_number
                    if lap_mode == "number"
                    else None,
                    "available_laps": available_laps,
                    "top_speed": round(
                        float(telemetry["Speed"].max()), 1
                    )
                    if telemetry is not None and not telemetry.empty
                    else None,
                    "full_throttle_pct": round(
                        float((telemetry["Throttle"] >= 98).mean() * 100), 1
                    )
                    if telemetry is not None and not telemetry.empty
                    else None,
                    "braking_pct": round(
                        float((telemetry["Brake"] > 0).mean() * 100), 1
                    )
                    if telemetry is not None and not telemetry.empty
                    else None,
                    "corners": metrics,
                    "stints": stints,
                    "telemetry_trace": trace,
                }
            )

        drivers.sort(
            key=lambda item: (
                item["position"] is None,
                item["position"] or 99,
            )
        )
        weather = session.weather_data
        return {
            "event": {
                "year": year,
                "round": round_number,
                "name": event_name,
                "location": event_location,
                "date": event_date,
            },
            "telemetry_session": telemetry_session,
            "lap_mode": lap_mode,
            "requested_lap_number": lap_number if lap_mode == "number" else None,
            "available_laps": sorted(session_lap_numbers),
            "circuit_map": circuit_map,
            "methodology": {
                "representative_lap": (
                    (
                        f"Giro {lap_number} quando disponibile, fallback sul "
                        f"giro accurato più veloce per pilota in "
                    )
                    if lap_mode == "number" and lap_number is not None
                    else "Giro accurato più veloce per pilota in "
                )
                + (
                    f"{session_labels.get(telemetry_session, session_code)}"
                ),
                "race_pace": "Mediana dei giri rapidi accurati senza pit",
                "corner_classes": {
                    "slow": "velocità minima < 140 km/h",
                    "medium": "140–209 km/h",
                    "fast": ">= 210 km/h",
                },
                "stint_trend": (
                    "Pendenza grezza del passo: include degrado, carburante, "
                    "evoluzione pista, traffico e meteo"
                ),
            },
            "weather": {
                "air_temperature": round(float(weather["AirTemp"].mean()), 1)
                if weather is not None and not weather.empty
                else None,
                "track_temperature": round(
                    float(weather["TrackTemp"].mean()), 1
                )
                if weather is not None and not weather.empty
                else None,
                "rainfall": bool(weather["Rainfall"].any())
                if weather is not None and not weather.empty
                else None,
            },
            "drivers": drivers,
        }

    async def practice_metrics(
        self, year: int, round_number: int
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._practice_metrics, year, round_number
        )

    def _practice_metrics(
        self, year: int, round_number: int
    ) -> dict[str, Any]:
        fastf1 = self._library()
        sessions = []
        for name in ("FP1", "FP2", "FP3"):
            try:
                session = fastf1.get_session(year, round_number, name)
                session.load(
                    laps=True,
                    telemetry=False,
                    weather=True,
                    messages=False,
                )
                laps = session.laps
                if laps.empty:
                    continue
                sessions.append((session.name, laps))
            except Exception:
                continue
        if not sessions:
            raise TelemetryUnavailable(
                "Free practice concluse non ancora disponibili"
            )

        per_driver: dict[str, dict[str, Any]] = {}
        for session_name, session_laps in sessions:
            for driver_code in session_laps["Driver"].dropna().unique():
                laps = session_laps.pick_drivers(driver_code).pick_accurate()
                quick = laps.pick_quicklaps().pick_wo_box()
                if quick.empty:
                    continue
                lap_times = [
                    value.total_seconds()
                    for value in quick["LapTime"].dropna().tolist()
                ]
                if not lap_times:
                    continue
                driver = per_driver.setdefault(
                    str(driver_code),
                    {
                        "driver": str(driver_code),
                        "team": str(quick.iloc[0]["Team"]),
                        "best_laps": [],
                        "long_runs": [],
                        "laps": 0,
                        "sessions": set(),
                    },
                )
                driver["best_laps"].append(min(lap_times))
                driver["laps"] += len(lap_times)
                driver["sessions"].add(session_name)
                long_run = [
                    item
                    for item in lap_times
                    if item <= min(lap_times) * 1.12
                ]
                if len(long_run) >= 4:
                    driver["long_runs"].append(statistics.median(long_run))

        if not per_driver:
            raise TelemetryUnavailable(
                "Free practice senza giri comparabili"
            )
        best_overall = min(
            min(item["best_laps"]) for item in per_driver.values()
        )
        long_values = [
            min(item["long_runs"])
            for item in per_driver.values()
            if item["long_runs"]
        ]
        best_long = min(long_values) if long_values else None
        return {
            "sessions": [name for name, _ in sessions],
            "drivers": [
                {
                    "driver": item["driver"],
                    "team": item["team"],
                    "best_lap": round(min(item["best_laps"]), 3),
                    "qualifying_gap": round(
                        min(item["best_laps"]) - best_overall, 3
                    ),
                    "long_run_gap": round(
                        min(item["long_runs"]) - best_long, 3
                    )
                    if item["long_runs"] and best_long is not None
                    else None,
                    "laps": item["laps"],
                    "sessions": sorted(item["sessions"]),
                }
                for item in per_driver.values()
            ],
        }
