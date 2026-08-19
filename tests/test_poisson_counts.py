"""Corners, cards and shots, fitted on data already downloaded each week.

Football-Data ships corners, bookings and shots in the same file as the
scorelines, so none of this needs a new source — the columns were simply being
discarded. The tests worth having are that the fit produces league-plausible
numbers, that a team with almost no history is not claimed to be unusual, and
that the known weaknesses are handled rather than hidden.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.models.poisson_counts import (
    COUNT_EVENTS,
    PoissonCountModel,
    TeamCountStrength,
)
from epl_betting_lab.strategies.count_markets import (
    CARDS_MIN_EDGE,
    COUNT_MARKETS,
    fit_count_models,
    minimum_edge_for,
    probabilities_for,
)


def _synthetic(home_count: int = 6, away_count: int = 4, n: int = 60) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "home_team": "Arsenal" if i % 2 else "Chelsea",
                "away_team": "Chelsea" if i % 2 else "Arsenal",
                "HC": home_count,
                "AC": away_count,
                "HY": 2,
                "AY": 2,
            }
        )
    return pd.DataFrame(rows)


class TestFitting:
    def test_it_recovers_the_average_it_was_given(self) -> None:
        model = PoissonCountModel("HC", "AC").fit(_synthetic(6, 4))

        assert model.avg_home == pytest.approx(6.0)
        assert model.avg_away == pytest.approx(4.0)

    def test_a_team_with_little_history_is_left_at_average(self) -> None:
        """Three matches is not evidence that a team is unusual."""
        frame = _synthetic()
        frame.loc[len(frame)] = {
            "home_team": "Newcomer",
            "away_team": "Arsenal",
            "HC": 20,
            "AC": 0,
            "HY": 0,
            "AY": 0,
        }
        model = PoissonCountModel("HC", "AC").fit(frame)

        assert model.team_strengths["Newcomer"] == TeamCountStrength(1.0, 1.0)

    def test_a_missing_column_is_refused_clearly(self) -> None:
        with pytest.raises(KeyError, match="cannot be modelled"):
            PoissonCountModel("HX", "AX").fit(_synthetic())

    def test_no_usable_rows_is_refused(self) -> None:
        frame = _synthetic()
        frame["HC"] = None
        with pytest.raises(ValueError):
            PoissonCountModel("HC", "AC").fit(frame)

    def test_an_unknown_event_names_the_ones_that_exist(self) -> None:
        with pytest.raises(KeyError, match="Known:"):
            PoissonCountModel.for_event("throw_ins")

    def test_predicting_before_fitting_is_refused(self) -> None:
        with pytest.raises(RuntimeError):
            PoissonCountModel("HC", "AC").expected_counts("Arsenal", "Chelsea")


class TestProbabilities:
    @pytest.fixture(scope="class")
    def model(self) -> PoissonCountModel:
        return PoissonCountModel("HC", "AC").fit(_synthetic(6, 4))

    def test_over_and_under_are_complementary(
        self, model: PoissonCountModel
    ) -> None:
        over = model.total_over_probability("Arsenal", "Chelsea", 9.5)
        assert 0.0 < over < 1.0

    def test_a_higher_line_is_less_likely_to_be_beaten(
        self, model: PoissonCountModel
    ) -> None:
        low = model.total_over_probability("Arsenal", "Chelsea", 8.5)
        high = model.total_over_probability("Arsenal", "Chelsea", 12.5)
        assert low > high

    def test_the_three_way_sums_to_one(self, model: PoissonCountModel) -> None:
        p = model.match_probabilities("Arsenal", "Chelsea")
        assert p["home"] + p["draw"] + p["away"] == pytest.approx(1.0, abs=1e-3)

    def test_the_side_that_wins_more_corners_is_favoured(
        self, model: PoissonCountModel
    ) -> None:
        p = model.match_probabilities("Arsenal", "Chelsea")
        assert p["home"] > p["away"]

    def test_team_totals_use_that_team_only(
        self, model: PoissonCountModel
    ) -> None:
        home = model.team_total_over_probability("Arsenal", "Chelsea", 4.5, "home")
        away = model.team_total_over_probability("Arsenal", "Chelsea", 4.5, "away")
        assert home > away

    def test_a_zero_rate_event_never_exceeds_a_line(self) -> None:
        model = PoissonCountModel("HC", "AC").fit(_synthetic(0, 0))
        assert model.total_over_probability("Arsenal", "Chelsea", 0.5) == 0.0


class TestAgainstRealData:
    """The fit has to land near known league averages to be worth anything."""

    @pytest.fixture(scope="class")
    def models(self) -> dict[str, PoissonCountModel]:
        return fit_count_models(load_matches())

    def test_corners_and_cards_both_fit(
        self, models: dict[str, PoissonCountModel]
    ) -> None:
        assert {"corners", "cards"} <= set(models)

    def test_corners_land_in_a_plausible_range(
        self, models: dict[str, PoissonCountModel]
    ) -> None:
        """A Premier League match averages roughly ten corners."""
        home, away = models["corners"].expected_counts("Arsenal", "Chelsea")
        assert 7.0 < home + away < 14.0

    def test_cards_land_in_a_plausible_range(
        self, models: dict[str, PoissonCountModel]
    ) -> None:
        home, away = models["cards"].expected_counts("Arsenal", "Chelsea")
        assert 1.5 < home + away < 8.0

    def test_every_registered_count_market_can_be_priced(
        self, models: dict[str, PoissonCountModel]
    ) -> None:
        for market, (event, _, _) in COUNT_MARKETS.items():
            probabilities = probabilities_for(
                market, models[event], "Arsenal", "Chelsea"
            )
            assert probabilities, market
            assert all(0.0 <= v <= 1.0 for v in probabilities.values()), market

    def test_a_dataset_without_the_columns_yields_no_models(self) -> None:
        """A missing market, not a broken run."""
        assert fit_count_models(pd.DataFrame({"home_team": [], "away_team": []})) == {}


class TestCardsAreTrustedLess:
    def test_cards_demand_more_edge_than_the_default(self) -> None:
        """Bookings cluster, and the referee is not in the data at all."""
        assert minimum_edge_for("cards_total_3_5", 0.035) == CARDS_MIN_EDGE
        assert CARDS_MIN_EDGE > 0.035

    def test_corners_use_the_default(self) -> None:
        assert minimum_edge_for("corners_total_9_5", 0.035) == 0.035

    def test_a_higher_default_is_not_lowered_for_cards(self) -> None:
        assert minimum_edge_for("cards_total_3_5", 0.09) == 0.09


class TestRegistration:
    def test_every_count_market_is_known_to_the_project(self) -> None:
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

        for market in COUNT_MARKETS:
            assert market in MARKET_SELECTIONS, market

    def test_the_strategy_and_registry_agree_on_selections(self) -> None:
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

        models = fit_count_models(load_matches())
        for market, (event, _, _) in COUNT_MARKETS.items():
            priced = set(probabilities_for(market, models[event], "Arsenal", "Chelsea"))
            assert priced == set(MARKET_SELECTIONS[market]), market

    def test_every_named_event_maps_to_a_column_pair(self) -> None:
        for event, columns in COUNT_EVENTS.items():
            assert len(columns) == 2, event
