#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import import process_current_odds_import


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or safely apply real sportsbook odds from a manual import CSV."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up and update current_odds.csv with valid rows only.",
    )
    parser.add_argument(
        "--input",
        default=str(MANUAL_DIR / "current_odds_import.csv"),
        help="Import CSV path. Defaults to data/manual/current_odds_import.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = process_current_odds_import(
        import_path=Path(args.input),
        current_odds_path=MANUAL_DIR / "current_odds.csv",
        output_dir=OUTPUTS_DIR,
        apply=args.apply,
    )
    if args.apply and "current_odds" in paths:
        print("Applied current odds import.")
    elif args.apply:
        print("Apply requested, but no valid additions or updates were written.")
    else:
        print("Previewed current odds import.")
    print(f"Preview CSV: {paths['csv']}")
    print(f"Report: {paths['markdown']}")
    if "backup" in paths:
        print(f"Backup: {paths['backup']}")
    if not args.apply:
        print(
            "No odds were changed. Review the report, then run "
            "`python scripts/import_current_odds.py --apply` if it looks correct."
        )


if __name__ == "__main__":
    main()
