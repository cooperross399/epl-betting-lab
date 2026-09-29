"""What the schedule costs the provider, in one place — and what it actually costs.

Those are two different numbers, and conflating them is how this went wrong.

THE MODEL. Multiply each scheduled workflow's firings by its measured cost per
firing. It is useful for deciding a cadence, because a cadence is exactly the
thing it varies. It is a FLOOR and nothing more: it can only count consumers
someone remembered to put in it. It has now failed that way twice — first by
omitting the Closing Snapshot entirely, which is the larger half of the bill,
and then by carrying a per-refresh cost of 62 when the measured figure was 122.
Both errors pointed the same way. A model of named consumers understates.

THE OBSERVED RATE. Read the provider's own counter across days and divide. It
cannot omit a consumer, because it never enumerates one — manual dispatches and
runs from a laptop are in it whether or not anybody modelled them. This is what
the card quotes, because the card is answering "when does this stop working",
and the honest answer to that has to include the spending nobody wrote down.

The gap between them is large and is not noise: the model says about 760 a day
and the counter says about a thousand. `test_the_model_is_a_floor_not_the_bill`
holds that gap open on purpose.
"""

from __future__ import annotations


#: Measured, not estimated: four consecutive live runs on 2026-09-28/29
#: published 19,540, 19,418, 19,296 and 19,174 remaining — 122 apart each time.
#:
#: It read 62, and 62 was right when it was written. The competitions added
#: since roughly doubled the cost and the constant did not move. Before that it
#: read 15 against a truth of 62. Re-measure it from the card's own quota line
#: whenever a competition or a market is added; two readings a run apart do it.
REQUESTS_PER_MATCHDAY_RUN = 122

#: Estimated, and less firmly than the figure above — say so rather than round
#: it and look certain.
#:
#: Taken from windows between two published cards containing a known number of
#: snapshots, with the refreshes in that window subtracted at 122 each: 481,
#: 504 and 522 across the last week of September 2026. Earlier windows in the
#: same month give 280 to 288, and the step up coincides with the competitions
#: that doubled the refresh cost, so the recent cluster is the live one.
#:
#: Anything in that 481-522 band supports the same conclusion — the scheduled
#: workflows alone are over the plan — so the imprecision does not change a
#: decision. It was 338 here, from a single differenced observation, and 338 is
#: the one value in the neighbourhood that made the schedule look affordable.
REQUESTS_PER_CLOSING_SNAPSHOT = 500

#: How often each fires. Pinned to the workflow files by
#: `test_the_cost_model_matches_the_schedule_it_models`.
MATCHDAY_RUNS_PER_WEEK = 15
CLOSING_SNAPSHOTS_PER_WEEK = 5

#: The whole account's burn, straight off the counter: 16,439 requests between
#: 2026-09-12 07:23 and 2026-09-28 18:17 UTC, 16.45 days, 999 a day. The last
#: 5.5 days of that window give 1,117.
#:
#: Individual days run from 321 to 2,019 — the high ones are days of heavy
#: interactive work, which will not recur every month, and the low ones are
#: days the Closing Snapshot barely fired. The average over two weeks is the
#: figure that survives both, and a number offered to reassure someone should
#: not be the optimistic one.
#:
#: Re-measure by differencing the quota line across the card feed's history.
#:
#: STALE BY DESIGN until it is re-measured. This figure was taken while the
#: Closing Snapshot fired seven times a week; it now fires five, which should
#: take about 143 a day out and land near 857. That arithmetic is deliberately
#: NOT applied here. The whole point of this constant is that it is read off
#: the counter rather than computed from a model of who is spending — adjusting
#: it by model arithmetic would quietly turn it back into the thing it replaced.
#: It stays at the last measured value, which errs short, until a fortnight of
#: the new cadence can be differenced.
OBSERVED_REQUESTS_PER_DAY = 1_000

#: The plan in use, as the provider reports it: the counter stood at 20,000
#: with nothing used, and the operating model doc says it resets monthly.
MONTHLY_REQUEST_ALLOWANCE = 20_000

#: Below this much runway the card stops reporting and starts arguing. Quota
#: running dry is one of the ways this automation stops without producing a
#: red X, so it has to be said in words rather than left in a table cell.
LOW_RUNWAY_DAYS = 14

#: Weeks in a month, for turning a weekly burn into a monthly one.
WEEKS_PER_MONTH = 4.35

#: Days in a month, for the same on the observed rate.
DAYS_PER_MONTH = 30.4


def scheduled_weekly_requests() -> int:
    """The floor: one week of the two workflows that are on a schedule."""
    return (
        MATCHDAY_RUNS_PER_WEEK * REQUESTS_PER_MATCHDAY_RUN
        + CLOSING_SNAPSHOTS_PER_WEEK * REQUESTS_PER_CLOSING_SNAPSHOT
    )


def scheduled_monthly_requests() -> float:
    """The same floor over a month, to compare against the allowance."""
    return scheduled_weekly_requests() * WEEKS_PER_MONTH


def observed_monthly_requests() -> float:
    """What the counter says a month of this configuration costs."""
    return OBSERVED_REQUESTS_PER_DAY * DAYS_PER_MONTH


def days_of_runway(remaining: int) -> int:
    """How many days `remaining` requests buys at the observed burn.

    Days, and measured rather than modelled. The card used to say "about 309
    more runs", which was Matchday Refresh runs at half their real cost, with
    no way for a reader to know that a second workflow was spending from the
    same account at four times the rate. Both the unit and the arithmetic hid
    the same thing.
    """
    if OBSERVED_REQUESTS_PER_DAY <= 0:
        raise ValueError("A configuration that spends nothing has no runway.")
    return int(remaining // OBSERVED_REQUESTS_PER_DAY)
