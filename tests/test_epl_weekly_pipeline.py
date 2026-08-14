from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import epl_betting_lab.dashboard_actions as dashboard_actions
import epl_betting_lab.reports.epl_weekly_pipeline as weekly_pipeline_module
from epl_betting_lab.reports.epl_weekly_pipeline import (
    EplWeeklyPipelineActions,
    run_epl_weekly_pipeline,
)
from epl_betting_lab.scheduled_thursday_workflow import WorkflowActionResult


FIXED_RUN_AT = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)


def _write(context, filename: str, content: str = "report\n") -> Path:
    path = context.output_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _paths(tmp_path: Path, *, include_odds: bool = True) -> dict[str, Path]:
    manual = tmp_path / "data" / "manual"
    processed = tmp_path / "data" / "processed"
    outputs = tmp_path / "data" / "outputs"
    manual.mkdir(parents=True)
    processed.mkdir(parents=True)
    current_odds = manual / "current_odds.csv"
    fixtures = manual / "upcoming_fixtures.csv"
    matches = processed / "epl_historical_matches.csv"
    ledger = manual / "bet_ledger.csv"
    if include_odds:
        current_odds.write_text(
            "date,home_team,away_team,market,selection,american_odds,book\n"
            "2026-08-15,Arsenal,Chelsea,1x2,home,-110,Example\n",
            encoding="utf-8",
        )
    fixtures.write_text(
        "date,home_team,away_team\n2026-08-15,Arsenal,Chelsea\n",
        encoding="utf-8",
    )
    matches.write_text(
        "date,home_team,away_team,home_goals,away_goals\n"
        "2026-05-01,Arsenal,Chelsea,2,1\n",
        encoding="utf-8",
    )
    ledger.write_text("bet_id,result\n", encoding="utf-8")
    return {
        "current_odds_path": current_odds,
        "fixtures_path": fixtures,
        "matches_path": matches,
        "ledger_path": ledger,
        "output_dir": outputs,
        "repository_root": tmp_path,
    }


def _complete_metadata() -> dict[str, object]:
    return {
        "completion_percentage": 1.0,
        "total_rows": 7,
        "rows_with_odds_filled": 7,
        "rows_missing_odds": 0,
        "rows_non_numeric_odds": 0,
        "missing_expected_rows": 0,
        "matches_fully_complete": 1,
        "matches_incomplete": 0,
    }


