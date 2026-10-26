"""Who referees the coming fixtures, from the Premier League's own feed.

`footballapi.pulselive.com` is what premierleague.com's match centre reads:
keyless, answering a request that carries the site's Origin. Each fixture's
detail lists its match officials, the referee under role MAIN, once the
appointment is announced (usually early in match week). Before that the list
is empty and the fixture gets no referee, never a guessed one.

The file written beside the processed data carries each appointment with the
referee's card factor (`models.referee`), which the props card applies to its
booked and sent-off prices.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from epl_betting_lab.models.referee import referee_factors, referee_key
from epl_betting_lab.providers.team_names import normalize_team_name

BASE = "https://footballapi.pulselive.com/football"
SEASONS = BASE + "/competitions/1/compseasons?page=0&pageSize=1"
UPCOMING = BASE + "/fixtures?comps=1&compSeasons={season}&page=0&pageSize=20&sort=asc&statuses=U"
DETAIL = BASE + "/fixtures/{fixture}"
HEADERS = {"Origin": "https://www.premierleague.com", "Referer": "https://www.premierleague.com/"}

APPOINTMENTS_FILENAME = "referee_appointments.csv"
FIELDS = ["home_team", "away_team", "kickoff", "referee", "card_factor"]

Requester = Callable[[str], Any]


class AppointmentsError(RuntimeError):
    pass


def default_requester(url: str) -> Any:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed host
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise AppointmentsError(f"The Premier League feed could not be read at {url}: {exc}") from exc


def _main_referee(detail: dict) -> str:
    for official in detail.get("matchOfficials") or []:
        if official.get("role") == "MAIN":
            return str((official.get("name") or {}).get("display") or "").strip()
    return ""


def fetch_appointments(*, fetch: Requester = default_requester) -> list[dict[str, str]]:
    """The coming fixtures that have a referee appointed."""
    seasons = fetch(SEASONS).get("content") or []
    if not seasons:
        raise AppointmentsError("The Premier League feed listed no season.")
    season = int(seasons[0]["id"])
    rows: list[dict[str, str]] = []
    for fixture in fetch(UPCOMING.format(season=season)).get("content") or []:
        teams = [normalize_team_name((t.get("team") or {}).get("name", "")) for t in fixture.get("teams") or []]
        if len(teams) != 2:
            continue
        referee = _main_referee(fetch(DETAIL.format(fixture=int(fixture["id"]))))
        if not referee:
            continue
        millis = (fixture.get("kickoff") or {}).get("millis")
        kickoff = pd.Timestamp(int(millis), unit="ms", tz="UTC").isoformat() if millis else ""
        rows.append({"home_team": teams[0], "away_team": teams[1], "kickoff": kickoff, "referee": referee})
    return rows


def refresh_appointments(
    path: Path, *, matches: pd.DataFrame, fetch: Requester = default_requester
) -> str:
    """Write the appointments with each referee's factor; soft on failure."""
    try:
        rows = fetch_appointments(fetch=fetch)
    except (AppointmentsError, KeyError, TypeError, ValueError) as exc:
        return f"WARNING: referee appointments not read: {exc}"
    factors = referee_factors(matches)
    for row in rows:
        row["card_factor"] = round(factors.get(referee_key(row["referee"]), 1.0), 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=FIELDS).to_csv(path, index=False)
    known = sum(1 for row in rows if referee_key(row["referee"]) in factors)
    return (
        f"Referees: {len(rows)} appointment(s) read, {known} with a card record "
        f"({len(factors)} referees rated) -> {path}"
    )
