import base64
import json
import zlib
from types import SimpleNamespace
from urllib.parse import quote

from app import f1signal
from app.f1signal import F1SignalRTranslator


def raw_deflate(payload: dict) -> str:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    data = compressor.compress(json.dumps(payload).encode())
    data += compressor.flush()
    return base64.b64encode(data).decode()


def reference_trace(points: int = 700) -> list[list[float]]:
    return [[float(index), float(index % 20)] for index in range(points)]


def test_f1_signal_translates_core_topics_to_snapshot():
    translator = F1SignalRTranslator()

    translator.apply_message(
        [
            "DriverList",
            json.dumps(
                {
                    "1": {
                        "FullName": "Max Verstappen",
                        "Tla": "VER",
                        "TeamName": "Red Bull Racing",
                        "TeamColour": "3671C6",
                    }
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "TimingData",
            json.dumps(
                {
                    "Lines": {
                        "1": {
                            "Position": "1",
                            "GapToLeader": {"Value": ""},
                            "IntervalToPositionAhead": {"Value": ""},
                            "LastLapTime": {"Value": "1:24.123"},
                            "NumberOfLaps": 42,
                            "Sectors": [
                                {
                                    "Value": "28.100",
                                    "PersonalFastest": True,
                                    "Segments": [
                                        {"Status": 2048},
                                        {"Status": 2049},
                                        {"Status": 0},
                                    ],
                                },
                                {
                                    "Value": "31.200",
                                    "OverallFastest": True,
                                    "Segments": [
                                        {"Status": 0},
                                        {"Status": 2064},
                                    ],
                                },
                            ],
                        }
                    }
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "WeatherData",
            json.dumps(
                {
                    "AirTemp": "27.2",
                    "TrackTemp": "43.0",
                    "Humidity": "55",
                    "Rainfall": "0",
                    "WindSpeed": "2.8",
                }
            ),
            "",
        ]
    )

    snapshot = translator.snapshot()

    assert snapshot["drivers"][0]["name_acronym"] == "VER"
    assert snapshot["positions"][0]["position"] == 1
    assert snapshot["intervals"][0]["driver_number"] == 1
    assert snapshot["weather"]["air_temperature"] == 27.2
    assert snapshot["best_lap"]["lap_duration"] == 84.123
    assert snapshot["best_lap"]["sectors"] == [
        {
            "number": 1,
            "time": "28.100",
            "status": "personal_best",
            "segments": [
                {"number": 1, "status": "personal_best", "time": None},
                {"number": 2, "status": "overall_best", "time": None},
                {"number": 3, "status": "normal", "time": None},
            ],
        },
        {
            "number": 2,
            "time": "31.200",
            "status": "overall_best",
            "segments": [
                {"number": 1, "status": "normal", "time": None},
                {"number": 2, "status": "pit", "time": None},
            ],
        },
    ]


def test_f1_signal_decodes_compressed_car_data():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "CarData.z",
            raw_deflate(
                {
                    "Entries": [
                        {
                            "Utc": "2026-06-17T12:00:00",
                            "Cars": {
                                "44": {
                                    "Channels": {
                                        "0": "11000",
                                        "2": "312",
                                        "3": "8",
                                        "4": "99",
                                        "5": "0",
                                        "45": "10",
                                    }
                                }
                            },
                        }
                    ]
                }
            ),
            "",
        ]
    )

    telemetry = translator.snapshot()["telemetry"][0]

    assert telemetry["driver_number"] == 44
    assert telemetry["rpm"] == 11000
    assert telemetry["speed"] == 312
    assert telemetry["n_gear"] == 8
    assert telemetry["throttle"] == 99
    assert telemetry["brake"] == 0
    assert telemetry["drs"] == 10


def test_f1_signal_keeps_best_lap_segments_after_slower_lap():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "TimingData",
            json.dumps(
                {
                    "Lines": {
                        "1": {
                            "LastLapTime": {"Value": "1:08.100"},
                            "NumberOfLaps": 8,
                            "Sectors": [
                                {
                                    "Value": "20.100",
                                    "Segments": [
                                        {"Status": 2049},
                                        {"Status": 2048},
                                    ],
                                }
                            ],
                        }
                    }
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "TimingData",
            json.dumps(
                {
                    "Lines": {
                        "1": {
                            "LastLapTime": {"Value": "1:10.500"},
                            "NumberOfLaps": 9,
                            "Sectors": [
                                {
                                    "Value": "22.500",
                                    "Segments": [{"Status": 0}],
                                }
                            ],
                        }
                    }
                }
            ),
            "",
        ]
    )

    best_lap = translator.snapshot()["best_lap"]

    assert best_lap["lap_duration"] == 68.1
    assert best_lap["lap_number"] == 8
    assert best_lap["sectors"][0]["segments"] == [
        {"number": 1, "status": "overall_best", "time": None},
        {"number": 2, "status": "personal_best", "time": None},
    ]


def test_f1_signal_demotes_previous_overall_best_sector():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "TimingData",
            json.dumps(
                {
                    "Lines": {
                        "1": {
                            "LastLapTime": {"Value": "1:10.000"},
                            "NumberOfLaps": 5,
                            "Sectors": [
                                {"Value": "30.000", "OverallFastest": True},
                            ],
                        }
                    }
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "TimingData",
            json.dumps(
                {
                    "Lines": {
                        "2": {
                            "LastLapTime": {"Value": "1:09.000"},
                            "NumberOfLaps": 6,
                            "Sectors": [
                                {"Value": "29.500", "OverallFastest": True},
                            ],
                        }
                    }
                }
            ),
            "",
        ]
    )

    laps = {
        lap["driver_number"]: lap
        for lap in translator.snapshot()["best_laps"]
    }

    assert laps[1]["sectors"][0]["status"] == "personal_best"
    assert laps[2]["sectors"][0]["status"] == "overall_best"


def test_f1_signal_omits_empty_sector_placeholders():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "TimingData",
            json.dumps(
                {
                    "Lines": {
                        "17": {
                            "LastLapTime": {"Value": "1:09.646"},
                            "NumberOfLaps": 20,
                            "Sectors": [
                                {"Value": "30.861"},
                                {"Value": ""},
                                {},
                            ],
                        }
                    }
                }
            ),
            "",
        ]
    )

    best_lap = translator.snapshot()["best_lap"]

    assert best_lap["sectors"] == [
        {
            "number": 1,
            "time": "30.861",
            "status": "normal",
            "segments": [],
        }
    ]


