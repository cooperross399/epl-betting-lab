#!/usr/bin/env python
"""Add ESPN finals to the Premier League dataset for fixtures Football-Data has not published.

Run after `scripts/fetch_data.py`. Football-Data's rows are never touched; an
ESPN row is added only for a fixture Football-Data does not hold yet, and
Football-Data's row replaces it on the first run after it is published. Keyless
and soft: if ESPN cannot be read the dataset is left exactly as it was. See
`epl_betting_lab.data.espn_results` for what an ESPN row does and does not carry.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import CURRENT_SEASON, LEAGUE_CODE
from epl_betting_lab.data.espn_results import supplement_file
from epl_betting_lab.data.fetch_football_data import processed_path_for


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=processed_path_for(LEAGUE_CODE))
    parser.add_argument("--season", default=CURRENT_SEASON)
    args = parser.parse_args(argv)

    status = supplement_file(args.dataset, season_code=args.season)
    if status.unmapped:
        print(
            "ESPN names the reviewed alias table does not map, skipped rather "
            f"than guessed: {', '.join(sorted(set(status.unmapped)))}"
        )
    if status.error:
        print(f"ESPN finals were not added: {status.error}")
        return 1
    if status.added:
        print(
            f"{status.added} finished fixture(s) of {args.season} that Football-Data "
            "has not published yet are in the dataset from ESPN (score, corners, "
            "shots; no odds, no card counts). Football-Data's rows replace them "
            "once published."
        )
    else:
        print("Football-Data holds every finished fixture ESPN lists; nothing added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
