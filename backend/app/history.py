import asyncio
from collections import Counter
from datetime import datetime, timezone
import re
import statistics
import unicodedata
from typing import Any

import httpx

from .jolpica import JolpicaClient
from .openf1 import OpenF1Client
from .config import settings


OPENF1_LOCATION_ALIASES = {
    "catalunya": "Barcelona",
    "hungaroring": "Budapest",
    "marina_bay": "Singapore",
    "red_bull_ring": "Spielberg",
    "rodriguez": "Mexico City",
    "interlagos": "São Paulo",
    "yas_marina": "Yas Marina",
    "losail": "Lusail",
    "miami": "Miami",
    "vegas": "Las Vegas",
    "americas": "Austin",
}


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode()
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


def driver_name(result: dict[str, Any]) -> str:
    driver = result["Driver"]
    return f"{driver['givenName']} {driver['familyName']}"


def parse_lap_time(value: str | None) -> float | None:
    if not value:
        return None
    parts = value.split(":")
    try:
        if len(parts) == 2:
            return round(int(parts[0]) * 60 + float(parts[1]), 3)
        return float(parts[0])
    except ValueError:
        return None


def leaderboard(counter: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [
        {"name": name, "value": value}
        for name, value in counter.most_common(limit)
    ]


def aggregate_jolpica(
    circuit: dict[str, Any],
    race_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    races: dict[tuple[str, str], dict[str, Any]] = {}
    for row in race_rows:
        key = (row["season"], row["round"])
        race = races.setdefault(key, {**row, "Results": []})
        race["Results"].extend(row.get("Results", []))

    ordered = sorted(
        races.values(), key=lambda race: (int(race["season"]), int(race["round"]))
    )
    wins: Counter[str] = Counter()
    constructor_wins: Counter[str] = Counter()
    podiums: Counter[str] = Counter()
    poles: Counter[str] = Counter()
    starters = classified = wins_from_pole = 0
    winner_grids: list[int] = []
    grid_distribution: Counter[str] = Counter()
    lap_records: list[dict[str, Any]] = []
    editions: list[dict[str, Any]] = []

    for race in ordered:
        results = sorted(
            race.get("Results", []), key=lambda item: int(item["position"])
        )
        if not results:
            continue
        starters += len(results)
        classified += sum(
            result["positionText"].isdigit()
            for result in results
        )
        winner = results[0]
        winner_label = driver_name(winner)
        constructor = winner["Constructor"]["name"]
        grid = int(winner["grid"])
        wins[winner_label] += 1
        constructor_wins[constructor] += 1
        winner_grids.append(grid)
        wins_from_pole += grid == 1
        grid_distribution[
            "Pit lane" if grid == 0 else "Pole" if grid == 1 else f"P{grid}"
        ] += 1

        for result in results[:3]:
            podiums[driver_name(result)] += 1
        for result in results:
            if result.get("grid") == "1":
                poles[driver_name(result)] += 1
            fastest = result.get("FastestLap", {})
            seconds = parse_lap_time(fastest.get("Time", {}).get("time"))
            if seconds is not None:
                lap_records.append(
                    {
                        "seconds": seconds,
                        "time": fastest["Time"]["time"],
                        "driver": driver_name(result),
                        "constructor": result["Constructor"]["name"],
                        "year": int(race["season"]),
                        "lap": int(fastest.get("lap", 0)),
                        "average_speed": float(
                            fastest.get("AverageSpeed", {}).get("speed", 0)
                        ),
                    }
                )

        pole = next(
            (driver_name(result) for result in results if result["grid"] == "1"),
            None,
        )
        fastest_candidates = [
            (seconds, result)
            for result in results
            if (
                seconds := parse_lap_time(
                    result.get("FastestLap", {}).get("Time", {}).get("time")
                )
            )
            is not None
        ]
        fastest_result = min(
            fastest_candidates,
            key=lambda item: item[0],
            default=(None, None),
        )
        dnfs = sum(
            not result["positionText"].isdigit()
            for result in results
        )
        editions.append(
            {
                "year": int(race["season"]),
                "date": race["date"],
                "race_name": race["raceName"],
                "winner": winner_label,
                "constructor": constructor,
                "grid": grid,
                "pole": pole,
                "fastest_lap_driver": (
                    driver_name(fastest_result[1])
                    if fastest_result[1] is not None
                    else None
                ),
                "fastest_lap": (
                    fastest_result[1]["FastestLap"]["Time"]["time"]
                    if fastest_result[1] is not None
                    else None
                ),
                "dnfs": dnfs,
                "starters": len(results),
            }
        )

    best_comebacks = sorted(
        (
            {
                "year": int(race["season"]),
                "driver": driver_name(winner),
                "grid": int(winner["grid"]),
            }
            for race in ordered
            if (winner := min(
                race.get("Results", []),
                key=lambda result: int(result["position"]),
                default=None,
            ))
            is not None
        ),
        key=lambda item: item["grid"],
        reverse=True,
    )[:5]
    lap_record = min(lap_records, key=lambda item: item["seconds"], default=None)
    edition_count = len(editions)

    return {
        "circuit": {
            "id": circuit["circuitId"],
            "name": circuit["circuitName"],
            "locality": circuit["Location"]["locality"],
            "country": circuit["Location"]["country"],
            "latitude": float(circuit["Location"]["lat"]),
            "longitude": float(circuit["Location"]["long"]),
            "url": circuit["url"],
        },
        "overview": {
            "editions": edition_count,
            "first_year": editions[0]["year"] if editions else None,
            "last_year": editions[-1]["year"] if editions else None,
            "unique_winners": len(wins),
            "unique_constructors": len(constructor_wins),
            "total_starters": starters,
            "completion_rate": round(classified / starters * 100, 1)
            if starters
            else None,
            "wins_from_pole": wins_from_pole,
            "wins_from_pole_rate": round(wins_from_pole / edition_count * 100, 1)
            if edition_count
            else None,
            "average_winner_grid": round(statistics.mean(winner_grids), 2)
            if winner_grids
            else None,
        },
        "records": {
            "lap": lap_record,
            "best_comebacks": best_comebacks,
        },
        "leaders": {
            "wins": leaderboard(wins),
            "constructor_wins": leaderboard(constructor_wins),
            "podiums": leaderboard(podiums),
            "poles": leaderboard(poles),
        },
        "winning_grid": [
            {"name": name, "value": value}
            for name, value in sorted(
                grid_distribution.items(),
                key=lambda item: (
                    0 if item[0] == "Pole" else 99 if item[0] == "Pit lane"
                    else int(item[0][1:])
                ),
            )
        ],
        "editions": list(reversed(editions)),
    }


def match_openf1_meetings(
    circuit: dict[str, Any],
    meetings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    alias = OPENF1_LOCATION_ALIASES.get(circuit["circuitId"])
    candidates = {
        normalize(circuit["Location"]["locality"]),
        normalize(circuit["circuitName"]),
        normalize(alias or ""),
    }
    candidates.discard("")
    return [
        meeting
        for meeting in meetings
        if normalize(meeting.get("location", "")) in candidates
        or normalize(meeting.get("circuit_short_name", "")) in candidates
    ]


async def aggregate_openf1(
    openf1: OpenF1Client,
    circuit: dict[str, Any],
    meetings: list[dict[str, Any]],
) -> dict[str, Any]:
    matched = match_openf1_meetings(circuit, meetings)
    if not matched:
        return {"available": False, "coverage": None}

    circuit_key = matched[-1]["circuit_key"]
    sessions = await openf1.get(
        "sessions",
        {"circuit_key": circuit_key, "session_type": "Race"},
        ttl=21600,
    )
    now = datetime.now(timezone.utc)
    sessions = [
        session
        for session in sessions
        if datetime.fromisoformat(session["date_end"]) < now
    ]

    async def session_data(session: dict[str, Any]) -> dict[str, Any]:
        key = session["session_key"]
        laps, pits, stints, overtakes, weather, drivers = await asyncio.gather(
            openf1.get("laps", {"session_key": key}, ttl=21600),
            openf1.get(
                "pit",
                {"session_key": key},
                ttl=21600,
                empty_on_not_found=True,
            ),
            openf1.get(
                "stints",
                {"session_key": key},
                ttl=21600,
                empty_on_not_found=True,
            ),
            openf1.get(
                "overtakes",
                {"session_key": key},
                ttl=21600,
                empty_on_not_found=True,
            ),
            openf1.get(
                "weather",
                {"session_key": key},
                ttl=21600,
                empty_on_not_found=True,
            ),
            openf1.get("drivers", {"session_key": key}, ttl=21600),
        )
        return {
            "session": session,
            "laps": laps,
            "pits": pits,
            "stints": stints,
            "overtakes": overtakes,
            "weather": weather,
            "drivers": drivers,
        }

    data = await asyncio.gather(*(session_data(session) for session in sessions))
    all_laps = [
        {
            **lap,
            "driver_name": next(
                (
                    driver["full_name"]
                    for driver in item["drivers"]
                    if driver["driver_number"] == lap["driver_number"]
                ),
                None,
            ),
        }
        for item in data
        for lap in item["laps"]
        if isinstance(lap.get("lap_duration"), (int, float))
        and not lap.get("is_pit_out_lap", False)
    ]
    all_pits = [
        {
            **pit,
            "year": item["session"]["year"],
            "driver_name": next(
                (
                    driver["full_name"]
                    for driver in item["drivers"]
                    if driver["driver_number"] == pit["driver_number"]
                ),
                None,
            ),
        }
        for item in data
        for pit in item["pits"]
        if isinstance(pit.get("pit_duration"), (int, float))
    ]
    compounds: Counter[str] = Counter(
        stint.get("compound", "UNKNOWN")
        for item in data
        for stint in item["stints"]
    )
    fastest_lap = min(
        all_laps, key=lambda lap: lap["lap_duration"], default=None
    )
    fastest_pit = min(
        all_pits, key=lambda pit: pit["pit_duration"], default=None
    )
    overtake_editions = [
        {
            "year": item["session"]["year"],
            "value": len(item["overtakes"]),
        }
        for item in data
    ]
    wet_years = [
        item["session"]["year"]
        for item in data
        if any(weather.get("rainfall", 0) for weather in item["weather"])
    ]

    return {
        "available": True,
        "coverage": {
            "from": min((session["year"] for session in sessions), default=None),
            "to": max((session["year"] for session in sessions), default=None),
            "races": len(sessions),
        },
        "fastest_lap": fastest_lap,
        "pit_stops": {
            "total": len(all_pits),
            "average_per_race": round(len(all_pits) / len(sessions), 1)
            if sessions
            else None,
            "average_duration": round(
                statistics.mean(pit["pit_duration"] for pit in all_pits), 3
            )
            if all_pits
            else None,
            "fastest": fastest_pit,
        },
        "compounds": leaderboard(compounds, limit=10),
        "overtakes": {
            "total": sum(item["value"] for item in overtake_editions),
            "average_per_race": round(
                statistics.mean(item["value"] for item in overtake_editions), 1
            )
            if overtake_editions
            else None,
            "by_year": overtake_editions,
        },
        "wet_races": sorted(set(wet_years)),
    }


async def build_circuit_history(
    circuit_id: str,
    jolpica: JolpicaClient,
    openf1: OpenF1Client,
) -> dict[str, Any]:
    circuits = await jolpica.circuits()
    circuit = next(
        (item for item in circuits if item["circuitId"] == circuit_id),
        None,
    )
    if circuit is None:
        raise ValueError("Circuito non trovato")

    historical_reason = None
    try:
        race_rows = await jolpica.circuit_results(circuit_id)
    except httpx.HTTPError:
        race_rows = []
        historical_reason = "Risultati storici Jolpica non disponibili"
    if not race_rows and historical_reason is None:
        historical_reason = "Nessuna edizione storica Jolpica per questo circuito"

    history = aggregate_jolpica(circuit, race_rows)
    history["data_status"] = {
        "historical_available": historical_reason is None,
        "historical_reason": historical_reason,
    }
    meetings: list[dict[str, Any]] = []
    if not settings.enable_openf1_history:
        history["openf1"] = {
            "available": False,
            "coverage": None,
            "reason": "Integrazione OpenF1 disattivata",
        }
    else:
        try:
            meetings = await openf1.get("meetings", ttl=21600)
            history["openf1"] = await aggregate_openf1(
                openf1, circuit, meetings
            )
        except httpx.HTTPError:
            history["openf1"] = {
                "available": False,
                "coverage": None,
                "reason": "OpenF1 non disponibile",
            }

    matched = match_openf1_meetings(circuit, meetings)
    history["circuit"]["image"] = (
        matched[-1].get("circuit_image") if matched else None
    )
    return history
