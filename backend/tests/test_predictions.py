from app.predictions import (
    apply_qualifying,
    apply_practice,
    baseline_prediction,
    classify_status,
    feature_diagnostics,
    ml_readiness,
    normalize_scores,
    prediction_feature_rows,
    profile_for,
    profile_similarity,
)


def race(round_number, circuit, results, season=2025):
    return {
        "season": str(season),
        "round": str(round_number),
        "raceName": f"Race {round_number}",
        "Circuit": {"circuitId": circuit},
        "Results": results,
    }


def result(
    driver_id,
    code,
    team,
    position,
    grid,
    points,
    finished=True,
    status=None,
):
    return {
        "position": str(position),
        "positionText": str(position) if finished else "R",
        "status": status or ("Finished" if finished else "Retired"),
        "grid": str(grid),
        "points": str(points),
        "Driver": {
            "driverId": driver_id,
            "code": code,
            "givenName": code,
            "familyName": driver_id,
        },
        "Constructor": {"name": team},
    }


def test_profile_similarity_is_highest_for_same_track():
    monza = profile_for("monza")
    assert profile_similarity(monza, monza) == 1
    assert profile_similarity(monza, profile_for("monaco")) < 0.7


def test_normalize_scores_handles_equal_values():
    assert normalize_scores({"a": 3, "b": 3}) == {"a": 50.0, "b": 50.0}


def test_baseline_rewards_form_and_similar_track_performance():
    races = [
        race(
            1,
            "monza",
            [
                result("fast", "FST", "Red", 1, 1, 25),
                result("slow", "SLW", "Blue", 5, 6, 10),
            ],
        ),
        race(
            2,
            "spa",
            [
                result("fast", "FST", "Red", 2, 2, 18),
                result("slow", "SLW", "Blue", 6, 7, 8),
            ],
        ),
    ]
    prediction = baseline_prediction(races, "silverstone")
    assert prediction[0]["driver"] == "FST"
    assert prediction[0]["score"] > prediction[1]["score"]


def test_baseline_includes_temperature_when_available():
    races = [
        race(
            1,
            "bahrain",
            [
                result("hot", "HOT", "Red", 1, 1, 25),
                result("cold", "CLD", "Blue", 5, 5, 10),
            ],
        ),
        race(
            2,
            "silverstone",
            [
                result("hot", "HOT", "Red", 5, 5, 10),
                result("cold", "CLD", "Blue", 1, 1, 25),
            ],
        ),
    ]
    prediction = baseline_prediction(
        races,
        "bahrain",
        temperature_by_round={1: 31.0, 2: 15.0},
        target_temperature=30.0,
    )
    assert "temperature_match" in prediction[0]["factors"]


def test_practice_can_update_order():
    baseline = [
        {
            "driver": "AAA",
            "full_name": "A Driver",
            "team": "A",
            "driver_id": "a",
            "score": 60,
            "factors": {},
            "rank": 1,
        },
        {
            "driver": "BBB",
            "full_name": "B Driver",
            "team": "B",
            "driver_id": "b",
            "score": 58,
            "factors": {},
            "rank": 2,
        },
    ]
    practice = {
        "drivers": [
            {
                "driver": "AAA",
                "team": "A",
                "qualifying_gap": 1.0,
                "long_run_gap": 1.0,
                "laps": 10,
            },
            {
                "driver": "BBB",
                "team": "B",
                "qualifying_gap": 0.0,
                "long_run_gap": 0.0,
                "laps": 30,
            },
        ]
    }
    updated = apply_practice(baseline, practice)
    assert updated[0]["driver"] == "BBB"
    assert updated[0]["practice"]["score"] > updated[1]["practice"]["score"]


