#!/usr/bin/env python
"""Answer, with the provider rather than from memory, what can actually be bought.

Two claims arrived from outside this project and both contradict what CLAUDE.md
has been asserting. Neither can be settled by reading code, and getting them
wrong in either direction is expensive: believing a market is unbuyable stops it
ever being validated, and believing it is buyable wastes a research programme.

  1. `bookmakers=` overrides `regions=`, so Pinnacle can be fetched from a US
     account. Pinnacle is the sharp reference every closing-line measurement is
     compared against. We cannot bet it and do not need to.
  2. The historical event-odds endpoint serves BTTS, corners and the other
     derived markets from 2023-05-03, which would make them backtestable — the
     thing this project has repeatedly said was impossible.

Read-only and deliberately tiny: it fetches a handful of events, writes no
staging bundle, creates no shadow run, and cannot touch the acceptance evidence
window. It prints what it found and spends a few credits doing it. The key comes
from the environment, is never printed, and never leaves the runner.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

ROOT = os.environ.get("EPL_ODDS_API_BASE_URL", "https://api.the-odds-api.com")
SPORT = "soccer_epl"
KEY_ENV = "EPL_ODDS_API_KEY"
#: The markets this project bets but has never been able to price historically.
DERIVED_MARKETS = ("btts", "draw_no_bet", "double_chance", "alternate_totals_corners")


def _get(path: str, params: dict) -> tuple[int, object, dict]:
    response = requests.get(f"{ROOT}{path}", params=params, timeout=30)
    used = {k: v for k, v in response.headers.items() if k.lower().startswith("x-requests")}
    try:
        return response.status_code, response.json(), used
    except ValueError:
        return response.status_code, None, used


def probe_pinnacle(key: str) -> None:
    print("\n=== CLAIM 1: bookmakers=pinnacle regardless of region ===")
    status, body, used = _get(
        f"/v4/sports/{SPORT}/odds",
        {"apiKey": key, "bookmakers": "pinnacle", "markets": "h2h", "oddsFormat": "american"},
    )
    if status != 200:
        print(f"  REFUSED  http={status}  {str(body)[:160]}")
        return
    titles = sorted({b.get("title", "") for e in body for b in e.get("bookmakers", [])})
    print(f"  http=200  events={len(body)}  bookmakers returned: {titles or 'NONE'}")
    print(f"  verdict: {'CONFIRMED' if titles else 'endpoint answered but returned no Pinnacle prices'}")
    print(f"  quota: {used}")


def probe_historical(key: str, when: datetime) -> None:
    stamp = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n=== CLAIM 2: historical derived markets at {stamp} ===")
    status, body, used = _get(
        f"/v4/historical/sports/{SPORT}/odds",
        {"apiKey": key, "regions": "us", "markets": "h2h", "oddsFormat": "american", "date": stamp},
    )
    if status != 200:
        print(f"  slate REFUSED  http={status}  {str(body)[:200]}")
        return
    data = body.get("data") if isinstance(body, dict) else body
    events = [e for e in (data or []) if isinstance(e, dict)]
    print(f"  slate http=200  events={len(events)}  quota={used}")
    if not events:
        print("  no events at that timestamp; try another date")
        return
    event = events[0]
    print(f"  probing event: {event.get('home_team')} v {event.get('away_team')}")
    status, body, used = _get(
        f"/v4/historical/sports/{SPORT}/events/{event['id']}/odds",
        {"apiKey": key, "regions": "us", "markets": ",".join(DERIVED_MARKETS),
         "oddsFormat": "american", "date": stamp},
    )
    if status != 200:
        print(f"  event odds REFUSED  http={status}  {str(body)[:200]}")
        return
    data = body.get("data") if isinstance(body, dict) else body
    if isinstance(data, list):
        data = data[0] if data else {}
    found: dict[str, set[str]] = {}
    for book in (data or {}).get("bookmakers", []):
        for market in book.get("markets", []):
            found.setdefault(market.get("key", "?"), set()).add(book.get("title", "?"))
    print(f"  event odds http=200  quota={used}")
    for market in DERIVED_MARKETS:
        books = sorted(found.get(market, []))
        print(f"    {market:<26} {'FOUND at ' + ', '.join(books[:4]) if books else 'absent'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-date", default="",
                        help="UTC timestamp to probe, e.g. 2025-09-20T12:00:00Z. Defaults to ~200 days ago.")
    args = parser.parse_args()
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        print(f"{KEY_ENV} is not set; nothing probed.")
        return 1
    print(f"Probing {ROOT} for {SPORT}. The key is never printed.")
    probe_pinnacle(key)
    when = (
        datetime.strptime(args.historical_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if args.historical_date
        else datetime.now(timezone.utc) - timedelta(days=200)
    )
    probe_historical(key, when)
    return 0


if __name__ == "__main__":
    sys.exit(main())
