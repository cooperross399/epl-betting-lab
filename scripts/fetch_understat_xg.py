#!/usr/bin/env python
"""Fetch per-match team xG from Understat into data/processed/understat_team_xg.csv."""
from __future__ import annotations

import argparse

from epl_betting_lab.data.fetch_understat_xg import DEFAULT_UNDERSTAT_SEASONS, fetch_and_build_team_xg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=list(DEFAULT_UNDERSTAT_SEASONS))
    parser.add_argument("--force", action="store_true", help="Re-download cached seasons")
    args = parser.parse_args()
    table = fetch_and_build_team_xg(args.seasons, force=args.force)
    print(f"Built {len(table):,} matches with team xG across seasons: {', '.join(args.seasons)}")
    print("Saved to data/processed/understat_team_xg.csv")


if __name__ == "__main__":
    main()
