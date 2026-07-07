"""Helpers for ClubElo ratings.

ClubElo exposes CSV-style API endpoints. The date endpoint is commonly used as:
https://api.clubelo.com/YYYY-MM-DD

The team endpoint is commonly used as:
https://api.clubelo.com/Arsenal
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from epl_betting_lab.config import RAW_DIR


def fetch_clubelo_by_date(date: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Fetch ClubElo ratings snapshot by date. Date format: YYYY-MM-DD."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://api.clubelo.com/{date}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text))
    out = raw_dir / f"clubelo_{date}.csv"
    df.to_csv(out, index=False)
    return df


def fetch_clubelo_team(team: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Fetch ClubElo history for one team, e.g. Arsenal, Liverpool, ManCity."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://api.clubelo.com/{team}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text))
    out = raw_dir / f"clubelo_team_{team}.csv"
    df.to_csv(out, index=False)
    return df
