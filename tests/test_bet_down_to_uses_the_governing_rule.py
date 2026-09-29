"""The card recommended a bet at a price its own advice said was too short.

"Bet down to" is computed as `probability - min_calibrated_edge(...)`: the
price at which the LIFT falls to the market's floor. For `total_2_5` the
anchored rule replaced that floor — what decides whether the row is staked
is the edge against the POSTED price, since `_confidence_tier` returns
Pass/Avoid at edge <= 0.

So a totals row at p = 0.58 recommended at −130 printed "bet down to −108",
a limit −130 has already passed. A reader following the instruction would
decline the bet the card had just made, in the same row.

The invariant this pins is the one that was violated: a price the card
recommends may not be shorter than the limit the card prints beside it.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.models.value import fair_american_from_prob
from epl_betting_lab.reports.thursday_best_bets import MIN_EDGE, _bet_down_to
from epl_betting_lab.models.calibration import min_calibrated_edge


def _row(market: str, selection: str, probability: float, odds: float) -> pd.Series:
    return pd.Series(
        {
            "market": market,
            "selection": selection,
            "calibrated_model_prob": probability,
            "american_odds": odds,
        }
    )


def _implied(american: float) -> float:
    return (
        -american / (-american + 100) if american < 0 else 100 / (american + 100)
    )


class TestTheLimitIsNotShorterThanTheRecommendedPrice:
    @pytest.mark.parametrize("selection", ["over", "under"])
    @pytest.mark.parametrize("probability", [0.55, 0.58, 0.62, 0.70])
    def test_a_staked_totals_row_never_contradicts_its_own_advice(
        self, selection, probability
    ) -> None:
        """Every price the anchored rule would stake, across the band.

        A single worked example passes as soon as that example stops being
        representative; the invariant holds for the whole range or it is
        not an invariant.
        """
        # The longest price the rule still stakes is where edge reaches zero.
        worst = fair_american_from_prob(probability)
        row = _row("total_2_5", selection, probability, worst)
        limit = _bet_down_to(row)

        assert limit != ""
        assert _implied(float(limit)) <= probability + 1e-9, (
            f"the printed limit {limit} is shorter than fair odds at "
            f"p={probability}, so the card recommends past its own advice"
        )

    def test_the_control_the_lift_floor_would_have_contradicted_it(self) -> None:
        """The defect, shown rather than described."""
        probability = 0.58
        floor = min_calibrated_edge("total_2_5", "over", MIN_EDGE)
        old_limit = fair_american_from_prob(probability - floor)

        assert floor > 0
        assert _implied(old_limit) < probability, (
            "the old limit was shorter than fair, so a row staked at fair "
            "odds already sat beyond it"
        )
        assert _implied(float(_bet_down_to(_row("total_2_5", "over", probability, -130)))) > (
            _implied(old_limit)
        )


class TestEveryOtherMarketKeepsItsFloor:
    """The anchored rule is the exception, not a new default.

    For the lift-gated markets the floor IS what decides the stake, so the
    limit must still come from it — a blanket change to fair odds would
    advise betting rows the card would refuse.
    """

    @pytest.mark.parametrize(
        "market,selection", [("btts", "yes"), ("double_chance", "home_or_draw")]
    )
    def test_the_limit_still_comes_from_the_calibrated_floor(
        self, market, selection
    ) -> None:
        probability = 0.62
        floor = min_calibrated_edge(market, selection, MIN_EDGE)
        expected = round(fair_american_from_prob(probability - floor))

        assert _bet_down_to(_row(market, selection, probability, -110)) == expected
        assert floor > 0, "this market has no floor, so the test proves nothing"
