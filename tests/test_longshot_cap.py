"""The model is not trusted at very long prices.

There was a cap on the short side — do not lay heavy juice — and none on the
long side. The backtest shows what that cost:

    +400..+600    83 bets    +6.4% ROI   19.3% win rate
    +600..+900    34 bets   -22.3% ROI    8.8% win rate
    +900 and up   12 bets  -100.0% ROI    0.0% win rate

Twelve claimed chances of roughly one in ten, none of which happened. An
independent-Poisson model puts too much mass in the tail of the scoreline
distribution, so it overstates exactly these outcomes, and the market's own
favourite-longshot bias prices them short on top of that.
"""

from __future__ import annotations

import pytest

from epl_betting_lab.config import MAX_DEFAULT_JUICE, MAX_DEFAULT_PRICE
from epl_betting_lab.models.value import grade_edge


class TestTheCap:
    def test_a_price_inside_the_cap_can_be_bet(self) -> None:
        assert grade_edge(0.30, 600.0)["status"] == "BETTABLE"

    def test_a_longer_price_is_refused(self) -> None:
        assert grade_edge(0.30, 700.0)["status"] == "PASS - price too long"

    def test_the_refusal_names_its_reason(self) -> None:
        """Distinct from a juice refusal and from an ordinary pass."""
        statuses = {
            grade_edge(0.30, 1700.0)["status"],
            grade_edge(0.90, -400.0)["status"],
            grade_edge(0.20, 200.0)["status"],
        }
        assert len(statuses) == 3

    def test_a_huge_apparent_edge_does_not_override_it(self) -> None:
        """The longer the price, the less the claimed edge is worth."""
        graded = grade_edge(0.60, 2000.0)

        assert graded["edge"] > 0.5
        assert graded["status"] == "PASS - price too long"

    def test_the_short_side_cap_still_works(self) -> None:
        assert grade_edge(0.95, -400.0)["status"] == "PASS - too much juice"

    def test_the_cap_can_be_overridden_per_call(self) -> None:
        graded = grade_edge(0.30, 700.0, max_default_price=800)

        assert graded["status"] == "BETTABLE"

    def test_it_can_be_disabled_entirely(self) -> None:
        """So a study can measure what the cap is costing."""
        graded = grade_edge(0.30, 5000.0, max_default_price=None)

        assert graded["status"] != "PASS - price too long"

    def test_both_caps_are_configured_in_one_place(self) -> None:
        assert MAX_DEFAULT_JUICE == -160
        assert MAX_DEFAULT_PRICE == 600


class TestTheThresholdIsNotFittedToTheSample:
    def test_it_is_not_the_roi_maximising_value(self) -> None:
        """+300 scored better in the backtest and was not chosen.

        The band from +400 to +600 is profitable, so cutting it would fit the
        threshold to the sample rather than to the failure it is meant to
        avoid.
        """
        assert MAX_DEFAULT_PRICE > 300

    def test_it_sits_where_the_win_rate_collapses(self) -> None:
        """Above +600 the observed win rate falls to 8.8%, then to zero."""
        assert MAX_DEFAULT_PRICE == 600

    def test_the_reasoning_is_recorded_with_the_number(self) -> None:
        """A bare constant would be re-tuned by the next person who sees it."""
        from epl_betting_lab.config import PROJECT_ROOT

        source = (PROJECT_ROOT / "src/epl_betting_lab/config.py").read_text(
            encoding="utf-8"
        )
        flat = " ".join(source.split())

        assert "favourite-longshot bias" in flat
        assert "ROI-maximising" in flat
        assert "three of four seasons" in flat
