"""The selected Week 1 fixture window.

`data/manual/upcoming_fixtures.csv` currently holds 20 matches spanning two
rounds (2026-08-21 through 2026-08-30). Week 1 is only the opening round, so
reports that silently treat the whole file as "Week 1" overstate their coverage.

This module is the single definition of that window. Both the Week 1 readiness
report and the provider shadow verifier import it, so they cannot disagree.
"""

from __future__ import annotations

from datetime import date

import pandas as pd


#: Inclusive first/last match date of the opening Week 1 round.
SELECTED_WEEK1_START = date(2026, 8, 21)
SELECTED_WEEK1_END = date(2026, 8, 24)

SELECTED_WEEK1_LABEL = (
    f"{SELECTED_WEEK1_START.isoformat()} through {SELECTED_WEEK1_END.isoformat()}"
)


def parse_dates(values: object) -> pd.Series:
    """Parse a date column into naive dates, leaving unparseable rows as NaT."""
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return parsed.dt.tz_convert(None).dt.normalize()


def in_selected_window(values: object) -> pd.Series:
    """Boolean mask of rows falling inside the selected Week 1 window."""
    parsed = parse_dates(values)
    start = pd.Timestamp(SELECTED_WEEK1_START)
    end = pd.Timestamp(SELECTED_WEEK1_END)
    return parsed.between(start, end)


def filter_to_selected_window(frame: pd.DataFrame) -> pd.DataFrame:
    """Return only the rows inside the selected Week 1 window."""
    if frame.empty or "date" not in frame.columns:
        return frame.iloc[0:0]
    return frame[in_selected_window(frame["date"])]


def outside_selected_window(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the rows that fall outside the selected Week 1 window."""
    if frame.empty or "date" not in frame.columns:
        return frame.iloc[0:0]
    return frame[~in_selected_window(frame["date"])]


def describe_window() -> str:
    return (
        f"Selected Week 1 window: {SELECTED_WEEK1_LABEL} (inclusive). Fixtures "
        "outside this window belong to a later round."
    )
