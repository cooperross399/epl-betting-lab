from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, PROCESSED_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import atomic_write_report
from epl_betting_lab.reports.bet_ledger import (
    load_bet_ledger,
    save_bet_ledger_reports,
    summarize_overall,
)
from epl_betting_lab.reports.bet_ledger_health import (
    SERIOUS_SEVERITIES,
    build_bet_ledger_health_check,
    save_bet_ledger_health_check,
)
from epl_betting_lab.reports.current_odds_validation import CurrentOddsValidationError
from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    PIPELINE_ARCHIVE_CSV_FILENAME,
    PIPELINE_ARCHIVE_JSON_FILENAME,
    PIPELINE_ARCHIVE_MARKDOWN_FILENAME,
    PIPELINE_COMPARISON_CSV_FILENAME,
    PIPELINE_COMPARISON_JSON_FILENAME,
    PIPELINE_COMPARISON_MARKDOWN_FILENAME,
    prepare_epl_weekly_pipeline_history,
    save_prepared_epl_weekly_pipeline_history,
)
from epl_betting_lab.reports.epl_weekly_pipeline_receipt_verification import (
    VERIFICATION_MARKDOWN_FILENAME,
    save_epl_weekly_pipeline_receipt_verification,
)
from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar import (
    SIDECAR_ARCHIVED_VERDICT,
    SIDECAR_FAILED_VERDICT,
    SIDECAR_MARKDOWN_FILENAME,
    SIDECAR_NOT_READY_VERDICT,
    save_epl_weekly_pipeline_verification_sidecar,
)
from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar_verification import (
    SIDECAR_VERIFICATION_MARKDOWN_FILENAME,
    save_epl_weekly_pipeline_verification_sidecar_verification,
)
from epl_betting_lab.reports.thursday_best_bets import list_recent_thursday_archives
from epl_betting_lab.reports.thursday_decision_queue import ACTION_PRIORITY
from epl_betting_lab.scheduled_thursday_workflow import (
    ScheduledWorkflowContext,
    WorkflowActionResult,
    default_scheduled_workflow_actions,
)
from epl_betting_lab.workflow_status import (
    build_data_freshness_checks,
    build_data_freshness_status,
    recommend_data_freshness_action,
)


PIPELINE_JSON_FILENAME = "epl_weekly_pipeline.json"
PIPELINE_MARKDOWN_FILENAME = "epl_weekly_pipeline.md"
PIPELINE_CSV_FILENAME = "epl_weekly_pipeline.csv"

FINAL_STATUSES = (
    "Ready for card review",
    "Needs odds",
    "Needs odds fixes",
    "Needs data refresh",
    "Card generated with warnings",
    "Blocked",
    "Failed",
)
STEP_STATUSES = (
    "Completed",
    "Completed with warnings",
    "Blocked",
    "Skipped",
    "Failed",
)
CARD_FRESHNESS_ITEMS = (
    "Historical results / Football-Data",
    "Upcoming fixtures",
)
EXPECTED_INPUT_ERRORS = (
    FileNotFoundError,
    OSError,
    UnicodeError,
    ValueError,
    pd.errors.EmptyDataError,
    pd.errors.ParserError,
    CurrentOddsValidationError,
)
RECEIPT_VERIFIED_VERDICT = "Weekly pipeline receipt verified"
RECEIPT_NOT_READY_VERDICT = "Weekly pipeline receipt not ready"
RECEIPT_PENDING_VERDICT = "Pending archive verification"
RECEIPT_ERROR_VERDICT = "Weekly pipeline receipt verification failed"
SIDECAR_VERIFIED_VERDICT = "Weekly verification sidecar verified"
SIDECAR_VERIFICATION_NOT_READY_VERDICT = "Weekly verification sidecar not ready"
SIDECAR_VERIFICATION_PENDING_VERDICT = "Pending sidecar verification"
SIDECAR_VERIFICATION_ERROR_VERDICT = "Weekly verification sidecar verification failed"


@dataclass(frozen=True)
class EplWeeklyPipelineActions:
    data_freshness: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    current_odds_validation: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    odds_completeness: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    thursday_best_bets: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    archive_count: Callable[[ScheduledWorkflowContext], int]
    comparison: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    decision_queue: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    ledger_health: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    ledger_summary: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    tier_performance: Callable[[ScheduledWorkflowContext], WorkflowActionResult]


def _json_safe(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is pd.NA:
        return None
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (AttributeError, TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if str(item).strip()))


def _run_data_freshness(context: ScheduledWorkflowContext) -> WorkflowActionResult:
    data_root = context.matches_path.parent.parent
    checks = build_data_freshness_checks(
        raw_dir=data_root / "raw",
        processed_dir=context.matches_path.parent,
        manual_dir=context.current_odds_path.parent,
        output_dir=context.output_dir,
    )
    freshness = build_data_freshness_status(checks, today=context.run_at.date())
    counts = freshness["status"].value_counts().to_dict() if not freshness.empty else {}
    statuses = (
        {
            str(row["item"]): str(row["status"])
            for _, row in freshness.iterrows()
        }
        if not freshness.empty
        else {}
    )
    card_inputs_ready = all(statuses.get(item) == "Fresh" for item in CARD_FRESHNESS_ITEMS)
    warnings: list[str] = []
    for item in (*CARD_FRESHNESS_ITEMS, "Current odds"):
        rows = freshness[freshness["item"] == item]
        if rows.empty:
            warnings.append(f"{item}: freshness was not checked.")
            continue
        row = rows.iloc[0]
        status = str(row.get("status", "Not checked"))
        note = str(row.get("note", "")).strip()
        warning = str(row.get("warning", "")).strip()
        if status != "Fresh":
            warnings.append(f"{item}: {status}. {note}")
        elif warning:
            warnings.append(f"{item}: {warning}")

    count_text = ", ".join(
        f"{status} {int(count)}" for status, count in sorted(counts.items())
    ) or "no freshness rows"
    return WorkflowActionResult(
        message=f"Data freshness checked ({count_text}).",
        warnings=tuple(warnings),
        metadata={
            "status_counts": {str(key): int(value) for key, value in counts.items()},
            "item_statuses": statuses,
            "card_input_statuses": {
                item: statuses.get(item, "Not checked") for item in CARD_FRESHNESS_ITEMS
            },
            "card_inputs_ready": card_inputs_ready,
            "recommended_action": recommend_data_freshness_action(freshness),
        },
    )


