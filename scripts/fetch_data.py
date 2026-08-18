#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.config import DEFAULT_SEASONS
from epl_betting_lab.data.fetch_football_data import fetch_and_build_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch historical EPL data from Football-Data.co.uk")
    parser.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS, help="Season codes like 2122 2223 2324 2425 2526")
    parser.add_argument("--force", action="store_true", help="Re-download even if files already exist")
    args = parser.parse_args()

    df = fetch_and_build_dataset(args.seasons, force=args.force)
    # Report the seasons actually in the data, not the ones asked for. The
    # season being played is skipped until it has results, and naming it here
    # would misreport what the model is fitted on.
    included = [str(season) for season in sorted(df["season"].unique())]
    print(f"Built dataset with {len(df):,} matches across seasons: {', '.join(included)}")
    print("Saved to data/processed/epl_historical_matches.csv")


if __name__ == "__main__":
    main()
