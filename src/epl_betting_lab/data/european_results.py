"""Champions League results, which are the only bridge between countries.

Ratings fitted on one country's league have no scale in common with another's:
clubs never move between countries, so nothing links the pools the way promotion
links the English divisions. European ties are the exception — a match with a
result, played between clubs from two different domestic pools. Fit them
alongside the domestic seasons and every country lands on one scale.

openfootball publishes them free, keyless and public domain, with a country code
on every club:

    18:45  AC Milan (ITA)          v Newcastle United FC (ENG)  0-0

Seven seasons are on file, 2019-20 through 2025-26, about 125 matches a season
before the league-phase format and about 189 after.

Two things this module refuses to do. It does not guess a club's domestic name —
that is `data/european_clubs.py`, hand-written, because normalising the strings
proposes `Paris Saint-Germain FC` -> `Paris FC` and a wrong name does not fail,
it silently rates a different club. And it does not invent a date: a match whose
date header could not be parsed is dropped rather than filed under the season's
first day, because a tie placed before the ratings that should have predicted it
would leak the result into its own forecast.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

import pandas as pd
import requests

from epl_betting_lab.config import COUNTRY_TO_LEAGUE, CURRENT_SEASON
from epl_betting_lab.data.european_clubs import domestic_name, espn_name

SOURCE_URL = (
    "https://raw.githubusercontent.com/openfootball/champions-league/master/"
    "{season}/{file}.txt"
)

#: Every European competition openfootball publishes in that repository, and
#: what each is worth here.
#:
#: All three are bridges: a match with a result between clubs from two
#: different domestic pools, which is the only thing that puts one country's
#: ratings on the same scale as another's. More bridges is a better-calibrated
#: scale, and the Conference League earns its place on that alone — it is used
#: to fit and never bet, so it improves the ratings at no exposure.
#:
#: The qualifying rounds (`clq`, `elq`, `confq`) are deliberately left out.
#: They are played in July against opposition from outside these eleven
#: leagues, so most of their ties have an unrateable side and the ones that do
#: not are between clubs whose seasons have not started.
COMPETITION_FILES = {
    "UCL": "cl",
    "UEL": "el",
    "UECL": "conf",
}

#: Every season from 2019-20 through the one being played. This was typed in
#: and stopped at 2025-26, so the ratings learnt nothing from a European match
#: of 2026-27. A season openfootball has not published (a 404) is filled from
#: ESPN instead; see `load_european_ties`.
def _seasons_through(code: str, first: int = 2019) -> tuple[str, ...]:
    last = 2000 + int(code[:2])
    return tuple(f"{year}-{(year + 1) % 100:02d}" for year in range(first, last + 1))


SEASONS = _seasons_through(CURRENT_SEASON)

#: ESPN's league slug for each competition, for what openfootball lacks.
ESPN_LEAGUES = {
    "UCL": "uefa.champions",
    "UEL": "uefa.europa",
    "UECL": "uefa.europa.conf",
}
ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"
    "?dates={year}&limit=1000"
)

#: `21:00  SS Lazio (ITA)    v Club Atlético de Madrid (ESP)  1-1 (0-1)`
#: The kick-off time is optional and the half-time score is ignored.
MATCH = re.compile(
    r"^\s*(?:\d{1,2}[:.]\d{2}\s+)?(.+?)\s+\(([A-Z]{3})\)\s+v\s+"
    r"(.+?)\s+\(([A-Z]{3})\)\s+(\d+)-(\d+)"
)

#: `  Tue Sep 19 2023` — a date header, which every following match belongs to
#: until the next one.
DATE_HEADER = re.compile(r"^\s{2}(\w{3} \w{3} \d{1,2} \d{4})\s*$")


class EuropeanResultsUnavailable(RuntimeError):
    """The season could not be read.

    Raised rather than returning an empty frame: an empty result would silently
    remove every bridge for that season and leave the countries unlinked, which
    looks exactly like a season nobody played.
    """


@dataclass(frozen=True)
class ParsedSeason:
    matches: pd.DataFrame
    #: Club appearances that could not be resolved to a domestic rating, with
    #: the country. Counted rather than dropped in silence: thirty of the clubs
    #: in these seasons play in countries Football-Data does not publish, and
    #: that is a fact about coverage rather than a parsing failure.
    unresolved: list[tuple[str, str]]


def parse_season(text: str, season: str, competition: str = "UCL") -> ParsedSeason:
    """Every tie in one season's file, with both clubs resolved where possible."""
    rows: list[dict[str, object]] = []
    unresolved: list[tuple[str, str]] = []
    current: pd.Timestamp | None = None

    for line in text.splitlines():
        header = DATE_HEADER.match(line)
        if header:
            current = pd.to_datetime(
                header.group(1), format="%a %b %d %Y", errors="coerce"
            )
            continue
        match = MATCH.match(line)
        if not match:
            continue
        home, home_country, away, away_country, home_goals, away_goals = match.groups()

        resolved: list[str] = []
        for club, country in ((home.strip(), home_country), (away.strip(), away_country)):
            if country not in COUNTRY_TO_LEAGUE:
                unresolved.append((club, country))
                continue
            name = domestic_name(club, country)
            if name is None:
                unresolved.append((club, country))
                continue
            resolved.append(name)

        if len(resolved) != 2 or current is None or pd.isna(current):
            continue
        rows.append(
            {
                "date": current,
                "home_team": resolved[0],
                "away_team": resolved[1],
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "competition": competition,
                "season": season,
            }
        )

    columns = ["date", "home_team", "away_team", "home_goals", "away_goals", "competition", "season"]
    frame = pd.DataFrame(rows, columns=columns)
    return ParsedSeason(frame, unresolved)