def test_f1_signal_resets_best_laps_when_session_changes():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Name": "Practice 1",
                    "Type": "Practice",
                    "StartDate": "2026-06-26T10:30:00",
                    "Meeting": {"Name": "Austrian Grand Prix"},
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "TimingData",
            json.dumps(
                {
                    "Lines": {
                        "17": {
                            "LastLapTime": {"Value": "1:07.000"},
                            "NumberOfLaps": 12,
                        }
                    }
                }
            ),
            "",
        ]
    )

    assert translator.snapshot()["best_lap"]["driver_number"] == 17

    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Name": "Practice 2",
                    "Type": "Practice",
                    "StartDate": "2026-06-26T14:00:00",
                    "Meeting": {"Name": "Austrian Grand Prix"},
                }
            ),
            "",
        ]
    )

    assert translator.snapshot()["best_lap"] is None
    assert translator.snapshot()["best_laps"] == []


def test_f1_signal_extracts_subscription_token_from_login_session(monkeypatch):
    monkeypatch.setattr(
        f1signal,
        "settings",
        SimpleNamespace(
            f1_signalr_auth_token=None,
            f1_signalr_login_session=quote(
                json.dumps({"data": {"subscriptionToken": "test-token"}})
            ),
        ),
    )

    assert f1signal.f1_subscription_token() == "test-token"
    assert (
        f1signal.f1_subscription_token_source()
        == "F1_SIGNALR_LOGIN_SESSION.subscriptionToken"
    )


def test_f1_signal_marks_finished_session_as_not_live():
    translator = F1SignalRTranslator()
    translator._connected = True
    translator.apply_message(
        [
            "SessionStatus",
            json.dumps({"Status": "Ends", "Started": "Finished"}),
            "",
        ]
    )

    assert translator.snapshot()["is_live_window"] is False


def test_f1_signal_hides_track_trace_until_reference_is_ready():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {"Cars": {"44": {"X": 10, "Y": 20, "Z": 0}}},
                        {"Cars": {"44": {"X": 12, "Y": 22, "Z": 0}}},
                    ]
                }
            ),
            "",
        ]
    )

    assert translator.snapshot()["track_map"] is None


