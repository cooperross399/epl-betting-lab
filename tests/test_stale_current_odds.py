from __future__ import annotations

from datetime import date

import pandas as pd

from epl_betting_lab.reports.stale_current_odds import (
    REPORT_COLUMNS,
    build_stale_current_odds_report,
    render_stale_current_odds_report,
    save_stale_current_odds_report,
)


TODAY = date(2026, 7, 21)


def _write_odds(path) -> None:
    pd.DataFrame(
        [
            {
                "date": "2026-07-20",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "market": "1x2",
                "selection": "home",
                "american_odds": "-120",
                "book": "ExampleBook",
            },
            {
                "date": "2026-07-21",
                "home_team": "Liverpool",
                "away_team": "Everton",
                "market": "total_2_5",
                "selection": "over",
                "american_odds": "+105",
                "book": "ExampleBook",
            },
            {
                "date": "2026-08-01",
                "home_team": "Fulham",
                "away_team": "Brentford",
                "market": "btts",
                "selection": "yes",
                "american_odds": "-110",
                "book": "ExampleBook",
            },
            {
                "date": "not-a-date",
                "home_team": "Leeds",
                "away_team": "Burnley",
                "market": "1x2",
                "selection": "draw",
                "american_odds": "+220",
                "book": "ExampleBook",
            },
            {
                "date": "",
                "home_team": "Sunderland",
                "away_team": "Bournemouth",
                "market": "total_2_5",
                "selection": "under",
                "american_odds": "+115",
                "book": "ExampleBook",
            },
        ]
    ).to_csv(path, index=False)


def test_report_classifies_stale_current_invalid_and_blank_rows(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    _write_odds(odds_path)

    report, summary = build_stale_current_odds_report(odds_path, today=TODAY)

    assert report.columns.tolist() == REPORT_COLUMNS
    assert report["row_number"].tolist() == [2, 3, 4, 5, 6]
    assert report["freshness_status"].tolist() == [
        "Stale",
        "Current",
        "Current",
        "Invalid date",
        "Blank date",
    ]
    assert report["recommended_action"].tolist() == [
        "Remove/archive",
        "Keep",
        "Keep",
        "Fix date",
        "Fix date",
    ]
    assert summary["stale_rows"] == 1
    assert summary["current_rows"] == 2
    assert summary["invalid_date_rows"] == 1
    assert summary["blank_date_rows"] == 1
    assert summary["earliest_odds_date"] == "2026-07-20"
    assert summary["latest_odds_date"] == "2026-08-01"
    assert summary["home_freshness_status"] == "Not checked"


def test_all_past_rows_get_clear_update_recommendation(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    pd.DataFrame(
        [
            {"date": "2026-07-01", "home_team": "Arsenal", "away_team": "Chelsea"},
            {"date": "2026-07-02", "home_team": "Liverpool", "away_team": "Everton"},
        ]
    ).to_csv(odds_path, index=False)

    report, summary = build_stale_current_odds_report(odds_path, today=TODAY)

    assert set(report["freshness_status"]) == {"Stale"}
    assert summary["home_freshness_status"] == "Needs refresh"
    assert "Current odds are tied to past matches" in str(summary["next_step"])


def test_missing_file_has_beginner_friendly_fallback(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"

    report, summary = build_stale_current_odds_report(odds_path, today=TODAY)
    markdown = render_stale_current_odds_report(report, summary)

    assert report.empty
    assert summary["status"] == "Missing file"
    assert "create_current_odds_template.py" in markdown
    assert "No current-odds rows were available" in markdown


def test_empty_and_missing_date_files_have_safe_fallbacks(tmp_path) -> None:
    empty_path = tmp_path / "empty.csv"
    empty_path.write_text("", encoding="utf-8")
    missing_date_path = tmp_path / "missing_date.csv"
    pd.DataFrame([{"home_team": "Arsenal", "away_team": "Chelsea"}]).to_csv(
        missing_date_path,
        index=False,
    )

    empty_report, empty_summary = build_stale_current_odds_report(empty_path, today=TODAY)
    missing_report, missing_summary = build_stale_current_odds_report(missing_date_path, today=TODAY)

    assert empty_report.empty
    assert empty_summary["status"] == "Empty file"
    assert missing_report.empty
    assert missing_summary["status"] == "Missing date column"
    assert missing_summary["total_rows"] == 1


def test_unreadable_file_has_safe_fallback(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    odds_path.write_bytes(b"\xff\xfe\x00\x00")

    report, summary = build_stale_current_odds_report(odds_path, today=TODAY)

    assert report.empty
    assert summary["status"] == "Unreadable file"
    assert "could not be read" in str(summary["message"])


def test_save_report_writes_outputs_without_editing_current_odds(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_odds(odds_path)
    before = odds_path.read_bytes()

    paths = save_stale_current_odds_report(odds_path, output_dir, today=TODAY)

    assert paths["csv"].name == "stale_current_odds_report.csv"
    assert paths["markdown"].name == "stale_current_odds_report.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert odds_path.read_bytes() == before
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Stale rows: 1" in markdown
    assert "Dates To Fix" in markdown
    assert "never edits it" in markdown


def test_save_report_writes_missing_file_fallback_outputs(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"

    paths = save_stale_current_odds_report(odds_path, output_dir, today=TODAY)

    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert not odds_path.exists()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Report status: Missing file" in markdown
    assert "create_current_odds_template.py" in markdown
