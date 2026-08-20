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
        df["date"] = _read_dates(df["date"])
    return df


def _read_dates(values: pd.Series) -> pd.Series:
    """Dates as written now, and as they were written before.

    A file produced before the serialisation fix holds microseconds since the
    epoch as a bare integer. Read as nanoseconds — pandas's default for an
    integer — every match lands in January 1970. Handling both means an old
    file already on disk is read correctly rather than silently wrongly.
    """
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_datetime(values, unit="us", errors="coerce")
    return pd.to_datetime(values, errors="coerce", format="mixed")


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
