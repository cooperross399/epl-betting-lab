from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from epl_betting_lab.thursday_readiness import build_thursday_readiness


def _write_completeness(output_dir: Path, completion: str = "85.0%", incomplete: int = 2) -> None:
    pd.DataFrame(columns=["severity", "issue"]).to_csv(output_dir / "current_odds_completeness.csv", index=False)
    (output_dir / "current_odds_completeness.md").write_text(
        "\n".join([
            "# Current Odds Entry Completeness",
            "",
            "## Summary",
            "",
            f"- Completion percentage: {completion}",
            f"- Matches incomplete: {incomplete}",
        ]),
        encoding="utf-8",
    )


def _write_validation(output_dir: Path, rows: list[dict[str, str]] | None = None) -> None:
    pd.DataFrame(rows or [], columns=["severity", "issue"]).to_csv(output_dir / "current_odds_validation.csv", index=False)
    (output_dir / "current_odds_validation.md").write_text("# Current Odds Validation\n", encoding="utf-8")


def _touch(path: Path, timestamp: int) -> None:
    path.write_text(path.read_text(encoding="utf-8") if path.exists() else "ok", encoding="utf-8")
    os.utime(path, (timestamp, timestamp))


def test_thursday_readiness_not_checked_when_reports_are_missing(tmp_path) -> None:
    status = build_thursday_readiness(tmp_path, tmp_path / "current_odds.csv")

    assert status.thursday_report_status == "Not checked"
    assert status.odds_completion_percentage is None
    assert status.incomplete_matches is None
    assert status.serious_validation_issues is None
    assert status.validation_warnings is None
    assert status.completeness_missing
    assert status.validation_missing


def test_thursday_readiness_ready_with_clean_reports(tmp_path) -> None:
    _write_completeness(tmp_path, completion="100.0%", incomplete=0)
    _write_validation(tmp_path)
    (tmp_path / "thursday_best_bets.md").write_text("# Thursday\n", encoding="utf-8")

    status = build_thursday_readiness(tmp_path, tmp_path / "current_odds.csv")

    assert status.thursday_report_status == "Ready"
    assert status.odds_completion_percentage == 1.0
    assert status.incomplete_matches == 0
    assert status.serious_validation_issues == 0
    assert status.validation_warnings == 0
    assert not status.thursday_report_missing


def test_thursday_readiness_warnings_only_counts_validation_warnings(tmp_path) -> None:
    _write_completeness(tmp_path, completion="75.0%", incomplete=1)
    _write_validation(tmp_path, [{"severity": "warning", "issue": "missing_book"}])

    status = build_thursday_readiness(tmp_path, tmp_path / "current_odds.csv")

    assert status.thursday_report_status == "Warnings only"
    assert status.odds_completion_percentage == 0.75
    assert status.incomplete_matches == 1
    assert status.serious_validation_issues == 0
    assert status.validation_warnings == 1
    assert status.thursday_report_missing


def test_thursday_readiness_blocked_for_serious_validation_issues(tmp_path) -> None:
    _write_completeness(tmp_path)
    _write_validation(
        tmp_path,
        [
            {"severity": "error", "issue": "blank_american_odds"},
            {"severity": "warning", "issue": "missing_book"},
        ],
    )

    status = build_thursday_readiness(tmp_path, tmp_path / "current_odds.csv")

    assert status.thursday_report_status == "Blocked"
    assert status.serious_validation_issues == 1
    assert status.validation_warnings == 1


def test_thursday_readiness_needs_refresh_when_current_odds_is_newer(tmp_path) -> None:
    current_odds = tmp_path / "current_odds.csv"
    _write_completeness(tmp_path)
    _write_validation(tmp_path)
    _touch(tmp_path / "current_odds_completeness.csv", 100)
    _touch(tmp_path / "current_odds_completeness.md", 100)
    _touch(tmp_path / "current_odds_validation.csv", 100)
    _touch(tmp_path / "current_odds_validation.md", 100)
    _touch(current_odds, 200)

    status = build_thursday_readiness(tmp_path, current_odds)

    assert status.thursday_report_status == "Needs refresh"
    assert status.is_stale
