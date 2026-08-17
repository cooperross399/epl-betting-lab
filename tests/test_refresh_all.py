"""One command to refresh everything, in an order that cannot be got wrong."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.reports.refresh_all import (
    REFRESH_JSON_FILENAME,
    refresh_all_reports,
    _steps,
)


NOW = datetime(2026, 8, 17, 22, 0, tzinfo=timezone.utc)


def test_every_step_runs_and_is_reported(tmp_path: Path) -> None:
    summary = refresh_all_reports(output_dir=tmp_path, now=NOW)

    assert len(summary["steps"]) == len(_steps())
    for step in summary["steps"]:
        assert step["status"] in {"ok", "failed", "skipped"}
        assert step["description"]


def test_the_order_puts_inputs_before_the_things_that_read_them() -> None:
    """A status page built from a stale card looks current, which is worse than
    no page. The order is the whole point of this module."""
    names = [name for name, _, _ in _steps()]

    assert names.index("card_input") < names.index("automated_card")
    assert names.index("automated_card") < names.index("epl_card_task")
    assert names.index("automated_card") < names.index("archive_card")
    assert names.index("archive_card") < names.index("card_comparison")
    assert names.index("status_page") == len(names) - 1


def test_a_failing_step_does_not_abort_the_rest(tmp_path: Path, monkeypatch) -> None:
    """A status page missing one section beats no output plus a traceback."""
    from epl_betting_lab.reports import refresh_all

    real_steps = _steps()

    def boom(_outputs):
        raise RuntimeError("deliberate failure")

    monkeypatch.setattr(
        refresh_all,
        "_steps",
        lambda: [("broken", "Always fails", boom), *real_steps[-1:]],
    )

    summary = refresh_all_reports(output_dir=tmp_path, now=NOW)

    statuses = {step["step"]: step["status"] for step in summary["steps"]}
    assert statuses["broken"] == "failed"
    assert statuses["status_page"] == "ok"
    assert summary["all_ok"] is False
    assert summary["failed_count"] == 1


def test_a_failure_message_is_captured_not_raised(tmp_path: Path, monkeypatch) -> None:
    from epl_betting_lab.reports import refresh_all

    def boom(_outputs):
        raise ValueError("something specific went wrong")

    monkeypatch.setattr(refresh_all, "_steps", lambda: [("broken", "Fails", boom)])

    summary = refresh_all_reports(output_dir=tmp_path, now=NOW)

    assert "something specific went wrong" in summary["steps"][0]["error"]


def test_only_runs_the_named_steps(tmp_path: Path) -> None:
    summary = refresh_all_reports(output_dir=tmp_path, only=["status_page"], now=NOW)

    statuses = {step["step"]: step["status"] for step in summary["steps"]}
    assert statuses["status_page"] == "ok"
    assert statuses["card_input"] == "skipped"
    assert summary["skipped_count"] > 0


def test_it_never_contacts_the_provider(tmp_path: Path) -> None:
    """Refreshing the view and refetching the data are separate actions."""
    summary = refresh_all_reports(output_dir=tmp_path, now=NOW)

    assert summary["safety"]["provider_contacted"] is False
    assert summary["safety"]["quota_spent"] is False
    assert summary["safety"]["bets_placed"] is False
    assert summary["safety"]["settlement_applied"] is False
    assert summary["safety"]["protected_files_written"] is False


def test_a_summary_is_written_for_later_inspection(tmp_path: Path) -> None:
    refresh_all_reports(output_dir=tmp_path, now=NOW)

    payload = json.loads((tmp_path / REFRESH_JSON_FILENAME).read_text(encoding="utf-8"))

    assert payload["report"] == "Refresh All Reports"
    assert payload["steps"]


def test_running_on_an_empty_directory_reports_rather_than_crashes(
    tmp_path: Path,
) -> None:
    """With no evidence at all, every step should still be accounted for."""
    summary = refresh_all_reports(output_dir=tmp_path, now=NOW)

    assert len(summary["steps"]) == len(_steps())
    assert summary["ok_count"] + summary["failed_count"] == len(_steps())
