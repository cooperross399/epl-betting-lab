from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.totals_diagnostics import (
    build_team_event_profile,
    enrich_totals_diagnostics,
    favorite_strength_bucket,
    projected_goal_bucket,
    save_totals_diagnostics_reports,
    summarize_totals_by,
)


def _sample_bets() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": "2025-08-16",
            "season": "2526",
            "home_team": "Arsenal",
            "away_team": "Everton",
            "score": "3-1",
            "market": "total_2_5",
            "selection": "over",
            "american_odds": 120,
            "raw_edge": 0.09,
            "calibrated_edge": 0.07,
            "projected_total_goals": 3.05,
            "favorite_strength": 0.62,
            "actual_total_goals": 4,
            "raw_would_bet": True,
            "generic_calibrated_would_bet": True,
            "calibrated_would_bet": True,
            "goal_environment_adjusted_would_bet": True,
            "won": True,
            "raw_profit_units": 1.2,
            "generic_calibrated_profit_units": 1.2,
            "calibrated_profit_units": 1.2,
            "goal_environment_adjusted_profit_units": 1.2,
            "goal_environment_adjusted_edge": 0.07,
            "profit_units": 1.2,
        },
        {
            "date": "2025-08-17",
            "season": "2526",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "score": "2-1",
            "market": "total_2_5",
            "selection": "under",
            "american_odds": -125,
            "raw_edge": 0.06,
            "calibrated_edge": 0.01,
            "projected_total_goals": 2.1,
            "favorite_strength": 0.48,
            "actual_total_goals": 3,
            "raw_would_bet": True,
            "generic_calibrated_would_bet": False,
            "calibrated_would_bet": False,
            "goal_environment_adjusted_would_bet": False,
            "won": False,
            "raw_profit_units": -1.0,
            "generic_calibrated_profit_units": 0.0,
            "calibrated_profit_units": 0.0,
            "goal_environment_adjusted_profit_units": 0.0,
            "goal_environment_adjusted_edge": 0.01,
            "profit_units": 0.0,
        },
        {
            "date": "2025-08-18",
            "season": "2526",
            "home_team": "Liverpool",
            "away_team": "Spurs",
            "score": "2-0",
            "market": "1x2",
            "selection": "home",
            "american_odds": -140,
            "raw_edge": 0.08,
            "calibrated_edge": 0.05,
            "raw_would_bet": True,
            "generic_calibrated_would_bet": True,
            "calibrated_would_bet": True,
            "won": True,
            "raw_profit_units": 0.714,
            "generic_calibrated_profit_units": 0.714,
            "calibrated_profit_units": 0.714,
            "profit_units": 0.714,
        },
    ])


def _sample_matches() -> pd.DataFrame:
    return pd.DataFrame([
        {"home_team": "Arsenal", "away_team": "Everton", "home_goals": 3, "away_goals": 1},
        {"home_team": "Arsenal", "away_team": "Chelsea", "home_goals": 4, "away_goals": 2},
        {"home_team": "Fulham", "away_team": "Everton", "home_goals": 0, "away_goals": 1},
        {"home_team": "Chelsea", "away_team": "Fulham", "home_goals": 1, "away_goals": 0},
    ])


def test_totals_bucket_labels_are_readable() -> None:
    assert projected_goal_bucket(2.1) == "under 2.2"
    assert projected_goal_bucket(2.6) == "2.5 to 2.79"
    assert projected_goal_bucket(3.2) == "3.1 or higher"
    assert favorite_strength_bucket(0.4) == "no clear favorite"
    assert favorite_strength_bucket(0.6) == "strong favorite"


def test_enrich_totals_diagnostics_filters_to_totals_and_adds_event_profiles() -> None:
    enriched = enrich_totals_diagnostics(_sample_bets(), _sample_matches())

    assert set(enriched["market"]) == {"total_2_5"}
    assert "projected_goal_total_bucket" in enriched.columns
    assert "home_event_bucket" in enriched.columns
    assert "match_event_profile" in enriched.columns


def test_summarize_totals_by_compares_raw_and_calibrated_results() -> None:
    enriched = enrich_totals_diagnostics(_sample_bets(), _sample_matches())
    summary = summarize_totals_by(enriched, ["selection"])

    under = summary[summary["selection"] == "under"].iloc[0]
    assert under["raw_bets"] == 1
    assert under["raw_profit_units"] == -1.0
    assert under["calibrated_bets"] == 0
    assert under["bets_filtered_out"] == 1
    assert under["goal_environment_adjusted_bets"] == 0
    assert under["goal_environment_bets_filtered_out"] == 1


def test_team_event_profile_is_available() -> None:
    profile = build_team_event_profile(_sample_matches())

    arsenal = profile[profile["team"] == "Arsenal"].iloc[0]
    assert arsenal["team_event_bucket"] == "high-event team"


def test_save_totals_diagnostics_reports(tmp_path) -> None:
    paths = save_totals_diagnostics_reports(_sample_bets(), _sample_matches(), tmp_path)

    assert paths["diagnostics"].name == "backtest_totals_diagnostics.csv"
    assert paths["selection"].name == "backtest_totals_by_selection.csv"
    assert paths["goal_bucket"].name == "backtest_totals_by_goal_bucket.csv"
    assert paths["price_bucket"].name == "backtest_totals_by_price_bucket.csv"
    assert paths["comparison"].name == "backtest_totals_goal_environment_comparison.csv"
    assert paths["team"].name == "backtest_totals_by_team.csv"
    assert paths["markdown"].name == "backtest_totals_diagnostics_report.md"
    assert paths["diagnostics"].exists()
    assert paths["selection"].exists()
    assert paths["goal_bucket"].exists()
    assert paths["team"].exists()
    assert "Totals Diagnostics" in paths["markdown"].read_text(encoding="utf-8")
