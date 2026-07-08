from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from epl_betting_lab.current_odds_status import build_current_odds_status


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    return (
        tmp_path / "current_odds_validation.csv",
        tmp_path / "current_odds_validation.md",
        tmp_path / "current_odds.csv",
    )


def _touch(path: Path, timestamp: int) -> None:
    path.write_text("ok", encoding="utf-8")
    os.utime(path, (timestamp, timestamp))


def test_current_odds_status_not_checked_when_validation_missing(tmp_path) -> None:
    validation_csv, validation_md, current_odds = _paths(tmp_path)

    status = build_current_odds_status(validation_csv, validation_md, current_odds)

    assert status.status == "Not checked"
    assert status.command == "python scripts/validate_current_odds.py"


def test_current_odds_status_ready_for_empty_issue_file(tmp_path) -> None:
    validation_csv, validation_md, current_odds = _paths(tmp_path)
    pd.DataFrame(columns=["severity", "issue"]).to_csv(validation_csv, index=False)

    status = build_current_odds_status(validation_csv, validation_md, current_odds)

    assert status.status == "Ready"
    assert status.serious_issues == 0
    assert status.warnings == 0


def test_current_odds_status_warnings_only(tmp_path) -> None:
    validation_csv, validation_md, current_odds = _paths(tmp_path)
    pd.DataFrame([
        {"severity": "warning", "issue": "missing_book"},
        {"severity": "warning", "issue": "heavy_juice"},
    ]).to_csv(validation_csv, index=False)

    status = build_current_odds_status(validation_csv, validation_md, current_odds)

    assert status.status == "Warnings only"
    assert status.serious_issues == 0
    assert status.warnings == 2


def test_current_odds_status_blocked_for_serious_issues(tmp_path) -> None:
    validation_csv, validation_md, current_odds = _paths(tmp_path)
    pd.DataFrame([
        {"severity": "error", "issue": "invalid_market"},
        {"severity": "warning", "issue": "missing_book"},
    ]).to_csv(validation_csv, index=False)

    status = build_current_odds_status(validation_csv, validation_md, current_odds)

    assert status.status == "Blocked"
    assert status.serious_issues == 1
    assert status.warnings == 1


def test_current_odds_status_needs_refresh_when_odds_are_newer(tmp_path) -> None:
    validation_csv, validation_md, current_odds = _paths(tmp_path)
    pd.DataFrame(columns=["severity", "issue"]).to_csv(validation_csv, index=False)
    _touch(validation_csv, 100)
    _touch(validation_md, 100)
    _touch(current_odds, 200)

    status = build_current_odds_status(validation_csv, validation_md, current_odds)

    assert status.status == "Needs refresh"
    assert status.is_stale
