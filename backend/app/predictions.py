import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import math
import statistics
from typing import Any

import httpx

from .config import settings
from .jolpica import JolpicaClient
from .telemetry import FastF1Service, TelemetryUnavailable
from .upgrades import (
    load_team_upgrades,
    normalize_team_name,
    upgrade_records_for_round,
    upgrade_signals_by_round_team,
    upgrade_signals_for_round,
)
from .weather import WeatherClient


TRACK_PROFILES: dict[str, dict[str, float]] = {
    "albert_park": {"slow": 0.20, "medium": 0.45, "fast": 0.35, "straight": 0.65, "tyre": 0.50},
    "americas": {"slow": 0.30, "medium": 0.35, "fast": 0.35, "straight": 0.55, "tyre": 0.65},
    "bahrain": {"slow": 0.35, "medium": 0.40, "fast": 0.25, "straight": 0.70, "tyre": 0.80},
    "baku": {"slow": 0.45, "medium": 0.35, "fast": 0.20, "straight": 0.95, "tyre": 0.40},
    "catalunya": {"slow": 0.25, "medium": 0.40, "fast": 0.35, "straight": 0.45, "tyre": 0.80},
    "hungaroring": {"slow": 0.45, "medium": 0.45, "fast": 0.10, "straight": 0.25, "tyre": 0.60},
    "imola": {"slow": 0.20, "medium": 0.50, "fast": 0.30, "straight": 0.45, "tyre": 0.55},
    "interlagos": {"slow": 0.30, "medium": 0.45, "fast": 0.25, "straight": 0.65, "tyre": 0.55},
    "jeddah": {"slow": 0.10, "medium": 0.30, "fast": 0.60, "straight": 0.85, "tyre": 0.45},
    "las_vegas": {"slow": 0.50, "medium": 0.35, "fast": 0.15, "straight": 0.95, "tyre": 0.35},
    "losail": {"slow": 0.10, "medium": 0.30, "fast": 0.60, "straight": 0.55, "tyre": 0.90},
    "marina_bay": {"slow": 0.60, "medium": 0.35, "fast": 0.05, "straight": 0.35, "tyre": 0.50},
    "miami": {"slow": 0.40, "medium": 0.35, "fast": 0.25, "straight": 0.75, "tyre": 0.45},
    "monaco": {"slow": 0.75, "medium": 0.25, "fast": 0.00, "straight": 0.10, "tyre": 0.25},
    "monza": {"slow": 0.25, "medium": 0.25, "fast": 0.50, "straight": 1.00, "tyre": 0.35},
    "red_bull_ring": {"slow": 0.30, "medium": 0.30, "fast": 0.40, "straight": 0.80, "tyre": 0.55},
    "rodriguez": {"slow": 0.35, "medium": 0.40, "fast": 0.25, "straight": 0.75, "tyre": 0.50},
    "shanghai": {"slow": 0.35, "medium": 0.40, "fast": 0.25, "straight": 0.75, "tyre": 0.75},
    "silverstone": {"slow": 0.10, "medium": 0.25, "fast": 0.65, "straight": 0.70, "tyre": 0.80},
    "spa": {"slow": 0.10, "medium": 0.30, "fast": 0.60, "straight": 0.85, "tyre": 0.75},
    "suzuka": {"slow": 0.10, "medium": 0.35, "fast": 0.55, "straight": 0.55, "tyre": 0.85},
    "yas_marina": {"slow": 0.40, "medium": 0.40, "fast": 0.20, "straight": 0.75, "tyre": 0.55},
    "zandvoort": {"slow": 0.15, "medium": 0.45, "fast": 0.40, "straight": 0.30, "tyre": 0.75},
}

GENERIC_PROFILE = {
    "slow": 0.33,
    "medium": 0.34,
    "fast": 0.33,
    "straight": 0.50,
    "tyre": 0.50,
}

