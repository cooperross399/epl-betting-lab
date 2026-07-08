from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.current_odds_completeness import (
    build_current_odds_completeness,
    render_current_odds_completeness_report,
    save_current_odds_completeness,
)


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"},
    ])


def test_completeness_flags_missing_non_numeric_duplicate_and_missing_expected_rows(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-150",
            "book": "FanDuel",
        },
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "draw",
            "american_odds": "",
            "book": "",
        },
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "away",
            "american_odds": "abc",
            "book": "FanDuel",
        },
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "away",
            "american_odds": "+400",
            "book": "FanDuel",
        },
    ]).to_csv(odds_path, index=False)

    issues, summary = build_current_odds_completeness(odds_path, fixtures=_fixtures())

    issue_names = set(issues["issue"])
    assert "blank_american_odds" in issue_names
    assert "non_numeric_american_odds" in issue_names
    assert "missing_book" in issue_names
    assert "duplicate_market_selection_row" in issue_names
    assert "missing_expected_market_row" in issue_names
    assert summary["total_rows"] == 4
    assert summary["rows_with_odds_filled"] == 2
    assert summary["rows_missing_odds"] == 1
    assert summary["rows_non_numeric_odds"] == 1
    assert summary["missing_expected_rows"] == 4
    assert summary["completion_percentage"] == 0.25
    assert summary["matches_fully_complete"] == 0
    assert summary["matches_incomplete"] == 1


def test_completeness_counts_complete_match_when_all_expected_rows_have_numeric_odds(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    rows = []
    for market, selection in [
        ("1x2", "home"),
        ("1x2", "draw"),
        ("1x2", "away"),
        ("total_2_5", "over"),
        ("total_2_5", "under"),
        ("btts", "yes"),
        ("btts", "no"),
    ]:
        rows.append({
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": market,
            "selection": selection,
            "american_odds": "-110",
            "book": "FanDuel",
        })
    pd.DataFrame(rows).to_csv(odds_path, index=False)

    issues, summary = build_current_odds_completeness(odds_path, fixtures=_fixtures())

    assert issues.empty
    assert summary["total_rows"] == 7
    assert summary["rows_with_odds_filled"] == 7
    assert summary["completion_percentage"] == 1.0
    assert summary["matches_fully_complete"] == 1
    assert summary["matches_incomplete"] == 0


def test_missing_current_odds_file_writes_beginner_friendly_issue(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"

    issues, summary = build_current_odds_completeness(odds_path, fixtures=_fixtures())
    markdown = render_current_odds_completeness_report(issues, summary)

    assert issues.iloc[0]["issue"] == "missing_current_odds_csv"
    assert "Copy data/manual/current_odds_template.csv" in issues.iloc[0]["details"]
    assert "missing_current_odds_csv" in markdown
    assert summary["completion_percentage"] == 0


def test_save_current_odds_completeness_writes_csv_and_markdown(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-150",
            "book": "FanDuel",
        }
    ]).to_csv(odds_path, index=False)

    paths = save_current_odds_completeness(odds_path, output_dir, fixtures=_fixtures())

    assert paths["csv"].name == "current_odds_completeness.csv"
    assert paths["markdown"].name == "current_odds_completeness.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Completion percentage" in markdown
    assert "missing_expected_market_row" in markdown


def test_render_current_odds_completeness_report_explains_percentage() -> None:
    issues = pd.DataFrame(columns=[
        "severity",
        "issue",
        "match",
        "date",
        "home_team",
        "away_team",
        "market",
        "selection",
        "book",
        "american_odds",
        "details",
    ])
    markdown = render_current_odds_completeness_report(
        issues,
        {
            "total_rows": 2,
            "rows_with_odds_filled": 1,
            "rows_missing_odds": 1,
            "rows_non_numeric_odds": 0,
            "missing_expected_rows": 0,
            "completion_percentage": 0.5,
            "matches_fully_complete": 0,
            "matches_incomplete": 1,
        },
    )

    assert "numeric odds filled divided by existing rows" in markdown
