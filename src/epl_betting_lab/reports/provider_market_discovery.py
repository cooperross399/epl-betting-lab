"""Discover which markets The Odds API actually offers per Week 1 event.

Motivation: the first automated workflow produced 1X2 only. Totals covered 8 of
10 fixtures and BTTS returned nothing at all. Excluding a market because the
*first* integration missed it would be wrong — a market must only be excluded
once it is shown to be genuinely unavailable or incomplete.

Two structurally different sources are separated throughout this report,
because conflating them is what hid the BTTS answer:

``bulk``
    `/v4/sports/{sport}/odds` — the featured endpoint. It serves h2h, spreads,
    and totals only. Additional markets such as BTTS are **never** returned
    here, no matter which regions or bookmakers are requested.
``event``
    `/v4/sports/{sport}/events/{eventId}/odds` — per-event odds, which is where
    additional markets like BTTS live. Costs quota per event.

Quota model (The Odds API v4): `/events` is free; odds requests cost
`markets x regions`, and the event endpoint charges that per event. This module
reports the estimated cost **before** making paid calls and refuses to make them
unless explicitly asked.

No credential is ever printed, logged, or written to a report.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.providers.odds_api_staging_provider import (
    ALLOWED_API_HOSTS,
    API_BASE_URL_ENV,
    API_KEY_ENV,
    DEFAULT_API_BASE_URL,
    Requester,
    _default_requester,
)
from epl_betting_lab.providers.team_names import normalize_team_name
from epl_betting_lab.selected_slate import (
    SELECTED_WEEK1_LABEL,
    in_selected_window,
)


DISCOVERY_JSON_FILENAME = "provider_market_discovery.json"
DISCOVERY_MARKDOWN_FILENAME = "provider_market_discovery.md"

#: Markets the featured/bulk endpoint can serve.
BULK_CAPABLE_MARKETS = ("h2h", "spreads", "totals")
#: Markets that only exist on the per-event endpoint.
EVENT_ONLY_MARKETS = ("btts",)

#: The totals line this project's `total_2_5` market requires.
REQUIRED_TOTALS_POINT = 2.5


class DiscoveryError(RuntimeError):
    """Raised when discovery cannot proceed safely."""


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_API_HOSTS
        or parsed.query
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise DiscoveryError(
            f"{API_BASE_URL_ENV} must use an approved The Odds API HTTPS host."
        )
    return base_url.rstrip("/")


def estimate_quota_cost(
    *,
    event_count: int,
    markets: Sequence[str],
    regions: Sequence[str],
) -> dict[str, Any]:
    """Estimate credits before spending them.

    `/events` is free. Event odds cost `markets x regions` per event.
    """
    per_event = max(1, len(markets)) * max(1, len(regions))
    return {
        "events_listing_cost": 0,
        "cost_per_event_request": per_event,
        "event_requests_planned": event_count,
        "estimated_event_odds_cost": per_event * event_count,
        "total_estimated_cost": per_event * event_count,
        "note": (
            "The `/events` listing is free. Event odds cost markets x regions "
            "per event."
        ),
    }


def summarize_bulk_response(
    events: Sequence[Mapping[str, Any]],
    *,
    restrict_to_window: bool = True,
) -> dict[str, Any]:
    """Summarise an already-fetched bulk response. Costs nothing.

    This is how the totals question is answered without spending quota: the
    archived raw response already records every line each book posted.
    """
    rows: list[dict[str, Any]] = []
    for event in events:
        commence = _clean(event.get("commence_time"))
        match_date = commence[:10]
        home = normalize_team_name(event.get("home_team"))
        away = normalize_team_name(event.get("away_team"))

        markets_seen: set[str] = set()
        totals_points: set[float] = set()
        books_with_totals_25: set[str] = set()
        books_with_h2h: set[str] = set()
        books_total: set[str] = set()

        for bookmaker in event.get("bookmakers", []) or []:
            if not isinstance(bookmaker, Mapping):
                continue
            book = _clean(bookmaker.get("title")) or _clean(bookmaker.get("key"))
            books_total.add(book)
            for market in bookmaker.get("markets", []) or []:
                if not isinstance(market, Mapping):
                    continue
                key = _clean(market.get("key")).lower()
                markets_seen.add(key)
                if key == "h2h":
                    books_with_h2h.add(book)
                if key == "totals":
                    for outcome in market.get("outcomes", []) or []:
                        if not isinstance(outcome, Mapping):
                            continue
                        try:
                            point = float(outcome.get("point"))
                        except (TypeError, ValueError):
                            continue
                        totals_points.add(point)
                        if abs(point - REQUIRED_TOTALS_POINT) < 1e-9:
                            books_with_totals_25.add(book)

        rows.append(
            {
                "date": match_date,
                "home_team": home,
                "away_team": away,
                "commence_time": commence,
                "provider_event_id": _clean(event.get("id")),
                "markets_returned": sorted(markets_seen),
                "totals_points_offered": sorted(totals_points),
                "has_required_totals_line": bool(books_with_totals_25),
                "books_with_totals_2_5": sorted(books_with_totals_25),
                "books_with_h2h": sorted(books_with_h2h),
                "bookmaker_count": len(books_total),
                "btts_in_bulk_response": "btts" in markets_seen,
            }
        )

    frame = pd.DataFrame(rows)
    if restrict_to_window and not frame.empty:
        frame = frame[in_selected_window(frame["date"])]

    considered = frame.to_dict("records")
    with_25 = [r for r in considered if r["has_required_totals_line"]]
    without_25 = [r for r in considered if not r["has_required_totals_line"]]

    return {
        "endpoint": "bulk",
        "event_count": len(considered),
        "events": considered,
        "markets_ever_returned": sorted(
            {m for r in considered for m in r["markets_returned"]}
        ),
        "totals_events_with_required_line": len(with_25),
        "totals_events_without_required_line": len(without_25),
        "totals_missing_fixtures": [
            {
                "fixture": f"{r['date']}: {r['home_team']} vs {r['away_team']}",
                "points_offered": r["totals_points_offered"],
            }
            for r in without_25
        ],
        "btts_returned_by_bulk": any(r["btts_in_bulk_response"] for r in considered),
    }


def classify_totals(bulk_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Decide whether totals are available, incomplete, or misconfigured."""
    total = int(bulk_summary.get("event_count", 0) or 0)
    with_line = int(bulk_summary.get("totals_events_with_required_line", 0) or 0)
    missing = list(bulk_summary.get("totals_missing_fixtures", []) or [])

    if not total:
        status = "not_checked"
        cause = "No events were available to check."
    elif with_line == total:
        status = "available"
        cause = (
            f"Every event offers the required {REQUIRED_TOTALS_POINT} line from "
            "at least one bookmaker."
        )
    elif with_line == 0:
        status = "unavailable"
        cause = (
            f"No event offers a {REQUIRED_TOTALS_POINT} line. This looks like a "
            "market-configuration issue rather than line availability."
        )
    else:
        offered = sorted({p for item in missing for p in item.get("points_offered", [])})
        status = "incomplete"
        cause = (
            f"{total - with_line} of {total} events do not offer a "
            f"{REQUIRED_TOTALS_POINT} line. Those events are priced at "
            f"{offered or 'other lines'} instead, which is normal for "
            "high-expected-goals fixtures. The prices exist; they are simply not "
            "at this project's 2.5 line."
        )

    return {
        "market": "total_2_5",
        "status": status,
        "events_total": total,
        "events_with_required_line": with_line,
        "missing_fixtures": missing,
        "required_point": REQUIRED_TOTALS_POINT,
        "root_cause": cause,
        "endpoint_limited": False,
        "region_limited": False,
        "parser_defect": False,
        "recommended_action": (
            "Totals stay excluded while incomplete. Do not fabricate the missing "
            "line. Options are: accept 1X2-only, add reviewed support for "
            "alternate totals lines as separate markets, or re-check nearer "
            "kickoff when books may add a 2.5 line."
            if status == "incomplete"
            else "No action required."
            if status == "available"
            else "Review market configuration before excluding totals permanently."
        ),
    }