def _actions(
    calls: list[str],
    *,
    freshness_ready: bool = True,
    validation: WorkflowActionResult | None = None,
    completeness: WorkflowActionResult | None = None,
    archive_count: int = 2,
    tier_error: Exception | None = None,
) -> EplWeeklyPipelineActions:
    def freshness_action(_context) -> WorkflowActionResult:
        calls.append("freshness")
        statuses = {
            "Historical results / Football-Data": "Fresh" if freshness_ready else "Needs refresh",
            "Upcoming fixtures": "Fresh",
        }
        return WorkflowActionResult(
            message="Freshness checked.",
            metadata={
                "card_inputs_ready": freshness_ready,
                "card_input_statuses": statuses,
            },
        )

    def validation_action(context) -> WorkflowActionResult:
        calls.append("validation")
        if validation is not None:
            return validation
        return WorkflowActionResult(
            outputs={"csv": _write(context, "current_odds_validation.csv")},
            message="Validation passed.",
            metadata={"serious_issue_count": 0, "warning_count": 0},
        )

    def completeness_action(context) -> WorkflowActionResult:
        calls.append("completeness")
        if completeness is not None:
            return completeness
        return WorkflowActionResult(
            outputs={"csv": _write(context, "current_odds_completeness.csv")},
            message="Odds are complete.",
            metadata=_complete_metadata(),
        )

    def best_bets_action(context) -> WorkflowActionResult:
        calls.append("best_bets")
        report = pd.DataFrame(
            [
                {"section": "Best bets", "home_team": "Arsenal"},
                {"section": "Leans", "home_team": "Chelsea"},
                {"section": "Passes / notable avoids", "home_team": "Liverpool"},
            ]
        )
        csv_path = context.output_dir / "thursday_best_bets.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        report.to_csv(csv_path, index=False)
        return WorkflowActionResult(
            outputs={
                "csv": csv_path,
                "markdown": _write(context, "thursday_best_bets.md"),
                "archive_csv": _write(
                    context,
                    "archive/thursday_best_bets/2026-08-13/090000_thursday_best_bets.csv",
                ),
                "archive_markdown": _write(
                    context,
                    "archive/thursday_best_bets/2026-08-13/090000_thursday_best_bets.md",
                ),
                "archive_metadata": _write(
                    context,
                    "archive/thursday_best_bets/2026-08-13/090000_thursday_best_bets_metadata.json",
                    "{}\n",
                ),
            },
            message="Card generated safely.",
        )

    def count_action(_context) -> int:
        calls.append("archive_count")
        return archive_count

    def comparison_action(context) -> WorkflowActionResult:
        calls.append("comparison")
        return WorkflowActionResult(
            outputs={"csv": _write(context, "thursday_best_bets_comparison.csv")},
            message="Comparison generated.",
        )

    def queue_action(context) -> WorkflowActionResult:
        calls.append("decision_queue")
        return WorkflowActionResult(
            outputs={"csv": _write(context, "thursday_decision_queue.csv")},
            message="Decision queue generated.",
            metadata={
                "total_rows": 3,
                "action_counts": {"Review price": 2, "Candidate upgrade": 1},
            },
        )

    def ledger_health_action(context) -> WorkflowActionResult:
        calls.append("ledger_health")
        return WorkflowActionResult(
            outputs={"csv": _write(context, "bet_ledger_health_check.csv")},
            message="Ledger health passed.",
            metadata={"error_count": 0, "warning_count": 0, "info_count": 0},
        )

    def ledger_summary_action(context) -> WorkflowActionResult:
        calls.append("ledger_summary")
        return WorkflowActionResult(
            outputs={"markdown": _write(context, "bet_ledger_summary.md")},
            message="Ledger summary generated.",
            metadata={
                "tracked_bets": 0,
                "pending_bets": 0,
                "profit_units": 0.0,
                "roi": 0.0,
            },
        )

    def tier_action(context) -> WorkflowActionResult:
        calls.append("tier_performance")
        if tier_error is not None:
            raise tier_error
        return WorkflowActionResult(
            outputs={"summary": _write(context, "tier_performance_summary.csv")},
            message="Tier performance generated.",
        )

    return EplWeeklyPipelineActions(
        data_freshness=freshness_action,
        current_odds_validation=validation_action,
        odds_completeness=completeness_action,
        thursday_best_bets=best_bets_action,
        archive_count=count_action,
        comparison=comparison_action,
        decision_queue=queue_action,
        ledger_health=ledger_health_action,
        ledger_summary=ledger_summary_action,
        tier_performance=tier_action,
    )


def test_weekly_pipeline_runs_all_safe_steps_in_order_and_preserves_inputs(tmp_path) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []
    odds_before = paths["current_odds_path"].read_bytes()
    ledger_before = paths["ledger_path"].read_bytes()

    result = run_epl_weekly_pipeline(
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
        "ledger_health",
        "ledger_summary",
        "tier_performance",
    ]
    assert result["status"] == "Ready for card review"
    assert result["json"].exists()
    assert result["markdown"].exists()
    assert result["csv"].exists()
    saved = json.loads(result["json"].read_text(encoding="utf-8"))
    assert saved["card_counts"] == {
        "best_bets": 1,
        "leans": 1,
        "passes": 1,
        "total_candidates": 3,
    }
    assert saved["decision_queue_counts"] == {
        "Candidate upgrade": 1,
        "Review price": 2,
    }
    assert saved["safety"]["force_mode_used"] is False
    assert saved["safety"]["settlement_applied"] is False
    assert saved["safety"]["bets_placed"] is False
    assert saved["pipeline_receipt_id"].startswith("epl-weekly-")
    assert saved["archive_receipt_id"] == saved["pipeline_receipt_id"]
    assert saved["receipt_verification_verdict"] == (
        "Weekly pipeline receipt verified"
    )
    assert saved["receipt_verification_status"] == "Verified"
    assert saved["receipt_verification_original_id"] == saved[
        "pipeline_receipt_id"
    ]
    assert saved["receipt_verification_recalculated_id"] == saved[
        "pipeline_receipt_id"
    ]
    assert saved["receipt_verification_mismatch_count"] == 0
    assert saved["receipt_verification_report_path"] in saved[
        "generated_report_paths"
    ]
    assert saved["pipeline_comparison_verdict"] == "Missing prior run"
    archive_dir = Path(saved["pipeline_archive_path"])
    assert Path(saved["archive_path"]) == archive_dir
    assert archive_dir == paths["output_dir"] / "archive/epl_weekly_pipeline/2026-08-13/090000"
    assert (archive_dir / "epl_weekly_pipeline.json").exists()
    assert (archive_dir / "epl_weekly_pipeline.md").exists()
    assert (archive_dir / "epl_weekly_pipeline.csv").exists()
    archived_pipeline = json.loads(
        (archive_dir / "epl_weekly_pipeline.json").read_text(encoding="utf-8")
    )
    assert archived_pipeline["receipt_verification_status"] == "Pending"
    assert archived_pipeline["archive_receipt_id"] == saved["archive_receipt_id"]
    pipeline_csv = pd.read_csv(result["csv"])
    for column in (
        "archive_receipt_id",
        "archive_path",
        "receipt_verification_verdict",
        "receipt_verification_status",
        "receipt_verification_original_id",
        "receipt_verification_recalculated_id",
        "receipt_verification_mismatch_count",
        "receipt_verification_report_path",
    ):
        assert column in pipeline_csv.columns
    pipeline_markdown = result["markdown"].read_text(encoding="utf-8")
    assert "Receipt verification: **Weekly pipeline receipt verified**" in pipeline_markdown
    assert "Receipt verification mismatches: 0" in pipeline_markdown
    assert paths["current_odds_path"].read_bytes() == odds_before
    assert paths["ledger_path"].read_bytes() == ledger_before