def test_qualifying_results_can_update_order():
    baseline = [
        {
            "driver": "AAA",
            "full_name": "A Driver",
            "team": "A",
            "driver_id": "a",
            "score": 80,
            "factors": {},
            "rank": 1,
        },
        {
            "driver": "BBB",
            "full_name": "B Driver",
            "team": "B",
            "driver_id": "b",
            "score": 50,
            "factors": {},
            "rank": 2,
        },
    ]
    qualifying = [
        {
            "position": "10",
            "Driver": {"code": "AAA"},
            "Q1": "1:05.000",
            "Q2": "1:04.500",
        },
        {
            "position": "1",
            "Driver": {"code": "BBB"},
            "Q1": "1:04.000",
            "Q2": "1:03.700",
            "Q3": "1:03.300",
        },
    ]

    updated = apply_qualifying(baseline, qualifying)

    assert updated[0]["driver"] == "BBB"
    assert updated[0]["rank"] == 1
    assert updated[0]["qualifying_result"]["position"] == 1
    assert updated[0]["qualifying_result"]["q3"] == "1:03.300"


def test_status_classification_separates_retirement_causes():
    context = {"year": 2025, "round_number": 1, "driver_id": "driver"}

    assert classify_status("Engine", **context) == "technical"
    assert classify_status("Collision", **context) == "incident"
    assert classify_status("Disqualified", **context) == "sporting"
    assert classify_status("Retired", **context) == "unknown"
    assert classify_status("Lapped", **context, position_text="12") == "finished"
    assert classify_status("Lapped", **context, position_text="R") == "unknown"


def test_technical_failure_reduces_team_reliability_for_both_drivers():
    races = [
        race(
            1,
            "monza",
            [
                result("first", "FST", "Team", 1, 1, 25),
                result("second", "SND", "Team", 2, 2, 18),
            ],
        ),
        race(
            2,
            "catalunya",
            [
                result(
                    "first",
                    "FST",
                    "Team",
                    16,
                    3,
                    0,
                    finished=False,
                    status="Engine",
                ),
                result("second", "SND", "Team", 3, 2, 15),
            ],
        ),
    ]

    prediction = {
        item["driver_id"]: item
        for item in baseline_prediction(races, "red_bull_ring")
    }

    assert prediction["first"]["factors"]["technical_reliability"] == 75.0
    assert prediction["second"]["factors"]["technical_reliability"] == 75.0
    assert prediction["first"]["evidence"]["technical_failures"] == 1
    assert prediction["second"]["evidence"]["team_starts"] == 4


def test_technical_reliability_uses_raw_percent_not_minmax_score():
    races = [
        race(
            1,
            "monza",
            [
                result("risk", "RSK", "Risk", 1, 1, 25),
                result("clean", "CLN", "Clean", 1, 1, 25),
            ],
        ),
        race(
            2,
            "spa",
            [
                result(
                    "risk",
                    "RSK",
                    "Risk",
                    1,
                    1,
                    25,
                    finished=False,
                    status="Engine",
                ),
                result("clean", "CLN", "Clean", 1, 1, 25),
            ],
        ),
    ]

    prediction = {
        item["driver_id"]: item
        for item in baseline_prediction(races, "silverstone")
    }

    assert prediction["risk"]["factors"]["technical_reliability"] == 50.0
    assert prediction["clean"]["factors"]["technical_reliability"] == 100.0
    assert prediction["clean"]["score"] - prediction["risk"]["score"] == 2.0


def test_clean_form_protects_driver_from_technical_retirement_noise():
    races = [
        race(
            1,
            "monza",
            [
                result("fast", "FST", "Red", 1, 1, 25),
                result("steady", "STD", "Blue", 4, 4, 12),
            ],
        ),
        race(
            2,
            "spa",
            [
                result(
                    "fast",
                    "FST",
                    "Red",
                    16,
                    2,
                    0,
                    finished=False,
                    status="Engine",
                ),
                result("steady", "STD", "Blue", 3, 3, 15),
            ],
        ),
    ]

    prediction = {
        item["driver_id"]: item
        for item in baseline_prediction(races, "silverstone")
    }

    assert prediction["fast"]["factors"]["clean_recent_form"] > prediction[
        "fast"
    ]["factors"]["recent_form"]
    assert prediction["fast"]["factors"]["technical_reliability"] < 100


