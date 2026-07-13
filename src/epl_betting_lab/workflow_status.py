from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, PROCESSED_DIR, RAW_DIR


@dataclass(frozen=True)
class WorkflowItem:
    step: str
    status: str
    files: str
    last_modified: str
    command: str
    note: str


@dataclass(frozen=True)
class WorkflowCheck:
    step: str
    paths: tuple[Path, ...]
    command: str
    stale_after: tuple[Path, ...] = ()
    any_path_ok: bool = False


@dataclass(frozen=True)
class DataFreshnessCheck:
    item: str
    path: Path
    command: str
    recommendation: str
    sources: tuple[Path, ...] = ()
    dependencies: tuple[str, ...] = ()
    minimum_sources: int = 0
    stale_status: str = "Stale"
    not_checked_until_sources: bool = False
    priority: int = 100


WORKFLOW_CHECKS = [
    WorkflowCheck(
        "Current odds file",
        (MANUAL_DIR / "current_odds.csv",),
        "python scripts/create_current_odds_template.py",
    ),
    WorkflowCheck(
        "Current odds validation",
        (OUTPUTS_DIR / "current_odds_validation.csv", OUTPUTS_DIR / "current_odds_validation.md"),
        "python scripts/validate_current_odds.py",
        stale_after=(MANUAL_DIR / "current_odds.csv",),
        any_path_ok=True,
    ),
    WorkflowCheck(
        "Current odds maintenance preview",
        (OUTPUTS_DIR / "current_odds_maintenance_preview.csv", OUTPUTS_DIR / "current_odds_maintenance_report.md"),
        "python scripts/maintain_current_odds.py",
        stale_after=(MANUAL_DIR / "current_odds.csv", MANUAL_DIR / "upcoming_fixtures.csv"),
        any_path_ok=True,
    ),
    WorkflowCheck(
        "Current odds completeness",
        (OUTPUTS_DIR / "current_odds_completeness.csv", OUTPUTS_DIR / "current_odds_completeness.md"),
        "python scripts/check_current_odds_completeness.py",
        stale_after=(MANUAL_DIR / "current_odds.csv", MANUAL_DIR / "upcoming_fixtures.csv"),
        any_path_ok=True,
    ),
    WorkflowCheck(
        "Weekly card",
        (OUTPUTS_DIR / "weekly_card.csv", OUTPUTS_DIR / "weekly_card.md"),
        "python scripts/generate_weekly_card.py",
        stale_after=(MANUAL_DIR / "current_odds.csv",),
        any_path_ok=True,
    ),
    WorkflowCheck(
        "Thursday best-bets report",
        (OUTPUTS_DIR / "thursday_best_bets.csv", OUTPUTS_DIR / "thursday_best_bets.md"),
        "python scripts/generate_thursday_best_bets.py",
        stale_after=(MANUAL_DIR / "current_odds.csv",),
        any_path_ok=True,
    ),
    WorkflowCheck(
        "Bet ledger",
        (MANUAL_DIR / "bet_ledger.csv",),
        "python scripts/run_bet_ledger.py",
    ),
    WorkflowCheck(
        "Ledger report",
        (OUTPUTS_DIR / "bet_ledger_summary.md",),
        "python scripts/run_bet_ledger.py",
        stale_after=(MANUAL_DIR / "bet_ledger.csv",),
    ),
    WorkflowCheck(
        "Ledger health check",
        (OUTPUTS_DIR / "bet_ledger_health_check.md",),
        "python scripts/check_bet_ledger.py",
        stale_after=(MANUAL_DIR / "bet_ledger.csv",),
    ),
    WorkflowCheck(
        "Settlement preview",
        (OUTPUTS_DIR / "bet_settlement_preview.md",),
        "python scripts/settle_bet_ledger.py",
        stale_after=(MANUAL_DIR / "bet_ledger.csv",),
    ),
    WorkflowCheck(
        "Backtest reports",
        (OUTPUTS_DIR / "backtest_summary.csv", OUTPUTS_DIR / "backtest_bets.csv"),
        "python scripts/run_backtest.py",
    ),
    WorkflowCheck(
        "CLV reports",
        (OUTPUTS_DIR / "clv_report.md", OUTPUTS_DIR / "clv_by_market.csv"),
        "python scripts/run_backtest.py",
    ),
]


