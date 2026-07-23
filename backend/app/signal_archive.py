from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings


TRACK_MAP_MIN_REFERENCE_POINTS = 120
TRACK_MAP_MIN_GPS_POINTS = 300


def _valid_track_trace(trace: Any) -> bool:
    if not isinstance(trace, list) or len(trace) < TRACK_MAP_MIN_REFERENCE_POINTS:
        return False
    points = [
        point
        for point in trace
        if (
            isinstance(point, list)
            and len(point) >= 2
            and isinstance(point[0], (int, float))
            and isinstance(point[1], (int, float))
        )
    ]
    if len(points) < TRACK_MAP_MIN_REFERENCE_POINTS:
        return False
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    return (max_x - min_x) > 1 and (max_y - min_y) > 1


def _total_coverage(track_map: dict[str, Any]) -> int:
    coverage = track_map.get("coverage")
    if not isinstance(coverage, dict):
        return 0
    values = [
        int(value)
        for value in coverage.values()
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    ]
    return sum(values)


def _track_map_score(track_map: Any) -> tuple[int, int]:
    if not isinstance(track_map, dict):
        return (0, 0)
    return (_total_coverage(track_map), len(track_map.get("trace") or []))


def _valid_track_map(track_map: Any) -> bool:
    if not isinstance(track_map, dict) or not _valid_track_trace(track_map.get("trace")):
        return False
    source = str(track_map.get("source") or "")
    if source == "F1 SignalR Position.z":
        return (
            track_map.get("aggregation") in {"all_cars", "best_car"}
            and len(track_map.get("trace") or []) >= TRACK_MAP_MIN_GPS_POINTS
            and _total_coverage(track_map) >= TRACK_MAP_MIN_GPS_POINTS
        )
    return True


def _legacy_cached_track_map(track_map: Any) -> dict[str, Any] | None:
    if not isinstance(track_map, dict):
        return None
    if track_map.get("source") != "F1 SignalR Position.z":
        return None
    if track_map.get("aggregation") is not None:
        return None
    if not _valid_track_trace(track_map.get("trace")):
        return None
    if _total_coverage(track_map) < TRACK_MAP_MIN_GPS_POINTS:
        return None
    normalized = dict(track_map)
    normalized["aggregation"] = (
        "all_cars" if normalized.get("driver_number") == 0 else "best_car"
    )
    normalized.setdefault("coordinate_system", "f1_position")
    return normalized


def _readable_track_map(track_map: Any) -> dict[str, Any] | None:
    if _valid_track_map(track_map):
        return track_map
    return _legacy_cached_track_map(track_map)


