"""Fetch and normalize English Premier League historical data from Football-Data.co.uk.

Football-Data season codes look like:
- 2122 = 2021/22
- 2223 = 2022/23
- 2324 = 2023/24
- 2425 = 2024/25
- 2526 = 2025/26

The EPL division code is E0.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from epl_betting_lab.config import LEAGUE_CODE, RAW_DIR, PROCESSED_DIR

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"


def football_data_url(season: str, league: str = LEAGUE_CODE) -> str:
    return BASE_URL.format(season=season, league=league)


class SeasonNotPublished(RuntimeError):
    """The season is in the schedule but Football-Data has no results for it."""


def _looks_like_a_results_csv(content: bytes) -> bool:
    """Is this the CSV we asked for, or a page saying it is not there?

    Football-Data answers a season it has not published with a redirect page
    rather than a 404 — an HTTP 300 carrying a few hundred bytes of HTML.
    `raise_for_status` is silent on 3xx, so without this check that page is
    written to disk as `E0.csv` and then parsed as if it were results.
    """
    head = content[:2048].lstrip().lower()
    if head.startswith(b"<"):
        return False
    return b"hometeam" in head and b"awayteam" in head


def fetch_season(season: str, league: str = LEAGUE_CODE, raw_dir: Path = RAW_DIR) -> Path:
    """Download one season CSV and return local path."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = football_data_url(season, league)
    dest = raw_dir / f"football_data_{league}_{season}.csv"

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    if not _looks_like_a_results_csv(response.content):
        raise SeasonNotPublished(
            f"{url} returned HTTP {response.status_code} with "
            f"{len(response.content)} bytes that are not a results CSV."
        )
    dest.write_bytes(response.content)
    return dest


def load_season(path: Path, season: str) -> pd.DataFrame:
    """Load a Football-Data CSV and keep the columns the project needs."""
    df = pd.read_csv(path)
    df = df.dropna(subset=["HomeTeam", "AwayTeam"], how="any").copy()
    df["season"] = season

    # Common columns on football-data. Some odds columns may be missing by season/book.
    desired = [
        "season", "Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
        "HTHG", "HTAG", "HTR", "HS", "AS", "HST", "AST", "HC", "AC", "HF", "AF", "HY", "AY", "HR", "AR",
        "B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA", "MaxH", "MaxD", "MaxA",
        "B365>2.5", "B365<2.5", "Avg>2.5", "Avg<2.5", "Max>2.5", "Max<2.5",
        "AHh", "B365AHH", "B365AHA", "AvgAHH", "AvgAHA",
        # Closing odds. Football-Data marks them with a C: AvgCH is the average
        # home price at kick-off, AvgH the opening one.
        #
        # These were being dropped, and the backtest asked for `CloseH` and
        # always got nothing — so every closing-line column came back empty and
        # CLV could not be computed at all. That matters more than it sounds:
        # profit needs about 1,500 settled bets to separate a 5% edge from
        # zero, roughly twelve seasons, while beating the closing line gives a
        # readable signal per bet. It is the only feedback loop here that
        # returns an answer inside a season.
        "B365CH", "B365CD", "B365CA", "AvgCH", "AvgCD", "AvgCA",
        "B365C>2.5", "B365C<2.5", "AvgC>2.5", "AvgC<2.5",
    ]
    keep = [c for c in desired if c in df.columns]
    df = df[keep].copy()

    # Normalize date. Football-Data has changed formats across years.
    df["date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df["home_team"] = df["HomeTeam"]
    df["away_team"] = df["AwayTeam"]
    df["home_goals"] = pd.to_numeric(df.get("FTHG"), errors="coerce")
    df["away_goals"] = pd.to_numeric(df.get("FTAG"), errors="coerce")
    df["result"] = df.get("FTR")

    # Everything that is not a label is a number — except the parsed date,
    # which is neither. Coercing it turned a datetime into microseconds since
    # the epoch, and reading that back as nanoseconds put every match in
    # January 1970. The integers stay in order, so sorting and walk-forward
    # never noticed; only something that read a date could.
    non_numeric = {
        "season", "Div", "Date", "Time", "HomeTeam", "AwayTeam",
        "FTR", "HTR", "home_team", "away_team", "result", "date",
    }
    for col in df.columns:
        if col not in non_numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def fetch_and_build_dataset(seasons: Iterable[str], force: bool = False) -> pd.DataFrame:
    """Download missing seasons and combine them into one processed CSV."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    ordered = list(seasons)
    frames: list[pd.DataFrame] = []
    skipped: list[str] = []
    for season in ordered:
        raw_path = RAW_DIR / f"football_data_{LEAGUE_CODE}_{season}.csv"
        try:
            if force or not raw_path.exists():
                fetch_season(season)
            frames.append(load_season(raw_path, season))
        except SeasonNotPublished as exc:
            # Only the season being played is allowed to be missing, and only
            # until its first result is published. A completed season going
            # quiet would shrink the training set without anyone noticing,
            # which is the failure this asymmetry exists to prevent.
            if season != ordered[-1]:
                raise RuntimeError(
                    f"Completed season {season} could not be fetched: {exc}. "
                    "Refusing to build a dataset that is missing a season the "
                    "model was fitted on."
                ) from exc
            skipped.append(season)
            print(
                f"Season {season} has no published results yet; building "
                "without it. It will be included once the season starts."
            )

    if not frames:
        raise RuntimeError(
            "No season could be fetched. Football-Data may be unreachable; "
            "the existing dataset was left untouched."
        )

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["date", "home_team", "away_team"], na_position="last")
    out = PROCESSED_DIR / "epl_historical_matches.csv"
    # Write the date as a readable string. Left to itself, pandas serialised a
    # microsecond-resolution datetime column as a bare integer, which read back
    # as nanoseconds and put every match in 1970. Ordering survived — the
    # integers are monotonic — so sorting and walk-forward were unaffected and
    # nothing noticed for as long as nobody looked at a date.
    written = combined.copy()
    written["date"] = pd.to_datetime(written["date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    written.to_csv(out, index=False)
    return combined
