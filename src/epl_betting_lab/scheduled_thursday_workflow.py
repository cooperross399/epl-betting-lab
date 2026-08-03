from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from epl_betting_lab.config import (
    MANUAL_DIR,
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_DIR,
)
from epl_betting_lab.dashboard_actions import run_thursday_best_bets_report
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures
from epl_betting_lab.github_runner_inputs import save_github_runner_input_handoff
from epl_betting_lab.reports.current_odds_completeness import (
    build_current_odds_completeness,
    render_current_odds_completeness_report,
)
from epl_betting_lab.reports.current_odds_validation import (
    CurrentOddsValidationError,
    build_current_odds_validation,
    render_current_odds_validation_report,
)
from epl_betting_lab.reports.thursday_best_bets import list_recent_thursday_archives
from epl_betting_lab.reports.thursday_best_bets_comparison import (
    save_thursday_best_bets_comparison,
)
from epl_betting_lab.reports.thursday_decision_queue import (
    save_thursday_decision_queue,
)
from epl_betting_lab.reports.tier_performance import save_tier_performance_reports
from epl_betting_lab.workflow_status import (
    build_data_freshness_checks,
    build_data_freshness_status,
)


SUMMARY_MARKDOWN_FILENAME = "scheduled_thursday_workflow_summary.md"
SUMMARY_JSON_FILENAME = "scheduled_thursday_workflow_summary.json"
OVERALL_STATUSES = ("Ready", "Warnings only", "Blocked", "Partial", "Failed")
INPUT_FRESHNESS_ITEMS = {
    "Historical results / Football-Data",
    "Upcoming fixtures",
    "Current odds",
}


@dataclass(frozen=True)
class ScheduledWorkflowContext:
    current_odds_path: Path
    fixtures_path: Path
    matches_path: Path
    ledger_path: Path
    output_dir: Path
    run_at: datetime


@dataclass(frozen=True)
class WorkflowActionResult:
    outputs: dict[str, Path] = field(default_factory=dict)
    message: str = ""
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduledWorkflowActions:
    data_freshness: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    current_odds_validation: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    odds_completeness: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    thursday_best_bets: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    archive_count: Callable[[ScheduledWorkflowContext], int]
    comparison: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    decision_queue: Callable[[ScheduledWorkflowContext], WorkflowActionResult]
    tier_performance: Callable[[ScheduledWorkflowContext], WorkflowActionResult]


def _issue_messages(issues: pd.DataFrame, severity: str, limit: int = 6) -> tuple[str, ...]:
    if issues.empty or not {"severity", "issue"}.issubset(issues.columns):
        return ()
    selected = issues[issues["severity"].astype(str).str.lower() == severity].head(limit)
    messages = []
    for _, row in selected.iterrows():
        row_number = row.get("row_number", "")
        row_label = ""
        if not pd.isna(row_number) and str(row_number).strip():
            row_label = f"row {row_number}: "
        detail = str(row.get("details", "")).strip()
        suffix = f" - {detail}" if detail else ""
        messages.append(f"{row_label}{row.get('issue', 'validation_issue')}{suffix}")
    total = int((issues["severity"].astype(str).str.lower() == severity).sum())
    if total > len(messages):
        messages.append(f"{total - len(messages)} more {severity} issue(s) are in the report.")
    return tuple(messages)