def _safe_part(value: Any, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("_") or fallback


class SignalArchive:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session_id: str | None = None
        self._last_snapshot_at = 0.0

    def enabled(self) -> bool:
        return settings.f1_signalr_archive_enabled

    def record_topic(self, topic: str, payload: Any, session_info: dict[str, Any]) -> None:
        if not self.enabled():
            return
        self._append(
            "events.jsonl",
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "topic": topic,
                "payload": payload,
            },
            session_info,
        )

    def record_snapshot(self, snapshot: dict[str, Any]) -> None:
        if not self.enabled():
            return
        now = time.monotonic()
        if (
            now - self._last_snapshot_at
            < settings.f1_signalr_snapshot_archive_interval_seconds
        ):
            return
        self._last_snapshot_at = now
        self._append(
            "snapshots.jsonl",
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "snapshot": snapshot,
            },
            snapshot.get("session", {}),
        )

    def get_team_radio_transcription(
        self,
        session_info: dict[str, Any],
        radio: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not settings.team_radio_transcription_cache_enabled:
            return None
        key = self._team_radio_cache_key(radio)
        if not key:
            return None
        cache = self._read_json("team_radio_transcriptions.json", session_info)
        item = cache.get(key)
        return item if isinstance(item, dict) else None

    def save_team_radio_transcription(
        self,
        session_info: dict[str, Any],
        radio: dict[str, Any],
        transcript: str,
        translation_it: str,
    ) -> None:
        if not settings.team_radio_transcription_cache_enabled:
            return
        key = self._team_radio_cache_key(radio)
        if not key:
            return
        with self._lock:
            cache = self._read_json_unlocked(
                "team_radio_transcriptions.json",
                session_info,
            )
            cache[key] = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "path": radio.get("path"),
                "url": radio.get("url"),
                "utc": radio.get("utc"),
                "driver_number": radio.get("driver_number"),
                "transcript": transcript,
                "translation_it": translation_it,
            }
            self._write_json_unlocked(
                "team_radio_transcriptions.json",
                cache,
                session_info,
            )

    def get_track_map(self, session_info: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled():
            return None
        cache = self._read_json("track_map.json", session_info)
        track_map = cache.get("track_map")
        readable = _readable_track_map(track_map)
        if readable:
            return readable
        return self.get_event_track_map(session_info)

    def get_event_track_map(
        self,
        session_info: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.enabled():
            return None
        meeting = self._meeting_slug(session_info)
        if not meeting:
            return None
        candidates: list[tuple[int, dict[str, Any]]] = []
        for path in Path(settings.f1_signalr_archive_dir).glob(
            f"*_{meeting}_*/track_map.json"
        ):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            track_map = _readable_track_map(data.get("track_map"))
            if not track_map:
                continue
            candidates.append((len(track_map.get("trace") or []), track_map))
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    def save_track_map(
        self,
        session_info: dict[str, Any],
        track_map: dict[str, Any],
    ) -> None:
        if not self.enabled():
            return
        if not _valid_track_map(track_map):
            return
        with self._lock:
            current = self._read_json_unlocked("track_map.json", session_info)
            current_track = current.get("track_map")
            if (
                _valid_track_map(current_track)
                and _track_map_score(current_track) >= _track_map_score(track_map)
            ):
                return
            self._write_json_unlocked(
                "track_map.json",
                {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "track_map": track_map,
                },
                session_info,
            )

    def _append(
        self,
        filename: str,
        row: dict[str, Any],
        session_info: dict[str, Any],
    ) -> None:
        directory = self._session_dir(session_info)
        directory.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with (directory / filename).open("a", encoding="utf-8") as file:
                file.write(json.dumps(row, ensure_ascii=False, default=str))
                file.write("\n")

    def _read_json(
        self,
        filename: str,
        session_info: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            return self._read_json_unlocked(filename, session_info)

    def _read_json_unlocked(
        self,
        filename: str,
        session_info: dict[str, Any],
    ) -> dict[str, Any]:
        path = self._session_dir(session_info) / filename
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_json_unlocked(
        self,
        filename: str,
        data: dict[str, Any],
        session_info: dict[str, Any],
    ) -> None:
        directory = self._session_dir(session_info)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temp_path.replace(path)

    def _session_dir(self, session_info: dict[str, Any]) -> Path:
        base_dir = Path(settings.f1_signalr_archive_dir)
        session_id = self._session_id_from(session_info)
        if self._session_id is None and session_id != "unknown_live_timing":
            self._session_id = session_id
        elif session_id != "unknown_live_timing":
            self._session_id = session_id
        return base_dir / (self._session_id or session_id)

    def _meeting_slug(self, session_info: dict[str, Any]) -> str | None:
        if not isinstance(session_info, dict):
            return None
        meeting = session_info.get("Meeting", {})
        meeting_name = (
            meeting.get("Name")
            if isinstance(meeting, dict)
            else None
        )
        meeting_name = meeting_name or session_info.get("meeting_name")
        if not isinstance(meeting_name, str) or not meeting_name.strip():
            return None
        return _safe_part(meeting_name, "meeting")

    def _session_id_from(self, session_info: dict[str, Any]) -> str:
        if not isinstance(session_info, dict):
            session_info = {}
        meeting = session_info.get("Meeting", {})
        if isinstance(meeting, dict):
            meeting_name = meeting.get("Name")
            meeting_date = (
                meeting.get("StartDate")
                or meeting.get("OfficialDate")
                or meeting.get("Date")
            )
        else:
            meeting_name = None
            meeting_date = None
        meeting_name = meeting_name or session_info.get("meeting_name")
        session_name = session_info.get("Name") or session_info.get("session_name")
        start_date = session_info.get("StartDate") or session_info.get("date_start")
        date = (
            str(start_date)[:10]
            if start_date
            else str(meeting_date)[:10]
            if meeting_date
            else "unknown"
        )
        return "_".join(
            [
                _safe_part(date, "unknown"),
                _safe_part(meeting_name, "live"),
                _safe_part(session_name, "timing"),
            ]
        )

    def _team_radio_cache_key(self, radio: dict[str, Any]) -> str | None:
        path = radio.get("path")
        if isinstance(path, str) and path:
            return path
        url = radio.get("url")
        if isinstance(url, str) and url:
            return url
        return None
