#!/usr/bin/env python
"""Who is missing this round, from the fantasy game's public squad list.

    PYTHONPATH=src python scripts/fetch_fpl_availability.py

One keyless request (`bootstrap-static`), written to
`data/processed/fpl_availability.csv` with each player's status, his stated
chance of playing, his position, minutes, points and expected goal
involvement. The card's match context (`models/match_context.py`) reads it
to take the missing regulars off each club's attack and defence; the props
card reads it to skip players who will not play.

Soft on purpose: a failure prints a warning and exits 0, and the previous
file, if any, stands. The card then reads nobody as missing and says so.
No odds, no credit, no bet.
"""
from __future__ import annotations

import sys
from pathlib import Path

from epl_betting_lab.config import PROCESSED_DIR
from epl_betting_lab.providers.fpl_players import (
    FPL_AVAILABILITY_FILENAME,
    FPL_BASE_URL,
    FplError,
    _default_requester,
    build_fpl_availability,
)


def main(argv: list[str] | None = None) -> int:
    directory = Path(argv[0]) if argv else Path(PROCESSED_DIR)
    try:
        bootstrap = _default_requester(f"{FPL_BASE_URL}/bootstrap-static/")
        if not isinstance(bootstrap, dict) or not bootstrap.get("elements"):
            raise FplError("FPL's bootstrap carries no players.")
        table = build_fpl_availability(bootstrap)
    except Exception as exc:  # soft: the card must not depend on this
        print(f"WARNING: availability not refreshed: {type(exc).__name__}: {exc}")
        return 0
    if table.empty:
        print("WARNING: FPL listed no players; the previous availability file stands.")
        return 0
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / FPL_AVAILABILITY_FILENAME
    table.to_csv(path, index=False)
    flagged = int((table["status"].astype(str).str.lower() != "a").sum())
    print(f"Availability: {len(table)} players, {flagged} flagged, written to {path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
