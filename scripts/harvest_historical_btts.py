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
DEFAULT_OUTPUT = "historical_market_odds.csv"
FIELDS = [
    "sampled_at",
    "commence_time",
    "home_team",
    "away_team",
    "market",
    "player",
    "selection",
    "american",
]


def _day(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _read_existing(
    output_path: Path, *, append: bool
) -> tuple[list[str], list[dict[str, str]], bool]:
    """What the file already holds: fixture keys, rows, and schema age.

    A player-prop row without a player predates the `player` column: it
    collapsed every player's line into one meaningless best price, so it does
    not count as holding that fixture — the fixture may be re-bought
    correctly. The old rows stay in the file (nothing is deleted); analysis
    requires a player on prop rows and so never reads them.
    """
    already: list[str] = []
    legacy_rows: list[dict[str, str]] = []
    needs_migration = False
    if not (append and output_path.is_file()):
        return already, legacy_rows, needs_migration
    with output_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        needs_migration = "player" not in (reader.fieldnames or [])
        for row in reader:
            legacy_rows.append(dict(row))
            market = str(row.get("market", "")).strip()
            if market.startswith("player_") and not str(
                row.get("player", "") or ""
            ).strip():
                continue
            day = str(row.get("commence_time", ""))[:10]
            home = str(row.get("home_team", "")).strip().casefold()
            away = str(row.get("away_team", "")).strip().casefold()
            already.append(f"{day}|{home}|{away}")
    return already, legacy_rows, needs_migration


def _write_rows(
    path: Path,
    rows: list[dict[str, object]],
    *,
    append: bool,
    needs_migration: bool,
    legacy_rows: list[dict[str, str]],
) -> int:
    """Write the harvest. Returns how many existing rows were migrated.

    A file that predates the `player` column cannot be appended to: rows with
    more fields than the header would misalign. It is rewritten once under
    the new header, every old row kept with an empty player.
    """
    exists = path.is_file()
    if append and exists and needs_migration:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for row in legacy_rows:
                writer.writerow({field: row.get(field, "") for field in FIELDS})
            for row in rows:
                writer.writerow(row)
        return len(legacy_rows)
    mode = "a" if (append and exists) else "w"
    with path.open(mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if mode == "w":
            writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return 0


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
    parser.add_argument(
        "--markets",
        default="btts",
        help="Comma-separated provider market keys. Several travel in one "
        "request, which prices them at the same instant — prices sampled "
        "minutes apart are not strictly comparable, and comparing markets is "
        "the point. Historical credits are charged per market, so this "
        "multiplies the cost.",
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

    # What has already been bought, so no credit is spent twice.
    output_path = Path(PROCESSED_DIR) / args.output
    already, legacy_rows, needs_migration = _read_existing(
        output_path, append=args.append
    )

    days = matchdays_between(_day(args.start), _day(args.end))
    print(f"EPL Betting Lab - Historical BTTS harvest")
    print(f"Range: {args.start} to {args.end} ({len(days)} day(s))")
    print(f"Credit ceiling: {args.credit_limit}")
    print(f"Sampling {args.hours_before}h before each fixture's own kick-off.")
    print(f"Markets: {args.markets}")
    if already:
        print(f"Already hold {len(already)} fixture(s); they will not be re-bought.")

    result = harvest_btts_history(
        days,
        api_key=api_key,
        budget=HarvestBudget(limit=args.credit_limit),
        hours_before=args.hours_before,
        markets=[m.strip() for m in args.markets.split(",") if m.strip()],
        already_harvested=already,
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    migrated = _write_rows(
        output_path,
        result.rows,
        append=args.append,
        needs_migration=needs_migration,
        legacy_rows=legacy_rows,
    )
    if migrated:
        print(
            f"Migrated {migrated} existing row(s) to the schema with "
            "a `player` column."
        )

    print(f"Snapshots: {result.snapshots}")
    print(f"Fixtures seen: {result.events_seen}; priced: {result.events_with_btts}; "
          f"already had: {result.already_had}")
    print(f"Rows written: {len(result.rows)} -> {path}")
    print(f"Credits spent: {result.credits_spent}")
    if result.stopped_early:
        print("STOPPED EARLY: the credit ceiling was reached before the range ended.")
    for error in result.errors:
        print(f"WARNING: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