TECHNICAL_STATUS_TERMS = {
    "alternator",
    "battery",
    "brakes",
    "clutch",
    "differential",
    "driveshaft",
    "electrical",
    "electronics",
    "engine",
    "exhaust",
    "fuel",
    "gearbox",
    "hydraulics",
    "mechanical",
    "oil",
    "overheating",
    "power unit",
    "radiator",
    "suspension",
    "throttle",
    "transmission",
    "turbo",
    "water leak",
}

INCIDENT_STATUS_TERMS = {
    "accident",
    "collision",
    "spun off",
}

SPORTING_STATUS_TERMS = {
    "disqualified",
    "did not qualify",
    "did not prequalify",
    "excluded",
    "illness",
    "injured",
    "not classified",
    "withdrew",
}

# Jolpica reports only "Retired" for this result. Contemporary reporting
# identified a mechanical failure, so the generic status can be resolved.
RETIREMENT_OVERRIDES = {
    (2026, 7, "antonelli"): "technical",
    # Canada 2026: Mercedes reported Russell retired from the lead after a
    # catastrophic battery failure.
    (2026, 5, "russell"): "technical",
    # China 2026: Jolpica can expose a generic non-start, while reporting
    # identified separate McLaren power-unit/electrical failures before the
    # formation lap.
    (2026, 2, "norris"): "technical",
    (2026, 2, "piastri"): "technical",
}

WEIGHTS_WITH_TEMPERATURE = {
    "recent_form": 0.18,
    "clean_recent_form": 0.18,
    "team_strength": 0.16,
    "track_affinity": 0.20,
    "qualifying": 0.10,
    "teammate_delta": 0.06,
    "technical_reliability": 0.05,
    "driver_confidence": 0.03,
    "temperature_match": 0.04,
}

WEIGHTS_WITHOUT_TEMPERATURE = {
    "recent_form": 0.18,
    "clean_recent_form": 0.18,
    "team_strength": 0.16,
    "track_affinity": 0.23,
    "qualifying": 0.12,
    "teammate_delta": 0.05,
    "technical_reliability": 0.04,
    "driver_confidence": 0.04,
}

UPGRADE_WEIGHT = 0.06


def model_weights(has_temperature: bool, has_upgrades: bool) -> dict[str, float]:
    base = (
        WEIGHTS_WITH_TEMPERATURE
        if has_temperature
        else WEIGHTS_WITHOUT_TEMPERATURE
    )
    if not has_upgrades:
        return base
    scaled = {
        name: round(weight * (1 - UPGRADE_WEIGHT), 4)
        for name, weight in base.items()
    }
    scaled["upgrade_signal"] = UPGRADE_WEIGHT
    return scaled


def weighted_score(factors: dict[str, float], weights: dict[str, float]) -> float:
    return sum(factors[name] * weight for name, weight in weights.items())


def profile_for(circuit_id: str) -> dict[str, float]:
    return TRACK_PROFILES.get(circuit_id, GENERIC_PROFILE)


def profile_similarity(first: dict[str, float], second: dict[str, float]) -> float:
    distance = math.sqrt(
        sum((first[key] - second[key]) ** 2 for key in first)
    )
    return max(0.0, 1 - distance / math.sqrt(len(first)))


