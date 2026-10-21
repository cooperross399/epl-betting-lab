"""The runway the card quotes has to be the runway the account has.

Four defects sat in this arithmetic at once, and every one of them pointed the
same way — the card claimed more headroom than existed:

  * the per-refresh cost was 62 against a measured 122;
  * the Closing Snapshot was not counted at all, then counted at 338 against a
    measured 481 to 522;
  * the figure was expressed in Matchday Refresh runs, a unit that cannot
    express a second workflow spending from the same account;
  * and the whole thing was modelled from named consumers, so manual and local
    runs — about a quarter of the real spend — were invisible by construction.

Together they turned about nineteen days into "about 309 more runs". Each test
below pins one of them.
"""

from __future__ import annotations

import pytest

from epl_betting_lab.providers import request_budget
from epl_betting_lab.providers.request_budget import (
    CLOSING_SNAPSHOTS_PER_WEEK,
    MATCHDAY_RUNS_PER_WEEK,
    MONTHLY_REQUEST_ALLOWANCE,
    OBSERVED_REQUESTS_PER_DAY,
    REQUESTS_PER_CLOSING_SNAPSHOT,
    REQUESTS_PER_MATCHDAY_RUN,
    days_of_runway,
    observed_monthly_requests,
    scheduled_monthly_requests,
    scheduled_weekly_requests,
)

#: The live reading on 2026-10-19, kept as the worked example so the numbers in
#: these tests are ones the account actually held. The 2026-09-29 reading,
#: 19,174, gave nineteen days at the rate measured then.
LIVE_REMAINING = 66_653


def test_the_scheduled_floor_counts_both_workflows() -> None:
    """Dropping either term is the defect this module was written for."""
    refreshes = MATCHDAY_RUNS_PER_WEEK * REQUESTS_PER_MATCHDAY_RUN
    snapshots = CLOSING_SNAPSHOTS_PER_WEEK * REQUESTS_PER_CLOSING_SNAPSHOT

    assert scheduled_weekly_requests() == refreshes + snapshots
    # The snapshot was the larger half until Tuesday and Wednesday runs were
    # added on 2026-10-21; they are now about even, which is the point: the
    # snapshot is far too big a share of the bill to leave out.
    assert snapshots > 0.9 * refreshes


def test_the_runway_is_what_the_live_account_actually_held() -> None:
    """Eighteen days, not 66.

    The card printed "about 66 days" on 2026-10-19 because it still divided by
    the 1,000 a day measured in September. The counter had fallen 33,020 in
    the nine days before. Only the counter's own rate gives 18.
    """
    assert days_of_runway(LIVE_REMAINING) == 18


def test_the_runway_does_not_come_from_the_schedule_model() -> None:
    """A modelled runway is the optimistic one, every time.

    The model cannot see a manual dispatch or a script run from a laptop, so
    it will always quote a longer life than the account has. Named for the
    difference rather than the mechanism, so a future reader sees the size of
    it: 25 modelled days against 19 real ones.
    """
    modelled = LIVE_REMAINING // (scheduled_monthly_requests() / 30.4)

    assert modelled > days_of_runway(LIVE_REMAINING)


def test_counting_only_refreshes_would_flatter_the_reader() -> None:
    """Named so the margin of the old error is on the record, not just the fix."""
    refresh_only_days = LIVE_REMAINING // (
        MATCHDAY_RUNS_PER_WEEK * REQUESTS_PER_MATCHDAY_RUN / 7
    )

    assert refresh_only_days > 3 * days_of_runway(LIVE_REMAINING)


def test_the_schedule_is_inside_the_plan() -> None:
    """The scheduled floor has to fit the plan with room for everything else.

    This asserted the overage until 2026-09-29, when Cooper cut the snapshot
    from seven firings a week to five against a 20,000 plan. The plan is
    100,000 from October 2026, and the schedule, Tuesday and Wednesday
    included, is under a quarter of it. The rest is what the counter shows
    going to props, team totals and interactive work.
    """
    weekly_allowance = MONTHLY_REQUEST_ALLOWANCE / request_budget.WEEKS_PER_MONTH

    assert scheduled_monthly_requests() < MONTHLY_REQUEST_ALLOWANCE / 4
    assert scheduled_weekly_requests() < weekly_allowance


def test_the_account_still_outspends_the_plan_even_though_the_schedule_does_not() -> None:
    """A fitting schedule is not a fitting account, and the card says so.

    The counter read about a thousand a day while the snapshot still fired
    seven times; the cut takes roughly 143 of that. What is left over the
    allowance is interactive work — the measured daily rate spans 321 on a
    quiet day and 2,019 on a working one — which no cron change reaches.

    Kept asserted because the card's runway comes from the counter, and a
    reader who saw the schedule brought inside the plan would otherwise assume
    the runway problem went with it.
    """
    assert observed_monthly_requests() > scheduled_monthly_requests()
    assert observed_monthly_requests() > MONTHLY_REQUEST_ALLOWANCE


def test_an_empty_account_buys_no_days() -> None:
    assert days_of_runway(0) == 0


def test_a_configuration_that_spends_nothing_is_refused_not_divided_by() -> None:
    """A ZeroDivisionError inside a card renderer loses the whole card."""
    saved = OBSERVED_REQUESTS_PER_DAY
    request_budget.OBSERVED_REQUESTS_PER_DAY = 0
    try:
        with pytest.raises(ValueError):
            days_of_runway(1000)
    finally:
        request_budget.OBSERVED_REQUESTS_PER_DAY = saved
