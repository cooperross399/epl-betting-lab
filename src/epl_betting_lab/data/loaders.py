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


def load_team_xg(path: Path | None = None) -> pd.DataFrame:
    """Understat per-match team xG in Football-Data naming; empty if not fetched."""
    path = path or PROCESSED_DIR / "understat_team_xg.csv"
    if not path.exists():
        return pd.DataFrame(columns=["date", "home_team", "away_team", "home_xg", "away_xg"])
    frame = pd.read_csv(path, parse_dates=["date"])
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame


def load_matches_with_xg(
    matches_path: Path | None = None, xg_path: Path | None = None
) -> pd.DataFrame:
    """Historical matches with `home_xg`/`away_xg` joined on where Understat has them.

    A left join: a match without xG keeps its goals and gets NaN, so a rating
    fitted on xG falls back to goals for that match rather than dropping it.
    """
    matches = load_matches(matches_path).copy()
    matches["date"] = pd.to_datetime(matches["date"]).dt.normalize()
    xg = load_team_xg(xg_path)
    if xg.empty:
        matches["home_xg"] = float("nan")
        matches["away_xg"] = float("nan")
        return matches
    return matches.merge(xg, on=["date", "home_team", "away_team"], how="left")

