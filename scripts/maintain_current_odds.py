#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_upcoming_fixtures
from epl_betting_lab.reports.current_odds_maintenance import maintain_current_odds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview or add missing rows to data/manual/current_odds.csv.")
    parser.add_argument("--apply", action="store_true", help="Write missing rows to current_odds.csv after creating a backup.")
    parser.add_argument("--dry-run", action="store_true", help="Preview only. This is the default behavior.")
    parser.add_argument("--book", default="", help="Optional book name to prefill only on newly added rows.")
    parser.add_argument(
        "--week",
        "--matchweek",
        dest="week",
        default=None,
        help="Optional week/matchweek filter if upcoming fixtures include a week or matchweek column.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fixtures = load_upcoming_fixtures()
    paths = maintain_current_odds(
        fixtures,
        MANUAL_DIR / "current_odds.csv",
        OUTPUTS_DIR,
        apply=args.apply,
        book=args.book,
        week=args.week,
    )
    mode = "Applied" if args.apply else "Previewed"
    print(f"{mode} current odds maintenance.")
    print(f"Preview CSV: {paths['csv']}")
    print(f"Report: {paths['markdown']}")
    if "backup" in paths:
        print(f"Backup: {paths['backup']}")
    if not args.apply:
        print("No odds file was changed. Run `python scripts/maintain_current_odds.py --apply` to add missing rows.")


if __name__ == "__main__":
    main()