def test_f1_signal_normalizes_live_location_coordinates():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {
                            "Timestamp": "2026-06-26T12:30:00Z",
                            "Cars": {
                                "44": {"X": "10.5", "Y": "20.25", "Z": "0"}
                            },
                        }
                    ]
                }
            ),
            "",
        ]
    )

    locations = translator.snapshot()["locations"]

    assert locations == [
        {
            "driver_number": 44,
            "date": "2026-06-26T12:30:00Z",
            "x": 10.5,
            "y": 20.25,
            "z": 0,
        }
    ]


def test_f1_signal_reads_position_entries_payload():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {
                            "Timestamp": "2026-06-26T12:31:00Z",
                            "Entries": {
                                "44": {"X": "-12", "Y": "34.5", "Z": "0"},
                                "63": {"X": "8", "Y": "-5", "Z": "1"},
                            },
                        },
                        {
                            "Timestamp": "2026-06-26T12:31:01Z",
                            "Entries": {
                                "44": {"X": "-11", "Y": "35.5", "Z": "0"},
                                "63": {"X": "9", "Y": "-4", "Z": "1"},
                            },
                        }
                    ]
                }
            ),
            "",
        ]
    )

    snapshot = translator.snapshot()

    assert snapshot["locations"] == [
        {
            "driver_number": 44,
            "date": "2026-06-26T12:31:01Z",
            "x": -11,
            "y": 35.5,
            "z": 0,
        },
        {
            "driver_number": 63,
            "date": "2026-06-26T12:31:01Z",
            "x": 9,
            "y": -4,
            "z": 1,
        },
    ]
    assert snapshot["track_map"] is None


def test_f1_signal_keeps_last_known_location_for_each_driver():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {
                            "Timestamp": "2026-06-26T12:31:00Z",
                            "Entries": {
                                "31": {"X": "10", "Y": "20", "Z": "0"},
                                "87": {"X": "30", "Y": "40", "Z": "0"},
                            },
                        },
                        {
                            "Timestamp": "2026-06-26T12:31:01Z",
                            "Entries": {
                                "87": {"X": "35", "Y": "45", "Z": "0"},
                            },
                        },
                    ]
                }
            ),
            "",
        ]
    )

    assert translator.snapshot()["locations"] == [
        {
            "driver_number": 31,
            "date": "2026-06-26T12:31:00Z",
            "x": 10,
            "y": 20,
            "z": 0,
        },
        {
            "driver_number": 87,
            "date": "2026-06-26T12:31:01Z",
            "x": 35,
            "y": 45,
            "z": 0,
        },
    ]


def test_f1_signal_builds_visual_track_map_from_complete_car_gps():
    class FakeArchive:
        def enabled(self):
            return True

    translator = F1SignalRTranslator()
    translator._archive = FakeArchive()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {"Name": "Austrian Grand Prix"},
                    "Name": "Practice 1",
                    "StartDate": "2026-06-26T13:30:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {
                            "Entries": {
                                "3": {
                                    "X": str(index),
                                    "Y": str((index % 100) * (1 if index < 150 else -1)),
                                }
                            }
                        }
                        for index in range(300)
                    ]
                }
            ),
            "",
        ]
    )

    track_map = translator.snapshot()["track_map"]

    assert track_map["source"] == "F1 SignalR Position.z"
    assert track_map["aggregation"] == "best_car"
    assert track_map["driver_number"] == 3
    assert len(track_map["trace"]) == 300


def test_f1_signal_keeps_gps_trace_internal_until_official_layout_exists():
    translator = F1SignalRTranslator()
    translator._archive = SimpleNamespace(
        enabled=lambda: False,
        get_track_map=lambda _session: None,
        save_track_map=lambda _session, _track_map: None,
    )
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {"Name": "Austrian Grand Prix"},
                    "Name": "Practice 1",
                    "StartDate": "2026-06-26T13:30:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {"Entries": {"3": {"X": str(index), "Y": "0"}}}
                        for index in range(170)
                    ]
                    + [
                        {"Entries": {"44": {"X": str(index), "Y": "100"}}}
                        for index in range(170)
                    ]
                }
            ),
            "",
        ]
    )

    assert translator.snapshot()["track_map"] is None
    assert len(translator._all_cars_track_trace(max_points=700)) == 340


