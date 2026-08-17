#!/usr/bin/env python
"""Discover which markets The Odds API offers for the selected Week 1 window.

Default mode is free: it analyses the archived raw bulk response and makes no
network request. `--check-event-markets` additionally queries the per-event
odds endpoint, which is the only place additional markets such as BTTS exist;
that costs quota and is reported before it is spent.

Never prints or writes a credential. Never fabricates a price. Never edits a
protected file, allowlists a provider, enables cron, or places a bet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import STAGING_DIR
from epl_betting_lab.providers.env_file import load_provider_env
from epl_betting_lab.providers.odds_api_staging_provider import (
    API_KEY_ENV,
    DEFAULT_API_BASE_URL,
)
from epl_betting_lab.reports.provider_market_discovery import (
    EVENT_ONLY_MARKETS,
    discover_event_markets,
    estimate_quota_cost,
    save_provider_market_discovery,
    summarize_bulk_response,
)

import json
import os


def _latest_raw_response() -> Path | None:
    raw_dir = STAGING_DIR / "raw"
    if not raw_dir.is_dir():
        return None
    candidates = sorted(raw_dir.glob("*_odds_api_response.json"))
    return candidates[-1] if candidates else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-response-path",
        type=Path,
        help="Archived bulk response JSON. Defaults to the newest under data/staging/raw/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    parser.add_argument(
        "--check-event-markets",
        action="store_true",
        help=(
            "Query the per-event odds endpoint to determine BTTS availability. "
            "Costs quota (markets x regions per event)."
        ),
    )
    parser.add_argument(
        "--regions",
        default="us",
        help="Comma-separated regions for event discovery. Defaults to us.",
    )
    parser.add_argument(
        "--markets",
        default=",".join(EVENT_ONLY_MARKETS),
        help=f"Markets to discover per event. Defaults to {','.join(EVENT_ONLY_MARKETS)}.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Limit event requests (0 = all events in the window).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Provider Market Discovery")
    print(
        "Bulk analysis is free and offline. Event discovery is opt-in and its "
        "quota cost is reported first. No secrets, no fabricated odds, no "
        "protected file edits, no allowlisting, no bets."
    )

    raw_path = args.raw_response_path or _latest_raw_response()
    if raw_path is None:
        print("BLOCKED: no archived provider response found under data/staging/raw/.")
        return 2
    print(f"Raw response: {raw_path.name}")

    event_summary = None
    if args.check_event_markets:
        load_provider_env()
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        if not api_key:
            print(f"BLOCKED: `{API_KEY_ENV}` is not configured.")
            return 2

        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        bulk = summarize_bulk_response(payload if isinstance(payload, list) else [])
        events = bulk["events"]
        if args.max_events > 0:
            events = events[: args.max_events]

        regions = [r for r in args.regions.split(",") if r.strip()]
        markets = [m for m in args.markets.split(",") if m.strip()]
        estimate = estimate_quota_cost(
            event_count=len(events), markets=markets, regions=regions
        )
        print(
            "Quota estimate before paid calls: "
            f"{estimate['total_estimated_cost']} credit(s) "
            f"({estimate['cost_per_event_request']} per event x "
            f"{estimate['event_requests_planned']} event(s))"
        )

        event_summary = discover_event_markets(
            events,
            api_key=api_key,
            base_url=os.environ.get("EPL_ODDS_API_BASE_URL", DEFAULT_API_BASE_URL),
            regions=args.regions,
            markets=args.markets,
        )
        print(
            "Event endpoint results: "
            f"{event_summary['events_with_btts']}/{event_summary['event_count']} "
            "event(s) returned BTTS"
        )
        for error in event_summary["errors"]:
            print(f"WARNING: {error}")

    result = save_provider_market_discovery(
        raw_response_path=raw_path,
        output_dir=args.output_dir,
        event_summary=event_summary,
        regions=args.regions,
    )
    summary = result["summary"]
    totals = summary["totals_classification"]
    btts = summary["btts_classification"]

    print(f"Events considered: {summary['bulk_coverage']['event_count']}")
    print(f"Bulk markets seen: {summary['bulk_coverage']['markets_ever_returned']}")
    print(
        f"Totals: {totals['status']} "
        f"({totals['events_with_required_line']}/{totals['events_total']} with a "
        f"{totals['required_point']} line)"
    )
    print(f"  cause: {totals['root_cause']}")
    print(f"BTTS: {btts['status']} (event endpoint checked: {btts['checked_event_endpoint']})")
    print(f"  cause: {btts['root_cause']}")
    for error in summary["errors"]:
        print(f"WARNING: {error}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
