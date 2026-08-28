"""The fixture round a card is about.

`data/manual/upcoming_fixtures.csv` holds more than one round at a time, so a
report that treats the whole file as "this week" overstates its coverage. This
module is the single definition of the window that separates them, and every
report imports it so they cannot disagree.

The window used to be two hardcoded dates — the opening round, 2026-08-21
through 2026-08-24. That was correct for exactly one week. Once the season
moved on, every provider price fell outside a window that had stopped moving,
so every market was reported `unavailable` and every card came back **Blocked**
with no fixture in range. Nothing was broken and nothing said so: the provider
fetch, the mapping and the completeness checks all passed, and the card was
empty because the calendar had been left behind.

So the window is now derived from the fixtures in hand rather than written
down. It is the next round still to be played: the earliest date on or after
today, extended through every date that follows it closely enough to belong to
the same round. When nothing is upcoming — an out-of-season file, or a frame of
finished matches — it falls back to the last round present, so a report about
past fixtures still describes the round it is actually about.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


#: Longest gap between two match dates that still belongs to one round. A round
#: is usually Friday to Monday, and the next one is a week behind it, so three
#: days separates rounds without splitting a Saturday-to-Tuesday spread.
MAX_ROUND_GAP = timedelta(days=3)


def parse_dates(values: object) -> pd.Series:
    """Parse a date column into naive dates, leaving unparseable rows as NaT."""
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return parsed.dt.tz_convert(None).dt.normalize()


def _match_dates(values: object) -> list[date]:
    """Every distinct, readable match date in ascending order."""
    parsed = parse_dates(values).dropna()
    return sorted({stamp.date() for stamp in parsed})


def _rounds(dates: list[date]) -> list[tuple[date, date]]:
    """Split ascending dates into rounds wherever the gap is too wide."""
    if not dates:
        return []
    rounds: list[tuple[date, date]] = []
    start = previous = dates[0]
    for current in dates[1:]:
        if current - previous > MAX_ROUND_GAP:
            rounds.append((start, previous))
            start = current
        previous = current
    rounds.append((start, previous))
    return rounds


def selected_window(
    values: object, *, today: date | None = None
) -> tuple[date, date] | None:
    """First and last date of the round these fixtures are about.

    `None` when no date can be read at all, which callers report as an empty
    window rather than silently matching everything.
    """
    rounds = _rounds(_match_dates(values))
    if not rounds:
        return None
    moment = today or date.today()
    for start, end in rounds:
        if end >= moment:
            return start, end
    # Nothing upcoming: describe the last round present rather than nothing.
    return rounds[-1]


def _column(frame: pd.DataFrame) -> object | None:
    if frame.empty or "date" not in frame.columns:
        return None
    return frame["date"]


def selected_window_label(values: object, *, today: date | None = None) -> str:
    """The window as it is written in reports, e.g. "2026-08-28 through 2026-08-30"."""
    window = selected_window(values, today=today)
    if window is None:
        return "no dated fixtures"
    start, end = window
    return f"{start.isoformat()} through {end.isoformat()}"


def frame_window_label(frame: pd.DataFrame, *, today: date | None = None) -> str:
    """`selected_window_label` for a frame that may be empty or undated."""
    column = _column(frame)
    if column is None:
        return "no dated fixtures"
    return selected_window_label(column, today=today)


def in_selected_window(values: object, *, today: date | None = None) -> pd.Series:
    """Boolean mask of the rows falling inside the selected round."""
    parsed = parse_dates(values)
    window = selected_window(values, today=today)
    if window is None:
        return pd.Series(False, index=parsed.index, dtype=bool)
    start, end = window
    return parsed.between(pd.Timestamp(start), pd.Timestamp(end))


def filter_to_selected_window(
    frame: pd.DataFrame, *, today: date | None = None
) -> pd.DataFrame:
    """Return only the rows inside the selected round."""
    column = _column(frame)
    if column is None:
        return frame.iloc[0:0]
    return frame[in_selected_window(column, today=today)]


def outside_selected_window(
    frame: pd.DataFrame, *, today: date | None = None
) -> pd.DataFrame:
    """Return the rows that fall outside the selected round."""
    column = _column(frame)
    if column is None:
        return frame.iloc[0:0]
    return frame[~in_selected_window(column, today=today)]


def describe_window(values: object = None, *, today: date | None = None) -> str:
    label = selected_window_label(values, today=today) if values is not None else "none"
    return (
        f"Selected round: {label} (inclusive). Fixtures outside this window "
        "belong to a different round."
    )