def normalize_scores(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if math.isclose(low, high):
        return {key: 50.0 for key in values}
    return {
        key: round((value - low) / (high - low) * 100, 1)
        for key, value in values.items()
    }


def parse_race_datetime(race: dict[str, Any]) -> datetime:
    time_value = race.get("time", "12:00:00Z").replace("Z", "+00:00")
    return datetime.fromisoformat(f"{race['date']}T{time_value}")


def classify_status(
    status: str,
    *,
    year: int,
    round_number: int,
    driver_id: str,
    position_text: str | None = None,
) -> str:
    normalized = status.strip().lower()
    classified = (position_text or "").strip().isdigit()
    if normalized == "finished" or normalized.startswith("+"):
        return "finished"
    if any(term in normalized for term in INCIDENT_STATUS_TERMS):
        return "incident"
    if any(term in normalized for term in TECHNICAL_STATUS_TERMS):
        return "technical"
    if any(term in normalized for term in SPORTING_STATUS_TERMS):
        return "sporting"
    override = RETIREMENT_OVERRIDES.get(
        (year, round_number, driver_id)
    )
    if override:
        return override
    if normalized == "lapped" and classified:
        return "finished"
    if normalized == "lapped" and position_text is None:
        return "finished"
    return "unknown"


def flatten_results(races: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for race in races:
        for result in race.get("Results", []):
            year = int(race["season"])
            round_number = int(race["round"])
            driver_id = result["Driver"]["driverId"]
            status = result.get("status", "")
            outcome = classify_status(
                status,
                year=year,
                round_number=round_number,
                driver_id=driver_id,
                position_text=result.get("positionText"),
            )
            rows.append(
                {
                    "year": year,
                    "round": round_number,
                    "circuit_id": race["Circuit"]["circuitId"],
                    "race_name": race["raceName"],
                    "driver_id": driver_id,
                    "driver": (
                        result["Driver"].get("code")
                        or result["Driver"]["familyName"][:3].upper()
                    ),
                    "full_name": (
                        f"{result['Driver']['givenName']} "
                        f"{result['Driver']['familyName']}"
                    ),
                    "team": result["Constructor"]["name"],
                    "position": int(result["position"])
                    if result["position"].isdigit()
                    else 20,
                    "grid": int(result["grid"]),
                    "points": float(result["points"]),
                    "status": status,
                    "outcome": outcome,
                }
            )
    return rows


def performance_score(row: dict[str, Any], points_weight: float = 0.35) -> float:
    return max(0, 21 - row["position"]) + row["points"] * points_weight


def clean_performance_score(
    row: dict[str, Any],
    points_weight: float = 0.35,
) -> float:
    if row["outcome"] in {"technical", "unknown"}:
        grid = row["grid"] or 20
        grid_proxy = max(0, 21 - grid) * 0.9
        return max(grid_proxy, performance_score(row, points_weight))
    return performance_score(row, points_weight)


def baseline_prediction(
    completed_races: list[dict[str, Any]],
    target_circuit_id: str,
    temperature_by_round: dict[int, float] | None = None,
    target_temperature: float | None = None,
    upgrade_by_team: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    rows = flatten_results(completed_races)
    if not rows:
        return []

    rounds = sorted({row["round"] for row in rows})
    recent_rounds = set(rounds[-5:])
    target_profile = profile_for(target_circuit_id)
    normalized_upgrades = {
        normalize_team_name(team): score
        for team, score in (upgrade_by_team or {}).items()
        if score > 0
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    team_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["driver_id"]].append(row)
        team_rows[row["team"]].append(row)

    raw_factors: dict[str, dict[str, float]] = {}
    metadata: dict[str, dict[str, str]] = {}
    evidence_by_driver: dict[str, dict[str, int]] = {}
    team_recent_strength_raw: dict[str, float] = {}
    for team, rows_for_team in team_rows.items():
        recent_team_rows = [
            row for row in rows_for_team if row["round"] in recent_rounds
        ] or rows_for_team
        team_recent_strength_raw[team] = statistics.mean(
            clean_performance_score(row) for row in recent_team_rows
        )
    for driver_id, driver_rows in grouped.items():
        latest = max(driver_rows, key=lambda row: row["round"])
        metadata[driver_id] = {
            "driver": latest["driver"],
            "full_name": latest["full_name"],
            "team": latest["team"],
        }
        recent = [row for row in driver_rows if row["round"] in recent_rounds]
        form = statistics.mean(
            performance_score(row)
            for row in recent
        )
        clean_form = statistics.mean(
            clean_performance_score(row)
            for row in recent
        )
        qualifying = statistics.mean(
            max(0, 21 - (row["grid"] or 20))
            for row in recent
        )
        current_team_rows = team_rows[latest["team"]]
        recent_teammates = [
            row
            for row in current_team_rows
            if row["round"] in recent_rounds
            and row["driver_id"] != driver_id
        ]
        teammate_delta = 0.0
        if recent_teammates:
            teammate_delta = clean_form - statistics.mean(
                clean_performance_score(row)
                for row in recent_teammates
            )
        technical_failures = sum(
            row["outcome"] == "technical" for row in current_team_rows
        )
        technical_reliability = (
            1 - technical_failures / len(current_team_rows)
        ) * 100
        incidents = sum(
            row["outcome"] == "incident" for row in driver_rows
        )
        incident_avoidance = (1 - incidents / len(driver_rows)) * 100
        unknown_retirements = sum(
            row["outcome"] == "unknown" for row in driver_rows
        )
        sporting_events = sum(
            row["outcome"] == "sporting" for row in driver_rows
        )
        confidence_events = incidents + sporting_events
        driver_confidence = (
            1 - confidence_events / len(driver_rows)
        ) * 100
        evidence_by_driver[driver_id] = {
            "technical_failures": technical_failures,
            "team_starts": len(current_team_rows),
            "incidents": incidents,
            "starts": len(driver_rows),
            "unknown_retirements": unknown_retirements,
            "sporting_events": sporting_events,
            "confidence_events": confidence_events,
        }
        affinity_rows = [
            (
                profile_similarity(
                    profile_for(row["circuit_id"]), target_profile
                ),
                clean_performance_score(row, points_weight=0.25),
            )
            for row in driver_rows
        ]
        similarity_total = sum(weight for weight, _ in affinity_rows)
        affinity = (
            sum(weight * performance for weight, performance in affinity_rows)
            / similarity_total
            if similarity_total
            else 0
        )
        factors = {
            "recent_form": form,
            "clean_recent_form": clean_form,
            "team_strength": team_recent_strength_raw[latest["team"]],
            "track_affinity": affinity,
            "qualifying": qualifying,
            "teammate_delta": teammate_delta,
            "technical_reliability": technical_reliability,
            "incident_avoidance": incident_avoidance,
            "driver_confidence": driver_confidence,
        }
        if normalized_upgrades:
            factors["upgrade_signal"] = normalized_upgrades.get(
                normalize_team_name(latest["team"]),
                0,
            )
        if temperature_by_round and target_temperature is not None:
            temperature_rows = [
                (
                    max(
                        0.05,
                        1
                        - abs(
                            temperature_by_round[row["round"]]
                            - target_temperature
                        )
                        / 20,
                    ),
                    max(0, 21 - row["position"]) + row["points"] * 0.25,
                )
                for row in driver_rows
                if row["round"] in temperature_by_round
            ]
            total = sum(weight for weight, _ in temperature_rows)
            if total:
                factors["temperature_match"] = sum(
                    weight * performance
                    for weight, performance in temperature_rows
                ) / total
        raw_factors[driver_id] = factors

    factor_names = [
        "recent_form",
        "clean_recent_form",
        "team_strength",
        "track_affinity",
        "qualifying",
        "teammate_delta",
    ]
    if any("temperature_match" in item for item in raw_factors.values()):
        factor_names.append("temperature_match")
    if normalized_upgrades:
        factor_names.append("upgrade_signal")
    normalized = {
        factor: normalize_scores(
            {
                driver_id: factors[factor]
                for driver_id, factors in raw_factors.items()
                if factor in factors
            }
        )
        for factor in factor_names
    }
    predictions = []
    for driver_id, info in metadata.items():
        factors = {
            "recent_form": normalized["recent_form"][driver_id],
            "clean_recent_form": normalized["clean_recent_form"][driver_id],
            "team_strength": normalized["team_strength"][driver_id],
            "track_affinity": normalized["track_affinity"][driver_id],
            "qualifying": normalized["qualifying"][driver_id],
            "teammate_delta": normalized["teammate_delta"][driver_id],
            "technical_reliability": raw_factors[driver_id][
                "technical_reliability"
            ],
            "incident_avoidance": raw_factors[driver_id]["incident_avoidance"],
            "driver_confidence": raw_factors[driver_id]["driver_confidence"],
        }
        if "upgrade_signal" in normalized:
            factors["upgrade_signal"] = normalized["upgrade_signal"].get(
                driver_id, 0
            )
        if "temperature_match" in normalized:
            factors["temperature_match"] = normalized[
                "temperature_match"
            ].get(driver_id, 50)
        weights = model_weights(
            "temperature_match" in factors,
            "upgrade_signal" in factors,
        )
        score = weighted_score(factors, weights)
        predictions.append(
            {
                **info,
                "driver_id": driver_id,
                "score": round(score, 1),
                "factors": {
                    **factors,
                    "technical_reliability": round(
                        raw_factors[driver_id]["technical_reliability"], 1
                    ),
                    "incident_avoidance": round(
                        raw_factors[driver_id]["incident_avoidance"], 1
                    ),
                    "driver_confidence": round(
                        raw_factors[driver_id]["driver_confidence"], 1
                    ),
                },
                "evidence": evidence_by_driver[driver_id],
            }
        )
    predictions.sort(key=lambda item: item["score"], reverse=True)
    for index, prediction in enumerate(predictions, start=1):
        prediction["rank"] = index
    return predictions


def apply_practice(
    baseline: list[dict[str, Any]],
    practice: dict[str, Any],
) -> list[dict[str, Any]]:
    practice_by_driver = {
        item["driver"]: item for item in practice["drivers"]
    }
    qualifying_raw = {
        item["driver"]: -item["qualifying_gap"]
        for item in practice["drivers"]
    }
    long_run_raw = {
        item["driver"]: -item["long_run_gap"]
        for item in practice["drivers"]
        if item["long_run_gap"] is not None
    }
    qualifying = normalize_scores(qualifying_raw)
    long_run = normalize_scores(long_run_raw)
    updated = []
    for item in baseline:
        fp = practice_by_driver.get(item["driver"])
        if fp is None:
            updated.append({**item, "practice": None})
            continue
        fp_score = (
            qualifying.get(item["driver"], 50) * 0.48
            + long_run.get(item["driver"], 50) * 0.42
            + min(fp["laps"] / 30 * 100, 100) * 0.10
        )
        updated.append(
            {
                **item,
                "score": round(item["score"] * 0.55 + fp_score * 0.45, 1),
                "practice": {
                    **fp,
                    "score": round(fp_score, 1),
                },
            }
        )
    updated.sort(key=lambda item: item["score"], reverse=True)
    for index, prediction in enumerate(updated, start=1):
        prediction["rank"] = index
    return updated


def apply_qualifying(
    baseline: list[dict[str, Any]],
    qualifying_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    qualifying_by_driver: dict[str, dict[str, Any]] = {}
    raw_scores: dict[str, float] = {}
    for row in qualifying_results:
        driver = row.get("Driver", {})
        code = driver.get("code") or driver.get("driverId")
        if not isinstance(code, str):
            continue
        try:
            position = int(row["position"])
        except (KeyError, TypeError, ValueError):
            continue
        code = code.upper()
        qualifying_by_driver[code] = {
            "position": position,
            "q1": row.get("Q1"),
            "q2": row.get("Q2"),
            "q3": row.get("Q3"),
        }
        raw_scores[code] = -position

    qualifying_scores = normalize_scores(raw_scores)
    updated = []
    for item in baseline:
        code = str(item["driver"]).upper()
        qualifying = qualifying_by_driver.get(code)
        if qualifying is None:
            updated.append({**item, "qualifying_result": None})
            continue
        qualifying_score = qualifying_scores.get(code, 50)
        updated.append(
            {
                **item,
                "score": round(item["score"] * 0.35 + qualifying_score * 0.65, 1),
                "qualifying_result": {
                    **qualifying,
                    "score": round(qualifying_score, 1),
                },
            }
        )
    updated.sort(key=lambda item: item["score"], reverse=True)
    for index, prediction in enumerate(updated, start=1):
        prediction["rank"] = index
    return updated


PREDICTION_FEATURES = [
    "score",
    "recent_form",
    "clean_recent_form",
    "team_strength",
    "track_affinity",
    "qualifying",
    "teammate_delta",
    "technical_reliability",
    "incident_avoidance",
    "driver_confidence",
    "temperature_match",
    "upgrade_signal",
]


def prediction_feature_rows(
    completed_races: list[dict[str, Any]],
    min_prior_races: int = 3,
    upgrade_by_round_team: dict[tuple[int, str], float] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    races = sorted(completed_races, key=lambda race: int(race["round"]))
    for race in races:
        round_number = int(race["round"])
        prior = [
            item
            for item in races
            if int(item["round"]) < round_number
        ]
        if len(prior) < min_prior_races:
            continue
        baseline = {
            item["driver_id"]: item
            for item in baseline_prediction(
                prior,
                race["Circuit"]["circuitId"],
                upgrade_by_team={
                    team: signal
                    for (round_key, team), signal in (
                        upgrade_by_round_team or {}
                    ).items()
                    if round_key == round_number
                },
            )
        }
        for result in flatten_results([race]):
            features = baseline.get(result["driver_id"])
            if features is None:
                continue
            factors = features.get("factors", {})
            rows.append(
                {
                    "year": result["year"],
                    "round": round_number,
                    "race_name": result["race_name"],
                    "circuit_id": result["circuit_id"],
                    "driver_id": result["driver_id"],
                    "driver": result["driver"],
                    "team": result["team"],
                    "features": {
                        "score": features["score"],
                        "recent_form": factors.get("recent_form"),
                        "clean_recent_form": factors.get("clean_recent_form"),
                        "team_strength": factors.get("team_strength"),
                        "track_affinity": factors.get("track_affinity"),
                        "qualifying": factors.get("qualifying"),
                        "teammate_delta": factors.get("teammate_delta"),
                        "technical_reliability": factors.get(
                            "technical_reliability"
                        ),
                        "incident_avoidance": factors.get(
                            "incident_avoidance"
                        ),
                        "driver_confidence": factors.get("driver_confidence"),
                        "temperature_match": factors.get("temperature_match"),
                        "upgrade_signal": factors.get("upgrade_signal"),
                    },
                    "target": {
                        "position": result["position"],
                        "points": result["points"],
                        "winner": result["position"] == 1,
                        "podium": result["position"] <= 3,
                        "top6": result["position"] <= 6,
                        "finished": result["outcome"] == "finished",
                    },
                }
            )
    return rows


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def feature_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics = []
    for feature in PREDICTION_FEATURES:
        podium_values = [
            float(row["features"][feature])
            for row in rows
            if row["features"].get(feature) is not None
            and row["target"]["podium"]
        ]
        non_podium_values = [
            float(row["features"][feature])
            for row in rows
            if row["features"].get(feature) is not None
            and not row["target"]["podium"]
        ]
        podium_mean = _mean(podium_values)
        non_podium_mean = _mean(non_podium_values)
        if podium_mean is None or non_podium_mean is None:
            continue
        diagnostics.append(
            {
                "feature": feature,
                "podium_mean": round(podium_mean, 2),
                "non_podium_mean": round(non_podium_mean, 2),
                "lift": round(podium_mean - non_podium_mean, 2),
                "coverage": len(podium_values) + len(non_podium_values),
            }
        )
    diagnostics.sort(key=lambda item: abs(item["lift"]), reverse=True)
    return {
        "target": "podium",
        "features": diagnostics,
        "note": (
            "Lift positivo significa che la feature e' mediamente piu' alta "
            "nei podi rispetto agli altri risultati. Non e' causalita'."
        ),
    }


def ml_readiness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    races = {(row["year"], row["round"]) for row in rows}
    drivers = {row["driver_id"] for row in rows}
    podiums = sum(row["target"]["podium"] for row in rows)
    usable = len(rows) >= 120 and len(races) >= 8 and podiums >= 24
    return {
        "usable_for_ml": usable,
        "examples": len(rows),
        "races": len(races),
        "drivers": len(drivers),
        "podium_examples": podiums,
        "recommended_next_step": (
            "train_lightweight_ranker"
            if usable
            else "collect_more_practice_and_race_examples"
        ),
        "warning": (
            "Dataset piccolo per ML robusto: meglio iniziare con ranking "
            "regolarizzato, backtest e feature audit."
        ),
    }


class PredictionService:
    def __init__(
        self,
        jolpica: JolpicaClient,
        telemetry: FastF1Service,
        weather: WeatherClient,
    ) -> None:
        self.jolpica = jolpica
        self.telemetry = telemetry
        self.weather = weather

    async def next_race(
        self,
        year: int,
        include_practice: bool = True,
    ) -> dict[str, Any]:
        schedule, result_races = await self._load_season(year)
        now = datetime.now(timezone.utc)
        next_race = next(
            (
                race
                for race in schedule
                if parse_race_datetime(race) > now
            ),
            None,
        )
        if next_race is None:
            raise ValueError("Nessuna gara futura nel calendario selezionato")

        next_round = int(next_race["round"])
        completed = [
            race
            for race in result_races
            if int(race["round"]) < next_round
        ]
        upgrade_records = load_team_upgrades(settings.prediction_upgrades_file)
        upgrade_signals = upgrade_signals_for_round(
            upgrade_records,
            year,
            next_round,
        )
        circuit = next_race["Circuit"]
        location = circuit["Location"]
        try:
            forecast = await self.weather.forecast(
                float(location["lat"]),
                float(location["long"]),
                date.fromisoformat(next_race["date"]),
            )
        except httpx.HTTPError:
            forecast = {
                "available": False,
                "reason": "Servizio meteo non raggiungibile",
            }

        target_temperature = None
        temperatures: dict[int, float] = {}
        if forecast.get("available"):
            target_temperature = (
                float(forecast["temperature_min"])
                + float(forecast["temperature_max"])
            ) / 2
            historical = await asyncio.gather(
                *(
                    self.weather.historical_temperature(
                        float(race["Circuit"]["Location"]["lat"]),
                        float(race["Circuit"]["Location"]["long"]),
                        date.fromisoformat(race["date"]),
                    )
                    for race in schedule
                    if int(race["round"]) < next_round
                ),
                return_exceptions=True,
            )
            previous_schedule = [
                race
                for race in schedule
                if int(race["round"]) < next_round
            ]
            for race, value in zip(previous_schedule, historical):
                if isinstance(value, (int, float)):
                    temperatures[int(race["round"])] = float(value)

        predictions = baseline_prediction(
            completed,
            circuit["circuitId"],
            temperatures,
            target_temperature,
            upgrade_signals,
        )
        phase = "baseline"
        practice_status = "Non richiesta"
        practice = None
        practice_window_open = now >= (
            parse_race_datetime(next_race).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            - timedelta(days=3)
        )
        if include_practice and practice_window_open:
            try:
                practice = await self.telemetry.practice_metrics(
                    year, next_round
                )
                predictions = apply_practice(predictions, practice)
                phase = "post_practice"
                practice_status = (
                    f"Aggiornata con {', '.join(practice['sessions'])}"
                )
            except TelemetryUnavailable as exc:
                practice_status = str(exc)
        elif include_practice:
            practice_status = "Weekend non ancora iniziato"

        qualifying_results = []
        if include_practice and practice_window_open:
            try:
                qualifying_results = await self.jolpica.qualifying_results(
                    year,
                    next_round,
                )
            except (KeyError, httpx.HTTPError):
                qualifying_results = []
            if qualifying_results:
                predictions = apply_qualifying(predictions, qualifying_results)
                phase = "post_qualifying"
                practice_status = (
                    f"{practice_status} · Qualifica aggiornata"
                    if practice_status
                    else "Qualifica aggiornata"
                )

        confidence = min(85, 40 + len(completed) * 4)
        if phase == "post_practice":
            confidence = min(92, confidence + 12)
        if phase == "post_qualifying":
            confidence = min(95, confidence + 18)
        if forecast.get("available") and forecast.get(
            "rain_probability", 0
        ) >= 50:
            confidence = max(25, confidence - 10)

        upgrade_validation = None
        if phase in {"post_practice", "post_qualifying"} and practice and upgrade_signals:
            validation_by_team: dict[str, list[float]] = defaultdict(list)
            for prediction in predictions:
                if prediction.get("practice") is None:
                    continue
                team_key = normalize_team_name(prediction["team"])
                if team_key in upgrade_signals:
                    validation_by_team[prediction["team"]].append(
                        prediction["practice"]["score"]
                    )
            upgrade_validation = [
                {
                    "team": team,
                    "practice_score": round(statistics.mean(scores), 1),
                    "drivers": len(scores),
                }
                for team, scores in validation_by_team.items()
            ]

        return {
            "race": {
                "year": year,
                "round": next_round,
                "name": next_race["raceName"],
                "date": next_race["date"],
                "time": next_race.get("time"),
                "circuit_id": circuit["circuitId"],
                "circuit_name": circuit["circuitName"],
                "locality": location["locality"],
                "country": location["country"],
            },
            "phase": phase,
            "practice_status": practice_status,
            "confidence": confidence,
            "completed_races": len(completed),
            "track_profile": profile_for(circuit["circuitId"]),
            "weather": forecast,
            "weights": (
                {
                    "baseline/practice": 0.35,
                    "qualifying": 0.65,
                }
                if phase == "post_qualifying"
                else
                {
                    "baseline": 0.55,
                    "free_practice": 0.45,
                }
                if phase == "post_practice"
                else model_weights(bool(temperatures), bool(upgrade_signals))
            ),
            "upgrades": {
                "available": bool(upgrade_signals),
                "source": settings.prediction_upgrades_file,
                "records": upgrade_records_for_round(
                    upgrade_records,
                    year,
                    next_round,
                ),
                "signals": upgrade_signals,
                "validation": upgrade_validation,
                "note": (
                    "Segnale manuale e pre-weekend: serve a separare "
                    "l'ipotesi sul pacchetto tecnico dalla conferma delle FP."
                ),
            },
            "predictions": predictions,
            "disclaimer": (
                "Ranking comparativo, non probabilità di vittoria. "
                "Incidenti, sviluppi tecnici e strategie non osservabili "
                "possono cambiare il risultato."
            ),
        }

    async def feature_dataset(
        self,
        year: int,
        min_prior_races: int = 3,
        include_rows: bool = False,
        limit: int = 200,
    ) -> dict[str, Any]:
        schedule, result_races = await self._load_season(year)
        completed_rounds = {int(race["round"]) for race in result_races}
        upgrade_records = load_team_upgrades(settings.prediction_upgrades_file)
        rows = prediction_feature_rows(
            result_races,
            min_prior_races,
            upgrade_signals_by_round_team(upgrade_records),
        )
        payload = {
            "year": year,
            "min_prior_races": min_prior_races,
            "completed_races": len(completed_rounds),
            "examples": len(rows),
            "features": PREDICTION_FEATURES,
            "upgrade_records": len(upgrade_records),
            "diagnostics": feature_diagnostics(rows),
            "ml_readiness": ml_readiness(rows),
            "disclaimer": (
                "Dataset derivato solo da informazioni disponibili prima "
                "della gara target. FP e qualifica saranno aggiunte come "
                "feature incrementali quando disponibili."
            ),
            "schedule_size": len(schedule),
        }
        if include_rows:
            payload["rows"] = rows[:limit]
            payload["row_limit"] = limit
        return payload

    async def _load_season(
        self, year: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return await asyncio.gather(
            self.jolpica.season_schedule(year),
            self.jolpica.season_results(year),
        )
