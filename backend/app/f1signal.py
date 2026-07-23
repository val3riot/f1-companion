from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import threading
import time
import zlib
from copy import deepcopy
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque
from urllib.parse import unquote

import requests

from .config import settings
from .radio_transcription import is_meaningful_transcript
from .signal_archive import SignalArchive


F1_SIGNALR_TOPICS = [
    "Heartbeat",
    "DriverList",
    "ExtrapolatedClock",
    "RaceControlMessages",
    "SessionInfo",
    "SessionStatus",
    "TeamRadio",
    "TimingAppData",
    "TimingStats",
    "TrackStatus",
    "WeatherData",
    "Position.z",
    "CarData.z",
    "SessionData",
    "TimingData",
    "TopThree",
    "LapCount",
]

CAR_CHANNELS = {
    "0": "rpm",
    "2": "speed",
    "3": "n_gear",
    "4": "throttle",
    "5": "brake",
    "45": "drs",
}

F1_LIVE_TIMING_BASE_URL = "https://livetiming.formula1.com"
F1_LIVE_TIMING_CIRCUIT_INFO_SOURCE = "F1 Live Timing CircuitInfo"
BUILT_IN_CIRCUIT_LAYOUT_SOURCE = "FastF1 circuit layout"
TRACK_MAP_MIN_REFERENCE_POINTS = 120
TRACK_MAP_MIN_GPS_POINTS = 300
TrackTransform = tuple[float, float, float, float, float]

BUILT_IN_CIRCUIT_LAYOUTS: dict[str, dict[str, Any]] = {
    "silverstone": {
        "trace": [
            [-1759.0, 1205.7], [-1504.9, 1531.0], [-1214.0, 1915.0],
            [-930.0, 2307.0], [-485.0, 2933.0], [-185.0, 3382.0],
            [256.0, 3963.0], [676.0, 4336.0], [1154.2, 4497.8],
            [1834.0, 4497.0], [2488.3, 4438.6], [2926.0, 4496.0],
            [3493.0, 4783.2], [3920.0, 5176.0], [4294.0, 5530.0],
            [4640.3, 5813.2], [4949.5, 5900.3], [5141.3, 5841.9],
            [5312.0, 5660.0], [5372.9, 5457.8], [5392.0, 5285.0],
            [5448.2, 5011.1], [5594.8, 4813.8], [5694.6, 4749.8],
            [5902.5, 4779.3], [6060.4, 4952.1], [6146.0, 5103.0],
            [6236.1, 5346.4], [6304.7, 5623.8], [6326.0, 6054.0],
            [6193.6, 6557.7], [5895.1, 7003.0], [5519.0, 7331.0],
            [5083.0, 7674.0], [4606.5, 8079.2], [4145.0, 8474.0],
            [3796.0, 8776.0], [3378.5, 9143.2], [2909.8, 9554.2],
            [2339.7, 10051.3], [1882.3, 10461.5], [1541.6, 10734.3],
            [970.0, 10949.0], [636.6, 10917.2], [368.0, 10739.0],
            [195.0, 10285.0], [173.3, 9939.1], [76.0, 9672.0],
            [-118.1, 9497.4], [-359.7, 9442.2], [-521.5, 9505.6],
            [-720.0, 9760.0], [-774.0, 9993.0], [-753.0, 10295.0],
            [-652.0, 10630.4], [-417.2, 11116.1], [-160.0, 11511.0],
            [201.2, 11918.9], [777.6, 12367.8], [1151.4, 12540.3],
            [1787.1, 12723.2], [2465.0, 12817.6], [3114.0, 12884.0],
            [3852.1, 12965.7], [4898.0, 13095.0], [5425.2, 13096.5],
            [6054.4, 12837.5], [6427.0, 12423.0], [6657.4, 11852.5],
            [6811.0, 11213.6], [6893.0, 10726.0], [6970.0, 9917.0],
            [6991.1, 9203.2], [7034.7, 8720.3], [7235.3, 7910.2],
            [7419.0, 7438.0], [7535.0, 6805.0], [7392.0, 6129.0],
            [7318.7, 5469.2], [7477.6, 5048.7], [7694.0, 4675.0],
            [7790.9, 4263.8], [7636.5, 3793.4], [7439.0, 3547.0],
            [6924.0, 3239.0], [6502.5, 2835.5], [6188.0, 2368.0],
            [5950.4, 1904.0], [5797.0, 1587.0], [5432.9, 824.7],
            [5141.5, 221.5], [4848.0, -387.0], [4548.6, -1006.5],
            [4211.4, -1692.1], [3947.9, -2213.9], [3558.9, -2948.9],
            [3336.0, -3329.0], [2889.0, -3870.0], [2432.5, -4095.8],
            [1784.0, -3997.0], [1547.2, -3822.3], [1207.0, -3351.0],
            [963.4, -2911.4], [569.6, -2361.5], [327.7, -2037.9],
            [-1.7, -1637.8], [-320.0, -1279.0], [-592.2, -1007.7],
            [-810.0, -918.0], [-1033.2, -936.2], [-1196.0, -1037.0],
            [-1431.0, -1168.0], [-1655.0, -1139.0], [-1853.6, -1034.8],
            [-2068.0, -796.0], [-2203.0, -567.0], [-2299.1, -230.8],
            [-2284.5, 298.6], [-1994.0, 883.0], [-1756.8, 1208.2],
        ],
        "corners": [
            {"number": 1, "letter": None, "x": 1192.5, "y": 4503.8},
            {"number": 2, "letter": None, "x": 2770.3, "y": 4462.9},
            {"number": 3, "letter": None, "x": 4845.3, "y": 5895.1},
            {"number": 4, "letter": None, "x": 5802.7, "y": 4733.5},
            {"number": 5, "letter": None, "x": 6232.3, "y": 6459.0},
            {"number": 6, "letter": None, "x": 631.4, "y": 10910.2},
            {"number": 7, "letter": None, "x": -566.3, "y": 9540.4},
            {"number": 8, "letter": None, "x": 761.3, "y": 12361.6},
            {"number": 9, "letter": None, "x": 5893.9, "y": 12947.2},
            {"number": 10, "letter": None, "x": 7295.8, "y": 7780.5},
            {"number": 11, "letter": None, "x": 7535.0, "y": 6906.2},
            {"number": 12, "letter": None, "x": 7336.7, "y": 5474.7},
            {"number": 13, "letter": None, "x": 7776.5, "y": 4163.5},
            {"number": 14, "letter": None, "x": 6806.8, "y": 3146.7},
            {"number": 15, "letter": None, "x": 2399.0, "y": -4099.2},
            {"number": 16, "letter": None, "x": -620.4, "y": -993.8},
            {"number": 17, "letter": None, "x": -1438.1, "y": -1146.8},
            {"number": 18, "letter": None, "x": -2309.3, "y": -105.7},
        ],
        "coordinate_system": "f1_position",
    },
}


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if (
            isinstance(value, dict)
            and isinstance(target.get(key), dict)
        ):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _parse_payload(topic: str, payload: Any) -> Any:
    if isinstance(payload, str):
        text = payload
    else:
        return payload

    if topic.endswith(".z"):
        if text.startswith('"') and text.endswith('"'):
            text = text.strip('"')
        inflated = zlib.decompress(base64.b64decode(text), -zlib.MAX_WBITS)
        return json.loads(inflated.decode("utf-8-sig"))

    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    if text.startswith('"') and text.endswith('"'):
        return json.loads(text)
    return payload


