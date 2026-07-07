from __future__ import annotations

import pandas as pd

from epl_betting_lab.models.calibration import (
    ShrinkageConfig,
    calibrate_probability,
    historical_baseline,
    min_calibrated_edge,
    shrinkage_weight,
)


def test_calibration_shrinks_toward_market() -> None:
    result = calibrate_probability(0.75, "1x2", "home", american_odds=100)
    assert result["raw_model_prob"] == 0.75
    assert result["calibrated_model_prob"] < 0.75
    assert result["calibrated_model_prob"] > 0.50
    assert result["calibration_target_source"] == "market implied probability"


def test_problem_spots_get_stronger_shrinkage() -> None:
    normal = shrinkage_weight(0.55, "1x2", "home", american_odds=-120)
    away_plus_money = shrinkage_weight(0.75, "1x2", "away", american_odds=220)
    assert away_plus_money > normal


def test_total_under_gets_stronger_market_specific_shrinkage() -> None:
    config = ShrinkageConfig()
    total_over = shrinkage_weight(0.50, "total_2_5", "over", american_odds=120, config=config)
    total_under = shrinkage_weight(0.50, "total_2_5", "under", american_odds=120, config=config)
    assert total_under > total_over


def test_market_specific_min_edges_are_configurable() -> None:
    config = ShrinkageConfig()
    assert min_calibrated_edge("1x2", "home", 0.035, config) == 0.035
    assert min_calibrated_edge("total_2_5", "over", 0.035, config) == 0.06
    assert min_calibrated_edge("total_2_5", "under", 0.035, config) == 0.08
    assert min_calibrated_edge("btts", "yes", 0.035, config) == 0.045


def test_historical_baseline_for_total_over() -> None:
    matches = pd.DataFrame({
        "home_goals": [2, 1, 0, 3],
        "away_goals": [1, 0, 0, 2],
    })
    assert historical_baseline(matches, "total_2_5", "over") == 0.5
