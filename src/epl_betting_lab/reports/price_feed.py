"""A durable record of the prices this project actually saw, and when.

Closing-line value is the only feedback this lab has that returns an answer
inside a season. Profit needs roughly 1,500 settled bets to separate a 5% edge
from zero — about twelve seasons at this rate — while every bet produces a CLV
reading the moment its market closes. And for the markets that carry the card
it is the ONLY feedback there will ever be: corners cannot be profit-backtested
because no source retains their historical prices, and they are 23 of the first
42 best bets.

None of that worked. `closing_american_odds` is written as the empty string by
the only live producer (`odds_api_staging_provider.py`), 0 of 448 staged rows
have ever carried one, and `save_clv_reports` is called from `run_backtest.py`
alone — so every CLV figure the project has published came from Football-Data
closing prices for seasons already in the dataset. In-sample, and about a
different population than the card.

The fix needs no new fetch. Every refresh already stages several hundred
book-level prices and then throws them away at the end of the run, and each
staged row already identifies itself completely: the provider's event id, the
bookmaker, and the moment it was fetched all travel in `notes`. Appending those
rows to a feed turns work already being paid for into a price history.

Two things this deliberately does not do.

**It does not call anything a closing price.** A row records when it was
observed, and nothing more. Whether the last observation before kick-off is
near enough to the close to deserve the name depends on when the snapshot ran,
which is a property of the schedule and not of this file. `live_clv` decides
that, and says how long before kick-off its "closing" reading actually was.

**It does not overwrite.** The feed is append-only and deduplicated on the
observation itself, so a snapshot that runs twice adds nothing and a re-run
after a failure cannot lose history.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

#: Columns of the feed, in order. One row is one price at one book at one moment.
FEED_COLUMNS = (
    "observed_at",
    "provider_event_id",
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "book",
    "american_odds",
)

#: What makes two observations the same observation.
IDENTITY = ("observed_at", "provider_event_id", "market", "selection", "book")

_EVENT_ID = re.compile(r"event\s+([0-9a-f]{8,})", re.IGNORECASE)


def event_id_from_notes(notes: object) -> str:
    """The provider's event id, which every staged row carries in its notes.

    Team names are the weakest possible join key — normalised differently by
    every source, and the same pairing recurs every season. The id is exact.
    """
    match = _EVENT_ID.search("" if notes is None else str(notes))
    return match.group(1) if match else ""


def observed_at(provenance: dict) -> str:
    """When the provider run that produced this staging actually fetched.

    Taken from the provenance rather than from the notes string or from the
    clock, because the provenance is the record the policy gates already check.
    `harvest_historical_btts` files its rows by the time it *asked* for instead,
    which is harmless at a three-hour lead and would be a lie on a snapshot
    taken to represent a close.
    """
    stamp = pd.to_datetime(str(provenance.get("generated_at", "")).strip(), errors="coerce", utc=True)
    return "" if pd.isna(stamp) else stamp.isoformat()


def snapshot_rows(staged_odds: pd.DataFrame, provenance: dict) -> pd.DataFrame:
    """One feed row per staged price, identified and timestamped."""
    empty = pd.DataFrame(columns=list(FEED_COLUMNS))
    when = observed_at(provenance)
    if staged_odds.empty or not when:
        return empty
    required = {"home_team", "away_team", "market", "selection", "american_odds"}
    if not required.issubset(staged_odds.columns):
        return empty
    frame = staged_odds.copy()
    frame["observed_at"] = when
    frame["provider_event_id"] = frame.get("notes", pd.Series("", index=frame.index)).map(event_id_from_notes)
    frame["book"] = frame.get("book", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip()
    frame["american_odds"] = pd.to_numeric(frame["american_odds"], errors="coerce")
    frame = frame.dropna(subset=["american_odds"])
    if "date" not in frame.columns:
        frame["date"] = ""
    return frame[list(FEED_COLUMNS)].reset_index(drop=True)


def load_feed(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(columns=list(FEED_COLUMNS))
    try:
        frame = pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=list(FEED_COLUMNS))
    for column in FEED_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[list(FEED_COLUMNS)]


def append_snapshot(feed: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    """Feed plus snapshot, with repeat observations dropped.

    Append-only by construction: an existing row is never replaced, so a
    snapshot that runs twice adds nothing and a retry cannot lose history.
    """
    if snapshot.empty:
        return feed
    combined = pd.concat([feed, snapshot], ignore_index=True)
    combined = combined.drop_duplicates(subset=list(IDENTITY), keep="first")
    return combined.sort_values(["observed_at", "provider_event_id", "market", "selection", "book"]).reset_index(drop=True)


def save_feed(feed: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    feed.to_csv(path, index=False)
    return path
