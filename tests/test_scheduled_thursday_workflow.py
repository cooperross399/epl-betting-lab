from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.scheduled_thursday_workflow import (
    ScheduledWorkflowActions,
    WorkflowActionResult,
    run_scheduled_thursday_workflow,
)


FIXED_RUN_AT = datetime(2026, 8, 6, 9, 0, tzinfo=timezone.utc)


def _write_output(context, filename: str) -> Path:
    path = context.output_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{filename}\n", encoding="utf-8")
    return path


def _workflow_paths(tmp_path: Path) -> dict[str, Path]:
    manual_dir = tmp_path / "manual"
    processed_dir = tmp_path / "processed"
    output_dir = tmp_path / "outputs"
    manual_dir.mkdir()
    processed_dir.mkdir()
    current_odds = manual_dir / "current_odds.csv"
    fixtures = manual_dir / "upcoming_fixtures.csv"
    matches = processed_dir / "epl_historical_matches.csv"
    ledger = manual_dir / "bet_ledger.csv"
    current_odds.write_text("date,american_odds\n2026-08-08,-120\n", encoding="utf-8")
    fixtures.write_text("date,home_team,away_team\n", encoding="utf-8")
    matches.write_text("date,home_team,away_team\n", encoding="utf-8")
    ledger.write_text("bet_id,result\n", encoding="utf-8")
    return {
        "current_odds_path": current_odds,
        "fixtures_path": fixtures,
        "matches_path": matches,
        "ledger_path": ledger,
        "output_dir": output_dir,
    }


def _actions(
    calls: list[str],
    *,
    validation: WorkflowActionResult | Exception | None = None,
    freshness: WorkflowActionResult | None = None,
    completeness: WorkflowActionResult | None = None,
    archive_count: int = 2,
    comparison_error: Exception | None = None,
) -> ScheduledWorkflowActions:
    def simple_action(
        name: str,
        filename: str,
        configured: WorkflowActionResult | None = None,
    ):
        def action(context) -> WorkflowActionResult:
            calls.append(name)
            if configured is not None:
                return configured
            path = _write_output(context, filename)
            return WorkflowActionResult(outputs={"report": path}, message=f"{name} complete.")

        return action

    def validation_action(context) -> WorkflowActionResult:
        calls.append("validation")
        if isinstance(validation, Exception):
            raise validation
        if validation is not None:
            return validation
        path = _write_output(context, "current_odds_validation.csv")
        return WorkflowActionResult(
            outputs={"csv": path},
            message="Validation complete.",
        )

    def best_bets_action(context) -> WorkflowActionResult:
        calls.append("best_bets")
        outputs = {
            "csv": _write_output(context, "thursday_best_bets.csv"),
            "markdown": _write_output(context, "thursday_best_bets.md"),
            "archive_csv": _write_output(
                context,
                "archive/thursday_best_bets/2026-08-06/090000_thursday_best_bets.csv",
            ),
            "archive_markdown": _write_output(
                context,
                "archive/thursday_best_bets/2026-08-06/090000_thursday_best_bets.md",
            ),
            "archive_metadata": _write_output(
                context,
                "archive/thursday_best_bets/2026-08-06/090000_thursday_best_bets_metadata.json",
            ),
        }
        return WorkflowActionResult(outputs=outputs, message="Thursday card complete.")

    def count_archives(_context) -> int:
        calls.append("archive_count")
        return archive_count

    def comparison_action(context) -> WorkflowActionResult:
        calls.append("comparison")
        if comparison_error is not None:
            raise comparison_error
        path = _write_output(context, "thursday_best_bets_comparison.csv")
        return WorkflowActionResult(outputs={"csv": path}, message="Comparison complete.")

    return ScheduledWorkflowActions(
        data_freshness=simple_action(
            "freshness",
            "freshness.txt",
            freshness,
        ),
        current_odds_validation=validation_action,
        odds_completeness=simple_action(
            "completeness",
            "current_odds_completeness.csv",
            completeness,
        ),
        thursday_best_bets=best_bets_action,
        archive_count=count_archives,
        comparison=comparison_action,
        decision_queue=simple_action(
            "decision_queue",
            "thursday_decision_queue.csv",
        ),
        tier_performance=simple_action(
            "tier_performance",
            "tier_performance_summary.csv",
        ),
    )


def test_scheduled_workflow_runs_safe_steps_in_order_and_reports_ready(tmp_path) -> None:
    paths = _workflow_paths(tmp_path)
    calls: list[str] = []
    current_odds_before = paths["current_odds_path"].read_text(encoding="utf-8")
    ledger_before = paths["ledger_path"].read_text(encoding="utf-8")

    result = run_scheduled_thursday_workflow(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls),
    )

    assert calls == [
        "freshness",
        "validation",
        "completeness",
        "best_bets",
        "archive_count",
        "comparison",
        "decision_queue",
        "tier_performance",
    ]
    assert result["status"] == "Ready"
    assert result["markdown"].exists()
    assert result["json"].exists()
    saved = json.loads(result["json"].read_text(encoding="utf-8"))
    assert saved["run_timestamp"] == "2026-08-06T09:00:00+00:00"
    assert saved["status"] == "Ready"
    assert saved["steps_skipped"] == []
    assert len(saved["steps"]) == 8
    assert "does not edit manual odds" in result["markdown"].read_text(encoding="utf-8")
    assert paths["current_odds_path"].read_text(encoding="utf-8") == current_odds_before
    assert paths["ledger_path"].read_text(encoding="utf-8") == ledger_before