def test_team_strength_rewards_current_car_package():
    races = [
        race(
            1,
            "monza",
            [
                result("first_red", "FRD", "Red", 1, 1, 25),
                result("second_red", "SRD", "Red", 2, 2, 18),
                result("first_blue", "FBL", "Blue", 7, 7, 6),
                result("second_blue", "SBL", "Blue", 8, 8, 4),
            ],
        ),
        race(
            2,
            "spa",
            [
                result("first_red", "FRD", "Red", 2, 2, 18),
                result("second_red", "SRD", "Red", 3, 3, 15),
                result("first_blue", "FBL", "Blue", 6, 6, 8),
                result("second_blue", "SBL", "Blue", 9, 9, 2),
            ],
        ),
    ]

    prediction = {
        item["driver_id"]: item
        for item in baseline_prediction(races, "silverstone")
    }

    assert prediction["first_red"]["factors"]["team_strength"] > prediction[
        "first_blue"
    ]["factors"]["team_strength"]


def test_upgrade_signal_rewards_declared_package():
    races = [
        race(
            1,
            "monza",
            [
                result("first_red", "FRD", "Red", 2, 2, 18),
                result("first_blue", "FBL", "Blue", 2, 2, 18),
            ],
        ),
        race(
            2,
            "spa",
            [
                result("first_red", "FRD", "Red", 3, 3, 15),
                result("first_blue", "FBL", "Blue", 3, 3, 15),
            ],
        ),
    ]

    baseline = {
        item["driver_id"]: item
        for item in baseline_prediction(races, "silverstone")
    }
    upgraded = {
        item["driver_id"]: item
        for item in baseline_prediction(
            races,
            "silverstone",
            upgrade_by_team={"Red": 80},
        )
    }

    assert "upgrade_signal" not in baseline["first_red"]["factors"]
    assert upgraded["first_red"]["factors"]["upgrade_signal"] == 100.0
    assert upgraded["first_blue"]["factors"]["upgrade_signal"] == 0.0
    assert upgraded["first_red"]["score"] > baseline["first_red"]["score"]


def test_incident_only_reduces_driver_incident_avoidance():
    races = [
        race(
            1,
            "monza",
            [
                result(
                    "first",
                    "FST",
                    "Team",
                    20,
                    1,
                    0,
                    finished=False,
                    status="Collision",
                ),
                result("second", "SND", "Team", 2, 2, 18),
            ],
        )
    ]

    prediction = {
        item["driver_id"]: item
        for item in baseline_prediction(races, "red_bull_ring")
    }

    assert prediction["first"]["factors"]["technical_reliability"] == 100.0
    assert prediction["first"]["factors"]["incident_avoidance"] == 0.0
    assert prediction["second"]["factors"]["incident_avoidance"] == 100.0


def test_unknown_retirement_is_reported_but_does_not_invent_a_cause():
    races = [
        race(
            1,
            "catalunya",
            [
                result(
                    "driver",
                    "DRV",
                    "Team",
                    16,
                    3,
                    0,
                    finished=False,
                    status="Retired",
                )
            ],
        )
    ]

    prediction = baseline_prediction(races, "red_bull_ring")[0]

    assert prediction["factors"]["technical_reliability"] == 100.0
    assert prediction["factors"]["incident_avoidance"] == 100.0
    assert prediction["evidence"]["unknown_retirements"] == 1


def test_lapped_classified_finish_is_not_unknown_retirement():
    races = [
        race(
            1,
            "catalunya",
            [
                {
                    **result("driver", "DRV", "Team", 12, 3, 0),
                    "status": "Lapped",
                    "positionText": "12",
                }
            ],
        )
    ]

    prediction = baseline_prediction(races, "red_bull_ring")[0]

    assert prediction["evidence"]["unknown_retirements"] == 0


def test_antonelli_barcelona_2026_override_is_technical():
    assert classify_status(
        "Retired",
        year=2026,
        round_number=7,
        driver_id="antonelli",
        position_text="16",
    ) == "technical"
    assert classify_status(
        "Finished",
        year=2026,
        round_number=7,
        driver_id="antonelli",
    ) == "finished"