def test_f1_signal_keeps_gps_visual_reference_up_to_date():
    class FakeArchive:
        def enabled(self):
            return True

        def get_track_map(self, _session_info):
            return None

        def save_track_map(self, _session_info, _track_map):
            return None

    translator = F1SignalRTranslator()
    translator._archive = FakeArchive()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {"Name": "Austrian Grand Prix"},
                    "Name": "Practice 1",
                    "StartDate": "2026-06-26T13:30:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {"Entries": {"3": {"X": str(index), "Y": str(index)}}}
                        for index in range(300)
                    ]
                }
            ),
            "",
        ]
    )

    first_track_map = translator.snapshot()["track_map"]

    assert first_track_map["coverage"] == {"3": 300}

    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {
                            "Entries": {
                                "3": {"X": str(index + 1000), "Y": str(index + 1000)}
                            }
                        }
                        for index in range(80)
                    ]
                }
            ),
            "",
        ]
    )

    updated_track_map = translator.snapshot()["track_map"]

    assert updated_track_map["coverage"] == {"3": 380}
    assert updated_track_map["trace"] != first_track_map["trace"]


def test_f1_signal_reuses_cached_event_track_map_when_gps_trace_is_partial():
    cached_map = {
        "source": "F1 SignalR Position.z",
        "driver_number": 3,
        "aggregation": "best_car",
        "trace": reference_trace(),
        "coverage": {"3": 700},
        "coordinate_system": "f1_position",
    }

    class FakeArchive:
        def enabled(self):
            return True

        def get_track_map(self, _session_info):
            return cached_map

        def save_track_map(self, _session_info, _track_map):
            raise AssertionError("partial GPS trace must not replace cached layout")

    translator = F1SignalRTranslator()
    translator._archive = FakeArchive()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {"Name": "Austrian Grand Prix"},
                    "Name": "Practice 1",
                    "StartDate": "2026-06-26T13:30:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {"Entries": {"44": {"X": "100", "Y": "200"}}},
                        {"Entries": {"44": {"X": "300", "Y": "400"}}},
                    ]
                }
            ),
            "",
        ]
    )

    assert translator.snapshot()["track_map"] == cached_map


def test_f1_signal_prefers_official_circuit_info_over_cached_gps(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "Corners": [
                    {"Number": 1, "X": 0, "Y": 0},
                    {"Number": 2, "X": 100, "Y": 0},
                    {"Number": 3, "X": 100, "Y": 60},
                    {"Number": 4, "X": 0, "Y": 60},
                ]
            }

    class FakeArchive:
        def enabled(self):
            return True

        def get_track_map(self, _session_info):
            return {
                "source": "F1 SignalR Position.z",
                "driver_number": 0,
                "aggregation": "all_cars",
                "trace": reference_trace(),
                "coverage": {"3": 700},
            }

        def save_track_map(self, _session_info, _track_map):
            raise AssertionError("official layout should be preferred")

    monkeypatch.setattr(f1signal.requests, "get", lambda *_args, **_kwargs: FakeResponse())
    translator = F1SignalRTranslator()
    translator._archive = FakeArchive()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {
                        "Name": "Austrian Grand Prix",
                        "OfficialDate": "2026-06-28",
                    },
                    "Name": "Practice 1",
                    "StartDate": "2026-06-26T13:30:00",
                }
            ),
            "",
        ]
    )

    track_map = translator.snapshot()["track_map"]

    assert track_map["source"] == "F1 Live Timing CircuitInfo"
    assert track_map["coverage"] == {"corners": 4}


def test_f1_signal_uses_official_circuit_info_when_gps_trace_is_partial(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "Corners": [
                    {"Number": 1, "X": 0, "Y": 0},
                    {"Number": 2, "X": 100, "Y": 0},
                    {"Number": 3, "X": 100, "Y": 60},
                    {"Number": 4, "X": 0, "Y": 60},
                ]
            }

    requested_urls = []

    def fake_get(url, timeout):
        requested_urls.append((url, timeout))
        return FakeResponse()

    monkeypatch.setattr(f1signal.requests, "get", fake_get)

    translator = F1SignalRTranslator()
    translator._archive = SimpleNamespace(
        enabled=lambda: False,
        get_track_map=lambda _session: None,
    )
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {
                        "Name": "Austrian Grand Prix",
                        "OfficialDate": "2026-06-28",
                    },
                    "Name": "Practice 1",
                    "StartDate": "2026-06-26T13:30:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "Position.z",
            raw_deflate(
                {
                    "Position": [
                        {"Entries": {"44": {"X": "10", "Y": "20"}}},
                        {"Entries": {"44": {"X": "11", "Y": "21"}}},
                    ]
                }
            ),
            "",
        ]
    )

    track_map = translator.snapshot()["track_map"]

    assert track_map["source"] == "F1 Live Timing CircuitInfo"
    assert len(track_map["trace"]) >= 120
    assert track_map["coverage"] == {"corners": 4}


