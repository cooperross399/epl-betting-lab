#!/usr/bin/env python
"""Read-only probe of Fantasy Premier League's public player data.

FPL publishes, keyless, every player's per-match Opta numbers for the current
season, including `saves` and (since 2025/26) `tackles`. Neither is in the
Understat logs, and the provider prices both. This prints the fields one
player's match history carries, so the reader is written against the real
shape. It costs no provider credit and writes nothing.
"""

from __future__ import annotations

import sys

import requests

BASE = "https://fantasy.premierleague.com/api"


def main() -> int:
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    boot = session.get(f"{BASE}/bootstrap-static/", timeout=30)
    print(f"bootstrap-static: HTTP {boot.status_code}")
    if boot.status_code != 200:
        return 1
    payload = boot.json()
    elements = payload.get("elements") or []
    print(f"players: {len(elements)}; element fields: {sorted(elements[0])}")
    types = {t["id"]: t.get("singular_name_short") for t in payload.get("element_types") or []}
    for wanted in ("GKP", "DEF", "MID"):
        player = max(
            (e for e in elements if types.get(e.get("element_type")) == wanted),
            key=lambda e: e.get("minutes") or 0,
        )
        summary = session.get(f"{BASE}/element-summary/{player['id']}/", timeout=30)
        history = summary.json().get("history") or []
        print(f"\n{wanted} {player.get('web_name')}: HTTP {summary.status_code}, {len(history)} match(es)")
        if history:
            print(f"history fields: {sorted(history[-1])}")
            print(f"latest: {history[-1]}")
    past = session.get(f"{BASE}/element-summary/{elements[0]['id']}/", timeout=30).json()
    print(f"\nhistory_past seasons: {[h.get('season_name') for h in past.get('history_past') or []]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
