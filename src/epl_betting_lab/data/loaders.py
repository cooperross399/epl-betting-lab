from __future__ import annotations

from pathlib import Path
import pandas as pd

from epl_betting_lab.config import PROCESSED_DIR, MANUAL_DIR


def load_matches(path: Path | None = None) -> pd.DataFrame:
    path = path or PROCESSED_DIR / "epl_historical_matches.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run scripts/fetch_data.py first.")
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    return df


def load_current_odds(path: Path | None = None) -> pd.DataFrame:
    path = path or MANUAL_DIR / "current_odds.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Copy data/manual/current_odds_template.csv to current_odds.csv and fill it in.")
    return pd.read_csv(path)


def load_upcoming_fixtures(path: Path | None = None) -> pd.DataFrame:
    path = path or MANUAL_DIR / "upcoming_fixtures.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}.")
    return pd.read_csv(path, parse_dates=["date"])
