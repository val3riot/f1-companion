from app.openf1 import best_laps, laps_completed_by, latest_by_driver, parse_date


def test_parse_date_accepts_zulu_time():
    parsed = parse_date("2025-03-16T04:00:00Z")
    assert parsed.utcoffset().total_seconds() == 0


def test_latest_by_driver_keeps_most_recent_row():
    rows = [
        {"driver_number": 4, "date": "2025-01-01T10:00:01Z", "speed": 280},
        {"driver_number": 4, "date": "2025-01-01T10:00:02Z", "speed": 290},
        {"driver_number": 81, "date": "2025-01-01T10:00:01Z", "speed": 275},
    ]
    result = {row["driver_number"]: row for row in latest_by_driver(rows)}
    assert result[4]["speed"] == 290
    assert result[81]["speed"] == 275


def test_best_laps_use_only_laps_completed_by_cursor():
    laps = [
        {
            "driver_number": 12,
            "lap_duration": 70.0,
            "date_start": "2026-06-26T10:00:00Z",
        },
        {
            "driver_number": 7,
            "lap_duration": 68.0,
            "date_start": "2026-06-26T10:02:00Z",
        },
        {
            "driver_number": 12,
            "lap_duration": 66.0,
            "date_start": "2026-06-26T10:04:00Z",
        },
    ]

    visible_laps = laps_completed_by(
        laps,
        parse_date("2026-06-26T10:03:30Z"),
    )
    session_best, driver_bests = best_laps(visible_laps)

    assert session_best["driver_number"] == 7
    assert [lap["driver_number"] for lap in driver_bests] == [7, 12]
