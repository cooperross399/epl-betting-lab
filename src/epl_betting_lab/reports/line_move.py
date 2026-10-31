"""Does the market's move since the first price run against a pick?

The CBB lab's `models/line_move.py` (2026-10-30): a lean the market has moved
against since the event's first line-movement capture is halved before the
edge bar reads it; a move with the lean changes nothing. This lab has had the
captures since 2026-09-02 (the price feed, `reports/price_feed.py`), and the
card never read them.

The first capture is the earliest observation of the selection in the feed,
the latest the newest one. Each is the median implied probability across the
books observed at that moment. A drop of at least `MIN_MOVE` (the market now
gives the selection less chance than it first did) is a move against.
Observations after kick-off are ignored. Forward only, and not evidence of
an edge: it removes stakes, it never adds one.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import PROCESSED_DIR
from epl_betting_lab.models.value import american_to_implied

#: One point of implied probability: smaller moves are book noise.
MIN_MOVE = 0.01
#: What a pick's edge is multiplied by when the market moved against it.
AGAINST_FACTOR = 0.5

DEFAULT_FEED = PROCESSED_DIR / "price_feed.csv"


def load_feed(path: Path | None = None) -> pd.DataFrame:
    path = Path(path) if path is not None else DEFAULT_FEED
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(
            path,
            usecols=lambda c: c in {
                "observed_at", "commence_time", "home_team", "away_team",
                "market", "selection", "book", "american_odds",
            },
            dtype=str,
        )
    except (OSError, ValueError):
        return pd.DataFrame()


def move_against(
    feed: pd.DataFrame, home: str, away: str, market: str, selection: str
) -> tuple[bool, float, float]:
    """(moved against, first implied, latest implied)."""
    nan = float("nan")
    needed = {"observed_at", "home_team", "away_team", "market", "selection", "american_odds"}
    if feed.empty or not needed <= set(feed.columns):
        return (False, nan, nan)
    def key(column: str) -> pd.Series:
        return feed[column].fillna("").astype(str).str.strip().str.casefold()

    def norm(value: str) -> str:
        return str(value).strip().casefold()

    rows = feed[
        (key("home_team") == norm(home))
        & (key("away_team") == norm(away))
        & (key("market") == norm(market))
        & (key("selection") == norm(selection))
    ].copy()
    if rows.empty:
        return (False, nan, nan)
    rows["observed"] = pd.to_datetime(rows["observed_at"], utc=True, errors="coerce")
    if "commence_time" in rows.columns:
        kickoff = pd.to_datetime(rows["commence_time"], utc=True, errors="coerce")
        rows = rows[kickoff.isna() | (rows["observed"] < kickoff)]
    rows["implied"] = pd.to_numeric(rows["american_odds"], errors="coerce").map(
        lambda v: american_to_implied(v) if pd.notna(v) and v != 0 else float("nan")
    )
    rows = rows.dropna(subset=["observed", "implied"])
    if rows["observed"].nunique() < 2:
        return (False, nan, nan)
    by_moment = rows.groupby("observed")["implied"].median().sort_index()
    first, latest = float(by_moment.iloc[0]), float(by_moment.iloc[-1])
    return (first - latest >= MIN_MOVE, first, latest)
