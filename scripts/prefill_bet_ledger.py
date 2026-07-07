#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.bet_ledger import ensure_ledger_template
from epl_betting_lab.reports.ledger_prefill import (
    DEFAULT_PREFILL_STATUSES,
    prefill_ledger_from_weekly_card,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create draft bet ledger rows from the latest weekly card."
    )
    parser.add_argument(
        "--weekly-card",
        default=str(OUTPUTS_DIR / "weekly_card.csv"),
        help="Path to weekly_card.csv. Default: data/outputs/weekly_card.csv",
    )
    parser.add_argument(
        "--ledger",
        default=str(MANUAL_DIR / "bet_ledger.csv"),
        help="Path to the manual bet ledger. Default: data/manual/bet_ledger.csv",
    )
    parser.add_argument(
        "--include-pass",
        action="store_true",
        help="Also prefill PASS rows from the weekly card. Default only includes BETTABLE and LEAN.",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Replace existing rows with the same bet_id. Leave off to avoid overwriting ledger entries.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_ledger_template(MANUAL_DIR / "bet_ledger_template.csv")
    ensure_ledger_template(MANUAL_DIR / "bet_ledger.csv")

    statuses = [*DEFAULT_PREFILL_STATUSES]
    if args.include_pass:
        statuses.append("PASS")

    stats = prefill_ledger_from_weekly_card(
        weekly_card_path=Path(args.weekly_card),
        ledger_path=Path(args.ledger),
        allowed_statuses=statuses,
        overwrite_existing=args.overwrite_existing,
    )

    print("Prefilled bet ledger from weekly card.")
    print(f"Draft rows found: {stats['draft_rows']}")
    print(f"Added rows: {stats['added_rows']}")
    print(f"Skipped duplicates: {stats['skipped_duplicates']}")
    print(f"Overwritten rows: {stats['overwritten_rows']}")
    print(f"Ledger path: {args.ledger}")


if __name__ == "__main__":
    main()
