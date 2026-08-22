#!/usr/bin/env python
"""Fetch live player-prop prices into data/staging/player_props_staging.csv.

Props live in their own staging file, invisible to the card pipeline: the
match odds validator rightly errors on markets it does not know, and no
prop reaches a card without a reviewed policy approval. This is dispatched
deliberately — never scheduled — and it states its quota cost before
spending it.

No pick, no card, no ledger, no policy edit, no cron. The credential is
read from the environment or a gitignored .env and never printed.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from epl_betting_lab.providers.env_file import load_provider_env
from epl_betting_lab.providers.player_props_staging import (
    LIVE_CREDITS_PER_EVENT,
    PlayerPropsFetchError,
    fetch_player_props,
    write_props_staging,
)


API_KEY_ENV = "EPL_ODDS_API_KEY"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Cap how many events are priced (0 = the whole slate).",
    )
    parser.add_argument(
        "--overwrite-staging",
        action="store_true",
        help="Replace an existing props staging file intentionally.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_provider_env()
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"BLOCKED: `{API_KEY_ENV}` is not configured.")
        return 2

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("EPL Betting Lab - Player Props Staging Fetch")
    print(
        "Props stage in their own file and reach no card without a reviewed "
        "policy approval. No pick, no bet, no settlement, no cron."
    )
    print(
        f"Cost: {LIVE_CREDITS_PER_EVENT} credit(s) per event"
        + (f", capped at {args.max_events} event(s)." if args.max_events else ".")
    )
    try:
        result = fetch_player_props(
            api_key=api_key,
            max_events=args.max_events,
            fetched_at=fetched_at,
        )
        target = write_props_staging(
            result.rows, overwrite=args.overwrite_staging
        )
    except PlayerPropsFetchError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    print(f"Events on the slate: {result.events_seen}")
    print(f"Events priced: {result.events_priced}")
    print(f"Rows written: {len(result.rows)} -> {target}")
    print(f"Credits spent: {result.credits_spent}")
    for error in result.errors:
        print(f"WARNING: {error}")
    print("Safety: the credential was not printed or written.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
