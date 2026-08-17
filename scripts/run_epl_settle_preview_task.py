#!/usr/bin/env python
"""EPL SETTLE (IGNORE) scheduled-task bridge.

Preview only. This command reads `bet_ledger.csv` and reports what is open. It
has no flag and no code path that applies settlement, edits the ledger, uses
force mode, or places a bet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.scheduled_task_bridge import (
    save_epl_settle_preview_task,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    parser.add_argument(
        "--ledger-path",
        type=Path,
        help="Bet ledger to read. Defaults to data/manual/bet_ledger.csv.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - EPL Settle Preview Task (IGNORE)")
    print(
        "Preview only: never applies settlement, never edits bet_ledger.csv, "
        "never uses force mode, never places bets."
    )
    result = save_epl_settle_preview_task(
        output_dir=args.output_dir,
        ledger_path=args.ledger_path,
    )
    summary = result["summary"]

    print(f"Mode: {summary['mode']}")
    print(f"Ledger: {summary['ledger_path']}")
    print(f"Ledger rows: {summary['ledger_row_count']}")
    print(f"Open bets: {summary['open_bet_count']}")
    print(f"Settled bets: {summary['settled_bet_count']}")
    print(f"Bets this run would settle: {summary['would_settle_count']}")
    for blocker in summary["blockers"]:
        print(f"BLOCKED: {blocker}")
    print(f"Next action: {summary['next_action']}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")

    return 0 if not summary["blockers"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
