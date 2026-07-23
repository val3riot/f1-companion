from app.history import aggregate_jolpica, normalize, parse_lap_time


def result(position, driver, constructor, grid, position_text=None, fastest=None):
    row = {
        "position": str(position),
        "positionText": position_text or str(position),
        "grid": str(grid),
        "Driver": {
            "givenName": driver.split()[0],
            "familyName": driver.split()[-1],
        },
        "Constructor": {"name": constructor},
    }
    if fastest:
        row["FastestLap"] = {
            "lap": "12",
            "Time": {"time": fastest},
            "AverageSpeed": {"speed": "220.5"},
        }
    return row


def test_normalize_removes_accents_and_symbols():
    assert normalize("São Paulo") == "saopaulo"


def test_parse_lap_time():
    assert parse_lap_time("1:21.046") == 81.046
    assert parse_lap_time(None) is None


def test_aggregate_jolpica_builds_historical_stats():
    circuit = {
        "circuitId": "test",
        "circuitName": "Test Circuit",
        "url": "https://example.com",
        "Location": {
            "locality": "Test",
            "country": "Italy",
            "lat": "1",
            "long": "2",
        },
    }
    races = [
        {
            "season": "2024",
            "round": "1",
            "date": "2024-01-01",
            "raceName": "Test GP",
            "Results": [
                result(1, "Ada Fast", "Red", 3, fastest="1:20.000"),
                result(2, "Bea Quick", "Blue", 1, fastest="1:19.500"),
                result(3, "Cara Pace", "Red", 2),
                result(4, "Dana Stop", "Green", 4, position_text="R"),
            ],
        }
    ]

    data = aggregate_jolpica(circuit, races)

    assert data["overview"]["editions"] == 1
    assert data["overview"]["completion_rate"] == 75.0
    assert data["leaders"]["wins"][0] == {"name": "Ada Fast", "value": 1}
    assert data["records"]["lap"]["driver"] == "Bea Quick"
    assert data["records"]["best_comebacks"][0]["grid"] == 3


def test_comeback_uses_winner_even_when_results_are_unsorted():
    circuit = {
        "circuitId": "interlagos",
        "circuitName": "Interlagos",
        "url": "https://example.com",
        "Location": {
            "locality": "São Paulo",
            "country": "Brazil",
            "lat": "-23.7",
            "long": "-46.7",
        },
    }
    races = [
        {
            "season": "2024",
            "round": "21",
            "date": "2024-11-03",
            "raceName": "São Paulo Grand Prix",
            "Results": [
                result(2, "Esteban Ocon", "Alpine", 4),
                result(1, "Max Verstappen", "Red Bull", 17),
            ],
        }
    ]

    data = aggregate_jolpica(circuit, races)

    assert data["records"]["best_comebacks"][0] == {
        "year": 2024,
        "driver": "Max Verstappen",
        "grid": 17,
    }
