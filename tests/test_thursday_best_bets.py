from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.thursday_best_bets import (
    build_thursday_best_bets,
    list_recent_thursday_archives,
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
            "home_team": "Liverpool",
            "away_team": "Leeds",
            "market": "1x2",
            "selection": "home",
            "status": "BETTABLE",
            "american_odds": 105,
            "raw_model_prob": 0.62,
            "calibrated_model_prob": 0.61,
            "model_prob": 0.61,
            "book_implied": 0.4878,
            "raw_edge": 0.15,
            "calibrated_edge": 0.1222,
            "edge": 0.1222,
            "ev_per_unit": 0.25,
            "fair_american": -156,
            "book": "DraftKings",
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
            "home_team": "Everton",
            "away_team": "Sunderland",
            "market": "total_2_5",
            "selection": "under",
            "status": "BETTABLE",
            "american_odds": 120,
            "raw_model_prob": 0.68,
            "calibrated_model_prob": 0.62,
            "model_prob": 0.62,
            "book_implied": 0.4545,
            "raw_edge": 0.2255,
            "calibrated_edge": 0.1655,
            "edge": 0.1655,
            "ev_per_unit": 0.36,
            "fair_american": -163,
            "book": "FanDuel",
            "goal_environment_under_guardrail": False,
            "goal_environment_reason": "Existing protections left this playable.",
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
    report = build_thursday_best_bets(_candidates(), market_reliability={"1x2": 8.0, "total_2_5": -8.0})

    assert list(report["section"]) == ["Best bets", "Best bets", "Best bets", "Leans", "Passes / notable avoids"]
    assert report.loc[report["section"] == "Passes / notable avoids", "suggested_units"].iloc[0] == 0.0
    chelsea_total = report[(report["home_team"] == "Chelsea") & (report["market"] == "total_2_5")].iloc[0]
    assert "Under guardrail" in chelsea_total["totals_note"]
    assert "qualifies_reason" in report.columns
    assert "ranking_score" in report.columns
    assert "confidence_tier" in report.columns
    assert "risk_flags" in report.columns
    assert report.iloc[0]["home_team"] == "Liverpool"
    assert report.iloc[0]["confidence_tier"] == "A"
    assert report.iloc[0]["suggested_units"] == 0.5


def test_render_thursday_best_bets_includes_checklist_and_prices() -> None:
    markdown = render_thursday_best_bets(build_thursday_best_bets(_candidates(), market_reliability={"1x2": 8.0, "total_2_5": -8.0}))

    assert "Wednesday/Thursday checklist" in markdown
    assert "Arsenal vs Coventry" in markdown
    assert "raw 62.0%" in markdown
    assert "calibrated 58.0%" in markdown
    assert "Fair price" in markdown
    assert "Ranking and confidence guide" in markdown
    assert "Ranking score" in markdown
    assert "Market reliability" in markdown
    assert "Risk flags" in markdown


def test_totals_unders_cannot_receive_a_tier() -> None:
    report = build_thursday_best_bets(_candidates(), market_reliability={"1x2": 8.0, "total_2_5": 12.0})
    totals_under = report[(report["market"] == "total_2_5") & (report["selection"] == "under") & (report["status"] == "BETTABLE")].iloc[0]

    assert totals_under["confidence_tier"] == "B"
    assert totals_under["suggested_units"] == 0.25
    assert "totals under caution" in totals_under["risk_flags"]


def test_missing_current_odds_message_is_beginner_friendly() -> None:
    message = missing_current_odds_message(Path("data/manual/current_odds.csv"))

    assert "Copy data/manual/current_odds_template.csv" in message
    assert "enter real sportsbook odds" in message


def test_save_thursday_best_bets(tmp_path) -> None:
    report = build_thursday_best_bets(_candidates())
    paths = save_thursday_best_bets(report, tmp_path, generated_at=datetime(2026, 7, 8, 12, 30, 5))

    assert paths["csv"].name == "thursday_best_bets.csv"
    assert paths["markdown"].name == "thursday_best_bets.md"
    assert paths["csv"].exists()
    assert "Thursday Best Bets" in paths["markdown"].read_text(encoding="utf-8")
    assert paths["archive_csv"].exists()
    assert paths["archive_markdown"].exists()
    assert paths["archive_metadata"].exists()
    assert "archive/thursday_best_bets/2026-07-08/123005_thursday_best_bets.md" in str(paths["archive_markdown"])

    metadata = json.loads(paths["archive_metadata"].read_text(encoding="utf-8"))
    assert metadata["generated_at"] == "2026-07-08T12:30:05"
    assert metadata["best_bets"] == 3
    assert metadata["leans"] == 1
    assert metadata["passes"] == 1
    assert metadata["validation_status"] == "not_checked"


def test_save_thursday_best_bets_does_not_overwrite_same_timestamp_archive(tmp_path) -> None:
    report = build_thursday_best_bets(_candidates())
    generated_at = datetime(2026, 7, 8, 12, 30, 5)

    first = save_thursday_best_bets(report, tmp_path, generated_at=generated_at)
    second = save_thursday_best_bets(report, tmp_path, generated_at=generated_at)

    assert first["archive_markdown"].exists()
    assert second["archive_markdown"].exists()
    assert first["archive_markdown"] != second["archive_markdown"]
    assert second["archive_markdown"].name == "123005_2_thursday_best_bets.md"


def test_list_recent_thursday_archives(tmp_path) -> None:
    report = build_thursday_best_bets(_candidates())
    older = save_thursday_best_bets(report, tmp_path, generated_at=datetime(2026, 7, 8, 12, 30, 5))
    newer = save_thursday_best_bets(report, tmp_path, generated_at=datetime(2026, 7, 9, 12, 30, 5))

    archives = list_recent_thursday_archives(tmp_path)

    assert list(archives["generated_at"]) == ["2026-07-09T12:30:05", "2026-07-08T12:30:05"]
    assert archives.iloc[0]["markdown"] == str(newer["archive_markdown"])
    assert archives.iloc[1]["csv"] == str(older["archive_csv"])
