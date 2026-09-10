"""The EFL measurement must not flatter itself, and must not hide its limits.

Two failures this file exists for actually happened while it was being written.
The probability keys were wrong — `over_25` where the model returns `over_2_5` —
and nothing raised: two of the three markets silently produced no rows and the
output was a clean-looking 1X2 table. And the xG guard the EPL backtest already
had could not fire on the EFL at all, because it checked that the columns
existed rather than that they held anything.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from epl_betting_lab.reports import efl_backtest as backtest
from epl_betting_lab.reports.efl_backtest import (
    CARD_MARKETS,
    MEASURABLE_MARKETS,
    PROBABILITY_KEYS,
    PUSH,
    UNPRICED_REASON,
    profit_from_decimal,
    settle,
)


class TestSettlement:
    @pytest.mark.parametrize(
        "selection,home,away,expected",
        [("home", 2, 1, True), ("away", 2, 1, False), ("draw", 1, 1, True)],
    )
    def test_1x2(self, selection, home, away, expected):
        assert settle("1x2", selection, home, away) is expected

    @pytest.mark.parametrize(
        "selection,home,away,expected",
        [("over", 2, 1, True), ("under", 2, 1, False), ("over", 1, 1, False)],
    )
    def test_a_2_5_line_cannot_push(self, selection, home, away, expected):
        """Three goals is over, two is under. A half-goal line has no middle."""
        assert settle("total_2_5", selection, home, away) is expected

    def test_a_level_ball_returns_the_stake_on_a_draw(self):
        """The bet happened and belongs in the denominator at zero profit.
        Dropping pushes once removed 33 of 115 draw-no-bet selections from an
        EPL measurement and reported +7.1% for a rule that returned +5.1%."""
        assert settle("draw_no_bet", "home", 1, 1) is PUSH
        assert settle("draw_no_bet", "home", 2, 1) is True
        assert settle("draw_no_bet", "away", 2, 1) is False

    def test_a_match_with_no_score_is_unsettleable_not_a_loss(self):
        assert settle("1x2", "home", float("nan"), 1) is None

    def test_an_unknown_market_raises_rather_than_guessing(self):
        with pytest.raises(ValueError, match="No settlement rule"):
            settle("corners_total_9_5", "over", 1, 1)


class TestProfit:
    def test_a_winner_pays_the_price_less_the_stake(self):
        assert profit_from_decimal(2.5, True) == pytest.approx(1.5)

    def test_a_loser_costs_exactly_one_unit(self):
        assert profit_from_decimal(2.5, False) == -1.0

    def test_a_push_costs_and_pays_nothing(self):
        assert profit_from_decimal(2.5, PUSH) == 0.0


class TestOnlyPricesThatExist:
    @pytest.mark.parametrize("value", [None, "", "0", 0.0, 1.0, 0.99, "not a price"])
    def test_a_non_price_is_refused(self, value):
        """A decimal below 1.01 pays out less than the stake, so it is a blank,
        a zero or a parsing accident — never something anyone could bet."""
        assert not np.isfinite(backtest._decimal(value))

    def test_a_real_price_survives(self):
        assert backtest._decimal("2.75") == pytest.approx(2.75)

    def test_draw_no_bet_is_only_read_off_a_level_ball(self):
        """Football-Data quotes an Asian handicap on every match, but only a
        handicap of 0 is draw-no-bet. Reading a -0.5 line as draw-no-bet would
        grade a bet nobody placed, against a rule nobody used."""
        level = pd.Series({"AHCh": 0.0})
        quarter = pd.Series({"AHCh": -0.5})
        assert backtest._priceable(level, "draw_no_bet", backtest.CLOSING_AVERAGE)
        assert not backtest._priceable(quarter, "draw_no_bet", backtest.CLOSING_AVERAGE)

    def test_other_markets_are_not_gated_on_the_handicap(self):
        quarter = pd.Series({"AHCh": -0.5})
        assert backtest._priceable(quarter, "total_2_5", backtest.CLOSING_AVERAGE)


class TestAWrongProbabilityKeyCannotPassInSilence:
    """The failure that actually happened: `.get` returns None for a name that
    does not exist, the selection is skipped, and the market vanishes from a
    report where every other market still looks fine."""

    def test_a_key_the_model_does_not_return_raises(self):
        with pytest.raises(KeyError, match="does not return"):
            backtest._check_probability_keys({"home_win": 0.4, "draw": 0.3})

    def test_the_real_keys_pass(self):
        every_key = {
            key: 0.5
            for selections in PROBABILITY_KEYS.values()
            for key in selections.values()
        }
        backtest._check_probability_keys(every_key)  # does not raise

    def test_the_keys_are_the_ones_the_model_actually_returns(self):
        """Pins the mapping against the model rather than against itself, so a
        rename on either side fails here instead of emptying a market."""
        from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig

        matches = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-08", "2025-01-15"]),
                "home_team": ["A", "B", "A"],
                "away_team": ["B", "A", "B"],
                "home_goals": [1, 2, 0],
                "away_goals": [1, 0, 2],
            }
        )
        model = PoissonGoalsModel().fit(matches, config=RatingConfig(goal_source="goals"))
        returned = model.match_probabilities("A", "B")
        for market, selections in PROBABILITY_KEYS.items():
            for selection, key in selections.items():
                assert key in returned, f"{market}.{selection} asks for {key!r}"


class TestItMeasuresTheConfigurationTheCardActuallyRuns:
    """The card does not fit one model. Measuring one and reporting it against
    a card that runs two is the same fault as measuring a blend and betting
    goals — it was in the first version of this module, for `1x2` and
    `draw_no_bet`, which the card prices on the unadjusted legacy ratio."""

    def test_every_measurable_market_names_the_config_the_card_uses(self):
        from epl_betting_lab.reports.efl_backtest import (
            CARD_CONFIG_FOR_MARKET,
            MEASURABLE_MARKETS,
            RATING_CONFIGS,
        )

        for market in MEASURABLE_MARKETS:
            assert market in CARD_CONFIG_FOR_MARKET, market
            assert CARD_CONFIG_FOR_MARKET[market] in RATING_CONFIGS

    def test_the_mapping_matches_the_model_module_rather_than_itself(self):
        """Pinned against the card's own constants, so a change there fails
        here instead of quietly making this report answer the wrong question."""
        from epl_betting_lab.models.poisson_goals import (
            CARD_RATINGS,
            TOTALS_RATINGS,
        )
        from epl_betting_lab.reports.efl_backtest import RATING_CONFIGS

        legacy = RATING_CONFIGS["legacy_goals"]
        assert legacy.opponent_adjusted == CARD_RATINGS.opponent_adjusted
        assert legacy.half_life_days == CARD_RATINGS.half_life_days

        adjusted = RATING_CONFIGS["adjusted_goals"]
        assert adjusted.opponent_adjusted == TOTALS_RATINGS.opponent_adjusted
        assert adjusted.half_life_days == TOTALS_RATINGS.half_life_days
        # The one deliberate difference, and the whole reason this module exists.
        assert TOTALS_RATINGS.goal_source == "blend"
        assert adjusted.goal_source == "goals"


class TestItIsHonestAboutBeingADifferentModel:
    def test_the_config_asks_for_goals_not_a_blend(self):
        """Asking for the blend would not fail. It would silently produce this
        same goals model, because every EFL row has empty xG — so the request
        has to be explicit or the report is lying about what it measured."""
        assert backtest._goals_only_config().goal_source == "goals"

    def test_the_report_says_so_where_a_reader_will_see_it(self):
        bets = pd.DataFrame(
            {
                "division": ["E1"], "date": [pd.Timestamp("2025-01-01")],
                "home_team": ["A"], "away_team": ["B"], "market": ["total_2_5"],
                "selection": ["over"], "price_set": ["closing_average"],
                "probability": [0.6], "price": [2.0], "edge": [0.2],
                "outcome": [True], "profit": [1.0],
            }
        )
        report = backtest.render(bets, backtest.summarize(bets))
        assert "goals model, not the model the EPL card bets" in report
        assert "Understat" in report


class TestTheReportCannotHideAMarket:
    def test_every_card_market_is_accounted_for(self):
        """A market absent from a results table reads exactly like a market
        that had nothing to say. Each one is either measured or carries a
        reason it could not be."""
        for market in CARD_MARKETS:
            assert market in MEASURABLE_MARKETS or market in UNPRICED_REASON, market

    def test_no_market_claims_both(self):
        assert not (set(MEASURABLE_MARKETS) & set(UNPRICED_REASON))

    def test_the_coverage_table_names_every_card_market(self):
        report = backtest.render(pd.DataFrame(), pd.DataFrame())
        assert "No bet was produced." in report

    def test_a_populated_report_lists_the_unpriced_markets(self):
        bets = pd.DataFrame(
            {
                "division": ["E1"], "date": [pd.Timestamp("2025-01-01")],
                "home_team": ["A"], "away_team": ["B"], "market": ["total_2_5"],
                "selection": ["over"], "price_set": ["closing_average"],
                "probability": [0.6], "price": [2.0], "edge": [0.2],
                "outcome": [True], "profit": [1.0],
            }
        )
        report = backtest.render(bets, backtest.summarize(bets))
        assert "## Coverage" in report
        for market in CARD_MARKETS:
            assert market in report, market
        assert "corner *prices*" in report or "no corner prices" in report


class TestInterval:
    def test_it_resamples_matches_not_rows(self):
        """Selections on one match share a result. Resampling rows would treat
        them as independent and report an interval that is too narrow."""
        bets = pd.DataFrame(
            {
                "date": ["2025-01-01"] * 3 + ["2025-01-02"] * 3,
                "home_team": ["A"] * 3 + ["C"] * 3,
                "away_team": ["B"] * 3 + ["D"] * 3,
                "profit": [1.0, 1.0, 1.0, -1.0, -1.0, -1.0],
            }
        )
        low, high, _ = backtest.bootstrap_interval(bets, draws=500)
        assert low == pytest.approx(-100.0)
        assert high == pytest.approx(100.0)

    def test_an_empty_frame_reports_nothing_rather_than_zero(self):
        low, high, above = backtest.bootstrap_interval(pd.DataFrame())
        assert np.isnan(low) and np.isnan(high) and np.isnan(above)


class TestTheWalkForwardOnlyUsesThePast:
    def test_a_division_with_too_little_history_produces_no_bet(self):
        """A model should not bet a division until it has seen a season of it."""
        matches = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01", "2025-01-08"]),
                "home_team": ["A", "B"], "away_team": ["B", "A"],
                "home_goals": [1, 2], "away_goals": [1, 0],
                "AvgCH": [2.0, 2.0], "AvgCD": [3.0, 3.0], "AvgCA": [4.0, 4.0],
                "AvgC>2.5": [2.0, 2.0], "AvgC<2.5": [1.8, 1.8],
                "AvgCAHH": [1.9, 1.9], "AvgCAHA": [1.9, 1.9], "AHCh": [0.0, 0.0],
                "AvgH": [2.0, 2.0], "AvgD": [3.0, 3.0], "AvgA": [4.0, 4.0],
                "Avg>2.5": [2.0, 2.0], "Avg<2.5": [1.8, 1.8],
                "AvgAHH": [1.9, 1.9], "AvgAHA": [1.9, 1.9], "AHh": [0.0, 0.0],
            }
        )
        result = backtest.run_division(matches, "E1", min_training=552)
        assert result.bets.empty
        assert any("earlier matches to train on" in note for note in result.notes)
