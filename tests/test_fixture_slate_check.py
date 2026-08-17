from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.fixture_slate_check import (
    SLATE_CHECK_CSV_FILENAME,
    SLATE_CHECK_JSON_FILENAME,
    SLATE_CHECK_MARKDOWN_FILENAME,
    build_fixture_slate_check,
    run_fixture_slate_check,
)


TODAY = date(2026, 8, 17)


def _write_fixtures(tmp_path: Path, rows: list[str]) -> Path:
    path = tmp_path / "upcoming_fixtures.csv"
    path.write_text("date,home_team,away_team,notes\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _write_matches(tmp_path: Path, teams: list[tuple[str, str]]) -> Path:
    path = tmp_path / "epl_historical_matches.csv"
    frame = pd.DataFrame(
        [
            {
                "date": "2026-05-01",
                "home_team": home,
                "away_team": away,
                "home_goals": 1,
                "away_goals": 0,
            }
            for home, away in teams
        ]
    )
    frame.to_csv(path, index=False)
    return path


def _clean_slate(tmp_path: Path) -> dict[str, Path]:
    fixtures = _write_fixtures(
        tmp_path,
        [
            "2026-08-21,Arsenal,Coventry,",
            "2026-08-22,Everton,Crystal Palace,",
            "2026-08-28,Coventry,Arsenal,note",
        ],
    )
    matches = _write_matches(
        tmp_path,
        [("Arsenal", "Everton"), ("Crystal Palace", "Arsenal"), ("Coventry", "Everton")],
    )
    return {"fixtures": fixtures, "matches": matches}


def test_clean_slate_is_ready_for_manual_confirmation(tmp_path: Path) -> None:
    paths = _clean_slate(tmp_path)

    result = build_fixture_slate_check(
        paths["fixtures"],
        matches_path=paths["matches"],
        current_odds_path=tmp_path / "missing_odds.csv",
        today=TODAY,
    )

    assert result["status"] == "Slate ready for manual confirmation"
    assert result["summary"]["error_count"] == 0
    assert result["summary"]["warning_count"] == 0
    assert result["summary"]["fixture_count"] == 3
    # Aug 21-22 and Aug 28 are more than three days apart: two matchweek groups.
    assert result["summary"]["matchweek_group_count"] == 2
    assert list(result["matchweeks"]["fixture_count"]) == [2, 1]
    checklist = result["summary"]["confirmation_checklist"]
    assert any("official EPL schedule" in item for item in checklist)


def test_missing_fixture_file_reports_missing_status(tmp_path: Path) -> None:
    result = build_fixture_slate_check(
        tmp_path / "missing_fixtures.csv",
        matches_path=tmp_path / "missing_matches.csv",
        current_odds_path=tmp_path / "missing_odds.csv",
        today=TODAY,
    )

    assert result["status"] == "Missing fixtures"
    assert result["summary"]["error_count"] == 1
    assert result["issues"].iloc[0]["category"] == "Missing file"


def test_duplicate_and_double_booked_fixtures_are_errors(tmp_path: Path) -> None:
    fixtures = _write_fixtures(
        tmp_path,
        [
            "2026-08-21,Arsenal,Coventry,",
            "2026-08-21,Arsenal,Coventry,",
            "2026-08-22,Arsenal,Everton,",
        ],
    )

    result = build_fixture_slate_check(
        fixtures,
        matches_path=tmp_path / "missing_matches.csv",
        current_odds_path=tmp_path / "missing_odds.csv",
        today=TODAY,
    )

    assert result["status"] == "Needs slate fixes"
    categories = set(result["issues"]["category"])
    assert "Duplicate fixture" in categories
    assert "Double-booked team" in categories
    double_booked = result["issues"][result["issues"]["category"] == "Double-booked team"]
    assert "Arsenal" in set(double_booked["home_team"])


def test_same_team_home_and_away_is_an_error(tmp_path: Path) -> None:
    fixtures = _write_fixtures(tmp_path, ["2026-08-21,Arsenal,Arsenal,"])

    result = build_fixture_slate_check(
        fixtures,
        matches_path=tmp_path / "missing_matches.csv",
        current_odds_path=tmp_path / "missing_odds.csv",
        today=TODAY,
    )

    assert result["status"] == "Needs slate fixes"
    assert "Same team twice" in set(result["issues"]["category"])


def test_invalid_and_past_dates_are_flagged(tmp_path: Path) -> None:
    fixtures = _write_fixtures(
        tmp_path,
        [
            "not-a-date,Arsenal,Coventry,",
            "2026-08-01,Everton,Fulham,",
            "2026-08-22,Chelsea,Brighton,",
        ],
    )

    result = build_fixture_slate_check(
        fixtures,
        matches_path=tmp_path / "missing_matches.csv",
        current_odds_path=tmp_path / "missing_odds.csv",
        today=TODAY,
    )

    assert result["status"] == "Needs slate fixes"
    categories = list(result["issues"]["category"])
    assert "Invalid date" in categories
    assert "Past fixture" in categories


def test_unknown_team_name_is_a_warning_not_an_error(tmp_path: Path) -> None:
    fixtures = _write_fixtures(tmp_path, ["2026-08-21,Arsenal,Coventry,"])
    matches = _write_matches(tmp_path, [("Arsenal", "Everton")])

    result = build_fixture_slate_check(
        fixtures,
        matches_path=matches,
        current_odds_path=tmp_path / "missing_odds.csv",
        today=TODAY,
    )

    assert result["status"] == "Slate ready with warnings"
    unknown = result["issues"][result["issues"]["category"] == "Unknown team name"]
    assert list(unknown["home_team"]) == ["Coventry"]
    assert "promoted" in unknown.iloc[0]["suggested_action"]


def test_repeated_pairing_on_different_dates_is_a_warning(tmp_path: Path) -> None:
    fixtures = _write_fixtures(
        tmp_path,
        [
            "2026-08-21,Arsenal,Coventry,",
            "2026-08-29,Arsenal,Coventry,",
        ],
    )

    result = build_fixture_slate_check(
        fixtures,
        matches_path=tmp_path / "missing_matches.csv",
        current_odds_path=tmp_path / "missing_odds.csv",
        today=TODAY,
    )

    assert result["status"] == "Slate ready with warnings"
    assert "Repeated pairing" in set(result["issues"]["category"])


def test_slate_odds_cross_check_flags_drift_both_ways(tmp_path: Path) -> None:
    paths = _clean_slate(tmp_path)
    odds = pd.DataFrame(
        [
            # Covers the first fixture only; the second is missing from odds, and
            # one odds fixture is not in the slate.
            {"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"},
            {"date": "2026-08-28", "home_team": "Coventry", "away_team": "Arsenal"},
            {"date": "2026-08-23", "home_team": "Leeds", "away_team": "Brentford"},
        ]
    )
    odds_path = tmp_path / "current_odds.csv"
    odds.to_csv(odds_path, index=False)

    result = build_fixture_slate_check(
        paths["fixtures"],
        matches_path=paths["matches"],
        current_odds_path=odds_path,
        today=TODAY,
    )

    assert result["status"] == "Slate ready with warnings"
    categories = list(result["issues"]["category"])
    assert "Fixture missing from odds file" in categories
    assert "Odds rows without a slate fixture" in categories
    missing = result["issues"][result["issues"]["category"] == "Fixture missing from odds file"]
    assert list(missing["home_team"]) == ["Everton"]


def test_run_writes_all_three_reports_and_does_not_edit_inputs(tmp_path: Path) -> None:
    paths = _clean_slate(tmp_path)
    fixtures_before = paths["fixtures"].read_bytes()
    output_dir = tmp_path / "outputs"

    result = run_fixture_slate_check(
        paths["fixtures"],
        matches_path=paths["matches"],
        current_odds_path=tmp_path / "missing_odds.csv",
        output_dir=output_dir,
        today=TODAY,
    )

    for filename in (
        SLATE_CHECK_JSON_FILENAME,
        SLATE_CHECK_MARKDOWN_FILENAME,
        SLATE_CHECK_CSV_FILENAME,
    ):
        assert (output_dir / filename).exists()
    assert paths["fixtures"].read_bytes() == fixtures_before
    markdown = (output_dir / SLATE_CHECK_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    assert "Manual confirmation checklist" in markdown
    assert "- [ ]" in markdown
    assert result["paths"]["markdown"] == output_dir / SLATE_CHECK_MARKDOWN_FILENAME


def test_missing_columns_are_a_single_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "upcoming_fixtures.csv"
    path.write_text("match_date,home,away\n2026-08-21,Arsenal,Coventry\n", encoding="utf-8")

    result = build_fixture_slate_check(
        path,
        matches_path=tmp_path / "missing_matches.csv",
        current_odds_path=tmp_path / "missing_odds.csv",
        today=TODAY,
    )

    assert result["status"] == "Needs slate fixes"
    assert list(result["issues"]["category"]) == ["Missing columns"]
