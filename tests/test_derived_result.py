"""Double chance and draw-no-bet, derived from the 1X2 distribution.

Neither needs a new model or a new data source: the Poisson fit already
produces the whole scoreline distribution, and these are two more ways of
grouping the same three outcomes. So the tests that matter are about the
grouping being right, and about the market behaving the way the configured
juice limit implies rather than the way these markets are normally used.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.strategies.derived_result import (
    DERIVED_MARKETS,
    evaluate_double_chance,
    evaluate_draw_no_bet,
    price_refusal_summary,
)


def _matches() -> pd.DataFrame:
    rows = []
    for i in range(60):
        rows.append(
            {
                "date": pd.Timestamp("2025-08-01") + pd.Timedelta(days=i),
                "season": "2526",
                "home_team": "Arsenal" if i % 2 else "Chelsea",
                "away_team": "Chelsea" if i % 2 else "Arsenal",
                "home_goals": 2 if i % 2 else 1,
                "away_goals": 1 if i % 3 else 0,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def probabilities() -> dict:
    model = PoissonGoalsModel().fit(_matches())
    return model.match_probabilities("Arsenal", "Chelsea")


class TestTheGroupingIsRight:
    def test_double_chance_is_the_sum_of_its_two_outcomes(
        self, probabilities: dict
    ) -> None:
        p = probabilities
        assert p["double_chance_home_or_draw"] == pytest.approx(
            p["home_win"] + p["draw"], abs=1e-3
        )
        assert p["double_chance_draw_or_away"] == pytest.approx(
            p["draw"] + p["away_win"], abs=1e-3
        )
        assert p["double_chance_home_or_away"] == pytest.approx(
            p["home_win"] + p["away_win"], abs=1e-3
        )

    def test_the_three_double_chances_sum_to_two(self, probabilities: dict) -> None:
        """Each outcome appears in exactly two of the three."""
        total = (
            probabilities["double_chance_home_or_draw"]
            + probabilities["double_chance_draw_or_away"]
            + probabilities["double_chance_home_or_away"]
        )
        assert total == pytest.approx(2.0, abs=1e-2)

    def test_draw_no_bet_is_conditional_not_additive(
        self, probabilities: dict
    ) -> None:
        """The draw voids the bet, so the fair price is P(home | not a draw).

        Pricing it as P(home) would overprice both sides at once — the mistake
        this market invites.
        """
        p = probabilities
        assert p["draw_no_bet_home"] == pytest.approx(
            p["home_win"] / (1 - p["draw"]), abs=1e-3
        )
        assert p["draw_no_bet_home"] > p["home_win"]

    def test_the_two_draw_no_bet_sides_sum_to_one(self, probabilities: dict) -> None:
        total = probabilities["draw_no_bet_home"] + probabilities["draw_no_bet_away"]
        assert total == pytest.approx(1.0, abs=1e-2)

    def test_a_certain_draw_does_not_divide_by_zero(self) -> None:
        model = PoissonGoalsModel()
        model.avg_home_goals = 0.0
        model.avg_away_goals = 0.0
        p = model.match_probabilities("A", "B")

        assert p["draw_no_bet_home"] == 0.0
        assert p["draw_no_bet_away"] == 0.0


def _projection() -> pd.DataFrame:
    model = PoissonGoalsModel().fit(_matches())
    p = model.match_probabilities("Arsenal", "Chelsea")
    return pd.DataFrame([{**p, "home_team": "Arsenal", "away_team": "Chelsea"}])


def _odds(market: str, selection: str, american: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "market": market,
                "selection": selection,
                "american_odds": american,
                "book": "FanDuel",
            }
        ]
    )


class TestGrading:
    def test_a_generous_price_is_graded(self) -> None:
        graded = evaluate_double_chance(
            _projection(), _odds("double_chance", "draw_or_away", 400.0)
        )
        assert not graded.empty
        assert graded.iloc[0]["market"] == "double_chance"

    def test_a_short_price_is_refused_for_juice(self) -> None:
        """The favourite side of these markets usually prices past the limit."""
        graded = evaluate_double_chance(
            _projection(), _odds("double_chance", "home_or_draw", -400.0)
        )
        assert graded.iloc[0]["status"] == "PASS - too much juice"

    def test_the_refusal_is_counted_not_hidden(self) -> None:
        """An empty section must not read as "nothing was found"."""
        graded = evaluate_double_chance(
            _projection(), _odds("double_chance", "home_or_draw", -400.0)
        )
        summary = price_refusal_summary(graded)

        assert summary == {"considered": 1, "refused_for_price": 1}

    def test_draw_no_bet_grades_its_own_market_only(self) -> None:
        graded = evaluate_draw_no_bet(
            _projection(), _odds("draw_no_bet", "away", 250.0)
        )
        assert set(graded["market"]) == {"draw_no_bet"}

    def test_odds_for_another_market_are_ignored(self) -> None:
        graded = evaluate_draw_no_bet(
            _projection(), _odds("double_chance", "home_or_draw", 150.0)
        )
        assert graded.empty

    def test_a_missing_price_is_skipped_not_invented(self) -> None:
        graded = evaluate_double_chance(_projection(), pd.DataFrame())
        assert graded.empty

    def test_no_projection_means_no_rows(self) -> None:
        graded = evaluate_double_chance(
            pd.DataFrame(), _odds("double_chance", "home_or_draw", 150.0)
        )
        assert graded.empty

    def test_the_book_is_carried_through(self) -> None:
        graded = evaluate_double_chance(
            _projection(), _odds("double_chance", "draw_or_away", 400.0)
        )
        assert graded.iloc[0]["book"] == "FanDuel"

    def test_an_empty_frame_summarises_as_nothing_considered(self) -> None:
        assert price_refusal_summary(pd.DataFrame()) == {
            "considered": 0,
            "refused_for_price": 0,
        }


class TestRegistration:
    def test_both_markets_are_known_to_the_project(self) -> None:
        assert "double_chance" in MARKET_SELECTIONS
        assert "draw_no_bet" in MARKET_SELECTIONS

    def test_the_strategy_and_the_registry_agree_on_selections(self) -> None:
        """Two lists that could drift apart and silently drop a selection."""
        for market, mapping in DERIVED_MARKETS.items():
            assert set(mapping) == set(MARKET_SELECTIONS[market]), market


class TestTheCardEvaluatesEveryPriceableMarket:
    """Which markets reach a card is a policy decision, not a wiring accident.

    Five markets were modelled, registered, fetched and validated, and still
    produced no picks because nothing evaluated them. That is the failure this
    covers: a market absent from the card should be a decision someone can
    read in the policy, never a gap nobody noticed.
    """

    def _source(self) -> str:
        from epl_betting_lab.config import PROJECT_ROOT

        return (PROJECT_ROOT / "src/epl_betting_lab/dashboard_actions.py").read_text(
            encoding="utf-8"
        )

    def test_the_derived_markets_are_evaluated(self) -> None:
        source = self._source()

        assert "evaluate_double_chance(" in source
        assert "evaluate_draw_no_bet(" in source

    def test_the_count_markets_are_evaluated(self) -> None:
        source = self._source()

        assert "evaluate_count_market(" in source
        assert "fit_count_models(" in source

    def test_markets_with_no_price_source_are_skipped(self) -> None:
        """Cards have no book, so evaluating them would only waste work."""
        source = self._source()

        assert "if market in UNAVAILABLE_MARKETS:" in source

    def test_every_registered_market_has_something_that_evaluates_it(self) -> None:
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
        from epl_betting_lab.strategies.count_markets import (
            COUNT_MARKETS,
            UNAVAILABLE_MARKETS,
        )
        from epl_betting_lab.strategies.derived_result import DERIVED_MARKETS

        evaluated = {"1x2", "total_2_5", "btts"}
        evaluated |= set(DERIVED_MARKETS)
        evaluated |= set(COUNT_MARKETS) - set(UNAVAILABLE_MARKETS)

        assert set(MARKET_SELECTIONS) <= evaluated

    def test_an_empty_strategy_result_does_not_break_the_concat(self) -> None:
        """Most markets return nothing on most bundles."""
        source = self._source()

        assert "if not frame.empty" in source
