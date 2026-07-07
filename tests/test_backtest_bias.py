from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.backtest_bias import (
    edge_bucket,
    favorite_bucket,
    odds_range,
    save_backtest_bias_reports,
    summarize_by,
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
            "model_prob": 0.5,
            "book_implied": 0.455,
            "edge": 0.045,
            "ev_per_unit": 0.1,
            "status": "BETTABLE",
            "won": False,
            "profit_units": -1.0,
        },
    ])


def test_report_buckets_are_readable() -> None:
    assert odds_range(-170) == "worse than -160"
    assert odds_range(-125) == "-160 to -121"
    assert odds_range(150) == "+101 to +200"
    assert edge_bucket(0.04) == "3.5% to 5%"
    assert edge_bucket(0.09) == "8% to 12%"
    assert favorite_bucket(-125) == "favorite / juiced"
    assert favorite_bucket(120) == "underdog / plus money"


def test_summarize_by_calculates_roi() -> None:
    summary = summarize_by(_sample_bets(), ["market"])
    one_x_two = summary[summary["market"] == "1x2"].iloc[0]
    assert one_x_two["bets"] == 1
    assert one_x_two["wins"] == 1
    assert one_x_two["roi"] == 0.8


def test_save_backtest_bias_reports(tmp_path) -> None:
    paths = save_backtest_bias_reports(_sample_bets(), tmp_path)

    assert paths["market"].name == "backtest_market_breakdown.csv"
    assert paths["markdown"].name == "backtest_bias_report.md"
    assert paths["market"].exists()
    assert paths["odds_range"].exists()
    assert paths["team"].exists()
    assert paths["edge_bucket"].exists()
    assert paths["markdown"].exists()
    assert "Backtest Bias Report" in paths["markdown"].read_text(encoding="utf-8")