def _load_reference_data(
    context: ScheduledWorkflowContext,
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    warnings: list[str] = []
    try:
        matches = load_matches(context.matches_path)
    except (FileNotFoundError, OSError, UnicodeError, pd.errors.ParserError) as exc:
        matches = pd.DataFrame()
        warnings.append(f"Historical results could not be loaded for validation: {exc}")
    try:
        fixtures = load_upcoming_fixtures(context.fixtures_path)
    except (FileNotFoundError, OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
        fixtures = pd.DataFrame()
        warnings.append(f"Upcoming fixtures could not be loaded for validation: {exc}")
    return matches, fixtures, tuple(warnings)


def _run_data_freshness(context: ScheduledWorkflowContext) -> WorkflowActionResult:
    checks = build_data_freshness_checks(
        raw_dir=RAW_DIR,
        processed_dir=context.matches_path.parent,
        manual_dir=context.current_odds_path.parent,
        output_dir=context.output_dir,
    )
    freshness = build_data_freshness_status(checks, today=context.run_at.date())
    counts = freshness["status"].value_counts().to_dict() if not freshness.empty else {}
    warnings = []
    if not freshness.empty:
        inputs = freshness[freshness["item"].isin(INPUT_FRESHNESS_ITEMS)]
        for _, row in inputs.iterrows():
            status = str(row.get("status", "Not checked"))
            warning = str(row.get("warning", "")).strip()
            if status != "Fresh":
                warnings.append(
                    f"{row.get('item', 'Input')}: {status}. {row.get('note', '')}"
                )
            elif warning:
                warnings.append(f"{row.get('item', 'Input')}: {warning}")
    count_text = ", ".join(
        f"{status} {int(count)}" for status, count in sorted(counts.items())
    ) or "no freshness rows"
    return WorkflowActionResult(
        message=f"Home/data freshness checked ({count_text}).",
        warnings=tuple(warnings),
        metadata={"status_counts": {str(key): int(value) for key, value in counts.items()}},
    )


def _run_current_odds_validation(
    context: ScheduledWorkflowContext,
) -> WorkflowActionResult:
    if context.current_odds_path.exists():
        matches, fixtures, reference_warnings = _load_reference_data(context)
    else:
        matches, fixtures, reference_warnings = pd.DataFrame(), pd.DataFrame(), ()
    issues = build_current_odds_validation(
        context.current_odds_path,
        matches=matches,
        fixtures=fixtures,
    )
    context.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = context.output_dir / "current_odds_validation.csv"
    markdown_path = context.output_dir / "current_odds_validation.md"
    issues.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_current_odds_validation_report(issues),
        encoding="utf-8",
    )
    serious_count = (
        int((issues["severity"].astype(str).str.lower() == "error").sum())
        if not issues.empty
        else 0
    )
    warning_count = (
        int((issues["severity"].astype(str).str.lower() == "warning").sum())
        if not issues.empty
        else 0
    )
    return WorkflowActionResult(
        outputs={"csv": csv_path, "markdown": markdown_path},
        message=(
            f"Current odds validation found {serious_count} serious issue(s) "
            f"and {warning_count} warning(s)."
        ),
        warnings=reference_warnings + _issue_messages(issues, "warning"),
        blockers=_issue_messages(issues, "error"),
        metadata={
            "serious_issue_count": serious_count,
            "warning_count": warning_count,
        },
    )


def _run_odds_completeness(
    context: ScheduledWorkflowContext,
) -> WorkflowActionResult:
    fixture_warning = ""
    try:
        fixtures = load_upcoming_fixtures(context.fixtures_path)
    except (FileNotFoundError, OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
        fixtures = None
        fixture_warning = f"Upcoming fixtures were unavailable for the completeness check: {exc}"
    issues, summary = build_current_odds_completeness(
        context.current_odds_path,
        fixtures=fixtures,
    )
    context.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = context.output_dir / "current_odds_completeness.csv"
    markdown_path = context.output_dir / "current_odds_completeness.md"
    issues.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_current_odds_completeness_report(issues, summary),
        encoding="utf-8",
    )
    error_count = (
        int((issues["severity"].astype(str).str.lower() == "error").sum())
        if not issues.empty
        else 0
    )
    warning_count = (
        int((issues["severity"].astype(str).str.lower() == "warning").sum())
        if not issues.empty
        else 0
    )
    warnings = []
    if fixture_warning:
        warnings.append(fixture_warning)
    if error_count:
        warnings.append(
            f"Odds completeness found {error_count} incomplete or invalid row issue(s)."
        )
    if warning_count:
        warnings.append(f"Odds completeness found {warning_count} warning(s).")
    completion = float(summary.get("completion_percentage", 0.0))
    return WorkflowActionResult(
        outputs={"csv": csv_path, "markdown": markdown_path},
        message=(
            f"Odds completeness is {completion:.1%}; "
            f"{int(summary.get('matches_incomplete', 0))} match(es) are incomplete."
        ),
        warnings=tuple(warnings),
        metadata={str(key): value for key, value in summary.items()},
    )


def _run_thursday_best_bets(
    context: ScheduledWorkflowContext,
) -> WorkflowActionResult:
    paths = run_thursday_best_bets_report(
        context.current_odds_path,
        context.output_dir,
        force=False,
        archive=True,
        overwrite_archive=False,
        matches_path=context.matches_path,
        fixtures_path=context.fixtures_path,
    )
    return WorkflowActionResult(
        outputs=paths,
        message="Thursday best-bets report generated through the validation gate.",
    )


def _run_comparison(context: ScheduledWorkflowContext) -> WorkflowActionResult:
    paths = save_thursday_best_bets_comparison(context.output_dir)
    return WorkflowActionResult(
        outputs=paths,
        message="Latest two Thursday archive snapshots compared.",
    )


def _run_decision_queue(context: ScheduledWorkflowContext) -> WorkflowActionResult:
    paths = save_thursday_decision_queue(context.output_dir)
    return WorkflowActionResult(
        outputs=paths,
        message="Thursday decision queue generated from the latest comparison.",
    )


def _run_tier_performance(context: ScheduledWorkflowContext) -> WorkflowActionResult:
    paths = save_tier_performance_reports(context.ledger_path, context.output_dir)
    return WorkflowActionResult(
        outputs=paths,
        message="Tier performance reports generated from available ledger/archive data.",
    )


def default_scheduled_workflow_actions() -> ScheduledWorkflowActions:
    return ScheduledWorkflowActions(
        data_freshness=_run_data_freshness,
        current_odds_validation=_run_current_odds_validation,
        odds_completeness=_run_odds_completeness,
        thursday_best_bets=_run_thursday_best_bets,
        archive_count=lambda context: len(
            list_recent_thursday_archives(context.output_dir, limit=2)
        ),
        comparison=_run_comparison,
        decision_queue=_run_decision_queue,
        tier_performance=_run_tier_performance,
    )


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _recommended_next_action(
    status: str,
    steps: list[dict[str, object]],
) -> str:
    if status == "Failed":
        failed = [str(step["step"]) for step in steps if step["status"] == "Failed"]
        return (
            f"Review the failed step(s): {', '.join(failed)}. Fix the reported file or "
            "data problem, then rerun the scheduled workflow."
        )
    if status == "Blocked":
        handoff_blocked = any(
            step["step"] == "GitHub runner input handoff"
            and step["status"] == "Blocked"
            for step in steps
        )
        if handoff_blocked:
            return (
                "Fix the odds-and-fixtures handoff blockers shown in "
                "`data/outputs/github_runner_input_handoff.md`, validate the "
                "prepared files locally, then start the manual GitHub Action again. "
                "Do not guess missing prices or force the card."
            )
        return (
            "Fix the serious current-odds validation issues, rerun "
            "`python scripts/validate_current_odds.py`, then rerun this workflow. "
            "Do not force the scheduled card."
        )
    if status == "Partial":
        skipped = [str(step["step"]) for step in steps if step["status"] == "Skipped"]
        if "Thursday snapshot comparison" in skipped:
            return (
                "Review the generated Thursday card. After a later refresh creates another "
                "archive, rerun this workflow to unlock comparison and the decision queue."
            )
        return (
            "Review the skipped or optional failed steps in the summary, fix their "
            "prerequisites, and rerun the workflow."
        )
    if status == "Warnings only":
        return (
            "Review the warnings before trusting the card, especially heavy juice and "
            "totals-under cautions. All betting decisions remain manual."
        )
    return (
        "Review the Thursday card and decision queue manually. This workflow did not "
        "confirm or place any bets."
    )


def _render_summary(summary: dict[str, object]) -> str:
    steps = pd.DataFrame(summary["steps"])
    display_steps = steps[["step", "status", "message", "outputs"]].copy()
    display_steps["outputs"] = display_steps["outputs"].apply(
        lambda values: "<br>".join(values) if values else ""
    )
    blockers = list(summary["key_blockers"])
    warnings = list(summary["key_warnings"])
    outputs = list(summary["output_files_created"])
    lines = [
        "# Scheduled Thursday Workflow Summary",
        "",
        (
            "This workflow only reads project inputs and generates reports. It does not "
            "edit manual odds, import files, the ledger, or profile settings; force a card; "
            "apply archives, rollbacks, imports, settlements, or profile installs; fabricate "
            "odds; or place bets."
        ),
        "",
        "## Run status",
        "",
        f"- Run timestamp: {summary['run_timestamp']}",
        f"- Status: **{summary['status']}**",
        f"- Recommended next action: {summary['recommended_next_action']}",
    ]
    handoff = summary.get("input_handoff")
    if isinstance(handoff, dict):
        allowed = "Yes" if handoff.get("card_generation_allowed") else "No"
        lines.extend(
            [
                "",
                "## GitHub runner input handoff",
                "",
                f"- Handoff status: **{handoff.get('status', 'Not checked')}**",
                (
                    "- Staging receipt: "
                    f"`{handoff.get('staging_receipt_path') or 'not provided'}`"
                ),
                (
                    "- Staging receipt verdict: "
                    f"**{handoff.get('staging_receipt_verdict', 'Not checked')}**"
                ),
                (
                    "- Staging receipt generated at: "
                    f"{handoff.get('staging_receipt_generated_at') or 'not available'}"
                ),
                (
                    "- Staging receipt binding: "
                    f"**{handoff.get('staging_receipt_binding_status', 'Not checked')}**"
                ),
                (
                    "- Receipt input checksum match: "
                    f"**{handoff.get('staging_receipt_input_checksum_status', 'Not checked')}**"
                ),
                f"- Current odds input: `{handoff.get('current_odds_path', '')}`",
                (
                    "- Current odds SHA-256: "
                    f"`{handoff.get('current_odds_checksum_sha256') or 'not available'}`"
                ),
                (
                    "- Current odds freshness: "
                    f"**{handoff.get('current_odds_freshness_status', 'Not checked')}**"
                ),
                f"- Fixtures input: `{handoff.get('fixtures_path', '')}`",
                (
                    "- Fixtures SHA-256: "
                    f"`{handoff.get('fixtures_checksum_sha256') or 'not available'}`"
                ),
                (
                    "- Fixtures freshness: "
                    f"**{handoff.get('fixtures_freshness_status', 'Not checked')}**"
                ),
                (
                    "- Current odds validation: "
                    f"**{handoff.get('validation_status', 'Not checked')}**"
                ),
                (
                    "- Odds completeness: "
                    f"**{handoff.get('completeness_status', 'Not checked')}** "
                    f"({float(handoff.get('completion_percentage', 0.0)):.1%})"
                ),
                f"- Thursday card generation allowed: **{allowed}**",
            ]
        )
    lines.extend(
        [
            "",
            "## Steps",
            "",
            display_steps.to_markdown(index=False),
            "",
            "## Key blockers",
            "",
        ]
    )
    lines.extend([f"- {item}" for item in blockers] or ["- None."])
    lines.extend(["", "## Key warnings", ""])
    lines.extend([f"- {item}" for item in warnings] or ["- None."])
    lines.extend(["", "## Output files created or refreshed", ""])
    lines.extend([f"- `{path}`" for path in outputs] or ["- No report outputs were created."])
    lines.extend(
        [
            "",
            "## Safety reminder",
            "",
            (
                "Review every recommendation and real sportsbook price manually. The project "
                "still respects the max-juice guard around -160 and the existing totals protections."
            ),
        ]
    )
    return "\n".join(lines)


def run_scheduled_thursday_workflow(
    *,
    current_odds_path: Path | None = None,
    fixtures_path: Path | None = None,
    matches_path: Path | None = None,
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
    run_at: datetime | None = None,
    require_github_runner_handoff: bool = False,
    repository_root: Path | None = None,
    expected_current_odds_sha256: str = "",
    expected_fixtures_sha256: str = "",
    staging_receipt_path: Path | None = None,
    require_staging_receipt: bool = False,
    actions: ScheduledWorkflowActions | None = None,
    progress: Callable[[str, str, str], None] | None = None,
) -> dict[str, object]:
    """Run the report-only Thursday package without force or manual-file writes."""
    if require_staging_receipt:
        require_github_runner_handoff = True
    repository_root = (repository_root or PROJECT_ROOT).resolve()
    output_dir = output_dir or OUTPUTS_DIR

    def resolve_input(path: Path | None, default: Path) -> Path:
        selected = path or default
        return (
            selected
            if selected.is_absolute()
            else (repository_root / selected).resolve(strict=False)
        )

    context = ScheduledWorkflowContext(
        current_odds_path=resolve_input(
            current_odds_path,
            MANUAL_DIR / "current_odds.csv",
        ),
        fixtures_path=resolve_input(
            fixtures_path,
            MANUAL_DIR / "upcoming_fixtures.csv",
        ),
        matches_path=resolve_input(
            matches_path,
            PROCESSED_DIR / "epl_historical_matches.csv",
        ),
        ledger_path=resolve_input(
            ledger_path,
            MANUAL_DIR / "bet_ledger.csv",
        ),
        output_dir=output_dir,
        run_at=run_at or datetime.now().astimezone(),
    )
    actions = actions or default_scheduled_workflow_actions()
    steps: list[dict[str, object]] = []
    warnings: list[str] = []
    blockers: list[str] = []
    output_files: list[str] = []
    required_failure = False
    optional_problem = False
    input_handoff: dict[str, object] | None = None

    def add_step(
        name: str,
        status: str,
        message: str,
        result: WorkflowActionResult | None = None,
    ) -> None:
        paths = [str(path) for path in (result.outputs.values() if result else [])]
        steps.append(
            {
                "step": name,
                "status": status,
                "message": message,
                "outputs": paths,
            }
        )
        output_files.extend(paths)
        if progress is not None:
            progress(name, status, message)

    def perform(
        name: str,
        action: Callable[[ScheduledWorkflowContext], WorkflowActionResult],
        *,
        required: bool,
        block_on_result: bool = False,
        blocked_exceptions: tuple[type[Exception], ...] = (),
    ) -> WorkflowActionResult | None:
        nonlocal required_failure, optional_problem
        if progress is not None:
            progress(name, "Running", f"Running {name.lower()}.")
        try:
            result = action(context)
        except Exception as exc:
            if blocked_exceptions and isinstance(exc, blocked_exceptions):
                blockers.append(str(exc))
                add_step(name, "Blocked", str(exc))
                return None
            add_step(name, "Failed", str(exc))
            if required:
                required_failure = True
            else:
                optional_problem = True
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

    handoff_paths_safe = True
    if require_github_runner_handoff:
        if progress is not None:
            progress(
                "GitHub runner input handoff",
                "Running",
                "Checking committed odds and fixture inputs.",
            )
        try:
            handoff_result = save_github_runner_input_handoff(
                output_dir=context.output_dir,
                current_odds_path=context.current_odds_path,
                fixtures_path=context.fixtures_path,
                matches_path=context.matches_path,
                run_at=context.run_at,
                repository_root=repository_root,
                expected_current_odds_sha256=expected_current_odds_sha256,
                expected_fixtures_sha256=expected_fixtures_sha256,
                staging_receipt_path=staging_receipt_path,
                require_staging_receipt=require_staging_receipt,
            )
        except Exception as exc:
            required_failure = True
            handoff_paths_safe = False
            add_step(
                "GitHub runner input handoff",
                "Failed",
                f"Input handoff could not be checked: {exc}",
            )
        else:
            input_handoff = dict(handoff_result["summary"])
            handoff_paths_safe = bool(
                input_handoff.get("current_odds_path_policy_valid")
                and input_handoff.get("fixtures_path_policy_valid")
            )
            handoff_action = WorkflowActionResult(
                outputs={
                    "json": Path(handoff_result["json"]),
                    "markdown": Path(handoff_result["markdown"]),
                },
                message=(
                    f"Input handoff is {input_handoff['status']}; "
                    "the selected paths and SHA-256 checksums were recorded."
                ),
                warnings=tuple(str(item) for item in input_handoff["warnings"]),
                blockers=tuple(str(item) for item in input_handoff["blockers"]),
                metadata=input_handoff,
            )
            warnings.extend(handoff_action.warnings)
            blockers.extend(handoff_action.blockers)
            add_step(
                "GitHub runner input handoff",
                "Blocked" if handoff_action.blockers else (
                    "Completed with warnings"
                    if handoff_action.warnings
                    else "Completed"
                ),
                handoff_action.message,
                handoff_action,
            )

    if require_github_runner_handoff and not handoff_paths_safe:
        add_step(
            "Home/data freshness check",
            "Skipped",
            "Skipped because the selected repository input paths did not pass the handoff policy.",
        )
        add_step(
            "Current odds validation",
            "Blocked",
            "Not run because the selected current-odds path was not a safe repository CSV path.",
        )
        add_step(
            "Odds completeness check",
            "Blocked",
            "Not run because the selected input paths did not pass the handoff policy.",
        )
        validation = None
    else:
        perform("Home/data freshness check", actions.data_freshness, required=False)
        validation = perform(
            "Current odds validation",
            actions.current_odds_validation,
            required=True,
            block_on_result=True,
        )
        perform("Odds completeness check", actions.odds_completeness, required=True)

    validation_blocked = bool(validation and validation.blockers)
    handoff_blocked = bool(
        require_github_runner_handoff
        and (
            input_handoff is None
            or not input_handoff.get("card_generation_allowed", False)
        )
    )
    best_bets: WorkflowActionResult | None = None
    archive_ready = False
    if required_failure:
        add_step(
            "Thursday best-bets generation",
            "Skipped",
            "Skipped because a required preflight report failed.",
        )
    elif handoff_blocked:
        add_step(
            "Thursday best-bets generation",
            "Skipped",
            (
                "Skipped because the GitHub runner odds-and-fixtures handoff is "
                "blocked. No force mode was used."
            ),
        )
    elif validation_blocked:
        add_step(
            "Thursday best-bets generation",
            "Skipped",
            "Skipped because serious current-odds validation issues exist. Force mode was not used.",
        )
    else:
        missing_inputs = [
            str(path)
            for path in (context.matches_path, context.fixtures_path)
            if not path.exists()
        ]
        if missing_inputs:
            optional_problem = True
            message = (
                "Skipped because required model input files are missing: "
                + ", ".join(missing_inputs)
            )
            warnings.append(message)
            add_step("Thursday best-bets generation", "Skipped", message)
        else:
            best_bets = perform(
                "Thursday best-bets generation",
                actions.thursday_best_bets,
                required=True,
                blocked_exceptions=(CurrentOddsValidationError,),
            )

    if best_bets is None:
        add_step(
            "Thursday archive snapshot",
            "Skipped",
            "Skipped because no new Thursday best-bets report was generated.",
        )
    else:
        archive_keys = ("archive_csv", "archive_markdown", "archive_metadata")
        archive_paths = {
            key: best_bets.outputs[key]
            for key in archive_keys
            if key in best_bets.outputs
        }
        archive_result = WorkflowActionResult(
            outputs=archive_paths,
            message="Successful Thursday report saved as a dated archive snapshot.",
        )
        if len(archive_paths) == len(archive_keys):
            archive_ready = True
            add_step(
                "Thursday archive snapshot",
                "Completed",
                archive_result.message,
                archive_result,
            )
        else:
            required_failure = True
            add_step(
                "Thursday archive snapshot",
                "Failed",
                "The report generated, but the expected archive files were not returned.",
                archive_result,
            )

    comparison_ready = False
    if not archive_ready:
        optional_problem = optional_problem or not validation_blocked
        add_step(
            "Thursday snapshot comparison",
            "Skipped",
            "Skipped because this run did not create a new archive snapshot.",
        )
    else:
        try:
            archive_count = int(actions.archive_count(context))
        except Exception as exc:
            optional_problem = True
            add_step(
                "Thursday snapshot comparison",
                "Failed",
                f"Archive history could not be checked: {exc}",
            )
        else:
            if archive_count < 2:
                optional_problem = True
                add_step(
                    "Thursday snapshot comparison",
                    "Skipped",
                    "At least two Thursday archive snapshots are required; one is available.",
                )
            else:
                comparison = perform(
                    "Thursday snapshot comparison",
                    actions.comparison,
                    required=False,
                )
                comparison_ready = comparison is not None

    if comparison_ready:
        perform(
            "Thursday decision queue",
            actions.decision_queue,
            required=False,
        )
    else:
        add_step(
            "Thursday decision queue",
            "Skipped",
            "Skipped because a current comparison report was not generated.",
        )

    perform(
        "Tier performance report",
        actions.tier_performance,
        required=False,
    )

    if required_failure:
        overall_status = "Failed"
    elif blockers:
        overall_status = "Blocked"
    elif optional_problem or any(step["status"] in {"Skipped", "Failed"} for step in steps):
        overall_status = "Partial"
    elif warnings:
        overall_status = "Warnings only"
    else:
        overall_status = "Ready"

    markdown_path = output_dir / SUMMARY_MARKDOWN_FILENAME
    json_path = output_dir / SUMMARY_JSON_FILENAME
    output_files.extend([str(markdown_path), str(json_path)])
    summary = {
        "run_timestamp": context.run_at.isoformat(timespec="seconds"),
        "status": overall_status,
        "steps_run": [
            str(step["step"]) for step in steps if step["status"] != "Skipped"
        ],
        "steps_skipped": [
            str(step["step"]) for step in steps if step["status"] == "Skipped"
        ],
        "key_warnings": _dedupe(warnings),
        "key_blockers": _dedupe(blockers),
        "output_files_created": _dedupe(output_files),
        "recommended_next_action": _recommended_next_action(overall_status, steps),
        "input_handoff": input_handoff,
        "steps": steps,
    }
    if summary["status"] not in OVERALL_STATUSES:
        raise ValueError(f"Unexpected scheduled workflow status: {summary['status']}")

    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_summary(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {
        "status": overall_status,
        "markdown": markdown_path,
        "json": json_path,
        "summary": summary,
    }
