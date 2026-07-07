from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.backtest_calibration import (
    probability_bucket,
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
            "model_prob": 0.62,
            "book_implied": 0.556,
            "edge": 0.064,
            "ev_per_unit": 0.116,
            "status": "BETTABLE",
            "won": True,
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
            "model_prob": 0.48,
            "book_implied": 0.455,
            "edge": 0.045,
            "ev_per_unit": 0.1,
            "status": "BETTABLE",
            "won": False,
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
    row = summary[summary["probability_bucket"] == "60% to 70%"].iloc[0]
    assert row["bets"] == 1
    assert row["wins"] == 1
    assert row["actual_win_rate"] == 1.0
    assert row["avg_model_prob"] == 0.62
    assert row["calibration_gap"] == 0.38


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
