"""Every prose description of the cadence had drifted from the crons.

The workflow's own header — the block CLAUDE.md sends a session to as the
authority on how the card is made — said one run a day against three, gave a
five-row table with one time per day and the wrong Thursday time, claimed
"every day's last trigger is 10:30 UTC" for a trigger that had been removed,
priced a run at 15 credits against a measured 122, and called the result
"about a ninth of the allowance" when this workflow alone is about two fifths
of it. Three more copies said "five times a week" and one said ten.

Every error ran the same way: it made adding a market or a competition look
cheaper than it is, which is the decision the header exists to inform and the
change that doubled the per-run cost last time.

So the table is not checked for being present. It is rebuilt from the crons
and compared.
"""

from __future__ import annotations

import re

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.providers.request_budget import (
    MATCHDAY_RUNS_PER_WEEK,
    REQUESTS_PER_MATCHDAY_RUN,
    WEEKS_PER_MONTH,
)

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"

#: cron day-of-week -> the name the header uses.
DAYS = {"4": "Thursday", "5": "Friday", "6": "Saturday", "0": "Sunday", "1": "Monday"}


def _header() -> str:
    """The comment block above `on:`, with runs of spaces collapsed.

    Collapsed because the table is aligned with padding, and a guard that
    depends on the padding fails on a reformat rather than on a drift.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    head = text.split("\non:", 1)[0]
    return re.sub(r"[ \t]+", " ", head)


def _times_by_day() -> dict[str, list[str]]:
    times: dict[str, list[str]] = {}
    for minute, hour, day in re.findall(
        r'- cron: "(\d+) (\d+) \* \* (\d)"', WORKFLOW.read_text(encoding="utf-8")
    ):
        times.setdefault(DAYS[day], []).append(f"{int(hour):02d}:{int(minute):02d}")
    return {day: sorted(values) for day, values in times.items()}


def test_the_header_describes_the_schedule_it_sits_above() -> None:
    """Rebuilt from the crons, not read for plausibility."""
    header = _header()

    for day, times in _times_by_day().items():
        expected = f"{day} {', '.join(times)} UTC"
        assert expected in header, f"the header does not say: {expected}"


def test_the_header_states_the_measured_per_run_cost() -> None:
    header = _header()

    assert f"about {REQUESTS_PER_MATCHDAY_RUN} requests a run" in header
    monthly = MATCHDAY_RUNS_PER_WEEK * REQUESTS_PER_MATCHDAY_RUN * WEEKS_PER_MONTH
    assert f"about {monthly:,.0f} a month" in header


def test_the_header_does_not_still_carry_a_dropped_trigger() -> None:
    """10:30 came off every match day and the header still promised it.

    Named for the figure rather than the rule, because a reader checking the
    cadence against this file would have found a time that no longer fires.
    """
    header = _header()

    assert "last trigger is 10:30" not in header
    assert "10:30 UTC" not in header.split("A 10:30 trigger was dropped")[0]


def test_every_prose_copy_of_the_firing_count_agrees_with_the_crons() -> None:
    """Four documents said five or ten. The crons say fifteen.

    A session asked whether the schedule can afford another market follows
    CLAUDE.md's reading order, takes five runs a week at 122, and reports
    about 17,000 credits of headroom against a real figure nearer 1,200.
    """
    words = {5: "five", 10: "ten", 15: "fifteen"}
    expected = words[MATCHDAY_RUNS_PER_WEEK]
    stale = {word for count, word in words.items() if count != MATCHDAY_RUNS_PER_WEEK}

    for relative in (
        "CLAUDE.md",
        "docs/soccer_scheduled_tasks_bridge.md",
        "src/epl_betting_lab/reports/card_notification.py",
    ):
        text = re.sub(r"\s+", " ", (PROJECT_ROOT / relative).read_text(encoding="utf-8"))
        claims = re.findall(r"(\w+) (?:times|triggers|runs) a week", text)
        assert claims, f"{relative} no longer states a firing count; re-pin this"
        for claim in claims:
            assert claim not in stale, (
                f"{relative} says {claim!r} a week; the crons say {expected}"
            )
        assert expected in claims, f"{relative} does not state {expected}"
