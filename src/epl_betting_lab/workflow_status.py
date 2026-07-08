from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR


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


WORKFLOW_CHECKS = [
    WorkflowCheck(
        "Current odds file",
        (MANUAL_DIR / "current_odds.csv",),
        "cp data/manual/current_odds_template.csv data/manual/current_odds.csv",
    ),
    WorkflowCheck(
        "Current odds validation",
        (OUTPUTS_DIR / "current_odds_validation.csv", OUTPUTS_DIR / "current_odds_validation.md"),
        "python scripts/validate_current_odds.py",
        stale_after=(MANUAL_DIR / "current_odds.csv",),
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