def fetch_season(season: str, competition: str = "UCL", *, timeout: int = 30) -> str:
    """One season's file for one competition, as text."""
    url = SOURCE_URL.format(season=season, file=COMPETITION_FILES[competition])
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise EuropeanResultsUnavailable(f"{url} could not be read: {exc}") from exc
    if response.status_code != 200:
        raise EuropeanResultsUnavailable(
            f"{url} returned HTTP {response.status_code}."
        )
    text = response.text
    if "v " not in text:
        raise EuropeanResultsUnavailable(
            f"{url} returned {len(text)} characters with no match line in them."
        )
    return text


def fetch_espn_season(season: str, competition: str, *, timeout: int = 30) -> list[dict]:
    """ESPN's scoreboards for the two calendar years a season spans. Keyless.

    urllib's own User-Agent on purpose: site.api.espn.com refuses descriptive
    agents (see web/settle_results.py).
    """
    start = int(season[:4])
    payloads: list[dict] = []
    for year in (start, start + 1):
        url = ESPN_SCOREBOARD.format(league=ESPN_LEAGUES[competition], year=year)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed host
                payloads.append(json.load(response))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise EuropeanResultsUnavailable(f"{url} could not be read: {exc}") from exc
    return payloads


def espn_season_ties(payloads: list[dict], season: str, competition: str) -> pd.DataFrame:
    """Every completed tie of `season` on ESPN's scoreboards, in Football-Data's names.

    Dated by the UTC calendar day of kick-off: every European fixture kicks
    off between 16:00 and 21:00 UTC, so that is also the local date.
    """
    year = int(season[:4])
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for payload in payloads:
        for event in (payload or {}).get("events", []) or []:
            if ((event.get("season") or {}).get("year")) != year:
                continue
            if not ((event.get("status") or {}).get("type") or {}).get("completed"):
                continue
            key = str(event.get("id") or event.get("date")) + str(event.get("name", ""))
            competition_block = (event.get("competitions") or [{}])[0]
            sides = {c.get("homeAway"): c for c in competition_block.get("competitors", []) or []}
            home, away = sides.get("home"), sides.get("away")
            when = pd.to_datetime(event.get("date"), errors="coerce", utc=True)
            if not home or not away or pd.isna(when):
                continue
            try:
                home_goals, away_goals = int(home.get("score")), int(away.get("score"))
            except (TypeError, ValueError):
                continue
            names = [espn_name(" ".join(str((s.get("team") or {}).get("displayName") or "").split()))
                     for s in (home, away)]
            identity = f"{key}|{names[0]}|{names[1]}|{when.date()}"
            if identity in seen:
                continue
            seen.add(identity)
            rows.append({
                "date": pd.Timestamp(when.date()),
                "home_team": names[0],
                "away_team": names[1],
                "home_goals": home_goals,
                "away_goals": away_goals,
                "competition": competition,
                "season": season,
            })
    columns = ["date", "home_team", "away_team", "home_goals", "away_goals", "competition", "season"]
    return pd.DataFrame(rows, columns=columns)


def load_european_ties(
    seasons: tuple[str, ...] = SEASONS,
    competitions: tuple[str, ...] = tuple(COMPETITION_FILES),
    *,
    fetcher=fetch_season,
    espn_fetcher=fetch_espn_season,
) -> ParsedSeason:
    """Every resolvable European tie across the seasons and competitions on file.

    openfootball first, because its clubs carry a country. ESPN fills a
    season and competition openfootball has not published, and only those,
    so no tie is counted twice.
    """
    frames: list[pd.DataFrame] = []
    unresolved: list[tuple[str, str]] = []
    for season in seasons:
        for competition in competitions:
            try:
                parsed = parse_season(fetcher(season, competition), season, competition)
            except EuropeanResultsUnavailable as exc:
                try:
                    filled = espn_season_ties(espn_fetcher(season, competition), season, competition)
                except EuropeanResultsUnavailable as espn_exc:
                    # One file missing costs its own bridges and not the rest.
                    print(f"{season}/{competition}: {exc}; ESPN: {espn_exc}")
                    continue
                print(f"{season}/{competition}: {exc}; {len(filled)} ties from ESPN instead.")
                if not filled.empty:
                    frames.append(filled)
                continue
            frames.append(parsed.matches)
            unresolved.extend(parsed.unresolved)
    if not frames:
        raise EuropeanResultsUnavailable(
            "No European season could be read, so no country can be linked to "
            "another and every rating would be on its own scale."
        )
    return ParsedSeason(pd.concat(frames, ignore_index=True), unresolved)
