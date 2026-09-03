"""The backtest must not flatter the card.

Every one of these pins a way this measurement could quietly lie: by grading a
bet against the wrong side, by scoring a price nobody could have taken, by
letting a market through with no rule applied, or by reporting an interval
that treats correlated bets as independent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from epl_betting_lab.reports.derived_market_backtest import (
    PUSH,
    _require_xg,
    _selection_for,
    _settle,
    _settle_corner,
    american_to_profit,
    bootstrap_interval,
    build_backtest,
    load_bettable_prices,
    summarize,
)


class TestSelectionMapping:
    """The provider names sides by club; the card names them by position."""

    @pytest.mark.parametrize(
        "market,name,expected",
        [
            ("btts", "Yes", "yes"),
            ("btts", "No", "no"),
            ("draw_no_bet", "Liverpool", "home"),
            ("draw_no_bet", "Bournemouth", "away"),
            ("double_chance", "Liverpool or Draw", "home_or_draw"),
            ("double_chance", "Bournemouth or Draw", "draw_or_away"),
            ("double_chance", "Bournemouth or Liverpool", "home_or_away"),
        ],
    )
    def test_it_maps_the_side_to_the_right_position(self, market, name, expected):
        assert _selection_for(market, name, "Liverpool", "Bournemouth") == expected

    def test_an_unrecognised_side_is_refused_not_guessed(self):
        """Guessing would grade the home bet against the away result."""
        assert _selection_for("draw_no_bet", "Real Madrid", "Liverpool", "Bournemouth") is None
        assert _selection_for("double_chance", "Anything", "Liverpool", "Bournemouth") is None

    def test_the_draw_side_is_read_from_the_word_not_the_position(self):
        """`Draw or Liverpool` is the same bet as `Liverpool or Draw`."""
        assert (
            _selection_for("double_chance", "Draw or Liverpool", "Liverpool", "Bournemouth")
            == "home_or_draw"
        )


class TestSettlement:
    def _match(self, home_goals, away_goals):
        return pd.Series({"home_goals": home_goals, "away_goals": away_goals})

    def test_btts_settles_on_both_teams_scoring(self):
        assert _settle("btts", "yes", self._match(1, 1)) is True
        assert _settle("btts", "no", self._match(1, 1)) is False
        assert _settle("btts", "no", self._match(2, 0)) is True

    def test_a_drawn_draw_no_bet_is_a_push_not_a_loss(self):
        """A returned stake is neither a win nor a loss - but it IS a bet.

        Dropping pushes removed 33 of 115 draw-no-bet selections from the
        denominator and reported +7.1% for a rule that returned +5.1%.
        """
        assert _settle("draw_no_bet", "home", self._match(1, 1)) is PUSH

    def test_a_corner_total_landing_on_the_line_is_a_push(self):
        row = pd.Series({"selection": "over", "line": 9.5})
        assert _settle_corner(row, pd.Series({"HC": 5, "AC": 5})) is True
        row = pd.Series({"selection": "over", "line": 10.0})
        assert _settle_corner(row, pd.Series({"HC": 5, "AC": 5})) is PUSH

    def test_a_match_with_no_corner_counts_is_unsettleable_not_a_push(self):
        """Conflating the two hid both: a push belongs in the denominator, an
        unsettleable row has to be counted and reported as dropped."""
        row = pd.Series({"selection": "over", "line": 9.5})
        assert _settle_corner(row, pd.Series({"HC": None, "AC": None})) is None

    def test_double_chance_covers_two_of_three_results(self):
        assert _settle("double_chance", "home_or_draw", self._match(0, 0)) is True
        assert _settle("double_chance", "home_or_draw", self._match(0, 1)) is False
        assert _settle("double_chance", "home_or_away", self._match(0, 0)) is False


class TestTheModelMeasuredIsTheModelBet:
    def test_a_frame_without_xg_is_refused(self):
        """BTTS_RATINGS asks for a 70/30 xG blend and PoissonGoalsModel
        silently serves pure goals when the columns are absent, so passing
        load_matches() measured a model the card does not bet - BTTS read
        -1.5% where the real rule returned -10.6%."""
        goals_only = pd.DataFrame({"home_goals": [1], "away_goals": [0]})
        with pytest.raises(ValueError, match="xG blend"):
            _require_xg(goals_only)

    def test_a_frame_with_xg_is_accepted(self):
        with_xg = pd.DataFrame(
            {"home_goals": [1], "away_goals": [0], "home_xg": [1.2], "away_xg": [0.7]}
        )
        _require_xg(with_xg)  # does not raise


class TestOnlyTakeablePrices:
    def _rows(self, book):
        return pd.DataFrame(
            {
                "commence_time": ["2025-08-16T14:00:00Z"],
                "home_team": ["Arsenal"],
                "away_team": ["Chelsea"],
                "market": ["btts"],
                "book": [book],
                "player": [""],
                "selection": ["Yes"],
                "american": [120.0],
            }
        )

    def test_a_price_at_a_book_that_cannot_be_bet_is_dropped(self):
        kept, notes = load_bettable_prices(self._rows("Betsson"))
        assert kept.empty
        assert any("BETTABLE_BOOKS" in note for note in notes)

    def test_a_price_with_no_book_is_dropped_not_defaulted(self):
        """Those rows carry a maximum across every book the provider returned,
        including ones the card may not price - optimistic by construction."""
        kept, notes = load_bettable_prices(self._rows(float("nan")))
        assert kept.empty
        assert any("no book" in note for note in notes)

    def test_a_frame_with_no_book_column_at_all_yields_nothing(self):
        """Fails closed: 'I cannot tell whose price this is' must never mean
        'measure it anyway'."""
        frame = self._rows("FanDuel").drop(columns=["book"])
        kept, notes = load_bettable_prices(frame)
        assert kept.empty
        assert notes

    def test_a_bettable_book_survives(self):
        kept, notes = load_bettable_prices(self._rows("FanDuel"))
        assert len(kept) == 1
        assert notes == []


class TestProfit:
    def test_a_plus_money_winner_pays_the_price(self):
        assert american_to_profit(150, True) == pytest.approx(1.5)

    def test_a_favourite_winner_pays_less_than_a_unit(self):
        assert american_to_profit(-200, True) == pytest.approx(0.5)

    def test_a_loser_costs_exactly_one_unit(self):
        assert american_to_profit(150, False) == -1.0


class TestInterval:
    def test_it_resamples_matches_not_rows(self):
        """Selections on one match share a result. Resampling rows would treat
        them as independent and report an interval that is too narrow."""
        # Six bets, but only two matches, and the two matches disagree utterly.
        bets = pd.DataFrame(
            {
                "date": ["2025-08-16"] * 3 + ["2025-08-17"] * 3,
                "home_team": ["A"] * 3 + ["C"] * 3,
                "away_team": ["B"] * 3 + ["D"] * 3,
                "profit": [1.0, 1.0, 1.0, -1.0, -1.0, -1.0],
            }
        )
        low, high, _ = bootstrap_interval(bets, draws=500)
        # Resampling two whole matches can only ever give -100, 0 or +100.
        assert low == pytest.approx(-100.0)
        assert high == pytest.approx(100.0)

    def test_an_empty_frame_reports_nothing_rather_than_zero(self):
        low, high, above = bootstrap_interval(pd.DataFrame())
        assert np.isnan(low) and np.isnan(high) and np.isnan(above)


class TestTheReportRefusesToInventBets:
    def test_no_prices_produces_a_reason_not_an_empty_pass(self):
        """An empty answer and a null answer are different facts."""
        empty = pd.DataFrame(
            columns=[
                "commence_time",
                "home_team",
                "away_team",
                "market",
                "book",
                "player",
                "selection",
                "american",
            ]
        )
        result = build_backtest(empty, pd.DataFrame())
        assert result.bets.empty
        assert result.notes
        assert summarize(result).empty
