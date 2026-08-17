#!/usr/bin/env python
"""Archive the current automated card and compare the two most recent runs.

Reports what changed between runs: selections added, removed, moved between
sections, and prices that moved. It never regenerates a card, contacts a
provider, edits a protected file, places a bet, or applies settlement.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.card_history import archive_card, save_card_comparison


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Defaults to data/outputs.")
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Compare existing archives without archiving the current card.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Automated Card History")
    print(
        "Archives the current card and compares the two most recent runs. "
        "No card regeneration, no provider contact, no bets, no settlement."
    )

    if not args.no_archive:
        archived = archive_card(output_dir=args.output_dir)
        if archived.get("archived"):
            print(f"Archived: {archived['path']}")
        else:
            print(f"Not archived: {archived.get('reason', 'unknown reason')}")

    result = save_card_comparison(output_dir=args.output_dir)
    summary = result["summary"]

    print(f"Archived cards: {summary['archived_card_count']}")
    if not summary["comparable"]:
        for note in summary["notes"]:
            print(f"NOTE: {note}")
    else:
        print(f"Added: {len(summary['added'])}")
        print(f"Removed: {len(summary['removed'])}")
        print(f"Moved section: {len(summary['moved_section'])}")
        print(f"Price changed: {len(summary['price_changed'])}")
        print(f"Unchanged: {summary['unchanged_count']}")
        for row in summary["price_changed"][:5]:
            print(
                f"  price: {row['label']} {row['from_price']} -> {row['to_price']}"
            )

    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
