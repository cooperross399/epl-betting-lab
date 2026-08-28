#!/usr/bin/env python
"""Refresh `data/manual/upcoming_fixtures.csv` from Football-Data's feed.

The card can only look as far ahead as this file goes, and while it was typed
by hand that was a standing appointment somebody had to keep. Now it is
fetched. Football-Data is public CSV over HTTP: no key, no quota, no secret.

The file is only ever replaced by a fetch that produced fixtures. A bad day at
Football-Data leaves the previous slate in place and says so, because a slate
erased is worse than a slate that is a few days old.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR
from epl_betting_lab.data.fetch_fixtures import (
    FixturesUnavailable,
    fetch_upcoming_fixtures,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=MANUAL_DIR / "upcoming_fixtures.csv",
        help="Where to write the slate.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    args = parser.parse_args()

    try:
        fixtures = fetch_upcoming_fixtures()
    except FixturesUnavailable as exc:
        print(f"Fixtures were not refreshed: {exc}")
        if args.path.is_file():
            print(f"The previous slate at `{args.path}` was left in place.")
        return 1

    before = 0
    if args.path.is_file():
        try:
            before = len(pd.read_csv(args.path))
        except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
            before = 0

    window = f"{fixtures['date'].iloc[0]} through {fixtures['date'].iloc[-1]}"
    print(f"Fetched {len(fixtures)} upcoming fixture(s): {window}")

    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0

    args.path.parent.mkdir(parents=True, exist_ok=True)
    fixtures.to_csv(args.path, index=False)
    print(f"Wrote {len(fixtures)} fixture(s) to `{args.path}` (was {before}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
