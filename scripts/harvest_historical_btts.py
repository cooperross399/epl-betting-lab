#!/usr/bin/env python
"""Buy historical BTTS prices so the market can be measured.

BTTS produces most of the picks on a card and has never been backtested for
profit: Football-Data ships no BTTS odds at all. The provider sells them at ten
credits per event, so this spends real money and refuses to spend past a
ceiling given on the command line.
"""
from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.config import PROCESSED_DIR
from epl_betting_lab.providers.env_file import load_provider_env
from epl_betting_lab.providers.historical_btts import (
    HarvestBudget,
    harvest_btts_history,
    matchdays_between,
)

API_KEY_ENV = "EPL_ODDS_API_KEY"
DEFAULT_OUTPUT = "historical_btts_odds.csv"
FIELDS = [
    "sampled_at",
    "commence_time",
    "home_team",
    "away_team",
    "btts_yes_american",
    "btts_no_american",
]


def _day(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD, inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD, inclusive")
    parser.add_argument(
        "--credit-limit",
        type=int,
        required=True,
        help="Hard ceiling on provider credits. The harvest stops rather than "
        "exceed it, and reports that it stopped.",
    )
    parser.add_argument(
        "--hours-before",
        type=int,
        default=3,
        help="Sample this many hours before kick-off. A card is built and bet "
        "at a set time, so a fixed lead is the honest comparison.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--append",
        action="store_true",
        help="Add to an existing file rather than replacing it, so a season "
        "can be bought in affordable pieces.",
    )
    args = parser.parse_args()

    load_provider_env()
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"BLOCKED: `{API_KEY_ENV}` is not configured.")
        return 2

    days = matchdays_between(_day(args.start), _day(args.end))
    print(f"EPL Betting Lab - Historical BTTS harvest")
    print(f"Range: {args.start} to {args.end} ({len(days)} day(s))")
    print(f"Credit ceiling: {args.credit_limit}")
    print(f"Sampling {args.hours_before}h before kick-off.")

    result = harvest_btts_history(
        days,
        api_key=api_key,
        budget=HarvestBudget(limit=args.credit_limit),
        hours_before=args.hours_before,
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(PROCESSED_DIR) / args.output
    exists = path.is_file()
    mode = "a" if (args.append and exists) else "w"
    with path.open(mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if mode == "w":
            writer.writeheader()
        for row in result.rows:
            writer.writerow(row)

    print(f"Snapshots: {result.snapshots}")
    print(f"Events seen: {result.events_seen}; with BTTS: {result.events_with_btts}")
    print(f"Rows written: {len(result.rows)} -> {path}")
    print(f"Credits spent: {result.credits_spent}")
    if result.stopped_early:
        print("STOPPED EARLY: the credit ceiling was reached before the range ended.")
    for error in result.errors:
        print(f"WARNING: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
