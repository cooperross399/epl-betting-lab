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
    probe_totals_regions,
    discover_event_markets,
    estimate_quota_cost,
    save_provider_market_discovery,
    fetch_events_live,
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


def _parse_line_coverage(raw: str) -> list[tuple[str, float]]:
    """"market@line,market@line" -> [(market, line)]."""
    pairs: list[tuple[str, float]] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or "@" not in chunk:
            continue
        market, _, line = chunk.partition("@")
        try:
            pairs.append((market.strip(), float(line)))
        except ValueError:
            continue
    return pairs


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
        "--probe-totals-regions",
        default="",
        help=(
            "Comma-separated regions to probe for the required totals line. "
            "Read-only: writes no staging bundle and creates no archived run. "
            "Costs markets x regions."
        ),
    )
    parser.add_argument(
        "--line-coverage",
        default="",
        help=(
            "Comma-separated market@line pairs, e.g. "
            "alternate_totals@2.5,alternate_totals_corners@9.5. Reports which "
            "bookmakers carry that exact line, across how many fixtures. A line "
            "offered only by a book with no account is not a price."
        ),
    )
    parser.add_argument(
        "--dump-outcome-shapes",
        action="store_true",
        help=(
            "Print how each returned market shapes its outcomes, so a parser "
            "can be written against the real field names rather than guessed. "
            "Reports structure only: names, descriptions and points, never a "
            "price and never the credential."
        ),
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
    if raw_path is None and not (args.probe_totals_regions or args.check_event_markets):
        print("BLOCKED: no archived provider response found under data/staging/raw/.")
        return 2
    if raw_path is not None:
        print(f"Raw response: {raw_path.name}")
    else:
        # The region probe fetches live, so it does not need an archived
        # response. Requiring one made the probe unrunnable in CI, where
        # data/staging/raw/ is not committed - which is precisely where the
        # probe has a working credential.
        print(
            "No archived provider response found. Running the live probe only; "
            "the bulk analysis and report need an archived response."
        )

    event_summary = None
    if args.check_event_markets:
        load_provider_env()
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        if not api_key:
            print(f"BLOCKED: `{API_KEY_ENV}` is not configured.")
            return 2

        if raw_path is not None:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            bulk = summarize_bulk_response(payload if isinstance(payload, list) else [])
            events = bulk["events"]
        else:
            # The events list is a free endpoint, and event discovery only needs
            # the ids. Requiring an archived bulk response made this unrunnable
            # in CI, where data/staging/raw/ is not committed - which is exactly
            # where the working credential lives.
            print("No archived response; fetching the free events list instead.")
            events = fetch_events_live(api_key=api_key)
            print(f"Events in the provider window: {len(events)}")
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
            dump_outcome_shapes=args.dump_outcome_shapes,
            line_coverage=_parse_line_coverage(args.line_coverage),
        )
        print(
            "Event endpoint results: "
            f"{event_summary['events_with_btts']}/{event_summary['event_count']} "
            "event(s) returned BTTS"
        )
        returned = event_summary.get("markets_returned") or []
        absent = event_summary.get("markets_absent") or []
        print(f"Markets returned: {', '.join(returned) or 'none'}")
        if absent:
            print(f"Markets requested but never returned: {', '.join(absent)}")
        for market, shape in (event_summary.get("outcome_shapes") or {}).items():
            print(f"\n=== {market}  (example book: {shape['example_bookmaker']})")
            print(f"    outcome fields: {', '.join(shape['outcome_fields'])}")
            for outcome in shape["outcomes"]:
                print(
                    "    name={name!r} description={description!r} "
                    "point={point!r} priced={has_price}".format(**outcome)
                )
        for key, books in (event_summary.get("line_coverage") or {}).items():
            print(f"\n=== line coverage: {key}")
            if not books:
                print("    no bookmaker offered this line on any fixture")
            for book, count in sorted(books.items(), key=lambda kv: -kv[1]):
                print(f"    {book:20} {count} fixture(s)")
        for error in event_summary["errors"]:
            print(f"WARNING: {error}")

    if args.probe_totals_regions:
        load_provider_env()
        api_key = os.environ.get(API_KEY_ENV, "").strip()
        if not api_key:
            print(f"BLOCKED: `{API_KEY_ENV}` is not configured.")
            return 2
        regions = [r for r in args.probe_totals_regions.split(",") if r.strip()]
        print(
            f"Totals region probe: {len(regions)} region(s), estimated cost "
            f"{len(regions)} credit(s) (1 market x 1 region each)."
        )
        probe = probe_totals_regions(
            api_key=api_key,
            regions=regions,
            base_url=os.environ.get("EPL_ODDS_API_BASE_URL", DEFAULT_API_BASE_URL),
        )
        print(
            f"Fixtures seen: {probe['fixtures_seen']}; with a "
            f"{probe['required_point']} line in at least one region: "
            f"{probe['fixtures_with_line_in_any_region']}"
        )
        for row in probe["per_region"]:
            print(
                f"  {row['region']}: {row['events_with_required_line']}/"
                f"{row['events']} with the line"
            )
        for row in probe["per_region"]:
            covering = row["books_covering_every_fixture"]
            if covering:
                print(f"    {row['region']} books covering every fixture: {covering}")
        if probe["books_covering_every_fixture"]:
            print(
                "Books carrying the line for every fixture: "
                f"{probe['books_covering_every_fixture']}"
            )
        for fixture in probe["missing_in_every_region"]:
            print(f"  MISSING EVERYWHERE: {fixture}")
        for error in probe["errors"]:
            print(f"WARNING: {error}")
        print(
            "Complete in some region: "
            f"{'Yes' if probe['complete_in_any_region'] else 'No'}"
        )
        print(f"NOTE: {probe['note']}")

    if raw_path is None:
        print("Skipping the bulk report: no archived response to analyse.")
        return 0

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
