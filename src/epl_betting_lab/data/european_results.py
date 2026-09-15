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

import re
from dataclasses import dataclass

import pandas as pd
import requests

from epl_betting_lab.config import COUNTRY_TO_LEAGUE
from epl_betting_lab.data.european_clubs import domestic_name

SOURCE_URL = (
    "https://raw.githubusercontent.com/openfootball/champions-league/master/"
    "{season}/cl.txt"
)

#: Seasons openfootball publishes. 2026-27 is not up yet; asking for it returns
#: a 404 rather than an empty file, which `fetch_season` reports as absence
#: rather than as an empty competition.
SEASONS = (
    "2019-20",
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
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


def parse_season(text: str, season: str) -> ParsedSeason:
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
                "competition": "UCL",
                "season": season,
            }
        )

    columns = ["date", "home_team", "away_team", "home_goals", "away_goals", "competition", "season"]
    frame = pd.DataFrame(rows, columns=columns)
    return ParsedSeason(frame, unresolved)


def fetch_season(season: str, *, timeout: int = 30) -> str:
    """One season's file as text."""
    url = SOURCE_URL.format(season=season)
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


def load_european_ties(
    seasons: tuple[str, ...] = SEASONS, *, fetcher=fetch_season
) -> ParsedSeason:
    """Every resolvable European tie across the seasons on file."""
    frames: list[pd.DataFrame] = []
    unresolved: list[tuple[str, str]] = []
    for season in seasons:
        try:
            parsed = parse_season(fetcher(season), season)
        except EuropeanResultsUnavailable as exc:
            # One season missing costs its bridges and not the rest. A season
            # that simply is not published yet is the ordinary case.
            print(f"{season}: {exc}")
            continue
        frames.append(parsed.matches)
        unresolved.extend(parsed.unresolved)
    if not frames:
        raise EuropeanResultsUnavailable(
            "No European season could be read, so no country can be linked to "
            "another and every rating would be on its own scale."
        )
    return ParsedSeason(pd.concat(frames, ignore_index=True), unresolved)
