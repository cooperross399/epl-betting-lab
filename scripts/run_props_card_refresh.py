#!/usr/bin/env python
"""Refresh the player-props card, spending nothing while props are held.

This is the matchday pipeline's props step, and it gates itself on the
reviewed policy: while no prop market is approved, it writes the
Held-by-policy report and exits without a single network request or credit
spent. Only after an approval does it refresh the player logs (free,
Understat), fetch live prop prices (about four credits per event), and
build the props card.

A props failure must never cost a match card; the workflow runs this step
with continue-on-error, and this script still reports its own failures
honestly. No pick beyond the props report, no bet, no settlement, no
protected file, no cron.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.config import PROCESSED_DIR
from epl_betting_lab.providers.env_file import load_provider_env
from epl_betting_lab.providers.player_props_staging import (
    PlayerPropsFetchError,
    fetch_player_props,
    write_props_staging,
)
from epl_betting_lab.providers.understat_players import (
    LOG_FIELDS,
    fetch_player_match_logs,
)
from epl_betting_lab.reports.player_props_card import (
    HELD_STATUS,
    approved_prop_markets,
    save_player_props_card,
)


API_KEY_ENV = "EPL_ODDS_API_KEY"
LOGS_FILENAME = "player_match_logs.csv"

#: The current Understat season, refreshed incrementally on approved runs.
CURRENT_SEASON = "2026"


def _refresh_player_logs() -> str:
    logs_path = Path(PROCESSED_DIR) / LOGS_FILENAME
    already: set[str] = set()
    if logs_path.is_file():
        with logs_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                match_id = str(row.get("match_id", "")).strip()
                if match_id:
                    already.add(match_id)
    result = fetch_player_match_logs(
        [CURRENT_SEASON], already_fetched=already, sleep_seconds=1.0
    )
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    exists = logs_path.is_file()
    mode = "a" if exists else "w"
    with logs_path.open(mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LOG_FIELDS))
        if mode == "w":
            writer.writeheader()
        for row in result.rows:
            writer.writerow(row)
    return (
        f"Player logs: {result.matches_fetched} match(es) added, "
        f"{result.already_had} already held."
    )


def main() -> int:
    print("EPL Betting Lab - Props Card Refresh")
    approved = approved_prop_markets()
    if not approved:
        result = save_player_props_card()
        print(f"Status: {result['summary']['status']}")
        print(
            "Every prop market is held by the reviewed policy. Nothing was "
            "fetched and no credit was spent."
        )
        print(f"Markdown: {result['markdown']}")
        return 0

    load_provider_env()
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        print(f"BLOCKED: props are approved but `{API_KEY_ENV}` is missing.")
        return 2

    print(f"Approved prop markets: {', '.join(approved)}")
    print(_refresh_player_logs())
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        fetch_result = fetch_player_props(
            api_key=api_key, markets=approved, fetched_at=fetched_at
        )
        write_props_staging(fetch_result.rows, overwrite=True)
    except PlayerPropsFetchError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(
        f"Props prices: {fetch_result.events_priced}/{fetch_result.events_seen} "
        f"event(s) priced, {fetch_result.credits_spent} credit(s) spent."
    )
    for error in fetch_result.errors:
        print(f"WARNING: {error}")

    result = save_player_props_card()
    summary = result["summary"]
    print(f"Status: {summary['status']}")
    print(f"Picks: {len(summary['picks'])}")
    print(f"Markdown: {result['markdown']}")
    print(
        "Safety: no bet, no settlement, no protected file, no cron, and the "
        "credential was not printed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
