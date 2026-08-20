"""A lean is information, not a bet.

LEAN fires at a 1.5% modelled edge. That is smaller than this model's own
demonstrated error — calibration found it off by four to fifteen points
depending on the band — and smaller than a typical book margin of four to six
per cent. A threshold below the noise floor cannot be selecting for skill.

Measured: 1X2 leans returned -18.6% over 65 bets, positive in one season of
four. BTTS leans -1.0% over 85. Combined, 150 bets at -8.6%. Not significant
alone, and pointing the same way as the reason to expect it.
"""

from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.thursday_best_bets import (
    LEAN_TIER,
    _confidence_tier,
    _suggested_units,
)


def _row(**over) -> pd.Series:
    base = {
        "section": "Leans",
        "status": "LEAN",
        "market": "1x2",
        "selection": "home",
        "ranking_score": 60.0,
        "calibrated_edge": 0.02,
        "edge": 0.02,
    }
    base.update(over)
    return pd.Series(base)


class TestLeansAreNotStaked:
    def test_a_lean_gets_its_own_tier(self) -> None:
        assert _confidence_tier(_row()) == LEAN_TIER

    def test_that_tier_suggests_no_stake(self) -> None:
        assert _suggested_units(LEAN_TIER) == 0.0

    def test_the_tier_says_so_in_words(self) -> None:
        """It appears on the card, so it has to read as an instruction."""
        assert "no stake" in LEAN_TIER.lower()

    def test_a_lean_no_longer_looks_like_a_c_tier_bet(self) -> None:
        """It used to be tier C, which stakes 0.1 units — a real bet."""
        assert _confidence_tier(_row()) != "C"
        assert _suggested_units("C") > 0

    def test_real_bets_are_untouched(self) -> None:
        assert _suggested_units("A") == 0.5
        assert _suggested_units("B") == 0.25
        assert _suggested_units("C") == 0.1

    def test_a_bettable_pick_still_gets_a_stake(self) -> None:
        tier = _confidence_tier(_row(status="BETTABLE", ranking_score=75.0))

        assert tier == "A"
        assert _suggested_units(tier) == 0.5

    def test_a_pass_is_still_a_pass(self) -> None:
        assert _confidence_tier(_row(status="PASS")) == "Pass/Avoid"

    def test_an_unknown_tier_stakes_nothing(self) -> None:
        """The safe direction for anything unrecognised."""
        assert _suggested_units("something new") == 0.0


class TestTheCardPresentsThemAsUnstaked:
    def test_a_zero_unit_lean_is_split_out_of_the_staked_rows(self) -> None:
        """The card already separates zero-unit rows, so nothing new is needed."""
        from epl_betting_lab.reports.pick_display import split_stakeable

        rows = [
            {"selection": "home", "suggested_units": 0.25},
            {"selection": "draw", "suggested_units": _suggested_units(LEAN_TIER)},
        ]
        stakeable, not_stakeable = split_stakeable(rows)

        assert [r["selection"] for r in stakeable] == ["home"]
        assert [r["selection"] for r in not_stakeable] == ["draw"]