def _number(value: Any) -> int | float | None:
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return None
    cleaned = value.replace("+", "").replace("s", "")
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _timing_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _number(value.get("Value")) or value.get("Value")
    return _number(value) or value


def _driver_number(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def f1_subscription_token() -> str | None:
    if settings.f1_signalr_auth_token:
        return settings.f1_signalr_auth_token
    if not settings.f1_signalr_login_session:
        return None
    try:
        session = json.loads(unquote(settings.f1_signalr_login_session))
    except json.JSONDecodeError:
        return None
    token = session.get("data", {}).get("subscriptionToken")
    return token if isinstance(token, str) and token else None


def f1_subscription_token_source() -> str:
    if settings.f1_signalr_auth_token:
        return "F1_SIGNALR_AUTH_TOKEN"
    if f1_subscription_token():
        return "F1_SIGNALR_LOGIN_SESSION.subscriptionToken"
    return "none"


def _slug(value: str) -> str:
    return value.strip().replace(" ", "_")


def _utc_timestamp(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if value.endswith("Z") or "+" in value[10:] or value.endswith("+00:00"):
        return value
    return f"{value}Z"


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


def _valid_track_map(track_map: Any) -> bool:
    if not isinstance(track_map, dict) or not _valid_track_trace(track_map.get("trace")):
        return False
    if track_map.get("source") != "F1 SignalR Position.z":
        return True
    if track_map.get("aggregation") not in {"all_cars", "best_car"}:
        return False
    coverage = track_map.get("coverage")
    coverage_values = (
        [
            int(value)
            for value in coverage.values()
            if isinstance(value, int)
            or (isinstance(value, str) and value.isdigit())
        ]
        if isinstance(coverage, dict)
        else []
    )
    return (
        len(track_map.get("trace") or []) >= TRACK_MAP_MIN_GPS_POINTS
        and sum(coverage_values) >= TRACK_MAP_MIN_GPS_POINTS
    )


def _is_official_circuit_info_map(track_map: Any) -> bool:
    return (
        isinstance(track_map, dict)
        and track_map.get("source") == F1_LIVE_TIMING_CIRCUIT_INFO_SOURCE
    )


def _is_reference_circuit_map(track_map: Any) -> bool:
    return (
        isinstance(track_map, dict)
        and track_map.get("source") != "F1 SignalR Position.z"
        and _valid_track_trace(track_map.get("trace"))
    )


class F1SignalRTranslator:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._archive = SignalArchive()
        self._topics: dict[str, Any] = {}
        self._track_points: dict[int, Deque[tuple[float, float]]] = {}
        self._latest_locations: dict[int, dict[str, Any]] = {}
        self._track_reference_map: dict[str, Any] | None = None
        self._gps_to_layout_transform: TrackTransform | None = None
        self._official_circuit_map_cache: dict[tuple[str, ...], dict[str, Any] | None] = {}
        self._best_laps: dict[int, dict[str, Any]] = {}
        self._best_sectors: dict[int, dict[int, dict[str, Any]]] = {}
        self._session_signature: tuple[str, ...] | None = None
        self._team_radio: list[dict[str, Any]] = []
        self._team_radio_keys: set[tuple[Any, Any, Any]] = set()
        self._last_message_at: float | None = None
        self._subscribed_at: float | None = None
        self._last_error: str | None = None
        self._connected = False
        self._started = False
        self._thread: threading.Thread | None = None
        self._connection: Any = None
        self._logger = logging.getLogger("f1signal")

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._thread = threading.Thread(
                target=self._run,
                name="f1-signalr",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            connection = self._connection
            self._started = False
            self._connected = False
        if connection is not None:
            try:
                connection.stop()
            except Exception:
                self._logger.exception("Unable to stop F1 SignalR connection")

    async def wait_for_first_message(self, timeout: float = 3) -> None:
        started_at = time.monotonic()
        while time.monotonic() - started_at < timeout:
            with self._lock:
                if self._last_message_at or self._last_error:
                    return
            await asyncio.sleep(0.1)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": "f1_signalr",
                "started": self._started,
                "connected": self._connected,
                "authenticated": bool(f1_subscription_token()),
                "token_source": f1_subscription_token_source(),
                "archive_enabled": self._archive.enabled(),
                "archive_dir": settings.f1_signalr_archive_dir,
                "team_radio_count": len(self._team_radio),
                "subscribed_at": self._subscribed_iso(),
                "last_message_at": self._last_message_iso(),
                "last_error": self._last_error,
                "topics": sorted(self._topics.keys()),
                "note": (
                    "Adapter sperimentale per uso personale. Senza token F1 "
                    "il feed puo' essere vuoto o parziale."
                ),
            }

    def team_radio_by_path(self, path: str) -> dict[str, Any] | None:
        with self._lock:
            for radio in self._team_radio:
                if radio.get("path") == path:
                    return deepcopy(radio)
        return None

    def set_team_radio_text(
        self,
        path: str,
        transcript: str,
        translation_it: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            for radio in self._team_radio:
                if radio.get("path") == path:
                    radio["transcript"] = transcript
                    radio["translation_it"] = translation_it
                    radio["transcription_status"] = "done"
                    radio.pop("transcription_error", None)
                    return deepcopy(radio)
        return None

    def hydrate_team_radio_transcription_cache(
        self,
        snapshot: dict[str, Any],
    ) -> None:
        session = snapshot.get("session", {})
        if not isinstance(session, dict):
            session = {}
        with self._lock:
            radios = snapshot.get("team_radio", [])
            if not isinstance(radios, list):
                return
            by_path = {
                radio.get("path"): radio
                for radio in self._team_radio
                if isinstance(radio, dict) and radio.get("path")
            }
            for radio in radios:
                if not isinstance(radio, dict) or radio.get("transcript"):
                    continue
                cached = self._archive.get_team_radio_transcription(
                    session,
                    radio,
                )
                if not cached:
                    continue
                transcript = cached.get("transcript")
                translation_it = cached.get("translation_it")
                if (
                    not isinstance(transcript, str)
                    or not is_meaningful_transcript(transcript)
                ):
                    continue
                radio["transcript"] = transcript
                radio["translation_it"] = (
                    translation_it if isinstance(translation_it, str) else ""
                )
                radio["transcription_status"] = "done"
                stored = by_path.get(radio.get("path"))
                if stored is not None:
                    stored.update(
                        {
                            "transcript": radio["transcript"],
                            "translation_it": radio["translation_it"],
                            "transcription_status": "done",
                        }
                    )
                    stored.pop("transcription_error", None)

    def cache_team_radio_transcription(
        self,
        session: dict[str, Any],
        radio: dict[str, Any],
        transcript: str,
        translation_it: str,
    ) -> None:
        self._archive.save_team_radio_transcription(
            session,
            radio,
            transcript,
            translation_it,
        )

    def set_team_radio_transcription_status(
        self,
        path: str,
        status: str,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            for radio in self._team_radio:
                if radio.get("path") == path:
                    if status == "transcribing":
                        radio["transcription_attempts"] = (
                            int(radio.get("transcription_attempts") or 0) + 1
                        )
                    radio["transcription_status"] = status
                    if error:
                        radio["transcription_error"] = error
                    else:
                        radio.pop("transcription_error", None)
                    return deepcopy(radio)
        return None

    def snapshot(self, archive: bool = False) -> dict[str, Any]:
        with self._lock:
            topics = deepcopy(self._topics)
            cursor = self._last_message_iso()
            status = self.status()

        session_info = topics.get("SessionInfo", {})
        timing_data = topics.get("TimingData", {})
        drivers = self._drivers(topics.get("DriverList", {}))
        session_status = topics.get("SessionStatus")
        track_map = self._track_map(session_info)
        gps_transform = self._gps_to_layout_transform_for(track_map)
        snapshot = {
            "provider": "f1_signalr",
            "cursor": cursor or datetime.now(timezone.utc).isoformat(),
            "is_live_window": self._is_live_session(session_status),
            "status": status,
            "session": self._session(session_info, session_status),
            "drivers": drivers,
            "results": [],
            "positions": self._positions(timing_data),
            "intervals": self._intervals(timing_data),
            "locations": self._locations(
                topics.get("Position.z", {}),
                gps_transform,
            ),
            "track_map": track_map,
            "telemetry": self._telemetry(topics.get("CarData.z", {})),
            "weather": self._weather(topics.get("WeatherData")),
            "best_lap": self._best_lap(timing_data),
            "best_laps": self._driver_best_laps(timing_data),
            "track_status": topics.get("TrackStatus"),
            "race_control": topics.get("RaceControlMessages"),
            "team_radio": deepcopy(self._team_radio),
            "lap_count": topics.get("LapCount"),
        }
        if archive:
            self._archive.record_snapshot(snapshot)
        return snapshot

    def _is_live_session(self, session_status: dict[str, Any] | None) -> bool:
        if not self._connected or not isinstance(session_status, dict):
            return self._connected
        values = {
            str(value).lower()
            for value in session_status.values()
            if isinstance(value, str)
        }
        finished_values = {"ends", "finished", "finalised", "finalized"}
        return not bool(values & finished_values)

    def apply_message(self, message: Any) -> None:
        if hasattr(message, "result"):
            for topic, payload in (message.result or {}).items():
                self._apply_topic(topic, payload)
            return

        if isinstance(message, list) and len(message) >= 2:
            topic = message[0]
            payload = message[1]
            if isinstance(topic, str):
                self._apply_topic(topic, payload)

    def _run(self) -> None:
        try:
            from signalrcore.hub_connection_builder import HubConnectionBuilder
        except ImportError as exc:
            self._set_error("Dipendenza signalrcore non installata")
            self._logger.exception("signalrcore is not installed")
            return

        try:
            headers: dict[str, str] = {}
            response = requests.options(
                settings.f1_signalr_negotiate_url,
                timeout=10,
                headers=headers,
            )
            if "AWSALBCORS" in response.cookies:
                headers["Cookie"] = (
                    f"AWSALBCORS={response.cookies['AWSALBCORS']}"
                )

            options = {
                "verify_ssl": True,
                "access_token_factory": (
                    f1_subscription_token
                    if f1_subscription_token()
                    else None
                ),
                "headers": headers,
            }
            connection = (
                HubConnectionBuilder()
                .with_url(settings.f1_signalr_connection_url, options=options)
                .configure_logging(logging.INFO)
                .build()
            )
            self._connection = connection
            connection.on_open(self._on_open)
            connection.on_close(self._on_close)
            connection.on("feed", self.apply_message)
            connection.start()

            started_at = time.monotonic()
            while not self._connected and time.monotonic() - started_at < 15:
                time.sleep(0.1)

            if not self._connected:
                self._set_error("Connessione F1 SignalR non stabilita")
                return

            connection.send(
                "Subscribe",
                [F1_SIGNALR_TOPICS],
                on_invocation=self.apply_message,
            )
            with self._lock:
                self._subscribed_at = time.time()
            self._supervise()
        except Exception as exc:
            self._set_error(str(exc))
            self._logger.exception("F1 SignalR connection failed")
        finally:
            with self._lock:
                self._connected = False
                self._started = False

    def _supervise(self) -> None:
        while True:
            time.sleep(1)
            with self._lock:
                if not self._started:
                    return
                last_message_at = self._last_message_at
            if (
                last_message_at
                and time.time() - last_message_at
                > settings.f1_signalr_timeout_seconds
            ):
                self._set_error("Timeout: nessun dato ricevuto dal feed F1")
                self.stop()
                return

    def _on_open(self) -> None:
        with self._lock:
            self._connected = True
            self._last_error = None

    def _on_close(self) -> None:
        with self._lock:
            self._connected = False

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message

    def _apply_topic(self, topic: str, payload: Any) -> None:
        try:
            parsed = _parse_payload(topic, payload)
        except Exception as exc:
            self._set_error(f"Payload {topic} non traducibile: {exc}")
            return

        with self._lock:
            existing = self._topics.get(topic)
            if isinstance(existing, dict) and isinstance(parsed, dict):
                _deep_merge(existing, parsed)
            else:
                self._topics[topic] = parsed
            if topic == "SessionInfo":
                self._reset_session_accumulators_if_needed()
            if topic == "Position.z":
                self._accumulate_track_points(parsed)
            if topic == "TimingData":
                timing_data = self._topics.get("TimingData", {})
                if isinstance(timing_data, dict):
                    self._accumulate_best_laps(timing_data)
            if topic == "TeamRadio":
                self._accumulate_team_radio(parsed)
                self._record_team_radio_topic(parsed)
            self._last_message_at = time.time()
            self._last_error = None

    def _record_team_radio_topic(self, payload: Any) -> None:
        record_topic = getattr(self._archive, "record_topic", None)
        if record_topic is None:
            return
        session_info = self._topics.get("SessionInfo", {})
        record_topic(
            "TeamRadio",
            payload,
            session_info if isinstance(session_info, dict) else {},
        )

    def _reset_session_accumulators_if_needed(self) -> None:
        session_info = self._topics.get("SessionInfo", {})
        signature = self._session_signature_for(session_info)
        if signature is None:
            return
        if self._session_signature is None:
            self._session_signature = signature
            return
        if signature == self._session_signature:
            return

        self._session_signature = signature
        self._track_points.clear()
        self._latest_locations.clear()
        self._track_reference_map = None
        self._gps_to_layout_transform = None
        self._best_laps.clear()
        self._best_sectors.clear()
        self._topics = {"SessionInfo": session_info}

    def _session_signature_for(
        self,
        session_info: Any,
    ) -> tuple[str, ...] | None:
        if not isinstance(session_info, dict) or not session_info:
            return None
        meeting = session_info.get("Meeting", {})
        meeting = meeting if isinstance(meeting, dict) else {}
        circuit = meeting.get("Circuit", {})
        circuit = circuit if isinstance(circuit, dict) else {}
        country = meeting.get("Country", {})
        country = country if isinstance(country, dict) else {}
        values = (
            session_info.get("Name"),
            session_info.get("Type"),
            session_info.get("StartDate"),
            meeting.get("Name"),
            meeting.get("Location"),
            country.get("Name"),
            circuit.get("ShortName"),
        )
        normalized = tuple(str(value or "") for value in values)
        return normalized if any(normalized) else None

    def _accumulate_team_radio(self, data: Any) -> None:
        for item in self._team_radio_items(data):
            normalized = self._normalize_team_radio(item)
            if normalized is None:
                continue
            key = (
                normalized.get("utc"),
                normalized.get("driver_number"),
                normalized.get("path"),
            )
            if key in self._team_radio_keys:
                continue
            self._team_radio_keys.add(key)
            self._team_radio.append(normalized)
        self._team_radio = self._team_radio[-200:]

    def _team_radio_items(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("Captures", "Messages", "TeamRadio", "Radio"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                return [item for item in value.values() if isinstance(item, dict)]
        if data and all(isinstance(value, dict) for value in data.values()):
            return [item for item in data.values() if isinstance(item, dict)]
        return [data]

    def _normalize_team_radio(self, item: dict[str, Any]) -> dict[str, Any] | None:
        driver_number = _driver_number(
            item.get("RacingNumber")
            or item.get("DriverNumber")
            or item.get("RacingNo")
            or item.get("CarNumber")
            or item.get("driver_number")
        )
        path = (
            item.get("Path")
            or item.get("path")
            or item.get("Url")
            or item.get("URL")
            or item.get("Uri")
            or item.get("AudioPath")
            or item.get("AudioUrl")
        )
        if not path and driver_number is None:
            return None
        url = str(path) if path else None
        return {
            "utc": _utc_timestamp(
                item.get("Utc") or item.get("UTC") or item.get("Date")
            ),
            "driver_number": driver_number,
            "path": path,
            "url": self._team_radio_url(url),
            "message": item.get("Message") or item.get("Transcript"),
            "transcription_status": "pending",
        }

    def _team_radio_url(self, path: str | None) -> str | None:
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        session_info = self._topics.get("SessionInfo", {})
        if not isinstance(session_info, dict):
            return None
        static_path = self._session_static_path(session_info)
        if not static_path:
            return None
        return f"{F1_LIVE_TIMING_BASE_URL}{static_path}{path.lstrip('/')}"

    def _session_static_path(self, session_info: dict[str, Any]) -> str | None:
        meeting = session_info.get("Meeting", {})
        if not isinstance(meeting, dict):
            return None
        meeting_name = meeting.get("Name")
        session_name = session_info.get("Name")
        start_date = session_info.get("StartDate")
        if not (
            isinstance(meeting_name, str)
            and isinstance(session_name, str)
            and isinstance(start_date, str)
        ):
            return None

        session_date = start_date[:10]
        year = session_date[:4]
        event_date = self._meeting_date(meeting, session_date)
        return (
            f"/static/{year}/{event_date}_{_slug(meeting_name)}/"
            f"{session_date}_{_slug(session_name)}/"
        )

    def _meeting_date(self, meeting: dict[str, Any], fallback: str) -> str:
        for key in ("OfficialDate", "Date", "RaceDate", "EndDate"):
            value = meeting.get(key)
            if isinstance(value, str) and len(value) >= 10:
                return value[:10]
        try:
            session_day = datetime.fromisoformat(fallback[:10]).date()
        except ValueError:
            return fallback
        race_day = session_day + timedelta(days=(6 - session_day.weekday()) % 7)
        return race_day.isoformat()

    def _accumulate_track_points(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        for entry in self._position_entries(data):
            timestamp = entry.get("Timestamp") or entry.get("Utc")
            for number, car in self._position_cars(entry).items():
                driver_number = _driver_number(number)
                if driver_number is None or not isinstance(car, dict):
                    continue
                x = _number(car.get("X"))
                y = _number(car.get("Y"))
                z = _number(car.get("Z"))
                if x is None or y is None:
                    continue
                self._latest_locations[driver_number] = {
                    "driver_number": driver_number,
                    "date": timestamp,
                    "x": x,
                    "y": y,
                    "z": z,
                }
                points = self._track_points.setdefault(
                    driver_number,
                    deque(maxlen=2500),
                )
                if not points or points[-1] != (float(x), float(y)):
                    points.append((float(x), float(y)))

    def _last_message_iso(self) -> str | None:
        if self._last_message_at is None:
            return None
        return datetime.fromtimestamp(
            self._last_message_at,
            tz=timezone.utc,
        ).isoformat()

    def _subscribed_iso(self) -> str | None:
        if self._subscribed_at is None:
            return None
        return datetime.fromtimestamp(
            self._subscribed_at,
            tz=timezone.utc,
        ).isoformat()

    def _session(
        self,
        info: dict[str, Any],
        session_status: dict[str, Any] | None,
    ) -> dict[str, Any]:
        meeting = info.get("Meeting", {}) if isinstance(info, dict) else {}
        return {
            "session_key": -1,
            "session_name": info.get("Name", "Live Timing"),
            "session_type": info.get("Type", "Live"),
            "date_start": info.get("StartDate"),
            "date_end": None,
            "meeting_key": -1,
            "meeting_name": meeting.get("Name", ""),
            "location": meeting.get("Location", ""),
            "country_name": meeting.get("Country", {}).get("Name", ""),
            "circuit_short_name": meeting.get("Circuit", {}).get(
                "ShortName",
                "",
            ),
            "status": session_status,
        }

    def _drivers(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(data, dict):
            return []
        drivers = []
        for number, driver in data.items():
            driver_number = _driver_number(number)
            if driver_number is None or not isinstance(driver, dict):
                continue
            drivers.append(
                {
                    "driver_number": driver_number,
                    "full_name": (
                        driver.get("FullName")
                        or driver.get("BroadcastName")
                        or driver.get("Tla")
                        or str(driver_number)
                    ),
                    "name_acronym": driver.get("Tla") or driver.get("RacingNumber"),
                    "team_name": driver.get("TeamName", ""),
                    "team_colour": driver.get("TeamColour", ""),
                    "headshot_url": None,
                }
            )
        return sorted(drivers, key=lambda item: item["driver_number"])

    def _timing_lines(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        lines = data.get("Lines", data)
        return lines if isinstance(lines, dict) else {}

    def _positions(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for number, line in self._timing_lines(data).items():
            driver_number = _driver_number(number)
            if driver_number is None or not isinstance(line, dict):
                continue
            timing_laps = self._timing_laps(line)
            rows.append(
                {
                    "driver_number": driver_number,
                    "position": _driver_number(line.get("Position")),
                    "date": self._last_message_iso(),
                    "last_lap_time": timing_laps.get("last_lap_time"),
                    "last_lap_duration": timing_laps.get("last_lap_duration"),
                    "best_lap_time": timing_laps.get("best_lap_time"),
                    "best_lap_duration": timing_laps.get("best_lap_duration"),
                }
            )
        return sorted(
            rows,
            key=lambda item: item["position"] or item["driver_number"],
        )

    def _intervals(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for number, line in self._timing_lines(data).items():
            driver_number = _driver_number(number)
            if driver_number is None or not isinstance(line, dict):
                continue
            rows.append(
                {
                    "driver_number": driver_number,
                    "date": self._last_message_iso(),
                    "gap_to_leader": _timing_value(line.get("GapToLeader")),
                    "interval": _timing_value(line.get("IntervalToPositionAhead")),
                }
            )
        return rows

    def _locations(
        self,
        data: dict[str, Any],
        transform: TrackTransform | None = None,
    ) -> list[dict[str, Any]]:
        if not self._latest_locations:
            self._accumulate_track_points(data)
        if not self._latest_locations:
            return []
        rows = []
        for driver_number, location in sorted(self._latest_locations.items()):
            x = _number(location.get("x"))
            y = _number(location.get("y"))
            if x is None or y is None:
                continue
            mapped = (
                self._apply_track_transform(float(x), float(y), transform)
                if transform is not None
                else None
            )
            output_x, output_y = mapped if mapped is not None else (x, y)
            row = {
                "driver_number": driver_number,
                "date": location.get("date"),
                "x": output_x,
                "y": output_y,
                "z": location.get("z"),
            }
            if transform is not None:
                row["mapped_to_track"] = True
            rows.append(row)
        return rows

    def _position_entries(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        entries = data.get("Position", data.get("Entries", []))
        return entries if isinstance(entries, list) else []

    def _position_cars(self, entry: Any) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {}
        cars = entry.get("Cars") or entry.get("Entries") or {}
        return cars if isinstance(cars, dict) else {}

    def _gps_to_layout_transform_for(
        self,
        track_map: dict[str, Any] | None,
    ) -> TrackTransform | None:
        if not _is_reference_circuit_map(track_map):
            return None
        if track_map.get("coordinate_system") == "f1_position":
            return (1.0, 1.0, 0.0, 0.0, 0.0)
        if self._gps_to_layout_transform is not None:
            return self._gps_to_layout_transform
        if not self._track_points:
            return None

        gps_trace = self._all_cars_track_trace(max_points=240)
        layout_trace = track_map.get("trace") if isinstance(track_map, dict) else None
        if not _valid_track_trace(gps_trace) or not _valid_track_trace(layout_trace):
            return None

        transform = self._best_similarity_transform(
            [(point[0], point[1]) for point in gps_trace],
            [(point[0], point[1]) for point in layout_trace],
        )
        self._gps_to_layout_transform = transform
        return transform

    def _best_similarity_transform(
        self,
        source: list[tuple[float, float]],
        target: list[tuple[float, float]],
    ) -> TrackTransform | None:
        source_stats = self._point_cloud_stats(source)
        target_stats = self._point_cloud_stats(target)
        if source_stats is None or target_stats is None:
            return None
        source_cx, source_cy, source_angle, source_radius = source_stats
        target_cx, target_cy, target_angle, target_radius = target_stats
        if source_radius <= 0:
            return None

        scale = target_radius / source_radius
        candidates: list[TrackTransform] = []
        for reflected in (False, True):
            adjusted_source = (
                [(x, (2 * source_cy) - y) for x, y in source]
                if reflected
                else source
            )
            adjusted_stats = self._point_cloud_stats(adjusted_source)
            if adjusted_stats is None:
                continue
            adjusted_cx, adjusted_cy, adjusted_angle, adjusted_radius = adjusted_stats
            if adjusted_radius <= 0:
                continue
            adjusted_scale = target_radius / adjusted_radius
            for extra_rotation in (0.0, math.pi):
                angle = target_angle - adjusted_angle + extra_rotation
                cos_angle = math.cos(angle)
                sin_angle = math.sin(angle)
                tx = target_cx - adjusted_scale * (
                    cos_angle * adjusted_cx - sin_angle * adjusted_cy
                )
                ty = target_cy - adjusted_scale * (
                    sin_angle * adjusted_cx + cos_angle * adjusted_cy
                )
                if reflected:
                    candidates.append(
                        (
                            -adjusted_scale,
                            cos_angle,
                            sin_angle,
                            tx + adjusted_scale * sin_angle * 2 * source_cy,
                            ty - adjusted_scale * cos_angle * 2 * source_cy,
                        )
                    )
                else:
                    candidates.append((adjusted_scale, cos_angle, sin_angle, tx, ty))

        if not candidates:
            return None
        target_sample = target[:: max(1, len(target) // 80)]
        source_sample = source[:: max(1, len(source) // 80)]
        return min(
            candidates,
            key=lambda transform: self._mean_nearest_distance(
                [
                    point
                    for point in (
                        self._apply_track_transform(x, y, transform)
                        for x, y in source_sample
                    )
                    if point is not None
                ],
                target_sample,
            ),
        )

    def _point_cloud_stats(
        self,
        points: list[tuple[float, float]],
    ) -> tuple[float, float, float, float] | None:
        if len(points) < 2:
            return None
        cx = sum(point[0] for point in points) / len(points)
        cy = sum(point[1] for point in points) / len(points)
        centered = [(x - cx, y - cy) for x, y in points]
        xx = sum(x * x for x, _ in centered) / len(centered)
        yy = sum(y * y for _, y in centered) / len(centered)
        xy = sum(x * y for x, y in centered) / len(centered)
        angle = 0.5 * math.atan2(2 * xy, xx - yy)
        radius = math.sqrt(
            sum((x * x) + (y * y) for x, y in centered) / len(centered)
        )
        return cx, cy, angle, radius

    def _mean_nearest_distance(
        self,
        source: list[tuple[float, float]],
        target: list[tuple[float, float]],
    ) -> float:
        if not source or not target:
            return float("inf")
        total = 0.0
        for sx, sy in source:
            total += min(math.hypot(sx - tx, sy - ty) for tx, ty in target)
        return total / len(source)

    def _apply_track_transform(
        self,
        x: float,
        y: float,
        transform: TrackTransform | None,
    ) -> tuple[float, float] | None:
        if transform is None:
            return None
        scale, cos_angle, sin_angle, tx, ty = transform
        return (
            round(scale * (cos_angle * x - sin_angle * y) + tx, 1),
            round(scale * (sin_angle * x + cos_angle * y) + ty, 1),
        )

    def _track_map(self, session_info: dict[str, Any]) -> dict[str, Any] | None:
        if _is_reference_circuit_map(self._track_reference_map):
            return deepcopy(self._track_reference_map)
        official_map = self._official_circuit_map(session_info)
        if _valid_track_map(official_map):
            self._track_reference_map = deepcopy(official_map)
            return official_map
        built_in_map = self._built_in_circuit_map(session_info)
        if _valid_track_map(built_in_map):
            self._track_reference_map = deepcopy(built_in_map)
            return built_in_map
        gps_map = self._gps_track_map()
        if _valid_track_map(gps_map):
            self._save_track_map(session_info, gps_map)
            return gps_map
        cached_map = self._cached_track_map(session_info)
        if _valid_track_map(cached_map):
            return cached_map
        return None

    def _cached_track_map(self, session_info: dict[str, Any]) -> dict[str, Any] | None:
        get_track_map = getattr(self._archive, "get_track_map", None)
        if get_track_map is None:
            return None
        return get_track_map(session_info)

    def _save_track_map(
        self,
        session_info: dict[str, Any],
        track_map: dict[str, Any],
    ) -> None:
        save_track_map = getattr(self._archive, "save_track_map", None)
        if save_track_map is not None:
            save_track_map(session_info, track_map)

    def _gps_track_map(self) -> dict[str, Any] | None:
        """Build a live fallback from one car's chronological GPS history.

        Mixing every car and sorting by angle produces crossed or malformed
        layouts on non-convex circuits. The car with the richest trace gives a
        stable circuit outline while keeping live locations in the same
        coordinate system.
        """
        candidates = [
            (driver_number, list(points))
            for driver_number, points in self._track_points.items()
            if len(points) >= TRACK_MAP_MIN_GPS_POINTS
        ]
        if not candidates:
            return None
        driver_number, points = max(candidates, key=lambda item: len(item[1]))
        trace = self._downsample_xy(points, max_points=700)
        if not _valid_track_trace(trace):
            return None
        return {
            "source": "F1 SignalR Position.z",
            "driver_number": driver_number,
            "aggregation": "best_car",
            "trace": trace,
            "coverage": {str(driver_number): len(points)},
            "coordinate_system": "f1_position",
        }

    def _built_in_circuit_map(
        self,
        session_info: dict[str, Any],
    ) -> dict[str, Any] | None:
        meeting = session_info.get("Meeting", {})
        candidates: list[Any] = [session_info.get("Circuit"), session_info.get("Location")]
        if isinstance(meeting, dict):
            circuit = meeting.get("Circuit")
            if isinstance(circuit, dict):
                candidates.extend([circuit.get("ShortName"), circuit.get("Name")])
            candidates.extend([meeting.get("Location"), meeting.get("Name")])

        key = None
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            normalized = candidate.lower()
            if "silverstone" in normalized or "british" in normalized:
                key = "silverstone"
                break
        if key is None:
            return None

        layout = BUILT_IN_CIRCUIT_LAYOUTS.get(key)
        if not layout:
            return None
        trace = self._interpolated_layout_trace(layout.get("trace") or [])
        return {
            "source": BUILT_IN_CIRCUIT_LAYOUT_SOURCE,
            "driver_number": 0,
            "trace": trace,
            "coverage": {"layout": key, "points": len(trace)},
            "corners": deepcopy(layout.get("corners") or []),
            "coordinate_system": layout.get("coordinate_system"),
        }

    def _official_circuit_map(
        self,
        session_info: dict[str, Any],
    ) -> dict[str, Any] | None:
        signature = self._session_signature_for(session_info)
        if signature is None:
            return None
        if signature in self._official_circuit_map_cache:
            return self._official_circuit_map_cache[signature]
        static_path = self._session_static_path(session_info)
        if not static_path:
            self._official_circuit_map_cache[signature] = None
            return None
        try:
            response = requests.get(
                f"{F1_LIVE_TIMING_BASE_URL}{static_path}CircuitInfo.json",
                timeout=2,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            self._official_circuit_map_cache[signature] = None
            return None

        corners = self._official_circuit_corners(data)
        trace = self._interpolated_corner_trace(corners)
        if len(trace) < TRACK_MAP_MIN_REFERENCE_POINTS:
            self._official_circuit_map_cache[signature] = None
            return None
        track_map = {
            "source": F1_LIVE_TIMING_CIRCUIT_INFO_SOURCE,
            "driver_number": 0,
            "trace": trace,
            "coverage": {"corners": len(corners)},
            "corners": corners,
        }
        self._official_circuit_map_cache[signature] = track_map
        return track_map

    def _all_cars_track_trace(self, max_points: int) -> list[list[float]]:
        points: list[tuple[float, float]] = []
        seen: set[tuple[int, int]] = set()
        for driver_points in self._track_points.values():
            for x, y in driver_points:
                key = (round(x), round(y))
                if key in seen:
                    continue
                seen.add(key)
                points.append((float(x), float(y)))
        if len(points) < TRACK_MAP_MIN_GPS_POINTS:
            return []

        center_x = sum(point[0] for point in points) / len(points)
        center_y = sum(point[1] for point in points) / len(points)
        ordered = sorted(
            points,
            key=lambda point: math.atan2(point[1] - center_y, point[0] - center_x),
        )
        return self._downsample_xy(ordered, max_points=max_points)

    def _official_circuit_corners(self, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, dict):
            return []
        raw_corners = data.get("Corners")
        if isinstance(raw_corners, dict):
            corner_items = raw_corners.values()
        elif isinstance(raw_corners, list):
            corner_items = raw_corners
        else:
            return []

        corners: list[dict[str, Any]] = []
        for index, corner in enumerate(corner_items, start=1):
            if not isinstance(corner, dict):
                continue
            raw_x = corner.get("X") if "X" in corner else corner.get("x")
            raw_y = corner.get("Y") if "Y" in corner else corner.get("y")
            x = _number(raw_x)
            y = _number(raw_y)
            if x is None or y is None:
                continue
            corners.append(
                {
                    "number": _driver_number(corner.get("Number")) or index,
                    "letter": corner.get("Letter") or None,
                    "x": float(x),
                    "y": float(y),
                }
            )
        return sorted(corners, key=lambda item: item["number"])

    def _interpolated_corner_trace(
        self,
        corners: list[dict[str, Any]],
    ) -> list[list[float]]:
        if len(corners) < 3:
            return []
        points = [(corner["x"], corner["y"]) for corner in corners]
        segments = list(zip(points, [*points[1:], points[0]]))
        steps_per_segment = max(
            2,
            TRACK_MAP_MIN_REFERENCE_POINTS // len(segments) + 1,
        )
        trace: list[tuple[float, float]] = []
        for start, end in segments:
            for step in range(steps_per_segment):
                progress = step / steps_per_segment
                trace.append(
                    (
                        start[0] + (end[0] - start[0]) * progress,
                        start[1] + (end[1] - start[1]) * progress,
                    )
                )
        return self._downsample_xy(trace, max_points=700)

    def _interpolated_layout_trace(
        self,
        points: list[list[float]],
    ) -> list[list[float]]:
        anchors = [
            (float(point[0]), float(point[1]))
            for point in points
            if isinstance(point, list)
            and len(point) >= 2
            and isinstance(point[0], (int, float))
            and isinstance(point[1], (int, float))
        ]
        if len(anchors) < 3:
            return []
        segments = list(zip(anchors, [*anchors[1:], anchors[0]]))
        steps_per_segment = max(
            2,
            TRACK_MAP_MIN_REFERENCE_POINTS // len(segments) + 1,
        )
        trace: list[tuple[float, float]] = []
        for start, end in segments:
            for step in range(steps_per_segment):
                progress = step / steps_per_segment
                trace.append(
                    (
                        start[0] + (end[0] - start[0]) * progress,
                        start[1] + (end[1] - start[1]) * progress,
                    )
                )
        return self._downsample_xy(trace, max_points=700)

    def _downsample_xy(
        self,
        rows: list[tuple[float, float]],
        max_points: int,
    ) -> list[list[float]]:
        if len(rows) <= max_points:
            selected = rows
        else:
            indexes = {
                round(index * (len(rows) - 1) / (max_points - 1))
                for index in range(max_points)
            }
            selected = [rows[index] for index in sorted(indexes)]
        return [[round(x, 1), round(y, 1)] for x, y in selected]

    def _telemetry(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        entries = data.get("Entries", [])
        if not isinstance(entries, list) or not entries:
            return []
        latest = entries[-1]
        cars = latest.get("Cars", {}) if isinstance(latest, dict) else {}
        rows = []
        for number, car in cars.items():
            driver_number = _driver_number(number)
            channels = car.get("Channels", {}) if isinstance(car, dict) else {}
            if driver_number is None or not isinstance(channels, dict):
                continue
            row = {
                "driver_number": driver_number,
                "date": latest.get("Utc"),
            }
            for channel, field in CAR_CHANNELS.items():
                value = channels.get(channel)
                if value is not None:
                    row[field] = _number(value)
            rows.append(row)
        return rows

    def _weather(self, data: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        return {
            "air_temperature": _number(data.get("AirTemp")),
            "track_temperature": _number(data.get("TrackTemp")),
            "humidity": _number(data.get("Humidity")),
            "rainfall": _number(data.get("Rainfall")),
            "wind_speed": _number(data.get("WindSpeed")),
        }

    def _best_lap(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if self._best_laps:
            rows = self._normalize_overall_best_flags(
                deepcopy(list(self._best_laps.values()))
            )
            return min(rows, key=lambda item: item["lap_duration"])
        best: dict[str, Any] | None = None
        for number, line in self._timing_lines(data).items():
            driver_number = _driver_number(number)
            if driver_number is None or not isinstance(line, dict):
                continue
            candidate = self._lap_candidate(driver_number, line)
            if candidate is None:
                continue
            if best is None or candidate["lap_duration"] < best["lap_duration"]:
                best = candidate
        return best

    def _driver_best_laps(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        if self._best_laps:
            rows = sorted(
                deepcopy(list(self._best_laps.values())),
                key=lambda item: item["lap_duration"],
            )
            return self._normalize_overall_best_flags(rows)

        rows = []
        for number, line in self._timing_lines(data).items():
            driver_number = _driver_number(number)
            if driver_number is None or not isinstance(line, dict):
                continue
            candidate = self._lap_candidate(driver_number, line)
            if candidate is not None:
                rows.append(candidate)
        return self._normalize_overall_best_flags(
            sorted(rows, key=lambda item: item["lap_duration"])
        )

    def _normalize_overall_best_flags(
        self,
        laps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sector_leaders: dict[int, tuple[float, int]] = {}
        for lap_index, lap in enumerate(laps):
            for sector in lap.get("sectors", []):
                if sector.get("status") != "overall_best":
                    continue
                sector_time = self._sector_seconds(sector.get("time"))
                if sector_time is None:
                    continue
                number = int(sector["number"])
                current = sector_leaders.get(number)
                if current is None or sector_time < current[0]:
                    sector_leaders[number] = (sector_time, lap_index)

        normalized = deepcopy(laps)
        for lap_index, lap in enumerate(normalized):
            for sector in lap.get("sectors", []):
                number = int(sector["number"])
                if sector_leaders.get(number, (None, None))[1] == lap_index:
                    sector["status"] = "overall_best"
                elif sector.get("status") == "overall_best":
                    sector["status"] = "personal_best"
        return normalized

    def _accumulate_best_laps(self, data: dict[str, Any]) -> None:
        for number, line in self._timing_lines(data).items():
            driver_number = _driver_number(number)
            if driver_number is None or not isinstance(line, dict):
                continue
            self._accumulate_best_sectors(driver_number, line)
            candidate = self._lap_candidate(driver_number, line)
            if candidate is None:
                continue
            existing = self._best_laps.get(driver_number)
            if (
                existing is None
                or candidate["lap_duration"] < existing["lap_duration"]
            ):
                self._best_laps[driver_number] = candidate

    def _accumulate_best_sectors(
        self,
        driver_number: int,
        line: dict[str, Any],
    ) -> None:
        sectors = self._lap_sectors(line)
        if not sectors:
            return
        stored = self._best_sectors.setdefault(driver_number, {})
        for sector in sectors:
            if sector.get("status") == "overall_best":
                stored[int(sector["number"])] = {**sector, "segments": []}
                continue
            segments = [
                segment
                for segment in sector.get("segments", [])
                if segment.get("status") == "overall_best"
            ]
            if segments:
                stored[int(sector["number"])] = {
                    **sector,
                    "segments": segments,
                }

    def _lap_candidate(
        self,
        driver_number: int,
        line: dict[str, Any],
    ) -> dict[str, Any] | None:
        timing_laps = self._timing_laps(line)
        value = timing_laps.get("best_lap_time") or timing_laps.get("last_lap_time")
        if not isinstance(value, str):
            return None
        seconds = self._lap_seconds(value)
        if seconds is None:
            return None
        lap_number = (
            timing_laps.get("best_lap_number")
            or timing_laps.get("last_lap_number")
            or _driver_number(line.get("NumberOfLaps"))
        )
        sectors = self._lap_sectors(line)
        if timing_laps.get("best_lap_time") != timing_laps.get("last_lap_time"):
            sectors = self._best_laps.get(driver_number, {}).get("sectors", sectors)
        sectors = self._merge_best_sectors(driver_number, sectors)
        return {
            "driver_number": driver_number,
            "lap_duration": seconds,
            "lap_number": lap_number,
            "sectors": sectors,
        }

    def _timing_laps(self, line: dict[str, Any]) -> dict[str, Any]:
        last_lap = line.get("LastLapTime", {})
        best_lap = line.get("BestLapTime", {})
        last_value = (
            last_lap.get("Value")
            if isinstance(last_lap, dict)
            else last_lap if isinstance(last_lap, str) else None
        )
        best_value = (
            best_lap.get("Value")
            if isinstance(best_lap, dict)
            else best_lap if isinstance(best_lap, str) else None
        )
        last_seconds = (
            self._lap_seconds(last_value) if isinstance(last_value, str) else None
        )
        best_seconds = (
            self._lap_seconds(best_value) if isinstance(best_value, str) else None
        )
        return {
            "last_lap_time": last_value,
            "last_lap_duration": last_seconds,
            "last_lap_number": (
                _driver_number(last_lap.get("Lap"))
                if isinstance(last_lap, dict)
                else _driver_number(line.get("NumberOfLaps"))
            ),
            "best_lap_time": best_value,
            "best_lap_duration": best_seconds,
            "best_lap_number": (
                _driver_number(best_lap.get("Lap"))
                if isinstance(best_lap, dict)
                else None
            ),
        }

    def _merge_best_sectors(
        self,
        driver_number: int,
        sectors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        best = self._best_sectors.get(driver_number, {})
        if not best:
            return sectors
        by_number = {int(sector["number"]): sector for sector in sectors}
        for number, best_sector in best.items():
            current = by_number.get(number)
            if current is None:
                by_number[number] = deepcopy(best_sector)
                continue
            if best_sector.get("status") == "overall_best":
                current["status"] = "overall_best"
            best_segments = {
                int(segment["number"]): segment
                for segment in best_sector.get("segments", [])
            }
            for segment in current.get("segments", []):
                if int(segment["number"]) in best_segments:
                    segment["status"] = "overall_best"
        return [by_number[number] for number in sorted(by_number)]

    def _lap_sectors(self, line: dict[str, Any]) -> list[dict[str, Any]]:
        sectors = line.get("Sectors")
        if isinstance(sectors, dict):
            sector_items = [
                item
                for _, item in sorted(sectors.items(), key=lambda pair: str(pair[0]))
            ]
        elif isinstance(sectors, list):
            sector_items = sectors
        else:
            return []

        rows: list[dict[str, Any]] = []
        for index, sector in enumerate(sector_items, start=1):
            if not isinstance(sector, dict):
                continue
            value = sector.get("Value")
            segments = self._lap_segments(sector.get("Segments"))
            if not self._sector_has_visible_data(value, sector, segments):
                continue
            rows.append(
                {
                    "number": index,
                    "time": value if isinstance(value, str) and value else None,
                    "status": self._timing_status(sector),
                    "segments": segments,
                }
            )
        return rows

    def _sector_has_visible_data(
        self,
        value: Any,
        sector: dict[str, Any],
        segments: list[dict[str, Any]],
    ) -> bool:
        if isinstance(value, str) and value.strip():
            return True
        if segments:
            return True
        return self._timing_status(sector) != "normal"

    def _lap_segments(self, segments: Any) -> list[dict[str, Any]]:
        if isinstance(segments, dict):
            segment_items = [
                item
                for _, item in sorted(segments.items(), key=lambda pair: str(pair[0]))
            ]
        elif isinstance(segments, list):
            segment_items = segments
        else:
            return []

        rows: list[dict[str, Any]] = []
        for index, segment in enumerate(segment_items, start=1):
            if not isinstance(segment, dict):
                continue
            rows.append(
                {
                    "number": index,
                    "status": self._timing_status(segment),
                    "time": (
                        segment.get("Value")
                        if isinstance(segment.get("Value"), str)
                        else None
                    ),
                }
            )
        return rows

    def _timing_status(self, item: dict[str, Any]) -> str:
        if item.get("OverallFastest"):
            return "overall_best"
        if item.get("PersonalFastest"):
            return "personal_best"
        raw_status = item.get("Status")
        if raw_status in (2049, "2049"):
            return "overall_best"
        if raw_status in (2048, "2048"):
            return "personal_best"
        if raw_status in (2064, "2064"):
            return "pit"
        if raw_status in (0, "0", None, ""):
            return "normal"
        return str(raw_status).lower()

    def _lap_seconds(self, value: str) -> float | None:
        try:
            minutes, seconds = value.split(":", 1)
            return int(minutes) * 60 + float(seconds)
        except ValueError:
            return _number(value)

    def _sector_seconds(self, value: Any) -> float | None:
        if not isinstance(value, str) or not value.strip():
            return None
        return self._lap_seconds(value)
