#!/usr/bin/env python
"""Build one processed dataset per English division from Football-Data.co.uk.

Each division is built separately and deliberately. See
`epl_betting_lab.data.fetch_football_data` for why pooling them would produce a
rating scale that spans four leagues sharing almost no opponents.
"""
from __future__ import annotations

import argparse

from epl_betting_lab.config import DEFAULT_SEASONS, DIVISION_NAMES, LEAGUE_CODE
from epl_betting_lab.data.fetch_football_data import (
    fetch_and_build_dataset,
    processed_path_for,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch historical English league data from Football-Data.co.uk"
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=DEFAULT_SEASONS,
        help="Season codes like 2122 2223 2324 2425 2526",
    )
    parser.add_argument(
        "--divisions",
        nargs="+",
        default=[LEAGUE_CODE],
        choices=sorted(DIVISION_NAMES),
        help=(
            "Division codes to build, each into its own file. "
            "E0 Premier League, E1 Championship, E2 League One, E3 League Two."
        ),
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download even if files already exist"
    )
    args = parser.parse_args()

    failed: list[str] = []
    for division in args.divisions:
        try:
            df = fetch_and_build_dataset(
                args.seasons, force=args.force, league=division
            )
        except Exception as exc:
            # One division failing must not discard the ones that worked. A
            # partial build is reported and exits non-zero; it is not silently
            # rounded up to success.
            print(f"{division} ({DIVISION_NAMES[division]}) could not be built: {exc}")
            failed.append(division)
            continue
        # Report the seasons actually in the data, not the ones asked for. The
        # season being played is skipped until it has results, and naming it here
        # would misreport what the model is fitted on.
        included = [str(season) for season in sorted(df["season"].unique())]
        print(
            f"{division} ({DIVISION_NAMES[division]}): {len(df):,} matches across "
            f"seasons {', '.join(included)} -> {processed_path_for(division)}"
        )

    if failed:
        raise SystemExit(f"Divisions that could not be built: {', '.join(failed)}")


if __name__ == "__main__":
    main()
