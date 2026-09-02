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
from datetime import date
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, STAGING_DIR
from epl_betting_lab.data.fetch_fixtures import (
    FixturesUnavailable,
    NoUpcomingFixtures,
    fetch_upcoming_fixtures,
)


def staged_provider_fixtures(path: Path, today: date | None = None) -> pd.DataFrame | None:
    """Upcoming fixtures from the provider staging, in the slate's shape."""
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return None
    if not {"date", "home_team", "away_team"}.issubset(frame.columns):
        return None
    parsed = pd.to_datetime(frame["date"], errors="coerce").dt.date
    moment = today or date.today()
    keep = frame[parsed >= moment].copy()
    if keep.empty:
        return None
    out = pd.DataFrame({
        "date": [d.isoformat() for d in parsed[keep.index]],
        "home_team": keep["home_team"].astype(str).str.strip().values,
        "away_team": keep["away_team"].astype(str).str.strip().values,
        "notes": "from provider staging: Football-Data listed no upcoming fixture",
    })
    return out.drop_duplicates(["date", "home_team", "away_team"]).sort_values(["date", "home_team"]).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=MANUAL_DIR / "upcoming_fixtures.csv",
        help="Where to write the slate.",
    )
    parser.add_argument(
        "--staging-fixtures",
        type=Path,
        default=STAGING_DIR / "upcoming_fixtures_staging.csv",
        help="The provider's staged fixtures, used only when Football-Data lists none.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    args = parser.parse_args()

    try:
        fixtures = fetch_upcoming_fixtures()
    except NoUpcomingFixtures as exc:
        # A quiet week at Football-Data, not a fault: the feed lists only the
        # coming round and goes empty around an international break. But the
        # slate on file is whatever the last run left — on a fresh runner that
        # is the committed copy, which can be weeks old — and a slate with no
        # fixture in the card's window blocks the card at validation with a
        # wall of `fixture_not_found`. That happened on 2026-09-01.
        #
        # So fall back to the provider's own staged fixtures, when they are on
        # hand and upcoming. Football-Data stays the primary and independent
        # source; the provider only fills a week the feed has nothing for, and
        # the file says so in its notes column.
        print(f"Nothing at Football-Data: {exc}")
        staged = staged_provider_fixtures(args.staging_fixtures)
        if staged is None or staged.empty:
            if args.path.is_file():
                print(f"The previous slate at `{args.path}` stands.")
            return 0
        fixtures = staged
        print(f"Using {len(fixtures)} upcoming fixture(s) from the provider staging instead.")
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
