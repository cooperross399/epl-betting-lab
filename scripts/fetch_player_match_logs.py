#!/usr/bin/env python
"""Fetch per-player match logs from Understat into a processed CSV.

Player props need player-level rates to be modelled and player-level results
to be settled; Football-Data carries neither. This fetches both from
Understat's public endpoints, one request per played match, politely spaced,
and never twice for the same match — the CSV on disk is the working dataset
and each run only adds what is missing.

Reads no odds, prices nothing, places no bet, applies no settlement, and
touches no protected manual file.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from epl_betting_lab.config import PROCESSED_DIR
from epl_betting_lab.providers.understat_players import (
    LOG_FIELDS,
    fetch_player_match_logs,
)


DEFAULT_OUTPUT = "player_match_logs.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        default="2024,2025,2026",
        help=(
            "Comma-separated Understat season names; 2025 is 2025/26. "
            "Defaults to the two full seasons behind the current one plus "
            "the current one."
        ),
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Seconds between match requests. Politeness floor, not a knob to zero.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    output_path = Path(PROCESSED_DIR) / args.output

    already: set[str] = set()
    if output_path.is_file():
        with output_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                match_id = str(row.get("match_id", "")).strip()
                if match_id:
                    already.add(match_id)

    print("EPL Betting Lab - Player Match Logs (Understat)")
    print(f"Seasons: {', '.join(seasons)}")
    if already:
        print(f"Already hold {len(already)} match(es); they will not be re-fetched.")

    result = fetch_player_match_logs(
        seasons,
        already_fetched=already,
        sleep_seconds=args.sleep,
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    exists = output_path.is_file()
    mode = "a" if exists else "w"
    with output_path.open(mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LOG_FIELDS))
        if mode == "w":
            writer.writeheader()
        for row in result.rows:
            writer.writerow(row)

    print(f"Matches seen: {result.matches_seen}")
    print(
        f"Fetched: {result.matches_fetched}; already had: {result.already_had}; "
        f"not played yet: {result.not_played_yet}"
    )
    print(f"Rows written: {len(result.rows)} -> {output_path}")
    for error in result.errors:
        print(f"WARNING: {error}")
    print(
        "No odds were read, no price was fabricated, no bet was placed, and "
        "no settlement was applied."
    )
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
