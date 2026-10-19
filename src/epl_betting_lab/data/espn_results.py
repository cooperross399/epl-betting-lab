"""Premier League finals from ESPN, for the fixtures Football-Data has not published.

The ratings and the card's record both read `epl_historical_matches.csv`, and
Football-Data publishes a round some time after it is played. Until it does,
the round teaches the ratings nothing and every pick on it sits as "played,
waiting on results data". On Monday 2026-10-19 at 12:42 UTC the file held 60 of
the season's matches while ESPN had 69 finals: the whole 17-18 October round.

ESPN's public scoreboard (keyless, no quota, already read by the board and the
Due List) carries the score, the corners, the shots and the fouls of every
final. Those become rows in Football-Data's own columns, marked
`result_source = espn`, for fixtures Football-Data does not yet hold. Its row
replaces each one as soon as it is published, because `fetch_data.py` rebuilds
the file from Football-Data alone and this runs after it.

What is deliberately left blank:

- The odds columns. ESPN carries no closing prices, and a missing price stays
  missing.
- The card counts (HY/AY/HR/AR). The card markets were measured on
  Football-Data's counts, and ESPN's booking events do not count a second
  yellow the same way in every case. Card picks wait for Football-Data.
- Half-time scores.

A club whose ESPN name the reviewed alias table does not map is skipped and
reported, never coerced onto the nearest name.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from epl_betting_lab.config import LEAGUE_CODE
from epl_betting_lab.providers.team_names import (
    is_canonical_team_name,
    normalize_team_name,
)

SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
    "?dates={year}&limit=1000"
)

#: Football-Data dates its rows in UK time, and Understat's xG is joined on the
#: date, so a late kick-off has to land on the same day in all three.
UK = ZoneInfo("Europe/London")

SOURCE_COLUMN = "result_source"
SOURCE = "espn"

#: ESPN team statistic -> (home column, away column) in Football-Data's naming.
STATISTICS = {
    "wonCorners": ("HC", "AC"),
    "totalShots": ("HS", "AS"),
    "shotsOnTarget": ("HST", "AST"),
    "foulsCommitted": ("HF", "AF"),
}

#: Present on every row and blank on purpose; see the module docstring.
BLANK_COLUMNS = ("HY", "AY", "HR", "AR")

Requester = Callable[[str], Any]


class EspnResultsError(RuntimeError):
    """ESPN answered with something other than the scoreboard."""


def default_requester(url: str) -> Any:
    # urllib's default User-Agent on purpose: site.api.espn.com answers it and
    # refuses descriptive agents (see web/settle_results.py).
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed host
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise EspnResultsError(f"ESPN could not be read at {url}: {exc}") from exc


def espn_season_year(season_code: str) -> int:
    """Football-Data's `2627` is ESPN's season year 2026."""
    return 2000 + int(str(season_code)[:2])


def season_code_for(year: int) -> str:
    return f"{year % 100:02d}{(year + 1) % 100:02d}"


def _columns() -> list[str]:
    stats = [column for pair in STATISTICS.values() for column in pair]
    return [
        "season", "Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
        *stats, *BLANK_COLUMNS,
        "date", "home_team", "away_team", "home_goals", "away_goals", "result",
        SOURCE_COLUMN,
    ]


def empty_finals() -> pd.DataFrame:
    return pd.DataFrame(columns=_columns())


def _number(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _club(competitor: Mapping) -> str | None:
    name = " ".join(str(((competitor.get("team") or {}).get("displayName")) or "").split())
    mapped = normalize_team_name(name)
    return mapped if is_canonical_team_name(mapped) else None


def finals_from_scoreboard(
    payload: Mapping, *, season_year: int, unmapped: list[str] | None = None
) -> pd.DataFrame:
    """Every completed league fixture of `season_year` as a Football-Data-shaped row."""
    rows: list[dict[str, Any]] = []
    for event in payload.get("events", []) or []:
        if ((event.get("season") or {}).get("year")) != season_year:
            continue
        status = (event.get("status") or {}).get("type") or {}
        if not status.get("completed"):
            continue
        competition = (event.get("competitions") or [{}])[0]
        sides = {c.get("homeAway"): c for c in competition.get("competitors", []) or []}
        home, away = sides.get("home"), sides.get("away")
        if not home or not away:
            continue
        home_team, away_team = _club(home), _club(away)
        if home_team is None or away_team is None:
            if unmapped is not None:
                for side, team in ((home, home_team), (away, away_team)):
                    if team is None:
                        unmapped.append(str((side.get("team") or {}).get("displayName", "")))
            continue
        home_goals, away_goals = _number(home.get("score")), _number(away.get("score"))
        kickoff = pd.to_datetime(event.get("date"), errors="coerce", utc=True)
        if home_goals is None or away_goals is None or pd.isna(kickoff):
            continue
        local = kickoff.tz_convert(UK)
        result = "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D"
        row: dict[str, Any] = {
            "season": season_code_for(season_year),
            "Div": LEAGUE_CODE,
            "Date": local.strftime("%d/%m/%Y"),
            "Time": local.strftime("%H:%M"),
            "HomeTeam": home_team,
            "AwayTeam": away_team,
            "FTHG": home_goals,
            "FTAG": away_goals,
            "FTR": result,
            "date": local.strftime("%Y-%m-%d"),
            "home_team": home_team,
            "away_team": away_team,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "result": result,
            SOURCE_COLUMN: SOURCE,
        }
        for column in BLANK_COLUMNS:
            row[column] = float("nan")
        for side, index in ((home, 0), (away, 1)):
            stats = {
                str(s.get("name")): s.get("displayValue")
                for s in side.get("statistics", []) or []
            }
            for name, columns in STATISTICS.items():
                value = _number(stats.get(name))
                row[columns[index]] = float("nan") if value is None else value
        rows.append(row)
    if not rows:
        return empty_finals()
    return pd.DataFrame(rows, columns=_columns())


def _pairing(frame: pd.DataFrame) -> pd.Series:
    """A league pairing happens once per season, so (season, home, away) is its identity."""
    return (
        frame["season"].astype(str).str.strip()
        + "|" + frame["home_team"].astype(str).str.strip().str.casefold()
        + "|" + frame["away_team"].astype(str).str.strip().str.casefold()
    )


def supplement(dataset: pd.DataFrame, finals: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """The dataset with every ESPN final it does not already hold from Football-Data.

    Earlier ESPN rows are dropped and re-derived, so a fixture Football-Data
    has since published keeps only Football-Data's row. Returns the merged
    frame and how many ESPN rows it carries.
    """
    if SOURCE_COLUMN in dataset.columns:
        earlier = dataset[SOURCE_COLUMN].fillna("").astype(str) == SOURCE
        published = dataset[~earlier]
        if finals.empty:
            # Nothing new from ESPN: the rows an earlier run added still stand,
            # except where Football-Data has published the fixture since.
            finals = dataset[earlier]
    else:
        published = dataset
    if finals.empty:
        return dataset.copy(), 0
    held = set(_pairing(published)) if not published.empty else set()
    fresh = finals[~_pairing(finals).isin(held)]
    if fresh.empty:
        return published.copy(), 0
    merged = pd.concat([published, fresh], ignore_index=True)
    order = pd.to_datetime(merged["date"], errors="coerce")
    merged = (
        merged.assign(_order=order)
        .sort_values(["_order", "home_team", "away_team"], na_position="last", kind="stable")
        .drop(columns="_order")
        .reset_index(drop=True)
    )
    return merged, len(fresh)


@dataclass
class SupplementStatus:
    added: int = 0
    error: str = ""
    unmapped: list[str] = field(default_factory=list)


def supplement_file(
    path: Path, *, season_code: str, request: Requester = default_requester
) -> SupplementStatus:
    """Fill `path` with the season's ESPN finals it lacks. Soft: on any failure
    the file is left exactly as it was."""
    status = SupplementStatus()
    if not path.exists():
        status.error = f"No dataset at {path}; there is nothing to add ESPN finals to."
        return status
    year = espn_season_year(season_code)
    frames: list[pd.DataFrame] = []
    try:
        # One scoreboard per calendar year the season spans.
        for calendar_year in (year, year + 1):
            payload = request(SCOREBOARD.format(year=calendar_year))
            if not isinstance(payload, Mapping):
                raise EspnResultsError(f"ESPN returned no scoreboard for {calendar_year}.")
            frames.append(
                finals_from_scoreboard(payload, season_year=year, unmapped=status.unmapped)
            )
    except EspnResultsError as exc:
        status.error = str(exc)
        return status
    finals = pd.concat([f for f in frames if not f.empty] or [empty_finals()], ignore_index=True)
    if not finals.empty:
        finals = finals.drop_duplicates(subset=["season", "home_team", "away_team"])
    dataset = pd.read_csv(path)
    merged, added = supplement(dataset, finals)
    status.added = added
    merged.to_csv(path, index=False)
    return status
