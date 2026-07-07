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


def fetch_season(season: str, league: str = LEAGUE_CODE, raw_dir: Path = RAW_DIR) -> Path:
    """Download one season CSV and return local path."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = football_data_url(season, league)
    dest = raw_dir / f"football_data_{league}_{season}.csv"

    response = requests.get(url, timeout=30)
    response.raise_for_status()
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

    for col in df.columns:
        if col not in {"season", "Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTR", "HTR", "home_team", "away_team", "result"}:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def fetch_and_build_dataset(seasons: Iterable[str], force: bool = False) -> pd.DataFrame:
    """Download missing seasons and combine them into one processed CSV."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    frames: list[pd.DataFrame] = []
    for season in seasons:
        raw_path = RAW_DIR / f"football_data_{LEAGUE_CODE}_{season}.csv"
        if force or not raw_path.exists():
            fetch_season(season)
        frames.append(load_season(raw_path, season))

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["date", "home_team", "away_team"], na_position="last")
    out = PROCESSED_DIR / "epl_historical_matches.csv"
    combined.to_csv(out, index=False)
    return combined
