#!/usr/bin/env python
"""Append the prices this run staged to the durable price feed.

Costs nothing: every refresh already fetches several hundred book-level prices
and discards them at the end of the run. This keeps them, so closing-line value
becomes measurable for the live card — including for corners, which no source
retains historically and which are the majority of what the card stakes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import PROCESSED_DIR, STAGING_DIR
from epl_betting_lab.reports.price_feed import (
    append_snapshot,
    load_feed,
    save_feed,
    snapshot_rows,
)

DEFAULT_FEED = PROCESSED_DIR / "price_feed.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-odds", type=Path, default=STAGING_DIR / "current_odds_staging.csv")
    parser.add_argument("--provenance", type=Path, default=STAGING_DIR / "staging_provenance.json")
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()

    if not args.staged_odds.is_file() or not args.provenance.is_file():
        print("No staged prices to record this run; the feed is unchanged.")
        return 0
    try:
        odds = pd.read_csv(args.staged_odds)
        provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
        print(f"Staged prices could not be read ({exc}); the feed is unchanged.")
        return 0

    snapshot = snapshot_rows(odds, provenance)
    if snapshot.empty:
        print("Staged prices carried no usable observation; the feed is unchanged.")
        return 0

    before = load_feed(args.feed)
    after = append_snapshot(before, snapshot)
    save_feed(after, args.feed)
    added = len(after) - len(before)
    when = snapshot["observed_at"].iloc[0]
    print(f"Observed {len(snapshot)} price(s) at {when}; {added} new, feed now {len(after)} row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