def build_data_freshness_checks(
    raw_dir: Path | None = None,
    processed_dir: Path | None = None,
    manual_dir: Path | None = None,
    output_dir: Path | None = None,
) -> list[DataFreshnessCheck]:
    raw_dir = raw_dir or RAW_DIR
    processed_dir = processed_dir or PROCESSED_DIR
    manual_dir = manual_dir or MANUAL_DIR
    output_dir = output_dir or OUTPUTS_DIR

    raw_results = tuple(sorted(raw_dir.glob("football_data_E0_*.csv")))
    archive_root = output_dir / "archive" / "thursday_best_bets"
    archives = tuple(
        sorted(
            archive_root.glob("*/*_thursday_best_bets.csv"),
            key=lambda path: path.stat().st_mtime,
        )
    )
    latest_archive = (
        archives[-1]
        if archives
        else archive_root / "latest_thursday_best_bets.csv"
    )
    latest_archive_pair = archives[-2:]

    current_odds = manual_dir / "current_odds.csv"
    fixtures = manual_dir / "upcoming_fixtures.csv"
    validation = output_dir / "current_odds_validation.csv"
    completeness = output_dir / "current_odds_completeness.csv"
    thursday_report = output_dir / "thursday_best_bets.csv"
    comparison = output_dir / "thursday_best_bets_comparison.csv"
    decision_queue = output_dir / "thursday_decision_queue.csv"
    ledger = manual_dir / "bet_ledger.csv"

    return [
        DataFreshnessCheck(
            item="Historical results / Football-Data",
            path=processed_dir / "epl_historical_matches.csv",
            command="python scripts/fetch_data.py --seasons 2122 2223 2324 2425 2526",
            recommendation="Fetch and rebuild historical results before relying on model trends.",
            sources=raw_results,
            minimum_sources=1,
            stale_status="Needs refresh",
            priority=20,
        ),
        DataFreshnessCheck(
            item="Upcoming fixtures",
            path=fixtures,
            command="Update data/manual/upcoming_fixtures.csv",
            recommendation="Update upcoming fixtures before running Thursday analysis.",
            priority=10,
        ),
        DataFreshnessCheck(
            item="Current odds",
            path=current_odds,
            command="python scripts/create_current_odds_template.py",
            recommendation="Create or import current odds before running Thursday analysis.",
            priority=1,
        ),
        DataFreshnessCheck(
            item="Current odds validation report",
            path=validation,
            command="python scripts/validate_current_odds.py",
            recommendation="Update odds validation before generating the Thursday card.",
            sources=(current_odds,),
            minimum_sources=1,
            not_checked_until_sources=True,
            priority=2,
        ),
        DataFreshnessCheck(
            item="Odds completeness report",
            path=completeness,
            command="python scripts/check_current_odds_completeness.py",
            recommendation="Check odds completeness before generating the Thursday card.",
            sources=(current_odds, fixtures),
            minimum_sources=2,
            not_checked_until_sources=True,
            priority=3,
        ),
        DataFreshnessCheck(
            item="Thursday best-bets report",
            path=thursday_report,
            command="python scripts/generate_thursday_best_bets.py",
            recommendation="Run Thursday readiness refresh.",
            sources=(current_odds, validation, completeness),
            minimum_sources=3,
            not_checked_until_sources=True,
            priority=4,
        ),
        DataFreshnessCheck(
            item="Latest Thursday archive",
            path=latest_archive,
            command="python scripts/generate_thursday_best_bets.py",
            recommendation="Generate the Thursday best-bets report to create a fresh archive.",
            sources=(thursday_report,),
            minimum_sources=1,
            priority=40,
        ),
        DataFreshnessCheck(
            item="Thursday comparison report",
            path=comparison,
            command="python scripts/compare_thursday_best_bets.py",
            recommendation="Run post-refresh Thursday review after two archives exist.",
            sources=latest_archive_pair,
            minimum_sources=2,
            not_checked_until_sources=True,
            priority=50,
        ),
        DataFreshnessCheck(
            item="Thursday decision queue",
            path=decision_queue,
            command="python scripts/generate_thursday_decision_queue.py",
            recommendation="Run post-refresh Thursday review to rebuild the decision queue.",
            sources=(comparison,),
            dependencies=("Thursday comparison report",),
            minimum_sources=1,
            not_checked_until_sources=True,
            priority=60,
        ),
        DataFreshnessCheck(
            item="Tier performance report",
            path=output_dir / "tier_performance_summary.csv",
            command="python scripts/generate_tier_performance_report.py",
            recommendation="Generate the tier performance report after bets settle.",
            sources=(ledger, latest_archive),
            minimum_sources=1,
            not_checked_until_sources=True,
            priority=80,
        ),
        DataFreshnessCheck(
            item="Bet ledger report",
            path=output_dir / "bet_ledger_summary.md",
            command="python scripts/run_bet_ledger.py",
            recommendation="Refresh the bet ledger report after updating results or stakes.",
            sources=(ledger,),
            minimum_sources=1,
            not_checked_until_sources=True,
            priority=70,
        ),
    ]


