#!/usr/bin/env python
"""Per-match team xG into data/processed/understat_team_xg.csv.

Understat first. When it cannot be read, the table already on disk is kept
and every match it lacks is filled from Fantasy Premier League's Opta expected
goals (`data.fetch_understat_xg.fetch_and_fill_team_xg`), after refreshing the
FPL logs so the matches since the last props refresh are there to fill. Exits
non-zero only when no match could be added from either source, which is the
case the run summary reports as "goals alone".
"""
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import PROCESSED_DIR
from epl_betting_lab.data.fetch_understat_xg import (
    DEFAULT_UNDERSTAT_SEASONS,
    fetch_and_build_team_xg,
    fetch_and_fill_team_xg,
)
from epl_betting_lab.providers.fpl_players import FplError, fetch_fpl_player_data, write_fpl_data
from epl_betting_lab.providers.understat_players import UnderstatError


def _refresh_fpl_logs() -> None:
    try:
        result = fetch_fpl_player_data()
    except (FplError, OSError, ValueError) as exc:
        print(f"WARNING: FPL logs not refreshed for the xG fill: {exc}")
        return
    if result.logs.empty:
        print("WARNING: FPL returned no appearances; the carried logs stand.")
        return
    write_fpl_data(result, Path(PROCESSED_DIR))
    print(f"FPL logs refreshed for the xG fill: {len(result.logs)} appearance(s).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", nargs="+", default=list(DEFAULT_UNDERSTAT_SEASONS))
    parser.add_argument("--force", action="store_true", help="Re-download cached seasons")
    args = parser.parse_args()
    try:
        table = fetch_and_build_team_xg(args.seasons, force=args.force)
        note = "Team xG: Understat."
    except (UnderstatError, OSError, ValueError) as exc:
        print(f"Understat could not be read: {exc}")
        _refresh_fpl_logs()

        def still_down(url: str) -> object:
            raise UnderstatError(f"{exc}")

        try:
            table, note = fetch_and_fill_team_xg(args.seasons, requester=still_down)
        except (UnderstatError, OSError, ValueError) as final:
            print(f"No match could be added from FPL either: {final}")
            return 1
    print(note)
    print(f"Built {len(table):,} matches with team xG.")
    print("Saved to data/processed/understat_team_xg.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