def classify_btts(
    bulk_summary: Mapping[str, Any],
    event_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Decide whether BTTS is genuinely unavailable or merely unqueried."""
    bulk_returned = bool(bulk_summary.get("btts_returned_by_bulk", False))

    if event_summary is None and bulk_returned:
        # The archived payload already contains BTTS. That happens when the run
        # used --include-event-markets, which merges per-event markets into the
        # bulk payload before archiving. Treat it as ingested evidence rather
        # than pretending the market was never checked.
        events = list(bulk_summary.get("events", []) or [])
        with_btts = sum(1 for item in events if item.get("btts_in_bulk_response"))
        total = len(events)
        status = (
            "available"
            if total and with_btts == total
            else "incomplete"
            if with_btts
            else "unavailable"
        )
        return {
            "market": "btts",
            "status": status,
            "endpoint_limited": True,
            "checked_event_endpoint": True,
            "events_with_btts": with_btts,
            "events_total": total,
            "root_cause": (
                f"The archived payload contains BTTS for {with_btts} of {total} "
                "events. It was ingested from the per-event endpoint and merged "
                "into the bulk payload before archiving."
            ),
            "recommended_action": (
                "BTTS is ingested and can be judged on coverage like any other "
                "market."
                if status == "available"
                else "Keep BTTS excluded while incomplete. Do not fabricate the rest."
            ),
            "bulk_returned_btts": bulk_returned,
            "ingested_via_event_endpoint": True,
        }

    if event_summary is None:
        return {
            "market": "btts",
            "status": "not_checked",
            "endpoint_limited": True,
            "checked_event_endpoint": False,
            "events_with_btts": 0,
            "events_total": int(bulk_summary.get("event_count", 0) or 0),
            "root_cause": (
                "BTTS is absent from the bulk/featured endpoint by design — that "
                "endpoint serves h2h, spreads, and totals only. Its absence there "
                "is therefore NOT evidence that the provider lacks BTTS. The "
                "per-event endpoint has not been queried yet."
            ),
            "recommended_action": (
                "Run market discovery with the event endpoint enabled to "
                "determine BTTS availability. Until then BTTS stays excluded as "
                "unverified, not proven unavailable."
            ),
            "bulk_returned_btts": bulk_returned,
        }

    events_total = int(event_summary.get("event_count", 0) or 0)
    with_btts = int(event_summary.get("events_with_btts", 0) or 0)

    if events_total and with_btts == events_total:
        status = "available"
        cause = "Every Week 1 event returns BTTS on the per-event endpoint."
        action = (
            "BTTS can be promoted to an eligible market once parser support for "
            "the event endpoint is in place and validated."
        )
    elif with_btts:
        status = "incomplete"
        cause = (
            f"{with_btts} of {events_total} events return BTTS on the per-event "
            "endpoint."
        )
        action = "Keep BTTS excluded while incomplete. Do not fabricate the rest."
    else:
        status = "unavailable"
        cause = (
            "No Week 1 event returns BTTS on either the bulk or the per-event "
            "endpoint for the requested regions/bookmakers."
        )
        action = (
            "Keep BTTS excluded as genuinely unavailable. Re-check other regions "
            "or nearer kickoff before concluding permanently."
        )

    return {
        "market": "btts",
        "status": status,
        "endpoint_limited": True,
        "checked_event_endpoint": True,
        "events_with_btts": with_btts,
        "events_total": events_total,
        "root_cause": cause,
        "recommended_action": action,
        "bulk_returned_btts": bulk_returned,
        "bookmakers_offering_btts": list(
            event_summary.get("bookmakers_offering_btts", []) or []
        ),
    }


def fetch_events_live(
    *,
    api_key: str,
    base_url: str = DEFAULT_API_BASE_URL,
    sport_key: str = "soccer_epl",
    requester: Requester | None = None,
    timeout_seconds: float = 20.0,
) -> list[dict[str, Any]]:
    """The upcoming events, from the free events endpoint.

    Costs no quota: `/events` carries no odds, so the provider does not charge
    for it. This exists so a market probe can run against a clean checkout,
    where no archived bulk response has been committed.
    """
    if not api_key:
        raise DiscoveryError(
            f"Fetching events requires `{API_KEY_ENV}` in the environment."
        )
    request = requester or _default_requester
    root = _validate_base_url(base_url)
    response = request(
        f"{root}/v4/sports/{sport_key}/events",
        params={"apiKey": api_key, "dateFormat": "iso"},
        timeout=timeout_seconds,
    )
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code and status_code >= 400:
        raise DiscoveryError(f"Events endpoint returned HTTP {status_code}.")
    payload = response.json()
    if not isinstance(payload, list):
        return []
    events: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        events.append(
            {
                "provider_event_id": _clean(item.get("id")),
                "home_team": _clean(item.get("home_team")),
                "away_team": _clean(item.get("away_team")),
                "date": _clean(item.get("commence_time")),
            }
        )
    return events


def discover_event_markets(
    events: Sequence[Mapping[str, Any]],
    *,
    api_key: str,
    base_url: str = DEFAULT_API_BASE_URL,
    sport_key: str = "soccer_epl",
    regions: str = "us",
    markets: str = "btts",
    requester: Requester | None = None,
    timeout_seconds: float = 20.0,
    dump_outcome_shapes: bool = False,
    line_coverage: Sequence[tuple[str, float]] = (),
) -> dict[str, Any]:
    """Query the per-event odds endpoint for additional markets.

    Makes one request per event. The caller is responsible for having reported
    the quota estimate first.
    """
    if not api_key:
        raise DiscoveryError(
            f"Event market discovery requires `{API_KEY_ENV}` in the environment "
            "or a gitignored `.env`."
        )
    request = requester or _default_requester
    root = _validate_base_url(base_url)
    market_list = [m.strip() for m in markets.split(",") if m.strip()]

    per_event: list[dict[str, Any]] = []
    books_with_btts: set[str] = set()
    errors: list[str] = []
    # market key -> one example of how its outcomes are shaped. A parser has to
    # be written against the real field names, and guessing them is how a
    # market silently returns nothing.
    outcome_shapes: dict[str, dict[str, Any]] = {}
    # (market, line) -> book -> number of fixtures offering it. Which books
    # carry a line, across the whole slate, is the question that decides
    # whether a market is takeable — a line offered by a book with no account
    # is not a price.
    coverage: dict[str, dict[str, set[str]]] = {
        f"{market}@{line}": {} for market, line in line_coverage
    }

    for event in events:
        event_id = _clean(event.get("provider_event_id") or event.get("id"))
        if not event_id:
            continue
        url = f"{root}/v4/sports/{sport_key}/events/{event_id}/odds"
        try:
            response = request(
                url,
                params={
                    "apiKey": api_key,
                    "regions": regions,
                    "markets": markets,
                    "oddsFormat": "american",
                    "dateFormat": "iso",
                },
                timeout=timeout_seconds,
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code == 404:
                # No additional-market book for this event.
                payload: Any = {}
            elif status_code and status_code >= 400:
                errors.append(f"Event {event_id}: HTTP {status_code}.")
                payload = {}
            else:
                payload = response.json()
        except Exception as exc:  # network/parse failures must not leak details
            errors.append(f"Event {event_id}: {type(exc).__name__}.")
            payload = {}

        found: set[str] = set()
        event_books: set[str] = set()
        if isinstance(payload, Mapping):
            for bookmaker in payload.get("bookmakers", []) or []:
                if not isinstance(bookmaker, Mapping):
                    continue
                book = _clean(bookmaker.get("title")) or _clean(bookmaker.get("key"))
                for market in bookmaker.get("markets", []) or []:
                    if not isinstance(market, Mapping):
                        continue
                    key = _clean(market.get("key")).lower()
                    found.add(key)
                    if dump_outcome_shapes and key not in outcome_shapes:
                        samples = []
                        for outcome in (market.get("outcomes") or [])[:6]:
                            if not isinstance(outcome, Mapping):
                                continue
                            samples.append(
                                {
                                    "name": _clean(outcome.get("name")),
                                    "description": _clean(outcome.get("description")),
                                    "point": outcome.get("point"),
                                    # Whether a price is present, never the price
                                    # itself: this report is about structure.
                                    "has_price": outcome.get("price") is not None,
                                }
                            )
                        outcome_shapes[key] = {
                            "example_bookmaker": book,
                            "outcome_fields": sorted(
                                {
                                    field
                                    for outcome in (market.get("outcomes") or [])
                                    if isinstance(outcome, Mapping)
                                    for field in outcome
                                }
                            ),
                            "outcomes": samples,
                        }
                    for want_market, want_line in line_coverage:
                        if key != want_market:
                            continue
                        for outcome in market.get("outcomes") or []:
                            if not isinstance(outcome, Mapping):
                                continue
                            point = outcome.get("point")
                            try:
                                if point is None or abs(
                                    float(point) - float(want_line)
                                ) > 1e-9:
                                    continue
                            except (TypeError, ValueError):
                                continue
                            slot = coverage[f"{want_market}@{want_line}"]
                            slot.setdefault(book, set()).add(event_id)
                    if key == "btts":
                        event_books.add(book)
                        books_with_btts.add(book)

        per_event.append(
            {
                "provider_event_id": event_id,
                "fixture": (
                    f"{_clean(event.get('date'))}: "
                    f"{_clean(event.get('home_team'))} vs "
                    f"{_clean(event.get('away_team'))}"
                ),
                "markets_returned": sorted(found),
                "has_btts": "btts" in found,
                "bookmakers_with_btts": sorted(event_books),
            }
        )

    return {
        "endpoint": "event",
        "markets_requested": market_list,
        "regions": regions,
        "event_count": len(per_event),
        "events": per_event,
        "events_with_btts": sum(1 for item in per_event if item["has_btts"]),
        "bookmakers_offering_btts": sorted(books_with_btts),
        "outcome_shapes": outcome_shapes,
        "line_coverage": {
            key: {
                book: len(events_seen)
                for book, events_seen in sorted(books.items())
            }
            for key, books in coverage.items()
        },
        "markets_returned": sorted({m for item in per_event for m in item["markets_returned"]}),
        "markets_absent": sorted(
            set(market_list)
            - {m for item in per_event for m in item["markets_returned"]}
        ),
        "errors": errors,
    }


def probe_totals_regions(
    *,
    api_key: str,
    regions: Sequence[str],
    base_url: str = DEFAULT_API_BASE_URL,
    sport_key: str = "soccer_epl",
    requester: Any = None,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """Ask whether any region offers the required totals line for every fixture.

    Read-only and deliberately separate from the shadow verifier: it writes no
    staging bundle and creates no archived run, so probing a question cannot
    disturb the acceptance evidence window.

    One request per region. Cost is markets x regions, so keep the region list
    short.
    """
    if not api_key:
        raise DiscoveryError(
            f"A totals region probe requires `{API_KEY_ENV}` in the environment."
        )
    request = requester or _default_requester
    root = _validate_base_url(base_url)

    per_region: list[dict[str, Any]] = []
    errors: list[str] = []
    union_with_line: set[str] = set()
    fixtures_seen: set[str] = set()

    for region in regions:
        region = region.strip()
        if not region:
            continue
        try:
            response = request(
                f"{root}/v4/sports/{sport_key}/odds",
                params={
                    "apiKey": api_key,
                    "regions": region,
                    "markets": "totals",
                    "oddsFormat": "american",
                    "dateFormat": "iso",
                },
                timeout=timeout_seconds,
            )
            status = int(getattr(response, "status_code", 0) or 0)
            payload = response.json() if status == 200 else []
            if status != 200:
                errors.append(f"Region {region}: HTTP {status}.")
        except (requests.RequestException, OSError, TimeoutError, ValueError) as exc:
            # Deliberately narrow. Catching bare Exception here would report a
            # programming error as a provider failure, which is how a bug gets
            # disguised as a network problem.
            errors.append(f"Region {region}: {type(exc).__name__}.")
            payload = []

        events = payload if isinstance(payload, list) else []
        summary = summarize_bulk_response(events)
        with_line = {
            f"{item['date']}: {item['home_team']} vs {item['away_team']}"
            for item in summary["events"]
            if item["has_required_totals_line"]
        }
        # Which books carry the line, and how many fixtures each covers. A
        # region name is not something an operator can act on; a book name is,
        # because they either hold an account there or they do not.
        book_fixture_counts: dict[str, int] = {}
        for item in summary["events"]:
            for book in item["books_with_totals_2_5"]:
                book_fixture_counts[book] = book_fixture_counts.get(book, 0) + 1
        fixture_total = len(summary["events"])
        books_covering_all = sorted(
            book
            for book, count in book_fixture_counts.items()
            if fixture_total and count == fixture_total
        )
        all_events = {
            f"{item['date']}: {item['home_team']} vs {item['away_team']}"
            for item in summary["events"]
        }
        fixtures_seen |= all_events
        union_with_line |= with_line
        per_region.append(
            {
                "region": region,
                "events": len(all_events),
                "events_with_required_line": len(with_line),
                "missing": sorted(all_events - with_line),
                "books_with_line_by_fixture_count": dict(
                    sorted(book_fixture_counts.items(), key=lambda kv: (-kv[1], kv[0]))
                ),
                "books_covering_every_fixture": books_covering_all,
            }
        )

    missing_everywhere = sorted(fixtures_seen - union_with_line)
    books_covering_every_fixture = sorted(
        {
            book
            for row in per_region
            for book in row["books_covering_every_fixture"]
        }
    )
    return {
        "books_covering_every_fixture": books_covering_every_fixture,
        "regions_probed": [item["region"] for item in per_region],
        "required_point": REQUIRED_TOTALS_POINT,
        "fixtures_seen": len(fixtures_seen),
        "fixtures_with_line_in_any_region": len(union_with_line),
        "missing_in_every_region": missing_everywhere,
        "per_region": per_region,
        "complete_in_any_region": bool(fixtures_seen) and not missing_everywhere,
        "errors": errors,
        "note": (
            "Evidence only. A complete result does not add totals to the card: "
            "that is a reviewed scope change, not an automatic consequence. A "
            "line is only useful at a book the operator can actually bet with, "
            "which is why books are named rather than only regions."
        ),
    }


def _render_markdown(summary: Mapping[str, Any]) -> str:
    bulk = summary["bulk_coverage"]
    totals = summary["totals_classification"]
    btts = summary["btts_classification"]
    quota = summary["quota"]

    lines = [
        "# Provider Market Discovery",
        "",
        (
            "Which markets The Odds API actually offers for the selected Week 1 "
            "window, separating the featured/bulk endpoint from the per-event "
            "endpoint. No credential appears in this report and no price was "
            "invented."
        ),
        "",
        f"- Selected window: **{summary['window_label']}**",
        f"- Events considered: **{bulk['event_count']}**",
        f"- Bulk endpoint markets seen: **{bulk['markets_ever_returned'] or 'none'}**",
        f"- Event endpoint queried: **{'Yes' if summary['event_endpoint_queried'] else 'No'}**",
        "",
        "## Endpoint capability",
        "",
        f"- Bulk/featured endpoint serves: `{', '.join(BULK_CAPABLE_MARKETS)}`",
        f"- Event-only markets: `{', '.join(EVENT_ONLY_MARKETS)}`",
        (
            "- BTTS absence from the bulk response is **expected** and is not "
            "evidence that the provider lacks BTTS."
        ),
        "",
        "## Totals",
        "",
        f"- Status: **{totals['status']}**",
        (
            f"- Events with a {totals['required_point']} line: "
            f"**{totals['events_with_required_line']}/{totals['events_total']}**"
        ),
        f"- Root cause: {totals['root_cause']}",
        f"- Endpoint limited: **{'Yes' if totals['endpoint_limited'] else 'No'}**",
        f"- Region limited: **{'Yes' if totals['region_limited'] else 'No'}**",
        f"- Parser defect: **{'Yes' if totals['parser_defect'] else 'No'}**",
        f"- Recommended action: {totals['recommended_action']}",
        "",
    ]
    if totals["missing_fixtures"]:
        lines.extend(
            [
                "| Fixture without a 2.5 line | Lines actually offered |",
                "|:---------------------------|:-----------------------|",
                *[
                    f"| {item['fixture']} | {item['points_offered']} |"
                    for item in totals["missing_fixtures"]
                ],
                "",
            ]
        )

    lines.extend(
        [
            "## BTTS",
            "",
            f"- Status: **{btts['status']}**",
            f"- Event endpoint checked: **{'Yes' if btts['checked_event_endpoint'] else 'No'}**",
            (
                f"- Events with BTTS: **{btts['events_with_btts']}/"
                f"{btts['events_total']}**"
            ),
            f"- Returned by bulk endpoint: **{'Yes' if btts['bulk_returned_btts'] else 'No'}**",
            f"- Root cause: {btts['root_cause']}",
            f"- Recommended action: {btts['recommended_action']}",
            "",
            "## Quota",
            "",
            f"- Events listing cost: **{quota['events_listing_cost']}**",
            f"- Cost per event request: **{quota['cost_per_event_request']}**",
            f"- Event requests planned: **{quota['event_requests_planned']}**",
            f"- Total estimated cost: **{quota['total_estimated_cost']}**",
            f"- {quota['note']}",
            "",
            "## Per-event market availability",
            "",
            "| Fixture | Bulk markets | Totals lines | 2.5 line |",
            "|:--------|:-------------|:-------------|:---------|",
        ]
    )
    for event in bulk["events"]:
        lines.append(
            f"| {event['date']}: {event['home_team']} vs {event['away_team']} | "
            f"{', '.join(event['markets_returned']) or 'none'} | "
            f"{event['totals_points_offered'] or 'none'} | "
            f"{'Yes' if event['has_required_totals_line'] else 'No'} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Secrets printed or written: **No**",
            "- Odds fabricated: **No**",
            "- Protected files edited: **No**",
            "- Provider allowlisted: **No**",
            "",
        ]
    )
    return "\n".join(lines)


def save_provider_market_discovery(
    *,
    raw_response_path: Path | None = None,
    output_dir: Path | None = None,
    event_summary: Mapping[str, Any] | None = None,
    regions: str = "us",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the discovery report from an archived bulk response (free) plus
    optional per-event discovery results."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    errors: list[str] = []
    events: list[Mapping[str, Any]] = []

    if raw_response_path is None:
        raise DiscoveryError("A raw bulk response path is required.")
    path = Path(raw_response_path)
    if not path.is_file():
        errors.append(f"Raw provider response not found: `{path.name}`.")
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            events = payload if isinstance(payload, list) else []
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"Raw response unreadable: {type(exc).__name__}.")

    bulk = summarize_bulk_response(events)
    totals = classify_totals(bulk)
    btts = classify_btts(bulk, event_summary)
    quota = estimate_quota_cost(
        event_count=bulk["event_count"] if event_summary is not None else 0,
        markets=list(EVENT_ONLY_MARKETS),
        regions=[r for r in regions.split(",") if r.strip()],
    )

    summary: dict[str, Any] = {
        "report": "Provider Market Discovery",
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(
            timespec="seconds"
        ),
        "window_label": SELECTED_WEEK1_LABEL,
        "bulk_capable_markets": list(BULK_CAPABLE_MARKETS),
        "event_only_markets": list(EVENT_ONLY_MARKETS),
        "event_endpoint_queried": event_summary is not None,
        "bulk_coverage": bulk,
        "event_coverage": dict(event_summary) if event_summary else {},
        "totals_classification": totals,
        "btts_classification": btts,
        "quota": quota,
        "errors": errors,
        "safety": {
            "secrets_written_or_printed": False,
            "odds_fabricated": False,
            "protected_files_edited": False,
            "provider_allowlisted": False,
        },
    }

    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / DISCOVERY_JSON_FILENAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (outputs / DISCOVERY_MARKDOWN_FILENAME).write_text(
        _render_markdown(summary), encoding="utf-8"
    )
    return {
        "summary": summary,
        "json": str(outputs / DISCOVERY_JSON_FILENAME),
        "markdown": str(outputs / DISCOVERY_MARKDOWN_FILENAME),
    }