def test_weekly_pipeline_verifies_the_archive_path_it_just_created(
    tmp_path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []
    verified_paths: list[Path] = []
    original = weekly_pipeline_module.save_epl_weekly_pipeline_receipt_verification

    def capture_verification(*, archive_path, output_dir, generated_at):
        verified_paths.append(Path(archive_path))
        return original(
            archive_path=archive_path,
            output_dir=output_dir,
            generated_at=generated_at,
        )

    monkeypatch.setattr(
        weekly_pipeline_module,
        "save_epl_weekly_pipeline_receipt_verification",
        capture_verification,
    )

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls),
    )

    assert verified_paths == [Path(result["summary"]["archive_path"])]
    assert verified_paths[0] == Path(result["archive"]["archive_dir"])
    assert result["receipt_verification"]["verdict"] == (
        "Weekly pipeline receipt verified"
    )


def test_first_archive_skips_comparison_without_downgrading_ready_status(tmp_path) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, archive_count=1),
    )

    assert result["status"] == "Ready for card review"
    assert "comparison" not in calls
    assert "decision_queue" not in calls
    statuses = {step["step"]: step["status"] for step in result["summary"]["steps"]}
    assert statuses["Thursday best-bets comparison"] == "Skipped"
    assert statuses["Thursday decision queue"] == "Skipped"


def test_second_weekly_pipeline_run_compares_its_receipt_automatically(tmp_path) -> None:
    paths = _paths(tmp_path)
    first_calls: list[str] = []
    second_calls: list[str] = []

    first = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(first_calls),
    )
    second = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(second_calls),
    )

    assert first["summary"]["pipeline_comparison_verdict"] == "Missing prior run"
    assert second["summary"]["pipeline_comparison_verdict"] == "Stable ready state"
    assert first["summary"]["pipeline_archive_path"] != second["summary"][
        "pipeline_archive_path"
    ]
    assert second["comparison"]["important_changes"] == [
        "No meaningful weekly workflow changes were detected."
    ]


def test_incomplete_odds_block_card_but_keep_independent_reports_running(tmp_path) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []
    metadata = _complete_metadata()
    metadata.update(
        {
            "completion_percentage": 0.75,
            "rows_missing_odds": 1,
            "matches_incomplete": 1,
        }
    )
    completeness = WorkflowActionResult(
        message="Odds are incomplete.",
        warnings=("Two completeness items need attention.",),
        metadata=metadata,
    )

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, completeness=completeness, archive_count=0),
    )

    assert result["status"] == "Needs odds fixes"
    assert "best_bets" not in calls
    assert "ledger_health" in calls
    assert "ledger_summary" in calls
    assert "tier_performance" in calls
    assert "Odds are 75.0% complete" in " ".join(result["summary"]["key_blockers"])


def test_missing_current_odds_reports_needs_odds_without_creating_file(tmp_path) -> None:
    paths = _paths(tmp_path, include_odds=False)
    calls: list[str] = []
    validation = WorkflowActionResult(
        message="Current odds are missing.",
        blockers=("missing_current_odds_csv",),
        metadata={"serious_issue_count": 1, "warning_count": 0},
    )

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, validation=validation, archive_count=0),
    )

    assert result["status"] == "Needs odds"
    assert "best_bets" not in calls
    assert not paths["current_odds_path"].exists()
    assert result["summary"]["receipt_verification_verdict"] == (
        "Weekly pipeline receipt not ready"
    )
    assert result["summary"]["receipt_verification_status"] == "Not ready"
    assert result["summary"]["receipt_verification_mismatch_count"] == 0
    verification_step = next(
        step
        for step in result["summary"]["steps"]
        if step["step"] == "Weekly pipeline receipt verification"
    )
    assert verification_step["status"] == "Completed with warnings"


