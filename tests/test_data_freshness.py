from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from epl_betting_lab.workflow_status import (
    DataFreshnessCheck,
    build_data_freshness_checks,
    build_data_freshness_status,
    recommend_data_freshness_action,
)


def _touch(path: Path, timestamp: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok", encoding="utf-8")
    os.utime(path, (timestamp, timestamp))


def _fixture_check(path: Path) -> DataFreshnessCheck:
    return DataFreshnessCheck(
        "Upcoming fixtures",
        path,
        "update fixtures",
        "Update upcoming fixtures.",
        fixture_date_column="date",
        priority=1,
    )


def test_data_freshness_marks_available_inputs_fresh_and_absent_inputs_missing(
    tmp_path: Path,
) -> None:
    available = tmp_path / "available.csv"
    _touch(available, 100)
    checks = [
        DataFreshnessCheck("Available", available, "refresh", "Refresh available."),
        DataFreshnessCheck("Absent", tmp_path / "absent.csv", "create", "Create absent."),
    ]

    status = build_data_freshness_status(checks).set_index("item")

    assert status.loc["Available", "status"] == "Fresh"
    assert status.loc["Available", "command"] == ""
    assert status.loc["Absent", "status"] == "Missing"
    assert status.loc["Absent", "command"] == "create"


def test_data_freshness_marks_reports_stale_when_a_source_is_newer(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    report = tmp_path / "report.csv"
    processed = tmp_path / "processed.csv"
    _touch(report, 100)
    _touch(processed, 100)
    _touch(source, 200)
    checks = [
        DataFreshnessCheck(
            "Report",
            report,
            "make report",
            "Refresh report.",
            sources=(source,),
            minimum_sources=1,
        ),
        DataFreshnessCheck(
            "Processed data",
            processed,
            "rebuild",
            "Rebuild data.",
            sources=(source,),
            minimum_sources=1,
            stale_status="Needs refresh",
        ),
    ]

    status = build_data_freshness_status(checks).set_index("item")

    assert status.loc["Report", "status"] == "Stale"
    assert status.loc["Processed data", "status"] == "Needs refresh"
    assert str(source) in status.loc["Report", "note"]


def test_fixture_dates_need_refresh_when_every_match_is_in_the_past(tmp_path: Path) -> None:
    fixtures = tmp_path / "upcoming_fixtures.csv"
    fixtures.write_text("date\n2026-07-01\n2026-07-12\n", encoding="utf-8")

    status = build_data_freshness_status(
        [_fixture_check(fixtures)],
        today=date(2026, 7, 13),
    )
    row = status.iloc[0]

    assert row["status"] == "Needs refresh"
    assert row["earliest_fixture_date"] == "2026-07-01"
    assert row["latest_fixture_date"] == "2026-07-12"
    assert row["past_fixtures"] == 2
    assert row["today_or_future_fixtures"] == 0
    assert row["invalid_fixture_dates"] == 0
    assert recommend_data_freshness_action(status) == (
        "Upcoming fixtures are all in the past. Refresh fixtures before Thursday analysis."
    )


def test_fixture_dates_are_fresh_when_a_match_is_today_or_later(tmp_path: Path) -> None:
    fixtures = tmp_path / "upcoming_fixtures.csv"
    fixtures.write_text(
        "date\n2026-07-12\n2026-07-13\n2026-07-14\n",
        encoding="utf-8",
    )

    row = build_data_freshness_status(
        [_fixture_check(fixtures)],
        today=date(2026, 7, 13),
    ).iloc[0]

    assert row["status"] == "Fresh"
    assert row["past_fixtures"] == 1
    assert row["today_or_future_fixtures"] == 2
    assert row["command"] == ""


def test_fixture_dates_are_not_checked_when_values_are_malformed(tmp_path: Path) -> None:
    fixtures = tmp_path / "upcoming_fixtures.csv"
    fixtures.write_text("date\n2026-07-14\nnot-a-date\n", encoding="utf-8")

    row = build_data_freshness_status(
        [_fixture_check(fixtures)],
        today=date(2026, 7, 13),
    ).iloc[0]

    assert row["status"] == "Not checked"
    assert row["earliest_fixture_date"] == "2026-07-14"
    assert row["latest_fixture_date"] == "2026-07-14"
    assert row["today_or_future_fixtures"] == 1
    assert row["invalid_fixture_dates"] == 1
    assert "blank or malformed" in row["note"]


def test_fixture_dates_are_not_checked_when_date_column_is_missing(tmp_path: Path) -> None:
    fixtures = tmp_path / "upcoming_fixtures.csv"
    fixtures.write_text("home_team\nArsenal\n", encoding="utf-8")

    row = build_data_freshness_status(
        [_fixture_check(fixtures)],
        today=date(2026, 7, 13),
    ).iloc[0]

    assert row["status"] == "Not checked"
    assert "missing the `date` column" in row["note"]


def test_data_freshness_uses_not_checked_when_required_sources_are_missing(
    tmp_path: Path,
) -> None:
    check = DataFreshnessCheck(
        "Validation",
        tmp_path / "validation.csv",
        "validate",
        "Validate odds.",
        sources=(tmp_path / "current_odds.csv",),
        minimum_sources=1,
        not_checked_until_sources=True,
    )

    row = build_data_freshness_status([check]).iloc[0]

    assert row["status"] == "Not checked"
    assert "Missing sources" in row["note"]
    assert row["command"] == "validate"


def test_data_freshness_recommendation_uses_the_highest_priority_issue(
    tmp_path: Path,
) -> None:
    status = build_data_freshness_status([
        DataFreshnessCheck(
            "Later",
            tmp_path / "later.csv",
            "later",
            "Do this later.",
            priority=50,
        ),
        DataFreshnessCheck(
            "First",
            tmp_path / "first.csv",
            "first",
            "Do this first.",
            priority=1,
        ),
    ])

    assert recommend_data_freshness_action(status) == "Do this first."


def test_data_freshness_propagates_unavailable_report_dependencies(tmp_path: Path) -> None:
    comparison = tmp_path / "comparison.csv"
    queue = tmp_path / "queue.csv"
    _touch(comparison, 100)
    _touch(queue, 200)
    checks = [
        DataFreshnessCheck(
            "Comparison",
            comparison,
            "compare",
            "Build comparison.",
            sources=(tmp_path / "archive.csv",),
            minimum_sources=1,
        ),
        DataFreshnessCheck(
            "Queue",
            queue,
            "queue",
            "Build queue.",
            sources=(comparison,),
            dependencies=("Comparison",),
            minimum_sources=1,
        ),
    ]

    status = build_data_freshness_status(checks).set_index("item")

    assert status.loc["Comparison", "status"] == "Not checked"
    assert status.loc["Queue", "status"] == "Not checked"
    assert "Comparison (Not checked)" in status.loc["Queue", "note"]


def test_default_data_freshness_checks_track_required_items_and_latest_archives(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    manual_dir = tmp_path / "manual"
    output_dir = tmp_path / "outputs"
    older_archive = (
        output_dir
        / "archive"
        / "thursday_best_bets"
        / "2026-07-10"
        / "120000_thursday_best_bets.csv"
    )
    newer_archive = (
        output_dir
        / "archive"
        / "thursday_best_bets"
        / "2026-07-11"
        / "120000_thursday_best_bets.csv"
    )
    _touch(older_archive, 100)
    _touch(newer_archive, 200)

    checks = build_data_freshness_checks(raw_dir, processed_dir, manual_dir, output_dir)
    by_item = {check.item: check for check in checks}

    assert set(by_item) == {
        "Historical results / Football-Data",
        "Upcoming fixtures",
        "Current odds",
        "Current odds validation report",
        "Odds completeness report",
        "Thursday best-bets report",
        "Latest Thursday archive",
        "Thursday comparison report",
        "Thursday decision queue",
        "Tier performance report",
        "Bet ledger report",
    }
    assert by_item["Latest Thursday archive"].path == newer_archive
    assert by_item["Thursday comparison report"].sources == (older_archive, newer_archive)
