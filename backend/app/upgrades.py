import json
from pathlib import Path
from typing import Any


def normalize_team_name(team: str) -> str:
    return " ".join(team.strip().lower().split())


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def upgrade_signal(record: dict[str, Any]) -> float:
    magnitude = float(record.get("magnitude", 1))
    confidence = float(record.get("confidence", 1))
    return clamp((magnitude / 3) * 100 * confidence)


def load_team_upgrades(path: str | Path) -> list[dict[str, Any]]:
    upgrade_path = Path(path)
    if not upgrade_path.exists():
        return []
    data = json.loads(upgrade_path.read_text())
    records = data.get("upgrades", data) if isinstance(data, dict) else data
    if not isinstance(records, list):
        raise ValueError(
            "Il file upgrade deve contenere una lista o {upgrades: [...]}"
        )

    normalized = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if "year" not in record or "round" not in record or "team" not in record:
            continue
        normalized.append(
            {
                **record,
                "year": int(record["year"]),
                "round": int(record["round"]),
                "team": str(record["team"]),
                "team_key": normalize_team_name(str(record["team"])),
                "signal": round(upgrade_signal(record), 1),
            }
        )
    return normalized


def upgrade_signals_for_round(
    records: list[dict[str, Any]],
    year: int,
    round_number: int,
) -> dict[str, float]:
    signals: dict[str, float] = {}
    for record in records:
        if record["year"] != year or record["round"] != round_number:
            continue
        team_key = record["team_key"]
        signals[team_key] = clamp(signals.get(team_key, 0) + record["signal"])
    return {team: round(signal, 1) for team, signal in signals.items()}


def upgrade_records_for_round(
    records: list[dict[str, Any]],
    year: int,
    round_number: int,
) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in record.items()
            if key != "team_key"
        }
        for record in records
        if record["year"] == year and record["round"] == round_number
    ]


def upgrade_signals_by_round_team(
    records: list[dict[str, Any]],
) -> dict[tuple[int, str], float]:
    signals: dict[tuple[int, str], float] = {}
    for record in records:
        key = (record["round"], record["team_key"])
        signals[key] = clamp(signals.get(key, 0) + record["signal"])
    return {key: round(signal, 1) for key, signal in signals.items()}
