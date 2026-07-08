from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.thursday_best_bets import (
    build_thursday_best_bets,
    missing_current_odds_message,
    render_thursday_best_bets,
    save_thursday_best_bets,
)


def _candidates() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "status": "BETTABLE",
            "american_odds": -120,
            "raw_model_prob": 0.62,
            "calibrated_model_prob": 0.58,
            "model_prob": 0.58,
            "book_implied": 0.5455,
            "raw_edge": 0.0745,
            "calibrated_edge": 0.0345,
            "edge": 0.0345,
            "ev_per_unit": 0.05,
            "fair_american": -138,
            "book": "DraftKings",
            "notes": "real row in manual odds file",
        },
        {
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "under",
            "status": "LEAN",
            "american_odds": 120,
            "raw_model_prob": 0.55,
            "calibrated_model_prob": 0.50,
            "model_prob": 0.50,
            "book_implied": 0.4545,
            "raw_edge": 0.0955,
            "calibrated_edge": 0.0455,
            "edge": 0.0455,
            "ev_per_unit": 0.04,
            "fair_american": 100,
            "book": "FanDuel",
            "goal_environment_under_guardrail": True,
            "goal_environment_reason": "Recent games were hot.",
            "pre_goal_environment_calibrated_status": "LEAN",
        },
        {
            "home_team": "Spurs",
            "away_team": "Wolves",
            "market": "1x2",
            "selection": "home",
            "status": "PASS - too much juice",
            "american_odds": -220,
            "raw_model_prob": 0.70,
            "calibrated_model_prob": 0.64,
            "model_prob": 0.64,
            "book_implied": 0.6875,
            "raw_edge": 0.0125,
            "calibrated_edge": -0.0475,
            "edge": -0.0475,
            "ev_per_unit": -0.12,
            "fair_american": -178,
            "book": "BetMGM",
        },
    ])


def test_build_thursday_best_bets_sections_and_fields() -> None:
    report = build_thursday_best_bets(_candidates())

    assert list(report["section"]) == ["Best bets", "Leans", "Passes / notable avoids"]
    assert report.loc[report["section"] == "Passes / notable avoids", "suggested_units"].iloc[0] == 0.0
    assert "Under guardrail" in report.loc[report["market"] == "total_2_5", "totals_note"].iloc[0]
    assert "qualifies_reason" in report.columns


def test_render_thursday_best_bets_includes_checklist_and_prices() -> None:
    markdown = render_thursday_best_bets(build_thursday_best_bets(_candidates()))

    assert "Wednesday/Thursday checklist" in markdown
    assert "Arsenal vs Coventry" in markdown
    assert "raw 62.0%" in markdown
    assert "calibrated 58.0%" in markdown
    assert "Fair price" in markdown


def test_missing_current_odds_message_is_beginner_friendly() -> None:
    message = missing_current_odds_message(Path("data/manual/current_odds.csv"))

    assert "Copy data/manual/current_odds_template.csv" in message
    assert "enter real sportsbook odds" in message


def test_save_thursday_best_bets(tmp_path) -> None:
    report = build_thursday_best_bets(_candidates())
    paths = save_thursday_best_bets(report, tmp_path)

    assert paths["csv"].name == "thursday_best_bets.csv"
    assert paths["markdown"].name == "thursday_best_bets.md"
    assert paths["csv"].exists()
    assert "Thursday Best Bets" in paths["markdown"].read_text(encoding="utf-8")
