from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.backtest_calibration import (
    probability_bucket,
    save_market_specific_comparison,
    save_backtest_calibration_reports,
    summarize_calibration,
)


def _sample_bets() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": "2025-08-16",
            "season": "2526",
            "home_team": "Arsenal",
            "away_team": "Everton",
            "score": "2-0",
            "market": "1x2",
            "selection": "home",
            "decimal_odds": 1.8,
            "american_odds": -125,
            "raw_model_prob": 0.62,
            "calibrated_model_prob": 0.58,
            "model_prob": 0.58,
            "book_implied": 0.556,
            "raw_edge": 0.064,
            "calibrated_edge": 0.024,
            "edge": 0.024,
            "ev_per_unit": 0.116,
            "calibration_weight": 0.2,
            "status": "BETTABLE",
            "calibrated_would_bet": True,
            "won": True,
            "calibrated_profit_units": 0.8,
            "profit_units": 0.8,
        },
        {
            "date": "2025-08-17",
            "season": "2526",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "score": "0-1",
            "market": "total_2_5",
            "selection": "over",
            "decimal_odds": 2.2,
            "american_odds": 120,
            "raw_model_prob": 0.48,
            "calibrated_model_prob": 0.47,
            "model_prob": 0.47,
            "book_implied": 0.455,
            "raw_edge": 0.045,
            "calibrated_edge": 0.015,
            "edge": 0.015,
            "ev_per_unit": 0.1,
            "calibration_weight": 0.3,
            "status": "BETTABLE",
            "calibrated_would_bet": True,
            "won": False,
            "calibrated_profit_units": -1.0,
            "profit_units": -1.0,
        },
    ])


def test_probability_bucket_labels() -> None:
    assert probability_bucket(0.39) == "under 40%"
    assert probability_bucket(0.45) == "40% to 50%"
    assert probability_bucket(0.55) == "50% to 60%"
    assert probability_bucket(0.65) == "60% to 70%"
    assert probability_bucket(0.75) == "70% or higher"


def test_summarize_calibration_gap() -> None:
    summary = summarize_calibration(_sample_bets(), ["probability_bucket"])
    row = summary[summary["probability_bucket"] == "50% to 60%"].iloc[0]
    assert row["bets"] == 1
    assert row["wins"] == 1
    assert row["actual_win_rate"] == 1.0
    assert row["avg_raw_model_prob"] == 0.62
    assert row["avg_calibrated_model_prob"] == 0.58
    assert row["raw_calibration_gap"] == 0.38
    assert row["calibrated_calibration_gap"] == 0.42


def test_save_backtest_calibration_reports(tmp_path) -> None:
    paths = save_backtest_calibration_reports(_sample_bets(), tmp_path)

    assert paths["probability"].name == "backtest_calibration_by_probability.csv"
    assert paths["market"].name == "backtest_calibration_by_market.csv"
    assert paths["side"].name == "backtest_calibration_by_side.csv"
    assert paths["markdown"].name == "backtest_calibration_report.md"
    assert paths["probability"].exists()
    assert paths["market"].exists()
    assert paths["side"].exists()
    assert paths["markdown"].exists()
    assert "Backtest Calibration Report" in paths["markdown"].read_text(encoding="utf-8")


def test_save_market_specific_comparison(tmp_path) -> None:
    summary = pd.DataFrame([{
        "market": "total_2_5",
        "raw_bets": 10,
        "raw_roi": -0.1,
        "generic_calibrated_bets": 8,
        "generic_calibrated_roi": -0.05,
        "calibrated_bets": 2,
        "calibrated_roi": 0.1,
        "bets_filtered_out": 8,
        "calibrated_profit_units": 0.2,
    }])
    paths = save_market_specific_comparison(summary, tmp_path)

    assert paths["csv"].name == "backtest_market_specific_calibration_comparison.csv"
    assert paths["markdown"].name == "backtest_market_specific_calibration_comparison.md"
    assert paths["csv"].exists()
    assert "Market-Specific Calibration Comparison" in paths["markdown"].read_text(encoding="utf-8")
