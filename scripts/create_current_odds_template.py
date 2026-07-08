#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys

from epl_betting_lab.config import MANUAL_DIR
from epl_betting_lab.data.loaders import load_upcoming_fixtures
from epl_betting_lab.reports.current_odds_template import create_current_odds_template


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a manual current odds entry template from upcoming fixtures.")
    parser.add_argument("--overwrite", action="store_true", help="Replace data/manual/current_odds.csv if it already exists.")
    parser.add_argument("--book", default="", help="Optional book name to prefill in every row.")
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
    path, template, message = create_current_odds_template(
        fixtures,
        MANUAL_DIR / "current_odds.csv",
        overwrite=args.overwrite,
        book=args.book,
        week=args.week,
    )
    print(message)
    print(f"\nRows created: {len(template)}")
    print(f"Saved to: {path}")


if __name__ == "__main__":
    try:
        main()
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
