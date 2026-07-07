from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.clv import enrich_clv_bets, save_clv_reports, summarize_clv


def _sample_bets() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Everton",
            "market": "1x2",
            "selection": "home",
            "american_odds": -110,
            "opening_american_odds": -110,
            "closing_american_odds": -130,
            "calibrated_edge": 0.05,
            "goal_environment_adjusted_edge": 0.05,
            "goal_environment_adjusted_would_bet": True,
            "won": True,
            "goal_environment_adjusted_profit_units": 0.91,
            "profit_units": 0.91,
        },
        {
            "date": "2026-08-22",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "over",
            "american_odds": 120,
            "opening_american_odds": 120,
            "closing_american_odds": pd.NA,
            "calibrated_edge": 0.07,
            "goal_environment_adjusted_edge": 0.07,
            "goal_environment_adjusted_would_bet": True,
            "won": False,
            "goal_environment_adjusted_profit_units": -1.0,
            "profit_units": -1.0,
        },
        {
            "date": "2026-08-23",
            "home_team": "Spurs",
            "away_team": "Wolves",
            "market": "btts",
            "selection": "yes",
            "american_odds": -105,
            "closing_american_odds": -115,
            "goal_environment_adjusted_would_bet": True,
            "won": True,
            "profit_units": 0.95,
        },
    ])


def test_enrich_clv_calculates_positive_probability_points() -> None:
    clv = enrich_clv_bets(_sample_bets())
    row = clv[clv["market"] == "1x2"].iloc[0]

    assert set(clv["market"]) == {"1x2", "total_2_5"}
    assert bool(row["has_closing_odds"]) is True
    assert row["clv_probability_points"] > 0
    assert row["clv_american_odds_movement"] == 20


def test_missing_closing_odds_stays_missing() -> None:
    clv = enrich_clv_bets(_sample_bets())
    row = clv[clv["market"] == "total_2_5"].iloc[0]

    assert bool(row["has_closing_odds"]) is False
    assert pd.isna(row["closing_implied_probability"])
    assert pd.isna(row["clv_probability_points"])


def test_summarize_clv_counts_missing_prices() -> None:
    summary = summarize_clv(enrich_clv_bets(_sample_bets()), ["market"])
    totals = summary[summary["market"] == "total_2_5"].iloc[0]

    assert totals["bets"] == 1
    assert totals["with_closing_odds"] == 0
    assert totals["missing_closing_odds"] == 1


def test_save_clv_reports(tmp_path) -> None:
    paths = save_clv_reports(_sample_bets(), tmp_path)

    assert paths["market"].name == "clv_by_market.csv"
    assert paths["selection"].name == "clv_by_selection.csv"
    assert paths["team"].name == "clv_by_team.csv"
    assert paths["markdown"].name == "clv_report.md"
    assert paths["market"].exists()
    assert paths["selection"].exists()
    assert paths["team"].exists()
    assert "Closing-Line Value Report" in paths["markdown"].read_text(encoding="utf-8")
