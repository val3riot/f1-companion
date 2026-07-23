import json
from types import SimpleNamespace

from app.signal_archive import SignalArchive
from app import signal_archive


def reference_trace(points: int = 700) -> list[list[float]]:
    return [[float(index), float(index % 20)] for index in range(points)]


def test_signal_archive_writes_snapshots_as_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=0,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()

    archive.record_snapshot(
        {
            "provider": "f1_signalr",
            "session": {
                "meeting_key": 123,
                "meeting_name": "Spanish Grand Prix",
                "session_name": "Race",
                "date_start": "2026-06-14T15:00:00",
            },
            "positions": [{"driver_number": 44, "position": 1}],
        }
    )

    files = list(tmp_path.glob("*/snapshots.jsonl"))
    assert len(files) == 1

    row = json.loads(files[0].read_text().strip())
    assert row["snapshot"]["provider"] == "f1_signalr"
    assert row["snapshot"]["positions"][0]["driver_number"] == 44
    assert files[0].parent.name == "2026-06-14_Spanish_Grand_Prix_Race"


def test_signal_archive_respects_snapshot_interval(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    snapshot = {"session": {"session_name": "Live Timing"}}

    archive.record_snapshot(snapshot)
    archive.record_snapshot(snapshot)

    file = next(tmp_path.glob("*/snapshots.jsonl"))
    assert len(file.read_text().splitlines()) == 1


def test_signal_archive_caches_team_radio_transcription(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    session = {
        "meeting_name": "Spanish Grand Prix",
        "session_name": "Race",
        "date_start": "2026-06-14T15:00:00",
    }
    radio = {
        "path": "TeamRadio/HAM_44_20260614_164234.mp3",
        "url": "https://example.test/radio.mp3",
        "driver_number": 44,
    }

    archive.save_team_radio_transcription(
        session,
        radio,
        "Box this lap",
        "Rientra ai box questo giro",
    )

    cached = archive.get_team_radio_transcription(session, radio)

    assert cached["transcript"] == "Box this lap"
    assert cached["translation_it"] == "Rientra ai box questo giro"
    assert list(tmp_path.glob("*/team_radio_transcriptions.json"))


def test_signal_archive_caches_track_map(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    session = {
        "meeting_name": "Austrian Grand Prix",
        "session_name": "Practice 1",
        "date_start": "2026-06-26T13:30:00",
    }
    track_map = {
        "source": "F1 SignalR Position.z",
        "driver_number": 3,
        "aggregation": "best_car",
        "trace": reference_trace(),
        "coverage": {"3": 700},
    }

    archive.save_track_map(session, track_map)

    assert archive.get_track_map(session) == track_map
    assert list(tmp_path.glob("*/track_map.json"))


def test_signal_archive_ignores_partial_track_map(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    session = {
        "meeting_name": "Austrian Grand Prix",
        "session_name": "Practice 1",
        "date_start": "2026-06-26T13:30:00",
    }
    track_map = {
        "source": "F1 SignalR Position.z",
        "driver_number": 0,
        "aggregation": "all_cars",
        "trace": reference_trace(44),
        "coverage": {"3": 44},
    }

    archive.save_track_map(session, track_map)

    assert archive.get_track_map(session) is None


def test_signal_archive_replaces_legacy_single_driver_track_map(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    session = {
        "meeting_name": "Austrian Grand Prix",
        "session_name": "Practice 1",
        "date_start": "2026-06-26T13:30:00",
    }
    legacy = {
        "source": "F1 SignalR Position.z",
        "driver_number": 3,
        "trace": reference_trace(),
        "coverage": {"3": 700},
    }
    current = {
        "source": "F1 SignalR Position.z",
        "driver_number": 3,
        "aggregation": "best_car",
        "trace": reference_trace(300),
        "coverage": {"3": 300},
    }

    archive._write_json_unlocked(
        "track_map.json",
        {"track_map": legacy},
        session,
    )
    archive.save_track_map(session, current)

    assert archive.get_track_map(session) == current


def test_signal_archive_reads_legacy_single_driver_track_map(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    session = {
        "meeting_name": "Austrian Grand Prix",
        "session_name": "Practice 1",
        "date_start": "2026-06-26T13:30:00",
    }
    legacy = {
        "source": "F1 SignalR Position.z",
        "driver_number": 6,
        "trace": reference_trace(),
        "coverage": {"6": 700},
    }

    archive._write_json_unlocked(
        "track_map.json",
        {"track_map": legacy},
        session,
    )

    cached = archive.get_track_map(session)

    assert cached == {
        **legacy,
        "aggregation": "best_car",
        "coordinate_system": "f1_position",
    }


def test_signal_archive_replaces_lower_coverage_track_map(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    session = {
        "meeting_name": "Austrian Grand Prix",
        "session_name": "Practice 1",
        "date_start": "2026-06-26T13:30:00",
    }
    early = {
        "source": "F1 SignalR Position.z",
        "driver_number": 3,
        "aggregation": "best_car",
        "trace": reference_trace(300),
        "coverage": {"3": 300},
    }
    improved = {
        "source": "F1 SignalR Position.z",
        "driver_number": 3,
        "aggregation": "best_car",
        "trace": reference_trace(650),
        "coverage": {"3": 650},
    }

    archive.save_track_map(session, early)
    archive.save_track_map(session, improved)

    assert archive.get_track_map(session) == improved


def test_signal_archive_reuses_event_track_map_for_partial_session(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    practice = {
        "meeting_name": "Austrian Grand Prix",
        "session_name": "Practice 1",
        "date_start": "2026-06-26T13:30:00",
    }
    qualifying = {
        "meeting_name": "Austrian Grand Prix",
        "session_name": "Qualifying",
        "date_start": "2026-06-27T16:00:00",
    }
    track_map = {
        "source": "F1 SignalR Position.z",
        "driver_number": 3,
        "aggregation": "best_car",
        "trace": reference_trace(),
        "coverage": {"3": 700},
    }

    archive.save_track_map(practice, track_map)

    assert archive.get_track_map(qualifying) == track_map


def test_signal_archive_does_not_pin_unknown_session(tmp_path, monkeypatch):
    monkeypatch.setattr(
        signal_archive,
        "settings",
        SimpleNamespace(
            f1_signalr_archive_enabled=True,
            f1_signalr_archive_dir=str(tmp_path),
            f1_signalr_snapshot_archive_interval_seconds=60,
            team_radio_transcription_cache_enabled=True,
        ),
    )
    archive = SignalArchive()
    known_session = {
        "meeting_name": "Austrian Grand Prix",
        "session_name": "Practice 1",
        "date_start": "2026-06-26T13:30:00",
    }
    track_map = {
        "source": "F1 SignalR Position.z",
        "driver_number": 3,
        "aggregation": "best_car",
        "trace": reference_trace(),
        "coverage": {"3": 700},
    }

    assert archive.get_track_map({}) is None
    archive.save_track_map(known_session, track_map)

    assert archive.get_track_map(known_session) == track_map
    assert not (tmp_path / "unknown_live_timing").exists()