def _run_ledger_health(context: ScheduledWorkflowContext) -> WorkflowActionResult:
    ledger = load_bet_ledger(context.ledger_path)
    issues = build_bet_ledger_health_check(ledger)
    paths = save_bet_ledger_health_check(ledger, context.output_dir)
    severity = (
        issues["severity"].astype(str).str.lower()
        if not issues.empty and "severity" in issues.columns
        else pd.Series(dtype=str)
    )
    error_count = int((severity == "error").sum())
    warning_count = int((severity == "warning").sum())
    info_count = int((severity == "info").sum())
    serious_count = int(severity.isin(SERIOUS_SEVERITIES).sum())
    warnings = (
        (f"Bet ledger health found {serious_count} issue(s) that need review.",)
        if serious_count
        else ()
    )
    return WorkflowActionResult(
        outputs=paths,
        message=(
            f"Bet ledger health found {error_count} error(s), "
            f"{warning_count} warning(s), and {info_count} optional item(s)."
        ),
        warnings=warnings,
        metadata={
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "serious_issue_count": serious_count,
        },
    )


def _run_ledger_summary(context: ScheduledWorkflowContext) -> WorkflowActionResult:
    ledger = load_bet_ledger(context.ledger_path)
    overall = summarize_overall(ledger)
    paths = save_bet_ledger_reports(ledger, context.output_dir)
    return WorkflowActionResult(
        outputs=paths,
        message=(
            f"Ledger summary generated for {int(overall['tracked_bets'])} tracked bet(s), "
            f"including {int(overall['pending_bets'])} pending."
        ),
        metadata={str(key): _json_safe(value) for key, value in overall.items()},
    )


def _run_decision_queue(context: ScheduledWorkflowContext) -> WorkflowActionResult:
    scheduled = default_scheduled_workflow_actions()
    result = scheduled.decision_queue(context)
    csv_path = result.outputs.get("csv")
    queue = pd.read_csv(csv_path) if csv_path and csv_path.exists() else pd.DataFrame()
    counts = (
        queue["action_needed"].astype(str).value_counts().to_dict()
        if not queue.empty and "action_needed" in queue.columns
        else {}
    )
    return WorkflowActionResult(
        outputs=result.outputs,
        message=result.message,
        warnings=result.warnings,
        blockers=result.blockers,
        metadata={
            **result.metadata,
            "total_rows": int(len(queue)),
            "action_counts": {str(key): int(value) for key, value in counts.items()},
        },
    )


def default_epl_weekly_pipeline_actions() -> EplWeeklyPipelineActions:
    scheduled = default_scheduled_workflow_actions()
    return EplWeeklyPipelineActions(
        data_freshness=_run_data_freshness,
        current_odds_validation=scheduled.current_odds_validation,
        odds_completeness=scheduled.odds_completeness,
        thursday_best_bets=scheduled.thursday_best_bets,
        archive_count=scheduled.archive_count,
        comparison=scheduled.comparison,
        decision_queue=_run_decision_queue,
        ledger_health=_run_ledger_health,
        ledger_summary=_run_ledger_summary,
        tier_performance=scheduled.tier_performance,
    )


def _completeness_gate(result: WorkflowActionResult | None) -> tuple[bool, str]:
    if result is None:
        return False, "Odds completeness could not be checked."
    if result.blockers:
        return False, "Odds completeness reported blocking issues."
    metadata = result.metadata
    required = (
        "completion_percentage",
        "total_rows",
        "rows_missing_odds",
        "rows_non_numeric_odds",
        "missing_expected_rows",
        "matches_incomplete",
    )
    missing = [name for name in required if name not in metadata]
    if missing:
        return False, "Odds completeness is missing gate fields: " + ", ".join(missing)
    try:
        completion = float(metadata["completion_percentage"])
        total_rows = int(metadata["total_rows"])
        issue_total = sum(
            int(metadata[name])
            for name in (
                "rows_missing_odds",
                "rows_non_numeric_odds",
                "missing_expected_rows",
                "matches_incomplete",
            )
        )
    except (TypeError, ValueError):
        return False, "Odds completeness gate values are malformed."
    if total_rows <= 0:
        return False, "No current odds rows are available."
    if completion < 0.999999 or issue_total:
        return (
            False,
            f"Odds are {completion:.1%} complete with {issue_total} blocking completeness item(s).",
        )
    return True, "Odds are 100% complete for the expected fixture and market rows."


def _card_counts(result: WorkflowActionResult | None) -> dict[str, int]:
    counts = {"best_bets": 0, "leans": 0, "passes": 0, "total_candidates": 0}
    if result is None:
        return counts
    csv_path = result.outputs.get("csv")
    if csv_path is None or not csv_path.exists():
        return counts
    try:
        report = pd.read_csv(csv_path)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return counts
    counts["total_candidates"] = int(len(report))
    if "section" not in report.columns:
        return counts
    sections = report["section"].astype(str)
    counts["best_bets"] = int((sections == "Best bets").sum())
    counts["leans"] = int((sections == "Leans").sum())
    counts["passes"] = int((sections == "Passes / notable avoids").sum())
    return counts


def _recommended_next_action(status: str) -> str:
    recommendations = {
        "Ready for card review": (
            "Review the generated Thursday card and decision queue manually. Confirm every "
            "sportsbook price before deciding whether to bet."
        ),
        "Card generated with warnings": (
            "Review the warnings, ledger health, prices, and decision queue before trusting "
            "the card. Nothing was placed automatically."
        ),
        "Needs odds": (
            "Create or import real current odds, fill every sportsbook price and book, then "
            "rerun `python scripts/run_epl_weekly_pipeline.py`."
        ),
        "Needs odds fixes": (
            "Fix the issues in current odds validation and completeness, run "
            "`python scripts/validate_current_odds.py`, then rerun the weekly pipeline."
        ),
        "Needs data refresh": (
            "Refresh historical results or upcoming fixtures shown in the freshness step, "
            "then rerun the weekly pipeline before reviewing a card."
        ),
        "Blocked": (
            "Review the blocked steps and report paths below, fix their prerequisites, then "
            "rerun the weekly pipeline without force mode."
        ),
        "Failed": (
            "Review the failed step and error message, fix the unexpected problem, then rerun "
            "the weekly pipeline."
        ),
    }
    return recommendations[status]


