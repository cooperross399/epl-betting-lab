#!/usr/bin/env python
import argparse
import sys

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.dashboard_actions import run_thursday_best_bets_report
from epl_betting_lab.reports.current_odds_validation import CurrentOddsValidationError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Thursday best-bets report from manual current odds.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Generate a preview even when serious current-odds validation issues exist.",
    )
    parser.add_argument(
        "--overwrite-archive",
        action="store_true",
        help="Replace the archive snapshot if this run reuses an existing archive timestamp.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = run_thursday_best_bets_report(force=args.force, overwrite_archive=args.overwrite_archive)

    print((OUTPUTS_DIR / "thursday_best_bets.md").read_text(encoding="utf-8"))
    print(f"\nSaved CSV to {paths['csv']}")
    print(f"Saved Markdown to {paths['markdown']}")
    if "archive_csv" in paths:
        print(f"Archived CSV to {paths['archive_csv']}")
        print(f"Archived Markdown to {paths['archive_markdown']}")
        print(f"Archived metadata to {paths['archive_metadata']}")


if __name__ == "__main__":
    try:
        main()
    except CurrentOddsValidationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
