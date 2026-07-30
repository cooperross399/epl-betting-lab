#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.scheduled_thursday_workflow import (
    run_scheduled_thursday_workflow,
)


def _print_progress(step: str, status: str, message: str) -> None:
    print(f"[{status}] {step}: {message}")


def main() -> int:
    print("EPL Betting Lab - Scheduled Thursday Workflow")
    print(
        "Safe mode: report generation only. No odds, imports, ledger rows, profiles, "
        "settlements, or bets will be changed."
    )
    result = run_scheduled_thursday_workflow(progress=_print_progress)
    status = str(result["status"])
    summary = result["summary"]
    print("")
    print(f"Workflow status: {status}")
    print(f"Recommended next action: {summary['recommended_next_action']}")
    print(f"Markdown summary: {result['markdown']}")
    print(f"JSON summary: {result['json']}")
    print("No bets were placed and no protected manual files were edited.")
    if status == "Failed":
        return 1
    if status == "Blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