def test_russell_canada_2026_override_is_technical():
    assert classify_status(
        "Retired",
        year=2026,
        round_number=5,
        driver_id="russell",
        position_text="R",
    ) == "technical"


def test_retired_with_numeric_position_is_not_finished_without_override():
    assert classify_status(
        "Retired",
        year=2026,
        round_number=5,
        driver_id="other",
        position_text="16",
    ) == "unknown"


def test_piastri_china_2026_non_start_override_is_technical():
    assert classify_status(
        "Did not start",
        year=2026,
        round_number=2,
        driver_id="piastri",
    ) == "technical"


def test_prediction_feature_rows_use_only_prior_races():
    races = [
        race(
            1,
            "monza",
            [
                result("fast", "FST", "Red", 1, 1, 25),
                result("slow", "SLW", "Blue", 8, 8, 4),
            ],
        ),
        race(
            2,
            "spa",
            [
                result("fast", "FST", "Red", 2, 2, 18),
                result("slow", "SLW", "Blue", 7, 7, 6),
            ],
        ),
        race(
            3,
            "silverstone",
            [
                result("fast", "FST", "Red", 3, 3, 15),
                result("slow", "SLW", "Blue", 6, 6, 8),
            ],
        ),
        race(
            4,
            "monza",
            [
                result("fast", "FST", "Red", 1, 1, 25),
                result("slow", "SLW", "Blue", 10, 10, 1),
            ],
        ),
    ]

    rows = prediction_feature_rows(races, min_prior_races=3)

    assert len(rows) == 2
    assert {row["round"] for row in rows} == {4}
    fast = next(row for row in rows if row["driver_id"] == "fast")
    assert fast["target"]["winner"] is True
    assert fast["features"]["score"] > 0


def test_prediction_feature_rows_include_upgrade_signal():
    races = [
        race(
            1,
            "monza",
            [
                result("fast", "FST", "Red", 1, 1, 25),
                result("slow", "SLW", "Blue", 8, 8, 4),
            ],
        ),
        race(
            2,
            "spa",
            [
                result("fast", "FST", "Red", 2, 2, 18),
                result("slow", "SLW", "Blue", 7, 7, 6),
            ],
        ),
        race(
            3,
            "silverstone",
            [
                result("fast", "FST", "Red", 3, 3, 15),
                result("slow", "SLW", "Blue", 6, 6, 8),
            ],
        ),
        race(
            4,
            "monza",
            [
                result("fast", "FST", "Red", 1, 1, 25),
                result("slow", "SLW", "Blue", 10, 10, 1),
            ],
        ),
    ]

    rows = prediction_feature_rows(
        races,
        min_prior_races=3,
        upgrade_by_round_team={(4, "red"): 80},
    )

    fast = next(row for row in rows if row["driver_id"] == "fast")
    slow = next(row for row in rows if row["driver_id"] == "slow")
    assert fast["features"]["upgrade_signal"] == 100.0
    assert slow["features"]["upgrade_signal"] == 0.0


def test_feature_diagnostics_reports_lift_for_podium_target():
    rows = [
        {
            "features": {"score": 90, "recent_form": 80},
            "target": {"podium": True},
        },
        {
            "features": {"score": 30, "recent_form": 20},
            "target": {"podium": False},
        },
    ]

    diagnostics = feature_diagnostics(rows)

    assert diagnostics["target"] == "podium"
    assert diagnostics["features"][0]["lift"] > 0


def test_ml_readiness_requires_enough_examples():
    rows = [
        {
            "year": 2026,
            "round": index // 20,
            "driver_id": f"driver-{index % 20}",
            "target": {"podium": index % 20 < 3},
        }
        for index in range(40)
    ]

    readiness = ml_readiness(rows)

    assert readiness["usable_for_ml"] is False
    assert readiness["examples"] == 40
    assert readiness["recommended_next_step"] == "collect_more_practice_and_race_examples"
