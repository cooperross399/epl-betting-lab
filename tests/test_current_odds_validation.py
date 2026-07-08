from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.current_odds_validation import (
    build_current_odds_validation,
    has_serious_issues,
    render_current_odds_validation_report,
    save_current_odds_validation,
)
from epl_betting_lab.reports.thursday_best_bets import render_thursday_best_bets


def _matches() -> pd.DataFrame:
    return pd.DataFrame([
        {"home_team": "Arsenal", "away_team": "Coventry"},
        {"home_team": "Chelsea", "away_team": "Fulham"},
    ])


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"},
        {"date": "2026-08-22", "home_team": "Chelsea", "away_team": "Fulham"},
    ])


def test_missing_current_odds_file_is_serious_without_creating_file(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"

    issues = build_current_odds_validation(odds_path, matches=_matches(), fixtures=_fixtures())

    assert issues.iloc[0]["issue"] == "missing_current_odds_csv"
    assert issues.iloc[0]["severity"] == "error"
    assert "cp data/manual/current_odds_template.csv data/manual/current_odds.csv" in issues.iloc[0]["details"]
    assert not odds_path.exists()


def test_current_odds_validation_separates_errors_and_warnings(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-180",
            "book": "",
        },
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-180",
            "book": "",
        },
        {
            "date": "2026-08-22",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "under",
            "american_odds": "abc",
            "book": "ExampleBook",
        },
        {
            "date": "2026-08-23",
            "home_team": "Unknown FC",
            "away_team": "Fulham",
            "market": "shots",
            "selection": "over",
            "american_odds": "",
            "book": "ExampleBook",
        },
    ]).to_csv(odds_path, index=False)

    issues = build_current_odds_validation(odds_path, matches=_matches(), fixtures=_fixtures())

    issue_names = set(issues["issue"])
    assert {"duplicate_row", "non_numeric_american_odds", "unknown_home_team", "invalid_market", "missing_american_odds"} <= issue_names
    assert {"heavy_juice", "missing_book", "total_under_caution"} <= issue_names
    assert has_serious_issues(issues)

    serious = issues[issues["severity"] == "error"]
    warnings = issues[issues["severity"] == "warning"]
    assert not serious.empty
    assert not warnings.empty


def test_save_current_odds_validation_writes_csv_and_markdown(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "btts",
            "selection": "yes",
            "american_odds": "+120",
            "book": "ExampleBook",
        }
    ]).to_csv(odds_path, index=False)

    paths = save_current_odds_validation(odds_path, output_dir, matches=_matches(), fixtures=_fixtures())

    assert paths["csv"].name == "current_odds_validation.csv"
    assert paths["markdown"].name == "current_odds_validation.md"
    assert paths["csv"].exists()
    assert "No current odds validation issues found." in paths["markdown"].read_text(encoding="utf-8")


def test_validation_report_and_thursday_card_show_serious_warning() -> None:
    issues = pd.DataFrame([
        {
            "severity": "error",
            "issue": "invalid_market",
            "row_number": 2,
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "shots",
            "selection": "over",
            "american_odds": "+120",
            "book": "ExampleBook",
            "details": "Supported markets are 1x2, total_2_5, and btts.",
        }
    ])

    validation_markdown = render_current_odds_validation_report(issues)
    thursday_markdown = render_thursday_best_bets(pd.DataFrame(), validation_issues=issues)

    assert "1 serious issues" in validation_markdown
    assert "Current odds validation warning" in thursday_markdown
    assert "fix serious issues before trusting this card" in thursday_markdown
