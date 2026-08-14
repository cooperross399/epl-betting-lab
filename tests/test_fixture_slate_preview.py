from __future__ import annotations

from datetime import date

import pandas as pd

from epl_betting_lab.reports.fixture_slate_preview import (
    build_fixture_slate_preview,
    generate_fixture_slate_preview,
)


TODAY = date(2026, 8, 14)


def _write_fixtures(path, rows: list[dict[str, str]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _fixture(
    fixture_date: str,
    home: str,
    away: str,
    matchweek: str | None = None,
) -> dict[str, str]:
    row = {"date": fixture_date, "home_team": home, "away_team": away}
    if matchweek is not None:
        row["matchweek"] = matchweek
    return row


def test_default_selects_next_upcoming_date_cluster(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    _write_fixtures(
        fixtures_path,
        [
            _fixture("2026-08-13", "Past", "Match"),
            _fixture("2026-08-21", "Arsenal", "Chelsea"),
            _fixture("2026-08-22", "Liverpool", "Everton"),
            _fixture("2026-08-24", "Fulham", "Brentford"),
            _fixture("2026-08-28", "Leeds", "Sunderland"),
        ],
    )

    result = build_fixture_slate_preview(fixtures_path, today=TODAY)
    summary = result["summary"]

    assert result["status"] == "Slate ready"
    assert summary["selection_mode"] == "Next upcoming date cluster"
    assert summary["selected_date_from"] == "2026-08-21"
    assert summary["selected_date_to"] == "2026-08-24"
    assert summary["included_fixture_count"] == 3
    assert summary["excluded_past_fixture_count"] == 1
    assert summary["excluded_future_fixture_count"] == 1


def test_default_prefers_next_upcoming_matchweek_label(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    _write_fixtures(
        fixtures_path,
        [
            _fixture("2026-08-21", "Arsenal", "Chelsea", "MW1"),
            _fixture("2026-08-24", "Liverpool", "Everton", "MW1"),
            _fixture("2026-08-28", "Fulham", "Brentford", "MW2"),
        ],
    )

    result = build_fixture_slate_preview(fixtures_path, today=TODAY)

    assert result["status"] == "Slate ready"
    assert result["summary"]["selection_mode"] == "Next upcoming matchweek"
    assert result["summary"]["target_matchweek_label"] == "MW1"
    assert result["summary"]["included_fixture_count"] == 2


def test_explicit_date_window_filters_fixture_slate(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    _write_fixtures(
        fixtures_path,
        [
            _fixture("2026-08-21", "Arsenal", "Chelsea"),
            _fixture("2026-08-28", "Liverpool", "Everton"),
        ],
    )

    result = build_fixture_slate_preview(
        fixtures_path,
        today=TODAY,
        date_from=date(2026, 8, 28),
        date_to=date(2026, 8, 28),
    )

    assert result["status"] == "Slate ready"
    assert result["summary"]["selection_mode"] == "Date window"
    assert result["summary"]["included_fixture_count"] == 1
    assert result["included_fixtures"].iloc[0]["home_team"] == "Liverpool"


def test_empty_window_blocks_template_eligibility(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    _write_fixtures(
        fixtures_path,
        [_fixture("2026-08-21", "Arsenal", "Chelsea")],
    )

    result = build_fixture_slate_preview(
        fixtures_path,
        today=TODAY,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 2),
    )

    assert result["status"] == "Empty slate"
    assert result["summary"]["template_eligible"] is False
    assert result["included_fixtures"].empty


def test_all_past_fixtures_need_refresh(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    _write_fixtures(
        fixtures_path,
        [_fixture("2026-08-13", "Arsenal", "Chelsea")],
    )

    result = build_fixture_slate_preview(fixtures_path, today=TODAY)

    assert result["status"] == "Needs fixture refresh"
    assert result["summary"]["excluded_past_fixture_count"] == 1
    assert "all in the past" in result["summary"]["status_reason"]


def test_malformed_dates_are_surfaced_and_fail_closed(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    _write_fixtures(
        fixtures_path,
        [
            _fixture("not-a-date", "Arsenal", "Chelsea"),
            _fixture("2026-08-21", "Liverpool", "Everton"),
        ],
    )

    result = build_fixture_slate_preview(fixtures_path, today=TODAY)

    assert result["status"] == "Fixture date issues"
    assert result["summary"]["malformed_date_count"] == 1
    assert "Fixture date issue" in set(result["rows"]["disposition"])


def test_selected_duplicate_fixtures_are_surfaced(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    duplicate = _fixture("2026-08-21", "Arsenal", "Chelsea")
    _write_fixtures(fixtures_path, [duplicate, duplicate.copy()])

    result = build_fixture_slate_preview(fixtures_path, today=TODAY)

    assert result["status"] == "Duplicate fixtures"
    assert result["summary"]["selected_duplicate_fixture_count"] == 2
    assert result["included_fixtures"].empty


def test_selected_missing_team_is_surfaced(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    _write_fixtures(
        fixtures_path,
        [_fixture("2026-08-21", "", "Chelsea")],
    )

    result = build_fixture_slate_preview(fixtures_path, today=TODAY)

    assert result["status"] == "Fixture team issues"
    assert result["summary"]["selected_missing_team_count"] == 1


def test_unsupported_matchweek_request_explains_available_fields(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    _write_fixtures(
        fixtures_path,
        [_fixture("2026-08-21", "Arsenal", "Chelsea")],
    )

    result = build_fixture_slate_preview(
        fixtures_path,
        today=TODAY,
        matchweek="1",
    )

    assert result["status"] == "Blocked"
    assert "Available fields" in result["summary"]["status_reason"]
    assert result["summary"]["available_fields"] == ["date", "home_team", "away_team"]


def test_preview_writes_json_markdown_and_csv(tmp_path) -> None:
    fixtures_path = tmp_path / "fixtures.csv"
    output_dir = tmp_path / "outputs"
    _write_fixtures(
        fixtures_path,
        [_fixture("2026-08-21", "Arsenal", "Chelsea", "1")],
    )

    result = generate_fixture_slate_preview(
        fixtures_path,
        output_dir,
        today=TODAY,
    )

    assert result["json"].exists()
    assert result["markdown"].exists()
    assert result["csv"].exists()
    assert "Included matches" in result["markdown"].read_text(encoding="utf-8")
