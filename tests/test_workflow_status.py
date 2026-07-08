from __future__ import annotations

import os
from pathlib import Path

from epl_betting_lab.workflow_status import WorkflowCheck, build_workflow_status


def _touch(path: Path, timestamp: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok", encoding="utf-8")
    os.utime(path, (timestamp, timestamp))


def test_workflow_status_marks_missing_files(tmp_path) -> None:
    report = tmp_path / "output.md"
    checks = [WorkflowCheck("Report", (report,), "python make_report.py")]

    status = build_workflow_status(checks)
    row = status.iloc[0]

    assert row["status"] == "Missing"
    assert row["command"] == "python make_report.py"
    assert "Missing:" in row["note"]


def test_workflow_status_marks_complete_files(tmp_path) -> None:
    report = tmp_path / "output.md"
    _touch(report, 100)
    checks = [WorkflowCheck("Report", (report,), "python make_report.py")]

    row = build_workflow_status(checks).iloc[0]

    assert row["status"] == "Complete"
    assert row["command"] == ""
    assert row["last_modified"]


def test_workflow_status_marks_stale_reports(tmp_path) -> None:
    source = tmp_path / "manual.csv"
    report = tmp_path / "output.md"
    _touch(report, 100)
    _touch(source, 200)
    checks = [WorkflowCheck("Report", (report,), "python make_report.py", stale_after=(source,))]

    row = build_workflow_status(checks).iloc[0]

    assert row["status"] == "Needs refresh"
    assert row["command"] == "python make_report.py"
    assert str(source) in row["note"]


def test_workflow_status_supports_any_path_ok(tmp_path) -> None:
    csv_path = tmp_path / "weekly_card.csv"
    md_path = tmp_path / "weekly_card.md"
    _touch(csv_path, 100)
    checks = [WorkflowCheck("Weekly card", (csv_path, md_path), "python card.py", any_path_ok=True)]

    row = build_workflow_status(checks).iloc[0]

    assert row["status"] == "Complete"
