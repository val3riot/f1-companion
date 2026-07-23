from datetime import datetime, timedelta

import pytest

from app.telemetry import FastF1Service, TelemetryUnavailable
from app.telemetry import circuit_corners, downsample_trace, downsample_xy
from app.telemetry import add_trace_to_circuit_map, empty_circuit_map, lap_options


class FakeLapTime:
    def __init__(self, seconds):
        self.seconds = seconds

    def total_seconds(self):
        return self.seconds


def test_downsample_trace_limits_points_and_preserves_edges():
    rows = [
        (float(index), float(index + 100), 50.0, 0.0)
        for index in range(1000)
    ]

    trace = downsample_trace(rows, max_points=100)

    assert len(trace) == 100
    assert trace[0][0] == 0.0
    assert trace[-1][0] == 999.0


def test_downsample_trace_rounds_values():
    trace = downsample_trace([(1.234, 201.567, 87.654, 100.0)])
    assert trace == [[1.2, 201.6, 87.7, 100.0]]


def test_downsample_xy_limits_points_and_rounds_values():
    rows = [(float(index), float(index) + 0.456) for index in range(1000)]

    trace = downsample_xy(rows, max_points=50)

    assert len(trace) == 50
    assert trace[0] == [0.0, 0.5]
    assert trace[-1] == [999.0, 999.5]


def test_lap_options_exposes_valid_laps_sorted():
    rows = [
        {
            "LapNumber": 8.0,
            "LapTime": FakeLapTime(72.3456),
            "Compound": "MEDIUM",
            "Stint": 2,
        },
        {"LapNumber": 7.0, "LapTime": FakeLapTime(73.0), "Compound": "SOFT"},
        {"LapNumber": 9.0, "LapTime": None, "Compound": "SOFT"},
    ]

    assert lap_options(rows) == [
        {
            "lap_number": 7,
            "lap_time": 73.0,
            "compound": "SOFT",
            "stint": None,
        },
        {
            "lap_number": 8,
            "lap_time": 72.346,
            "compound": "MEDIUM",
            "stint": 2,
        },
    ]


def test_circuit_corners_keeps_number_and_coordinates():
    corners = circuit_corners(
        [
            {
                "Number": 1,
                "Letter": "A",
                "Distance": 120.456,
                "X": 10.12,
                "Y": 20.34,
            },
            {"Number": 2, "X": None, "Y": 10},
        ]
    )

    assert corners == [
        {
            "number": 1,
            "letter": "A",
            "distance": 120.5,
            "x": 10.1,
            "y": 20.3,
        }
    ]


def test_add_trace_to_circuit_map_uses_first_available_xy():
    class FakeTelemetry:
        empty = False
        columns = {"X", "Y"}

        def __getitem__(self, _):
            return self

        def dropna(self):
            return self

        def iterrows(self):
            return iter(
                [
                    (0, {"X": 1.23, "Y": 4.56}),
                    (1, {"X": 7.89, "Y": 0.12}),
                ]
            )

    circuit_map = empty_circuit_map([], "test")
    add_trace_to_circuit_map(circuit_map, FakeTelemetry())
    add_trace_to_circuit_map(circuit_map, FakeTelemetry())

    assert circuit_map["trace"] == [[1.2, 4.6], [7.9, 0.1]]


def test_practice_metrics_handles_sessions_without_loaded_laps():
    class FakeSession:
        name = "Practice 2"

        def load(self, **_):
            return None

        @property
        def laps(self):
            raise RuntimeError("The data has not been loaded yet")

    class FakeFastF1:
        def get_session(self, *_):
            return FakeSession()

    class FakeService(FastF1Service):
        def _library(self):
            return FakeFastF1()

    with pytest.raises(TelemetryUnavailable):
        FakeService()._practice_metrics(2026, 11)


def test_available_sessions_only_returns_finished_sessions():
    now = datetime.now()

    class FakeEvent:
        data = {
            "Session1": "Practice 1",
            "Session1Date": now - timedelta(hours=3),
            "Session2": "Practice 2",
            "Session2Date": now + timedelta(hours=1),
            "Session3": "Qualifying",
            "Session3Date": now - timedelta(hours=2),
            "Session4": "Race",
            "Session4Date": now - timedelta(hours=1),
            "Session5": "",
            "Session5Date": None,
        }

        def get(self, key, default=None):
            return self.data.get(key, default)

    class FakeFastF1:
        def get_event(self, *_):
            return FakeEvent()

    class FakeService(FastF1Service):
        def _library(self):
            return FakeFastF1()

    sessions = FakeService()._available_sessions(2026, 11)

    assert [session["value"] for session in sessions] == ["fp1", "qualifying"]
