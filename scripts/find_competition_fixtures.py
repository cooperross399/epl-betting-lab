#!/usr/bin/env python
"""Search every competition the provider sells for fixtures between named teams.

Answers "does this provider carry these matches ANYWHERE?", which is a different
question from "does it list a competition with this name". A provider is free to
file the CONCACAF Nations League under a generic key, bundle it into a
qualifiers feed, or not carry it at all, and the sports list cannot tell those
apart.

Uses `/v4/sports/{sport}/events`, which returns fixtures WITHOUT odds and costs
no quota — the same reason the credential check can afford to call `/v4/sports`.
No odds are requested, no bet is placed, nothing is written to the repository.
The credential is read from the environment and never printed.
"""

from __future__ import annotations

import argparse
import os

import requests

from epl_betting_lab.providers.credential_check import redact
from epl_betting_lab.providers.odds_api_staging_provider import (
    API_KEY_ENV,
    DEFAULT_API_BASE_URL,
)

#: Every CONCACAF member that appears in the results archive, so a fixture
#: between any two of them is found whatever competition it is filed under.
CONCACAF = {
    "Anguilla", "Antigua and Barbuda", "Aruba", "Bahamas", "Barbados", "Belize",
    "Bermuda", "Bonaire", "British Virgin Islands", "Canada", "Cayman Islands",
    "Costa Rica", "Cuba", "Curaçao", "Curacao", "Dominica",
    "Dominican Republic", "El Salvador", "French Guiana", "Grenada",
    "Guadeloupe", "Guatemala", "Guyana", "Haiti", "Honduras", "Jamaica",
    "Martinique", "Mexico", "Montserrat", "Nicaragua", "Panama", "Puerto Rico",
    "Saint Kitts and Nevis", "Saint Lucia", "Saint Martin",
    "Saint Vincent and the Grenadines", "Sint Maarten", "Suriname",
    "Trinidad and Tobago", "Turks and Caicos Islands", "United States", "USA",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default=os.environ.get("EPL_ODDS_API_BASE_URL", DEFAULT_API_BASE_URL)
    )
    parser.add_argument(
        "--all-sports",
        action="store_true",
        help="Include competitions that are out of season as well as in season.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    key = os.environ.get(API_KEY_ENV, "").strip()
    print("EPL Betting Lab - Fixture Search")
    if not key:
        print(f"No credential in {API_KEY_ENV}; nothing to search.")
        return 2

    root = args.base_url.rstrip("/")
    params = {"apiKey": key}
    if args.all_sports:
        params["all"] = "true"
    try:
        listing = requests.get(f"{root}/v4/sports", params=params, timeout=30)
    except Exception as exc:
        print(redact(f"Could not reach the provider ({type(exc).__name__})."))
        return 1
    if listing.status_code != 200:
        print(f"Sports list returned HTTP {listing.status_code}.")
        return 1

    sports = [s for s in listing.json() if str(s.get("key", "")).startswith("soccer")]
    print(f"Searching {len(sports)} soccer competitions for CONCACAF fixtures.")
    print("Endpoint: /v4/sports/{sport}/events (no odds, quota cost 0)\n")

    found = 0
    for sport in sports:
        sport_key = str(sport["key"])
        try:
            response = requests.get(
                f"{root}/v4/sports/{sport_key}/events",
                params={"apiKey": key},
                timeout=30,
            )
        except Exception as exc:
            print(f"  {sport_key}: unreachable ({type(exc).__name__})")
            continue
        if response.status_code != 200:
            # An out-of-season competition returns 404 here rather than an
            # empty list, which is not a fault worth printing for each one.
            continue
        try:
            events = response.json()
        except ValueError:
            continue
        if not isinstance(events, list):
            continue
        for event in events:
            home = str(event.get("home_team", ""))
            away = str(event.get("away_team", ""))
            if home in CONCACAF or away in CONCACAF:
                found += 1
                print(
                    f"  FOUND  {sport_key}  {event.get('commence_time','')}  "
                    f"{home} v {away}"
                )
    if not found:
        print("\nNo fixture between CONCACAF national teams is carried under ANY")
        print("competition this key can see. The absence is the provider's, not a")
        print("naming problem: the search is by team, not by competition name.")
    else:
        print(f"\n{found} CONCACAF fixture(s) found. The sport key above is the one")
        print("to wire into SPORT_KEYS in scripts/collect_extra_competitions.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