def _render_markdown(summary: dict[str, object]) -> str:
    steps = pd.DataFrame(summary["steps"])
    table = steps[["step", "status", "message", "outputs"]].copy()
    table["outputs"] = table["outputs"].apply(
        lambda paths: "<br>".join(f"`{path}`" for path in paths) if paths else ""
    )
    counts = summary["card_counts"]
    queue_counts = summary["decision_queue_counts"]
    ledger = summary["ledger_summary"]
    health = summary["ledger_health_summary"]
    lines = [
        "# EPL Weekly Operations Pipeline",
        "",
        (
            "This pipeline only reads project inputs and generates reports. It never uses "
            "force mode, edits protected manual files, imports odds, applies settlement, "
            "archives stale odds, rolls files back, promotes staging, runs live providers, "
            "allowlists providers, enables cron, fabricates odds, or places bets."
        ),
        "",
        "## Final summary",
        "",
        f"- Run timestamp: {summary['run_timestamp']}",
        f"- Final status: **{summary['status']}**",
        f"- Pipeline receipt ID: `{summary['pipeline_receipt_id']}`",
        f"- Pipeline archive: `{summary['pipeline_archive_path']}`",
        f"- Archive receipt ID: `{summary.get('archive_receipt_id') or 'Not available'}`",
        f"- Archive path: `{summary.get('archive_path') or 'Not available'}`",
        (
            "- Receipt verification: "
            f"**{summary.get('receipt_verification_verdict') or 'Not checked'}**"
        ),
        (
            "- Receipt verification mismatches: "
            f"{int(summary.get('receipt_verification_mismatch_count', 0) or 0)}"
        ),
        (
            "- Verification sidecar: "
            f"**{summary.get('verification_sidecar_verdict') or 'Not archived'}**"
        ),
        (
            "- Verification sidecar receipt ID: "
            f"`{summary.get('verification_sidecar_receipt_id') or 'Not available'}`"
        ),
        (
            "- Verification sidecar archive: "
            f"`{summary.get('verification_sidecar_archive_path') or 'Not available'}`"
        ),
        (
            "- Sidecar verification: "
            f"**{summary.get('sidecar_verification_verdict') or 'Not checked'}**"
        ),
        (
            "- Sidecar verification status: "
            f"{summary.get('sidecar_verification_status') or 'Not checked'}"
        ),
        (
            "- Sidecar verification receipt IDs: "
            f"`{summary.get('sidecar_verification_original_id') or 'Not available'}` / "
            f"`{summary.get('sidecar_verification_recalculated_id') or 'Not available'}`"
        ),
        (
            "- Sidecar verification mismatches: "
            f"{int(summary.get('sidecar_verification_mismatch_count', 0) or 0)}"
        ),
        (
            "- Sidecar verification report: "
            f"`{summary.get('sidecar_verification_report_path') or 'Not available'}`"
        ),
        (
            "- Sidecar archive checked: "
            f"`{summary.get('sidecar_verification_archive_path') or 'Not available'}`"
        ),
        f"- Latest pipeline comparison: **{summary['pipeline_comparison_verdict']}**",
        f"- Recommended next human action: {summary['recommended_next_action']}",
        (
            f"- Thursday card: {counts['best_bets']} best bet(s), {counts['leans']} lean(s), "
            f"{counts['passes']} pass/avoid row(s), {counts['total_candidates']} total candidate(s)."
        ),
        f"- Decision queue: {sum(queue_counts.values())} changed play(s).",
        (
            "- Ledger health: "
            f"{health.get('error_count', 0)} error(s), "
            f"{health.get('warning_count', 0)} warning(s), "
            f"{health.get('info_count', 0)} optional item(s)."
        ),
        (
            "- Ledger results: "
            f"{ledger.get('tracked_bets', 0)} tracked, "
            f"{ledger.get('pending_bets', 0)} pending, "
            f"{ledger.get('profit_units', 0.0)}u, "
            f"{float(ledger.get('roi', 0.0) or 0.0):.1%} ROI."
        ),
        "",
        "## Pipeline steps",
        "",
        table.to_markdown(index=False),
        "",
        "## Decision queue counts",
        "",
    ]
    lines.extend(
        [f"- {action}: {int(queue_counts.get(action, 0))}" for action in ACTION_PRIORITY]
        if queue_counts
        else ["- No current decision queue rows."]
    )
    lines.extend(["", "## Key blockers", ""])
    lines.extend([f"- {item}" for item in summary["key_blockers"]] or ["- None."])
    lines.extend(["", "## Key warnings", ""])
    lines.extend([f"- {item}" for item in summary["key_warnings"]] or ["- None."])
    lines.extend(["", "## Important changes since the previous run", ""])
    lines.extend(
        [f"- {item}" for item in summary["important_changes_since_previous_run"]]
        or ["- No comparison detail is available."]
    )
    lines.extend(["", "## Generated report paths", ""])
    lines.extend(
        [f"- `{path}`" for path in summary["generated_report_paths"]]
        or ["- No report outputs were generated."]
    )
    lines.extend(
        [
            "",
            "## Human review remains required",
            "",
            (
                "A Ready status means the report package is ready to inspect. It is not a "
                "bet slip, approval, or guarantee. Check current prices, risk flags, and "
                "the max-juice guard around -160 before making any manual decision."
            ),
        ]
    )
    return "\n".join(lines)