def test_f1_signal_uses_official_circuit_info_before_gps_arrives(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "Corners": [
                    {"Number": 1, "X": 0, "Y": 0},
                    {"Number": 2, "X": 100, "Y": 0},
                    {"Number": 3, "X": 100, "Y": 60},
                    {"Number": 4, "X": 0, "Y": 60},
                ]
            }

    requested_urls = []

    def fake_get(url, timeout):
        requested_urls.append((url, timeout))
        return Response()

    monkeypatch.setattr("app.f1signal.requests.get", fake_get)
    translator = F1SignalRTranslator()
    translator._archive = SimpleNamespace(
        enabled=lambda: False,
        get_track_map=lambda _session: None,
    )
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Name": "Practice 1",
                    "StartDate": "2026-06-26T11:30:00",
                    "Meeting": {
                        "Name": "Austrian Grand Prix",
                        "OfficialDate": "2026-06-28",
                    },
                }
            ),
            "",
        ]
    )

    snapshot = translator.snapshot()

    assert snapshot["locations"] == []
    assert snapshot["track_map"]["source"] == "F1 Live Timing CircuitInfo"
    assert len(snapshot["track_map"]["trace"]) >= 120
    assert requested_urls == [
        (
            "https://livetiming.formula1.com/static/2026/"
            "2026-06-28_Austrian_Grand_Prix/2026-06-26_Practice_1/"
            "CircuitInfo.json",
            2,
        )
    ]


def test_f1_signal_uses_best_lap_time_and_exposes_last_lap():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "TimingData",
            json.dumps(
                {
                    "Lines": {
                        "4": {
                            "Position": "2",
                            "LastLapTime": {"Value": "1:12.400", "Lap": 18},
                            "BestLapTime": {"Value": "1:10.250", "Lap": 14},
                            "NumberOfLaps": 18,
                        }
                    }
                }
            ),
            "",
        ]
    )

    snapshot = translator.snapshot()

    assert snapshot["positions"][0]["last_lap_time"] == "1:12.400"
    assert snapshot["positions"][0]["best_lap_time"] == "1:10.250"
    assert snapshot["best_lap"]["lap_duration"] == 70.25
    assert snapshot["best_lap"]["lap_number"] == 14


def test_f1_signal_collects_team_radio_clips():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {
                        "Name": "Spanish Grand Prix",
                        "StartDate": "2026-06-12T11:00:00",
                    },
                    "Name": "Race",
                    "StartDate": "2026-06-14T15:00:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "TeamRadio",
            json.dumps(
                {
                    "Captures": [
                        {
                            "Utc": "2026-06-17T12:00:00Z",
                            "RacingNumber": "44",
                            "Path": "TeamRadio/HAM_44_20260614_164234.mp3",
                        }
                    ]
                }
            ),
            "",
        ]
    )

    radio = translator.snapshot()["team_radio"][0]

    assert radio["driver_number"] == 44
    assert radio["utc"] == "2026-06-17T12:00:00Z"
    assert radio["path"] == "TeamRadio/HAM_44_20260614_164234.mp3"
    assert radio["url"] == (
        "https://livetiming.formula1.com/static/2026/"
        "2026-06-14_Spanish_Grand_Prix/2026-06-14_Race/"
        "TeamRadio/HAM_44_20260614_164234.mp3"
    )

    updated = translator.set_team_radio_text(
        "TeamRadio/HAM_44_20260614_164234.mp3",
        "Box this lap",
        "Rientra ai box questo giro",
    )

    assert updated["transcript"] == "Box this lap"
    assert updated["translation_it"] == "Rientra ai box questo giro"