def _mtime(path: Path) -> float | None:
    return path.stat().st_mtime if path.exists() else None


def _format_mtime(timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _existing_paths(paths: tuple[Path, ...]) -> list[Path]:
    return [path for path in paths if path.exists()]


def _is_complete(check: WorkflowCheck, existing: list[Path]) -> bool:
    if check.any_path_ok:
        return bool(existing)
    return len(existing) == len(check.paths)


def _stale_source(check: WorkflowCheck, newest_output: float | None) -> Path | None:
    if newest_output is None:
        return None
    for source in check.stale_after:
        source_mtime = _mtime(source)
        if source_mtime is not None and source_mtime > newest_output:
            return source
    return None


def build_data_freshness_status(
    checks: list[DataFreshnessCheck] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    item_statuses: dict[str, str] = {}
    for check in checks or build_data_freshness_checks():
        output_mtime = _mtime(check.path)
        existing_sources = _existing_paths(check.sources)
        newest_source = max((_mtime(path) for path in existing_sources), default=None)
        sources_ready = len(existing_sources) >= check.minimum_sources
        dependency_issues = [
            f"{item} ({item_statuses.get(item, 'Not checked')})"
            for item in check.dependencies
            if item_statuses.get(item) != "Fresh"
        ]

        if dependency_issues:
            status = "Not checked"
            note = f"Waiting for fresh dependencies: {', '.join(dependency_issues)}."
        elif output_mtime is None:
            if check.not_checked_until_sources and not sources_ready:
                status = "Not checked"
                note = "Waiting for required source files before this report can be checked."
            else:
                status = "Missing"
                note = f"Missing: {check.path}"
        elif check.minimum_sources and not sources_ready:
            status = "Not checked"
            note = "The file exists, but required source files are missing."
        elif newest_source is not None and newest_source > output_mtime:
            status = check.stale_status
            newest_path = max(existing_sources, key=lambda path: path.stat().st_mtime)
            note = f"Refresh because {newest_path} is newer than this file."
        else:
            status = "Fresh"
            note = (
                "Current relative to available source files."
                if check.sources
                else "File is available."
            )

        missing_sources = [str(path) for path in check.sources if not path.exists()]
        if status == "Not checked" and missing_sources:
            note = f"{note} Missing sources: {', '.join(missing_sources)}"

        rows.append(
            {
                "item": check.item,
                "status": status,
                "last_modified": _format_mtime(output_mtime),
                "source_last_modified": _format_mtime(newest_source),
                "file": str(check.path),
                "source_files": ", ".join(str(path) for path in check.sources),
                "command": "" if status == "Fresh" else check.command,
                "note": note,
                "recommendation": check.recommendation,
                "priority": check.priority,
            }
        )
        item_statuses[check.item] = status

    return pd.DataFrame(rows)


def recommend_data_freshness_action(status: pd.DataFrame) -> str:
    if status.empty or not {"status", "priority", "recommendation"}.issubset(status.columns):
        return "Data freshness is not available yet. Refresh the dashboard and try again."

    attention = status[status["status"] != "Fresh"]
    if attention.empty:
        return "No data refresh is needed right now."

    first = attention.sort_values(["priority", "item"], kind="stable").iloc[0]
    return str(first["recommendation"])


def build_workflow_status(checks: list[WorkflowCheck] | None = None) -> pd.DataFrame:
    rows: list[WorkflowItem] = []
    for check in checks or WORKFLOW_CHECKS:
        existing = _existing_paths(check.paths)
        complete = _is_complete(check, existing)
        newest_output = max((_mtime(path) for path in existing), default=None)
        stale_source = _stale_source(check, newest_output)

        if not complete:
            status = "Missing"
            missing = [str(path) for path in check.paths if not path.exists()]
            note = f"Missing: {', '.join(missing)}"
        elif stale_source is not None:
            status = "Needs refresh"
            note = f"Refresh because {stale_source} is newer than this report."
        else:
            status = "Complete"
            note = "Ready."

        rows.append(
            WorkflowItem(
                step=check.step,
                status=status,
                files=", ".join(str(path) for path in check.paths),
                last_modified=_format_mtime(newest_output),
                command=check.command if status != "Complete" else "",
                note=note,
            )
        )

    return pd.DataFrame([item.__dict__ for item in rows])