def test_archive_corruption_is_surfaced_without_crashing(tmp_path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []
    original = weekly_pipeline_module.save_prepared_epl_weekly_pipeline_history

    def save_then_corrupt(*args, **kwargs):
        result = original(*args, **kwargs)
        Path(result["archive_dir"], "epl_weekly_pipeline.md").write_text(
            "# Corrupted after archive\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(
        weekly_pipeline_module,
        "save_prepared_epl_weekly_pipeline_history",
        save_then_corrupt,
    )

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls),
    )

    assert result["status"] == "Failed"
    assert result["summary"]["receipt_verification_verdict"] == (
        "Weekly pipeline receipt changed"
    )
    assert result["summary"]["receipt_verification_status"] == "Failed"
    assert result["summary"]["receipt_verification_mismatch_count"] >= 1
    assert any(
        step["step"] == "Weekly pipeline receipt verification"
        and step["status"] == "Failed"
        for step in result["summary"]["steps"]
    )
    assert any(
        "Archive verification failed closed" in blocker
        for blocker in result["summary"]["key_blockers"]
    )


def test_unexpected_receipt_verification_error_is_reported_without_crashing(
    tmp_path,
    monkeypatch,
) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    def fail_verification(**_kwargs):
        raise RuntimeError("verification writer broke")

    monkeypatch.setattr(
        weekly_pipeline_module,
        "save_epl_weekly_pipeline_receipt_verification",
        fail_verification,
    )

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls),
    )

    assert result["status"] == "Failed"
    assert result["summary"]["receipt_verification_verdict"] == (
        "Weekly pipeline receipt verification failed"
    )
    assert result["summary"]["receipt_verification_status"] == "Failed"
    assert result["summary"]["receipt_verification_mismatch_count"] == 1
    assert any(
        "verification writer broke" in blocker
        for blocker in result["summary"]["key_blockers"]
    )


def test_stale_core_data_blocks_card_with_needs_data_refresh(tmp_path) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, freshness_ready=False, archive_count=0),
    )

    assert result["status"] == "Needs data refresh"
    assert "best_bets" not in calls
    assert any("Core data is not fresh" in item for item in result["summary"]["key_blockers"])


def test_validation_warning_generates_card_with_warning_status(tmp_path) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []
    validation = WorkflowActionResult(
        message="Validation found one warning.",
        warnings=("Missing book on one row.",),
        metadata={"serious_issue_count": 0, "warning_count": 1},
    )

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, validation=validation),
    )

    assert result["status"] == "Card generated with warnings"
    assert "best_bets" in calls
    assert result["summary"]["key_warnings"] == ["Missing book on one row."]


def test_unexpected_report_error_marks_pipeline_failed(tmp_path) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []

    result = run_epl_weekly_pipeline(
        **paths,
        run_at=FIXED_RUN_AT,
        actions=_actions(calls, tier_error=RuntimeError("tier report broke")),
    )

    assert result["status"] == "Failed"
    assert any(
        step["step"] == "Tier performance report" and step["status"] == "Failed"
        for step in result["summary"]["steps"]
    )
    assert result["json"].exists()


def test_dashboard_action_delegates_to_report_only_pipeline(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "outputs"
    expected = {"status": "Ready for card review", "summary": {}}
    calls: list[object] = []

    def fake_pipeline(*, output_dir, progress):
        calls.extend([output_dir, progress])
        return expected

    progress = lambda *_args: None
    monkeypatch.setattr(weekly_pipeline_module, "run_epl_weekly_pipeline", fake_pipeline)

    result = dashboard_actions.run_epl_weekly_pipeline(output_dir, progress=progress)

    assert result == expected
    assert calls == [output_dir, progress]


def test_dashboard_home_exposes_weekly_pipeline_button_and_summary() -> None:
    app_source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")

    assert '"Run Weekly EPL Pipeline"' in app_source
    assert '"Latest Weekly EPL Pipeline"' in app_source
    assert '"epl_weekly_pipeline.md"' in app_source
    assert "receipt_verification_verdict" in app_source
    assert "receipt_verification_mismatch_count" in app_source
    assert "apply_epl_weekly_pipeline" not in app_source