def test_f1_signal_collects_indexed_team_radio_payloads():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {
                        "Name": "Spanish Grand Prix",
                        "StartDate": "2026-06-12T11:00:00",
                    },
                    "Name": "Race",
                    "StartDate": "2026-06-14T15:00:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "TeamRadio",
            json.dumps(
                {
                    "Captures": {
                        "0": {
                            "Utc": "2026-06-17T12:00:00Z",
                            "RacingNo": "12",
                            "AudioPath": "TeamRadio/ANT_12_20260614_164234.mp3",
                        },
                        "1": {
                            "Utc": "2026-06-17T12:01:00Z",
                            "CarNumber": "81",
                            "URL": "https://example.test/team-radio.mp3",
                        },
                    }
                }
            ),
            "",
        ]
    )

    radios = translator.snapshot()["team_radio"]

    assert [radio["driver_number"] for radio in radios] == [12, 81]
    assert radios[0]["path"] == "TeamRadio/ANT_12_20260614_164234.mp3"
    assert radios[0]["url"].endswith(
        "/TeamRadio/ANT_12_20260614_164234.mp3"
    )
    assert radios[1]["path"] == "https://example.test/team-radio.mp3"
    assert radios[1]["url"] == "https://example.test/team-radio.mp3"


def test_f1_signal_archives_raw_team_radio_topic():
    recorded = []

    class FakeArchive:
        def enabled(self):
            return True

        def record_topic(self, topic, payload, session_info):
            recorded.append((topic, payload, session_info))

    translator = F1SignalRTranslator()
    translator._archive = FakeArchive()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {"Name": "Spanish Grand Prix"},
                    "Name": "Race",
                    "StartDate": "2026-06-14T15:00:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "TeamRadio",
            json.dumps(
                {
                    "Captures": [
                        {
                            "RacingNumber": "44",
                            "Path": "TeamRadio/HAM_44_20260614_164234.mp3",
                        }
                    ]
                }
            ),
            "",
        ]
    )

    assert recorded == [
        (
            "TeamRadio",
            {
                "Captures": [
                    {
                        "RacingNumber": "44",
                        "Path": "TeamRadio/HAM_44_20260614_164234.mp3",
                    }
                ]
            },
            {
                "Meeting": {"Name": "Spanish Grand Prix"},
                "Name": "Race",
                "StartDate": "2026-06-14T15:00:00",
            },
        )
    ]


def test_f1_signal_uses_race_date_for_practice_team_radio_static_path():
    translator = F1SignalRTranslator()
    translator.apply_message(
        [
            "SessionInfo",
            json.dumps(
                {
                    "Meeting": {
                        "Name": "Austrian Grand Prix",
                        "StartDate": "2026-06-26T11:00:00",
                    },
                    "Name": "Practice 1",
                    "StartDate": "2026-06-26T13:30:00",
                }
            ),
            "",
        ]
    )
    translator.apply_message(
        [
            "TeamRadio",
            json.dumps(
                {
                    "Captures": [
                        {
                            "Utc": "2026-06-26T12:03:14Z",
                            "RacingNumber": "3",
                            "Path": "TeamRadio/VER_3_20260626_140249.mp3",
                        }
                    ]
                }
            ),
            "",
        ]
    )

    radio = translator.snapshot()["team_radio"][0]

    assert radio["url"] == (
        "https://livetiming.formula1.com/static/2026/"
        "2026-06-28_Austrian_Grand_Prix/2026-06-26_Practice_1/"
        "TeamRadio/VER_3_20260626_140249.mp3"
    )


def test_f1_signal_hydrates_team_radio_text_from_cache():
    translator = F1SignalRTranslator()
    translator._archive = SimpleNamespace(
        enabled=lambda: True,
        get_team_radio_transcription=lambda session, radio: {
            "transcript": "Box this lap",
            "translation_it": "Rientra ai box questo giro",
        }
    )
    translator.apply_message(
        [
            "TeamRadio",
            json.dumps(
                {
                    "Captures": [
                        {
                            "Utc": "2026-06-17T12:00:00Z",
                            "RacingNumber": "44",
                            "Path": "https://example.test/radio.mp3",
                        }
                    ]
                }
            ),
            "",
        ]
    )
    snapshot = translator.snapshot()

    translator.hydrate_team_radio_transcription_cache(snapshot)

    radio = snapshot["team_radio"][0]
    assert radio["transcript"] == "Box this lap"
    assert radio["translation_it"] == "Rientra ai box questo giro"
    assert radio["transcription_status"] == "done"
    assert translator.team_radio_by_path("https://example.test/radio.mp3")[
        "transcript"
    ] == "Box this lap"
