#!/usr/bin/env python
"""Write the cup and Champions League section the card appends.

Separate from the card build on purpose. The Premier League card must not
depend on fourteen league datasets and a public-domain results repository being
reachable, so this writes a file and the card reads it if it is there. A run
where this fails loses the section and keeps the card.

Costs no provider quota: prices come from the observation feed the Closing
Snapshot already collects, and every rating input is free.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from epl_betting_lab.reports.extra_competitions_card import (
    COMPETITIONS,
    build_extra_card,
    render_extra_card,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", type=Path, default=PROCESSED_DIR / "price_feed_extra.csv")
    parser.add_argument(
        "--out", type=Path, default=OUTPUTS_DIR / "extra_competitions_card.md"
    )
    args = parser.parse_args()

    if not args.feed.is_file():
        print(f"No observation feed at `{args.feed}`; no section written.")
        return 0
    try:
        feed = pd.read_csv(args.feed)
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        print(f"The observation feed could not be read ({exc}); no section written.")
        return 0

    cards = {}
    for key in COMPETITIONS:
        try:
            cards[key] = build_extra_card(feed, key)
        except Exception as exc:
            # One competition failing must not cost the other. A pool that
            # could not be built is a missing section, not a broken card.
            print(f"{key}: could not be built ({exc}).")
    if not cards:
        print("No competition could be built; no section written.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(render_extra_card(cards)), encoding="utf-8")
    total = sum(len(c.selections) for c in cards.values())
    print(f"Wrote {args.out} — {total} selection(s) across {len(cards)} competition(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