def _render_step_csv(
    steps: list[dict[str, object]],
    summary: dict[str, object],
) -> bytes:
    verification_fields = {
        "archive_receipt_id": summary.get("archive_receipt_id", ""),
        "archive_path": summary.get("archive_path", ""),
        "receipt_verification_verdict": summary.get(
            "receipt_verification_verdict", ""
        ),
        "receipt_verification_status": summary.get(
            "receipt_verification_status", ""
        ),
        "receipt_verification_original_id": summary.get(
            "receipt_verification_original_id", ""
        ),
        "receipt_verification_recalculated_id": summary.get(
            "receipt_verification_recalculated_id", ""
        ),
        "receipt_verification_mismatch_count": int(
            summary.get("receipt_verification_mismatch_count", 0) or 0
        ),
        "receipt_verification_report_path": summary.get(
            "receipt_verification_report_path", ""
        ),
        "verification_sidecar_verdict": summary.get(
            "verification_sidecar_verdict", ""
        ),
        "verification_sidecar_receipt_id": summary.get(
            "verification_sidecar_receipt_id", ""
        ),
        "verification_sidecar_archive_path": summary.get(
            "verification_sidecar_archive_path", ""
        ),
        "verification_sidecar_report_path": summary.get(
            "verification_sidecar_report_path", ""
        ),
        "sidecar_verification_verdict": summary.get(
            "sidecar_verification_verdict", ""
        ),
        "sidecar_verification_status": summary.get(
            "sidecar_verification_status", ""
        ),
        "sidecar_verification_original_id": summary.get(
            "sidecar_verification_original_id", ""
        ),
        "sidecar_verification_recalculated_id": summary.get(
            "sidecar_verification_recalculated_id", ""
        ),
        "sidecar_verification_mismatch_count": int(
            summary.get("sidecar_verification_mismatch_count", 0) or 0
        ),
        "sidecar_verification_report_path": summary.get(
            "sidecar_verification_report_path", ""
        ),
        "sidecar_verification_archive_path": summary.get(
            "sidecar_verification_archive_path", ""
        ),
    }
    rows = []
    for step in steps:
        rows.append(
            {
                **verification_fields,
                "step": step["step"],
                "status": step["status"],
                "message": step["message"],
                "warnings": " | ".join(step["warnings"]),
                "blockers": " | ".join(step["blockers"]),
                "outputs": " | ".join(step["outputs"]),
                "metadata_json": json.dumps(step["metadata"], sort_keys=True),
            }
        )
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def _write_live_pipeline_outputs(
    summary: dict[str, object],
    *,
    json_path: Path,
    markdown_path: Path,
    csv_path: Path,
) -> dict[str, object]:
    safe_value = _json_safe(summary)
    if not isinstance(safe_value, dict):
        raise TypeError("Weekly pipeline summary must serialize to a JSON object.")
    atomic_write_report(
        json_path,
        (json.dumps(safe_value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        (_render_markdown(safe_value) + "\n").encode("utf-8"),
    )
    atomic_write_report(csv_path, _render_step_csv(summary["steps"], safe_value))
    return safe_value


def run_epl_weekly_pipeline(
    *,
    current_odds_path: Path | None = None,
    fixtures_path: Path | None = None,
    matches_path: Path | None = None,
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
    actions: EplWeeklyPipelineActions | None = None,
    progress: Callable[[str, str, str], None] | None = None,
) -> dict[str, object]:
    """Run the complete report-only weekly workflow without force or apply actions."""
    repository_root = (repository_root or PROJECT_ROOT).resolve()
    selected_output_dir = output_dir or OUTPUTS_DIR
    if not selected_output_dir.is_absolute():
        selected_output_dir = (repository_root / selected_output_dir).resolve(strict=False)

    def resolve_input(path: Path | None, default: Path) -> Path:
        selected = path or default
        return (
            selected.resolve(strict=False)
            if selected.is_absolute()
            else (repository_root / selected).resolve(strict=False)
        )

    context = ScheduledWorkflowContext(
        current_odds_path=resolve_input(current_odds_path, MANUAL_DIR / "current_odds.csv"),
        fixtures_path=resolve_input(fixtures_path, MANUAL_DIR / "upcoming_fixtures.csv"),
        matches_path=resolve_input(matches_path, PROCESSED_DIR / "epl_historical_matches.csv"),
        ledger_path=resolve_input(ledger_path, MANUAL_DIR / "bet_ledger.csv"),
        output_dir=selected_output_dir,
        run_at=run_at or datetime.now().astimezone(),
    )
    actions = actions or default_epl_weekly_pipeline_actions()
    steps: list[dict[str, object]] = []
    warnings: list[str] = []
    blockers: list[str] = []
    output_files: list[str] = []
    unexpected_failure = False

    def add_step(
        name: str,
        status: str,
        message: str,
        result: WorkflowActionResult | None = None,
    ) -> None:
        if status not in STEP_STATUSES:
            raise ValueError(f"Unexpected weekly pipeline step status: {status}")
        step_warnings = list(result.warnings) if result else []
        step_blockers = list(result.blockers) if result else []
        paths = [str(path) for path in result.outputs.values()] if result else []
        steps.append(
            {
                "step": name,
                "status": status,
                "message": message,
                "warnings": step_warnings,
                "blockers": step_blockers,
                "outputs": paths,
                "metadata": _json_safe(result.metadata) if result else {},
            }
        )
        output_files.extend(paths)
        if progress is not None:
            progress(name, status, message)

    def perform(
        name: str,
        action: Callable[[ScheduledWorkflowContext], WorkflowActionResult],
        *,
        block_on_result: bool = False,
        expected_failure_is_blocking: bool = True,
    ) -> WorkflowActionResult | None:
        nonlocal unexpected_failure
        if progress is not None:
            progress(name, "Running", f"Running {name.lower()}.")
        try:
            result = action(context)
        except EXPECTED_INPUT_ERRORS as exc:
            message = str(exc) or f"{name} could not read its required input."
            if expected_failure_is_blocking:
                blockers.append(message)
                add_step(name, "Blocked", message)
            else:
                warnings.append(message)
                add_step(name, "Blocked", message)
            return None
        except Exception as exc:
            unexpected_failure = True
            message = f"Unexpected error: {exc}"
            blockers.append(f"{name}: {message}")
            add_step(name, "Failed", message)
            return None

        warnings.extend(result.warnings)
        blockers.extend(result.blockers)
        if block_on_result and result.blockers:
            status = "Blocked"
        elif result.warnings:
            status = "Completed with warnings"
        else:
            status = "Completed"
        add_step(name, status, result.message, result)
        return result

    freshness = perform("Data freshness / workflow status", actions.data_freshness)
    validation = perform(
        "Current odds validation",
        actions.current_odds_validation,
        block_on_result=True,
    )
    completeness = perform("Current odds completeness", actions.odds_completeness)

    freshness_ready = bool(
        freshness
        and not freshness.blockers
        and freshness.metadata.get("card_inputs_ready")
    )
    validation_ready = bool(validation and not validation.blockers)
    completeness_ready, completeness_note = _completeness_gate(completeness)
    gate_reasons: list[str] = []
    if not freshness_ready:
        statuses = freshness.metadata.get("card_input_statuses", {}) if freshness else {}
        gate_reasons.append(f"Core data is not fresh: {statuses or 'freshness unavailable'}.")
    if not context.current_odds_path.exists():
        gate_reasons.append("Current odds are missing.")
    if not validation_ready:
        gate_reasons.append("Serious current-odds validation issues exist or validation failed.")
    if not completeness_ready:
        gate_reasons.append(completeness_note)

    best_bets: WorkflowActionResult | None = None
    if unexpected_failure:
        add_step(
            "Thursday best-bets generation",
            "Skipped",
            "Skipped because a required preflight step failed unexpectedly.",
        )
    elif gate_reasons:
        message = "Card generation blocked safely: " + " ".join(gate_reasons)
        blockers.extend(gate_reasons)
        add_step("Thursday best-bets generation", "Blocked", message)
    else:
        best_bets = perform(
            "Thursday best-bets generation",
            actions.thursday_best_bets,
            block_on_result=True,
        )
        if best_bets is not None and best_bets.blockers:
            best_bets = None

    archive_ready = False
    if best_bets is None:
        add_step(
            "Thursday report archive",
            "Skipped",
            "Skipped because this run did not generate a new Thursday card.",
        )
    else:
        archive_outputs = {
            key: best_bets.outputs[key]
            for key in ("archive_csv", "archive_markdown", "archive_metadata")
            if key in best_bets.outputs
        }
        archive_result = WorkflowActionResult(
            outputs=archive_outputs,
            message="The generated Thursday card was saved as a dated archive snapshot.",
        )
        if len(archive_outputs) == 3:
            archive_ready = True
            add_step("Thursday report archive", "Completed", archive_result.message, archive_result)
        else:
            unexpected_failure = True
            blockers.append("The Thursday card generated without all three expected archive files.")
            add_step(
                "Thursday report archive",
                "Failed",
                "The card generated, but its CSV, markdown, and metadata archive set is incomplete.",
                archive_result,
            )

    archive_count = 0
    try:
        archive_count = int(actions.archive_count(context))
    except EXPECTED_INPUT_ERRORS as exc:
        warnings.append(f"Thursday archive history could not be checked: {exc}")
        add_step(
            "Thursday archive history check",
            "Blocked",
            f"Archive history could not be checked: {exc}",
        )
    except Exception as exc:
        unexpected_failure = True
        blockers.append(f"Thursday archive history check: Unexpected error: {exc}")
        add_step(
            "Thursday archive history check",
            "Failed",
            f"Unexpected error: {exc}",
        )
    else:
        add_step(
            "Thursday archive history check",
            "Completed",
            f"Found {archive_count} recent Thursday archive snapshot(s).",
        )

    comparison: WorkflowActionResult | None = None
    if archive_count < 2:
        add_step(
            "Thursday best-bets comparison",
            "Skipped",
            "At least two archived Thursday cards are required; this is normal for the first snapshot.",
        )
    else:
        comparison = perform(
            "Thursday best-bets comparison",
            actions.comparison,
            expected_failure_is_blocking=False,
        )

    decision_queue: WorkflowActionResult | None = None
    if comparison is None:
        add_step(
            "Thursday decision queue",
            "Skipped",
            "Skipped because no fresh comparison report was generated.",
        )
    else:
        decision_queue = perform(
            "Thursday decision queue",
            actions.decision_queue,
            expected_failure_is_blocking=False,
        )

    ledger_health: WorkflowActionResult | None = None
    ledger_summary: WorkflowActionResult | None = None
    if not context.ledger_path.exists():
        ledger_message = (
            f"Bet ledger is missing at {context.ledger_path}; ledger reports were skipped "
            "without creating or editing it."
        )
        warnings.append(ledger_message)
        add_step("Bet ledger health check", "Skipped", ledger_message)
        add_step("Bet ledger summary", "Skipped", ledger_message)
    else:
        ledger_health = perform(
            "Bet ledger health check",
            actions.ledger_health,
            expected_failure_is_blocking=False,
        )
        ledger_summary = perform(
            "Bet ledger summary",
            actions.ledger_summary,
            expected_failure_is_blocking=False,
        )

    perform(
        "Tier performance report",
        actions.tier_performance,
        expected_failure_is_blocking=False,
    )

    card_generated = best_bets is not None and archive_ready
    if unexpected_failure:
        final_status = "Failed"
    elif not context.current_odds_path.exists():
        final_status = "Needs odds"
    elif not freshness_ready:
        final_status = "Needs data refresh"
    elif not validation_ready or not completeness_ready:
        final_status = "Needs odds fixes"
    elif blockers or not card_generated:
        final_status = "Blocked"
    elif warnings:
        final_status = "Card generated with warnings"
    else:
        final_status = "Ready for card review"
    if final_status not in FINAL_STATUSES:
        raise ValueError(f"Unexpected EPL weekly pipeline status: {final_status}")

    card_counts = _card_counts(best_bets)
    queue_counts = (
        {
            str(key): int(value)
            for key, value in decision_queue.metadata.get("action_counts", {}).items()
        }
        if decision_queue
        else {}
    )
    ledger_health_summary = dict(ledger_health.metadata) if ledger_health else {}
    ledger_overall = dict(ledger_summary.metadata) if ledger_summary else {}

    json_path = context.output_dir / PIPELINE_JSON_FILENAME
    markdown_path = context.output_dir / PIPELINE_MARKDOWN_FILENAME
    csv_path = context.output_dir / PIPELINE_CSV_FILENAME
    history_output_paths = [
        context.output_dir / PIPELINE_ARCHIVE_JSON_FILENAME,
        context.output_dir / PIPELINE_ARCHIVE_MARKDOWN_FILENAME,
        context.output_dir / PIPELINE_ARCHIVE_CSV_FILENAME,
        context.output_dir / PIPELINE_COMPARISON_JSON_FILENAME,
        context.output_dir / PIPELINE_COMPARISON_MARKDOWN_FILENAME,
        context.output_dir / PIPELINE_COMPARISON_CSV_FILENAME,
    ]
    output_files.extend(
        [str(json_path), str(markdown_path), str(csv_path)]
        + [str(path) for path in history_output_paths]
    )
    summary = {
        "run_timestamp": context.run_at.isoformat(timespec="seconds"),
        "status": final_status,
        "steps_run": [
            str(step["step"])
            for step in steps
            if step["status"] not in {"Skipped", "Blocked"}
        ],
        "steps_skipped": [
            str(step["step"]) for step in steps if step["status"] == "Skipped"
        ],
        "steps_blocked": [
            str(step["step"]) for step in steps if step["status"] == "Blocked"
        ],
        "key_blockers": _dedupe(blockers),
        "key_warnings": _dedupe(warnings),
        "generated_report_paths": _dedupe(output_files),
        "card_counts": card_counts,
        "decision_queue_counts": queue_counts,
        "ledger_health_summary": _json_safe(ledger_health_summary),
        "ledger_summary": _json_safe(ledger_overall),
        "archive_count": archive_count,
        "new_archive_created": archive_ready,
        "recommended_next_action": _recommended_next_action(final_status),
        "safety": {
            "force_mode_used": False,
            "settlement_applied": False,
            "manual_files_edited": False,
            "staging_promoted": False,
            "live_provider_run": False,
            "provider_allowlisted": False,
            "cron_enabled": False,
            "bets_placed": False,
        },
        "steps": steps,
    }
    history_plan = prepare_epl_weekly_pipeline_history(
        summary,
        output_dir=context.output_dir,
        archived_at=context.run_at,
    )
    summary.update(
        {
            "pipeline_receipt_id": history_plan["manifest"]["receipt_id"],
            "pipeline_receipt_checksum_sha256": history_plan["manifest"][
                "receipt_checksum_sha256"
            ],
            "pipeline_archive_path": str(history_plan["archive_dir"]),
            "pipeline_comparison_verdict": history_plan["comparison"]["verdict"],
            "pipeline_comparison_path": str(
                context.output_dir / PIPELINE_COMPARISON_MARKDOWN_FILENAME
            ),
            "important_changes_since_previous_run": history_plan["comparison"][
                "important_changes"
            ],
            "archive_receipt_id": history_plan["manifest"]["receipt_id"],
            "archive_path": str(history_plan["archive_dir"]),
            "receipt_verification_verdict": RECEIPT_PENDING_VERDICT,
            "receipt_verification_status": "Pending",
            "receipt_verification_original_id": "",
            "receipt_verification_recalculated_id": "",
            "receipt_verification_mismatch_count": 0,
            "receipt_verification_report_path": str(
                context.output_dir / VERIFICATION_MARKDOWN_FILENAME
            ),
            "verification_sidecar_verdict": "Pending verification sidecar",
            "verification_sidecar_receipt_id": "",
            "verification_sidecar_archive_path": "",
            "verification_sidecar_report_path": str(
                context.output_dir / SIDECAR_MARKDOWN_FILENAME
            ),
            "sidecar_verification_verdict": SIDECAR_VERIFICATION_PENDING_VERDICT,
            "sidecar_verification_status": "Pending",
            "sidecar_verification_original_id": "",
            "sidecar_verification_recalculated_id": "",
            "sidecar_verification_mismatch_count": 0,
            "sidecar_verification_report_path": str(
                context.output_dir / SIDECAR_VERIFICATION_MARKDOWN_FILENAME
            ),
            "sidecar_verification_archive_path": "",
        }
    )
    # Seal the canonical receipt before adding its own verification result.
    safe_summary = _write_live_pipeline_outputs(
        summary,
        json_path=json_path,
        markdown_path=markdown_path,
        csv_path=csv_path,
    )
    history_result = save_prepared_epl_weekly_pipeline_history(
        history_plan,
        pipeline_summary=safe_summary,
        pipeline_markdown_path=markdown_path,
        pipeline_csv_path=csv_path,
    )

    verification_result: dict[str, object] | None = None
    verification_verdict = RECEIPT_ERROR_VERDICT
    verification_status = "Failed"
    verification_original_id = ""
    verification_recalculated_id = ""
    verification_mismatch_count = 1
    verification_report_path = ""
    if progress is not None:
        progress(
            "Weekly pipeline receipt verification",
            "Running",
            "Verifying the archive created by this weekly run.",
        )
    try:
        verification_result = save_epl_weekly_pipeline_receipt_verification(
            archive_path=Path(history_result["archive_dir"]),
            output_dir=context.output_dir,
            generated_at=context.run_at,
        )
        verification_summary = verification_result.get("summary", {})
        if not isinstance(verification_summary, dict):
            raise ValueError("Receipt verification returned a malformed summary.")
        verification_verdict = str(
            verification_summary.get("verdict", RECEIPT_ERROR_VERDICT)
        ).strip()
        verification_original_id = str(
            verification_summary.get("original_receipt_id", "")
        ).strip()
        verification_recalculated_id = str(
            verification_summary.get("recalculated_receipt_id", "")
        ).strip()
        verification_mismatch_count = int(
            verification_summary.get("mismatch_count", 0) or 0
        )
        verification_report_path = str(verification_result.get("markdown", ""))
        verification_outputs = {
            key: Path(value)
            for key, value in verification_result.items()
            if key in {"json", "markdown", "csv"} and value
        }

        if verification_verdict == RECEIPT_VERIFIED_VERDICT:
            verification_status = "Verified"
            step_status = "Completed"
            verification_message = (
                "The newly created weekly pipeline archive passed receipt verification."
            )
            verification_warnings: tuple[str, ...] = ()
            verification_blockers: tuple[str, ...] = ()
        elif verification_verdict == RECEIPT_NOT_READY_VERDICT:
            verification_status = "Not ready"
            step_status = "Completed with warnings"
            verification_message = (
                "The archive is structurally consistent, but this weekly run was not ready "
                "for card review."
            )
            verification_warnings = (verification_message,)
            verification_blockers = ()
            warnings.append(verification_message)
        else:
            verification_status = "Failed"
            step_status = "Failed"
            verification_message = (
                f"Archive verification failed closed: {verification_verdict}."
            )
            verification_warnings = ()
            verification_blockers = (verification_message,)
            blockers.append(verification_message)
            final_status = "Failed"

        add_step(
            "Weekly pipeline receipt verification",
            step_status,
            verification_message,
            WorkflowActionResult(
                outputs=verification_outputs,
                message=verification_message,
                warnings=verification_warnings,
                blockers=verification_blockers,
                metadata={
                    "archive_path": str(history_result["archive_dir"]),
                    "archive_receipt_id": history_result["receipt_id"],
                    "verdict": verification_verdict,
                    "original_receipt_id": verification_original_id,
                    "recalculated_receipt_id": verification_recalculated_id,
                    "mismatch_count": verification_mismatch_count,
                },
            ),
        )
    except Exception as exc:
        final_status = "Failed"
        verification_message = f"Receipt verification failed unexpectedly: {exc}"
        blockers.append(verification_message)
        add_step(
            "Weekly pipeline receipt verification",
            "Failed",
            verification_message,
            WorkflowActionResult(
                message=verification_message,
                blockers=(verification_message,),
                metadata={
                    "archive_path": str(history_result["archive_dir"]),
                    "archive_receipt_id": history_result["receipt_id"],
                    "verdict": verification_verdict,
                    "mismatch_count": verification_mismatch_count,
                },
            ),
        )

    sidecar_result: dict[str, object] | None = None
    sidecar_verdict = SIDECAR_FAILED_VERDICT
    sidecar_receipt_id = ""
    sidecar_archive_path = ""
    sidecar_report_path = ""
    if progress is not None:
        progress(
            "Weekly pipeline verification sidecar",
            "Running",
            "Archiving the automatic receipt verification as a checksum-bound sidecar.",
        )
    try:
        verification_paths: dict[str, Path | None] = {}
        for key in ("json", "markdown", "csv"):
            value = verification_result.get(key) if verification_result else None
            verification_paths[key] = Path(value) if value else None
        sidecar_result = save_epl_weekly_pipeline_verification_sidecar(
            pipeline_archive_path=Path(history_result["archive_dir"]),
            pipeline_receipt_id=str(history_result["receipt_id"]),
            verification_paths=verification_paths,
            verification_verdict=verification_verdict,
            verification_status=verification_status,
            original_receipt_id=verification_original_id,
            recalculated_receipt_id=verification_recalculated_id,
            mismatch_count=verification_mismatch_count,
            output_dir=context.output_dir,
            archived_at=context.run_at,
        )
        sidecar_archive_path = str(sidecar_result.get("archive_dir", ""))
        sidecar_summary = sidecar_result.get("summary", {})
        if not isinstance(sidecar_summary, dict):
            raise ValueError("Verification sidecar returned a malformed summary.")
        sidecar_verdict = str(
            sidecar_summary.get("verdict", SIDECAR_FAILED_VERDICT)
        ).strip()
        sidecar_receipt_id = str(
            sidecar_summary.get("sidecar_receipt_id", "")
        ).strip()
        sidecar_report_path = str(sidecar_result.get("markdown", ""))
        sidecar_outputs = {
            key: Path(value)
            for key, value in sidecar_result.items()
            if key in {"json", "markdown", "csv"} and value
        }

        if sidecar_verdict == SIDECAR_ARCHIVED_VERDICT:
            sidecar_step_status = "Completed"
            sidecar_message = (
                "The automatic verification reports were archived with a deterministic "
                "checksum-bound sidecar receipt."
            )
            sidecar_warnings: tuple[str, ...] = ()
            sidecar_blockers: tuple[str, ...] = ()
        elif sidecar_verdict == SIDECAR_NOT_READY_VERDICT:
            sidecar_step_status = "Completed with warnings"
            sidecar_message = (
                "The verification sidecar was preserved, but this weekly run was not "
                "ready for card review."
            )
            sidecar_warnings = (sidecar_message,)
            sidecar_blockers = ()
            warnings.append(sidecar_message)
        else:
            sidecar_step_status = "Failed"
            sidecar_message = f"Verification sidecar failed closed: {sidecar_verdict}."
            sidecar_warnings = ()
            sidecar_blockers = (sidecar_message,)
            blockers.append(sidecar_message)
            final_status = "Failed"

        add_step(
            "Weekly pipeline verification sidecar",
            sidecar_step_status,
            sidecar_message,
            WorkflowActionResult(
                outputs=sidecar_outputs,
                message=sidecar_message,
                warnings=sidecar_warnings,
                blockers=sidecar_blockers,
                metadata={
                    "pipeline_archive_path": str(history_result["archive_dir"]),
                    "pipeline_receipt_id": history_result["receipt_id"],
                    "verdict": sidecar_verdict,
                    "sidecar_receipt_id": sidecar_receipt_id,
                    "sidecar_archive_path": sidecar_archive_path,
                },
            ),
        )
    except Exception as exc:
        final_status = "Failed"
        sidecar_message = f"Verification sidecar failed unexpectedly: {exc}"
        blockers.append(sidecar_message)
        add_step(
            "Weekly pipeline verification sidecar",
            "Failed",
            sidecar_message,
            WorkflowActionResult(
                message=sidecar_message,
                blockers=(sidecar_message,),
                metadata={
                    "pipeline_archive_path": str(history_result["archive_dir"]),
                    "pipeline_receipt_id": history_result["receipt_id"],
                    "verdict": sidecar_verdict,
                },
            ),
        )

    sidecar_verification_result: dict[str, object] | None = None
    sidecar_verification_verdict = SIDECAR_VERIFICATION_ERROR_VERDICT
    sidecar_verification_status = "Failed"
    sidecar_verification_original_id = ""
    sidecar_verification_recalculated_id = ""
    sidecar_verification_mismatch_count = 1
    sidecar_verification_report_path = ""
    sidecar_verification_archive_path = sidecar_archive_path
    if progress is not None:
        progress(
            "Weekly verification sidecar verification",
            "Running",
            "Verifying the exact sidecar archive created by this weekly run.",
        )
    if not sidecar_archive_path:
        final_status = "Failed"
        sidecar_verification_status = "Blocked"
        sidecar_verification_verdict = "Missing weekly verification sidecar"
        sidecar_verification_message = (
            "Sidecar verification stopped safely because this run did not return a "
            "sidecar archive path. No older sidecar was selected instead."
        )
        blockers.append(sidecar_verification_message)
        add_step(
            "Weekly verification sidecar verification",
            "Blocked",
            sidecar_verification_message,
            WorkflowActionResult(
                message=sidecar_verification_message,
                blockers=(sidecar_verification_message,),
                metadata={
                    "verdict": sidecar_verification_verdict,
                    "sidecar_archive_path": "",
                    "mismatch_count": sidecar_verification_mismatch_count,
                },
            ),
        )
    else:
        try:
            sidecar_verification_result = (
                save_epl_weekly_pipeline_verification_sidecar_verification(
                    sidecar_path=Path(sidecar_archive_path),
                    output_dir=context.output_dir,
                    generated_at=context.run_at,
                )
            )
            sidecar_verification_summary = sidecar_verification_result.get(
                "summary", {}
            )
            if not isinstance(sidecar_verification_summary, dict):
                raise ValueError(
                    "Sidecar verification returned a malformed summary."
                )
            sidecar_verification_verdict = str(
                sidecar_verification_summary.get(
                    "verdict", SIDECAR_VERIFICATION_ERROR_VERDICT
                )
            ).strip()
            sidecar_verification_original_id = str(
                sidecar_verification_summary.get(
                    "original_sidecar_receipt_id", ""
                )
            ).strip()
            sidecar_verification_recalculated_id = str(
                sidecar_verification_summary.get(
                    "recalculated_sidecar_receipt_id", ""
                )
            ).strip()
            sidecar_verification_mismatch_count = int(
                sidecar_verification_summary.get("mismatch_count", 0) or 0
            )
            sidecar_verification_report_path = str(
                sidecar_verification_result.get("markdown", "")
            )
            sidecar_verification_archive_path = sidecar_archive_path
            sidecar_verification_outputs = {
                key: Path(value)
                for key, value in sidecar_verification_result.items()
                if key in {"json", "markdown", "csv"} and value
            }

            if sidecar_verification_verdict == SIDECAR_VERIFIED_VERDICT:
                sidecar_verification_status = "Verified"
                sidecar_verification_step_status = "Completed"
                sidecar_verification_message = (
                    "The just-created verification sidecar and its referenced sealed "
                    "pipeline archive passed independent verification."
                )
                sidecar_verification_warnings: tuple[str, ...] = ()
                sidecar_verification_blockers: tuple[str, ...] = ()
            elif (
                sidecar_verification_verdict
                == SIDECAR_VERIFICATION_NOT_READY_VERDICT
                and sidecar_verdict == SIDECAR_NOT_READY_VERDICT
                and sidecar_verification_mismatch_count == 0
            ):
                sidecar_verification_status = "Not ready"
                sidecar_verification_step_status = "Completed with warnings"
                sidecar_verification_message = (
                    "The sidecar is structurally consistent, but the underlying weekly "
                    "run was not ready for card review."
                )
                sidecar_verification_warnings = (sidecar_verification_message,)
                sidecar_verification_blockers = ()
                warnings.append(sidecar_verification_message)
            else:
                sidecar_verification_status = "Failed"
                sidecar_verification_step_status = "Failed"
                sidecar_verification_message = (
                    "Sidecar verification failed closed: "
                    f"{sidecar_verification_verdict}."
                )
                sidecar_verification_warnings = ()
                sidecar_verification_blockers = (sidecar_verification_message,)
                blockers.append(sidecar_verification_message)
                final_status = "Failed"

            add_step(
                "Weekly verification sidecar verification",
                sidecar_verification_step_status,
                sidecar_verification_message,
                WorkflowActionResult(
                    outputs=sidecar_verification_outputs,
                    message=sidecar_verification_message,
                    warnings=sidecar_verification_warnings,
                    blockers=sidecar_verification_blockers,
                    metadata={
                        "verdict": sidecar_verification_verdict,
                        "status": sidecar_verification_status,
                        "sidecar_archive_path": sidecar_verification_archive_path,
                        "original_sidecar_receipt_id": (
                            sidecar_verification_original_id
                        ),
                        "recalculated_sidecar_receipt_id": (
                            sidecar_verification_recalculated_id
                        ),
                        "mismatch_count": sidecar_verification_mismatch_count,
                    },
                ),
            )
        except Exception as exc:
            final_status = "Failed"
            sidecar_verification_message = (
                f"Sidecar verification failed unexpectedly: {exc}"
            )
            blockers.append(sidecar_verification_message)
            add_step(
                "Weekly verification sidecar verification",
                "Failed",
                sidecar_verification_message,
                WorkflowActionResult(
                    message=sidecar_verification_message,
                    blockers=(sidecar_verification_message,),
                    metadata={
                        "verdict": sidecar_verification_verdict,
                        "sidecar_archive_path": sidecar_verification_archive_path,
                        "mismatch_count": sidecar_verification_mismatch_count,
                    },
                ),
            )

    summary.update(
        {
            "status": final_status,
            "steps_run": [
                str(step["step"])
                for step in steps
                if step["status"] not in {"Skipped", "Blocked"}
            ],
            "steps_skipped": [
                str(step["step"]) for step in steps if step["status"] == "Skipped"
            ],
            "steps_blocked": [
                str(step["step"]) for step in steps if step["status"] == "Blocked"
            ],
            "key_blockers": _dedupe(blockers),
            "key_warnings": _dedupe(warnings),
            "generated_report_paths": _dedupe(output_files),
            "recommended_next_action": _recommended_next_action(final_status),
            "steps": steps,
            "archive_receipt_id": history_result["receipt_id"],
            "archive_path": str(history_result["archive_dir"]),
            "receipt_verification_verdict": verification_verdict,
            "receipt_verification_status": verification_status,
            "receipt_verification_original_id": verification_original_id,
            "receipt_verification_recalculated_id": verification_recalculated_id,
            "receipt_verification_mismatch_count": verification_mismatch_count,
            "receipt_verification_report_path": verification_report_path,
            "verification_sidecar_verdict": sidecar_verdict,
            "verification_sidecar_receipt_id": sidecar_receipt_id,
            "verification_sidecar_archive_path": sidecar_archive_path,
            "verification_sidecar_report_path": sidecar_report_path,
            "sidecar_verification_verdict": sidecar_verification_verdict,
            "sidecar_verification_status": sidecar_verification_status,
            "sidecar_verification_original_id": sidecar_verification_original_id,
            "sidecar_verification_recalculated_id": (
                sidecar_verification_recalculated_id
            ),
            "sidecar_verification_mismatch_count": (
                sidecar_verification_mismatch_count
            ),
            "sidecar_verification_report_path": sidecar_verification_report_path,
            "sidecar_verification_archive_path": (
                sidecar_verification_archive_path
            ),
        }
    )
    safe_summary = _write_live_pipeline_outputs(
        summary,
        json_path=json_path,
        markdown_path=markdown_path,
        csv_path=csv_path,
    )
    return {
        "status": final_status,
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
        "archive": history_result,
        "comparison": history_plan["comparison"],
        "receipt_verification": verification_result,
        "verification_sidecar": sidecar_result,
        "verification_sidecar_verification": sidecar_verification_result,
        "summary": safe_summary,
    }