def test_scheduled_workflow_reports_warnings_only_when_all_steps_finish(tmp_path) -> None:
    paths = _workflow_paths(tmp_path)
    calls: list[str] = []
    validation = WorkflowActionResult(
        message="Validation found one warning.",
        warnings=("missing_book - Add the sportsbook name.",),
        metadata={"serious_issue_count": 0, "warning_count": 1},
    )

    result = run_scheduled_thursday_workflow(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, validation=validation),
    )

    assert result["status"] == "Warnings only"
    assert result["summary"]["key_blockers"] == []
    assert result["summary"]["key_warnings"] == [
        "missing_book - Add the sportsbook name."
    ]


def test_scheduled_workflow_blocks_card_without_force_and_still_runs_tiers(
    tmp_path,
) -> None:
    paths = _workflow_paths(tmp_path)
    calls: list[str] = []
    validation = WorkflowActionResult(
        message="Validation found a serious issue.",
        blockers=("row 2: missing_american_odds - Enter real sportsbook odds.",),
        metadata={"serious_issue_count": 1, "warning_count": 0},
    )

    result = run_scheduled_thursday_workflow(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, validation=validation),
    )

    assert result["status"] == "Blocked"
    assert calls == ["freshness", "validation", "completeness", "tier_performance"]
    assert result["summary"]["steps_skipped"] == [
        "Thursday best-bets generation",
        "Thursday archive snapshot",
        "Thursday snapshot comparison",
        "Thursday decision queue",
    ]
    assert "Do not force the scheduled card" in result["summary"]["recommended_next_action"]
    statuses = {
        step["step"]: step["status"] for step in result["summary"]["steps"]
    }
    assert statuses["Current odds validation"] == "Blocked"
    assert statuses["Thursday best-bets generation"] == "Skipped"


def test_scheduled_workflow_is_partial_until_two_archives_exist(tmp_path) -> None:
    paths = _workflow_paths(tmp_path)
    calls: list[str] = []

    result = run_scheduled_thursday_workflow(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, archive_count=1),
    )

    assert result["status"] == "Partial"
    assert "comparison" not in calls
    assert "decision_queue" not in calls
    assert "tier_performance" in calls
    assert result["summary"]["steps_skipped"] == [
        "Thursday snapshot comparison",
        "Thursday decision queue",
    ]
    assert "another archive" in result["summary"]["recommended_next_action"]


def test_scheduled_workflow_writes_failed_summary_after_required_error(
    tmp_path,
) -> None:
    paths = _workflow_paths(tmp_path)
    calls: list[str] = []

    result = run_scheduled_thursday_workflow(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, validation=ValueError("validation CSV is unreadable")),
    )

    assert result["status"] == "Failed"
    assert calls == ["freshness", "validation", "completeness", "tier_performance"]
    assert result["json"].exists()
    failed_steps = [
        step["step"]
        for step in result["summary"]["steps"]
        if step["status"] == "Failed"
    ]
    assert failed_steps == ["Current odds validation"]
    assert "validation CSV is unreadable" in result["markdown"].read_text(
        encoding="utf-8"
    )


def test_optional_comparison_error_keeps_workflow_partial(tmp_path) -> None:
    paths = _workflow_paths(tmp_path)
    calls: list[str] = []

    result = run_scheduled_thursday_workflow(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(
            calls,
            comparison_error=ValueError("archive CSV could not be compared"),
        ),
    )

    assert result["status"] == "Partial"
    assert "decision_queue" not in calls
    assert "tier_performance" in calls
    statuses = {
        step["step"]: step["status"] for step in result["summary"]["steps"]
    }
    assert statuses["Thursday snapshot comparison"] == "Failed"
    assert statuses["Thursday decision queue"] == "Skipped"


def test_default_workflow_blocks_missing_odds_without_creating_manual_file(
    tmp_path,
) -> None:
    paths = _workflow_paths(tmp_path)
    paths["current_odds_path"].unlink()

    result = run_scheduled_thursday_workflow(
        **paths,
        run_at=FIXED_RUN_AT,
    )

    assert result["status"] == "Blocked"
    assert not paths["current_odds_path"].exists()
    assert not (paths["output_dir"] / "thursday_best_bets.csv").exists()
    assert (paths["output_dir"] / "current_odds_validation.csv").exists()
    assert (paths["output_dir"] / "current_odds_completeness.csv").exists()
    assert (paths["output_dir"] / "tier_performance_report.md").exists()
