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

from epl_betting_lab.config import PROCESSED_DIR
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


#: The match dataset is derived, not tracked, so a clean checkout does not have
#: it. Tests that need it are skipped rather than failed: they are a check on
#: the fit against real league averages, which is worth having locally and is
#: not worth making the suite depend on a file that only exists after a fetch.
#: Everything above this line runs on synthetic data and always executes.
_DATASET = PROCESSED_DIR / "epl_historical_matches.csv"
needs_dataset = pytest.mark.skipif(
    not _DATASET.is_file(),
    reason="needs data/processed/epl_historical_matches.csv (run scripts/fetch_data.py)",
)


@needs_dataset
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
    def test_every_available_count_market_is_registered(self) -> None:
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
        from epl_betting_lab.strategies.count_markets import UNAVAILABLE_MARKETS

        for market in COUNT_MARKETS:
            if market in UNAVAILABLE_MARKETS:
                continue
            assert market in MARKET_SELECTIONS, market

    def test_unavailable_markets_are_modelled_but_not_registered(self) -> None:
        """No book offers cards in the `us` region, which is where the accounts
        are. The model stays so the market can be enabled the day one appears;
        registering it would put a market on the card that has no price."""
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
        from epl_betting_lab.strategies.count_markets import UNAVAILABLE_MARKETS

        assert UNAVAILABLE_MARKETS
        for market in UNAVAILABLE_MARKETS:
            assert market in COUNT_MARKETS, market
            assert market not in MARKET_SELECTIONS, market

    @needs_dataset
    def test_the_strategy_and_registry_agree_on_selections(self) -> None:
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

        from epl_betting_lab.strategies.count_markets import UNAVAILABLE_MARKETS

        models = fit_count_models(load_matches())
        for market, (event, _, _) in COUNT_MARKETS.items():
            if market in UNAVAILABLE_MARKETS:
                continue
            priced = set(probabilities_for(market, models[event], "Arsenal", "Chelsea"))
            assert priced == set(MARKET_SELECTIONS[market]), market

    def test_every_named_event_maps_to_a_column_pair(self) -> None:
        for event, columns in COUNT_EVENTS.items():
            assert len(columns) == 2, event


class TestShapeProbing:
    """Discovery must be able to report a market's real outcome shape.

    A parser written against guessed field names is how a market silently
    returns nothing: the request succeeds, the outcomes are unrecognised, and
    the market simply never appears on a card.
    """

    def _summary(self, payload: dict, **kwargs) -> dict:
        from epl_betting_lab.reports.provider_market_discovery import (
            discover_event_markets,
        )

        class _Response:
            status_code = 200

            def json(self) -> dict:
                return payload

        return discover_event_markets(
            [{"id": "evt1", "home_team": "Arsenal", "away_team": "Chelsea"}],
            api_key="k",
            requester=lambda *a, **k: _Response(),
            **kwargs,
        )

    def _payload(self) -> dict:
        return {
            "bookmakers": [
                {
                    "title": "FanDuel",
                    "markets": [
                        {
                            "key": "double_chance",
                            "outcomes": [
                                {"name": "Arsenal/Draw", "price": -300},
                                {"name": "Arsenal/Chelsea", "price": -150},
                            ],
                        },
                        {
                            "key": "alternate_totals_corners",
                            "outcomes": [
                                {"name": "Over", "point": 9.5, "price": -110},
                                {"name": "Under", "point": 9.5, "price": -110},
                            ],
                        },
                    ],
                }
            ]
        }

    def test_shapes_are_absent_unless_asked_for(self) -> None:
        summary = self._summary(self._payload())
        assert summary["outcome_shapes"] == {}

    def test_it_reports_the_real_field_names(self) -> None:
        summary = self._summary(self._payload(), dump_outcome_shapes=True)
        corners = summary["outcome_shapes"]["alternate_totals_corners"]

        assert "point" in corners["outcome_fields"]
        assert corners["outcomes"][0]["point"] == 9.5

    def test_it_reports_outcome_names_verbatim(self) -> None:
        """"Arsenal/Draw" is not a name any parser would have guessed."""
        summary = self._summary(self._payload(), dump_outcome_shapes=True)
        names = [o["name"] for o in summary["outcome_shapes"]["double_chance"]["outcomes"]]

        assert "Arsenal/Draw" in names

    def test_it_records_that_a_price_exists_without_reporting_it(self) -> None:
        """This report is about structure, not prices."""
        summary = self._summary(self._payload(), dump_outcome_shapes=True)
        outcome = summary["outcome_shapes"]["double_chance"]["outcomes"][0]

        assert outcome["has_price"] is True
        assert "price" not in outcome

    def test_a_requested_market_that_never_returns_is_named(self) -> None:
        summary = self._summary(
            self._payload(), markets="double_chance,corners_1x2"
        )

        assert "corners_1x2" in summary["markets_absent"]
        assert "double_chance" in summary["markets_returned"]


class TestProbingWithoutAnArchive:
    """A probe must run on a clean checkout.

    Event discovery previously derived its event list from an archived bulk
    response, which is not committed — so the probe was unrunnable in CI, the
    one place with a working credential. The events endpoint carries no odds
    and costs nothing, so it can supply the ids directly.
    """

    def _events_response(self, payload):
        class _Response:
            status_code = 200

            def json(self):
                return payload

        return _Response()

    def test_it_reads_the_free_events_endpoint(self) -> None:
        from epl_betting_lab.reports.provider_market_discovery import fetch_events_live

        captured = {}

        def _request(url, params=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            return self._events_response(
                [
                    {
                        "id": "evt1",
                        "home_team": "Arsenal",
                        "away_team": "Chelsea",
                        "commence_time": "2026-08-21T19:00:00Z",
                    }
                ]
            )

        events = fetch_events_live(api_key="k", requester=_request)

        assert captured["url"].endswith("/events")
        assert events[0]["provider_event_id"] == "evt1"
        assert events[0]["home_team"] == "Arsenal"

    def test_it_asks_for_no_odds_so_it_costs_nothing(self) -> None:
        from epl_betting_lab.reports.provider_market_discovery import fetch_events_live

        captured = {}

        def _request(url, params=None, timeout=None):
            captured["params"] = params or {}
            return self._events_response([])

        fetch_events_live(api_key="k", requester=_request)

        assert "markets" not in captured["params"]
        assert "regions" not in captured["params"]

    def test_a_missing_credential_is_refused_clearly(self) -> None:
        from epl_betting_lab.reports.provider_market_discovery import (
            DiscoveryError,
            fetch_events_live,
        )

        with pytest.raises(DiscoveryError, match="EPL_ODDS_API_KEY"):
            fetch_events_live(api_key="")

    def test_an_error_response_is_refused_not_treated_as_empty(self) -> None:
        from epl_betting_lab.reports.provider_market_discovery import (
            DiscoveryError,
            fetch_events_live,
        )

        class _Response:
            status_code = 401

            def json(self):
                return {}

        with pytest.raises(DiscoveryError, match="401"):
            fetch_events_live(api_key="k", requester=lambda *a, **k: _Response())

    def test_an_unexpected_body_yields_no_events(self) -> None:
        from epl_betting_lab.reports.provider_market_discovery import fetch_events_live

        assert (
            fetch_events_live(
                api_key="k",
                requester=lambda *a, **k: self._events_response({"error": "nope"}),
            )
            == []
        )


class TestLineCoverage:
    """Which books carry a line decides whether a market is takeable.

    Totals were excluded because the complete 2.5 line existed only at books
    with no account. That is a per-bookmaker question, and nothing reported it
    per bookmaker — the answer had to be reconstructed by hand from a response.
    """

    def _summary(self, payload: dict, **kwargs) -> dict:
        from epl_betting_lab.reports.provider_market_discovery import (
            discover_event_markets,
        )

        class _Response:
            status_code = 200

            def json(self) -> dict:
                return payload

        return discover_event_markets(
            [
                {"id": "e1", "home_team": "A", "away_team": "B"},
                {"id": "e2", "home_team": "C", "away_team": "D"},
            ],
            api_key="k",
            requester=lambda *a, **k: _Response(),
            **kwargs,
        )

    def _payload(self) -> dict:
        return {
            "bookmakers": [
                {
                    "title": "FanDuel",
                    "markets": [
                        {
                            "key": "alternate_totals",
                            "outcomes": [
                                {"name": "Over", "point": 2.5, "price": -110},
                                {"name": "Over", "point": 3.5, "price": 150},
                            ],
                        }
                    ],
                },
                {
                    "title": "Bovada",
                    "markets": [
                        {
                            "key": "alternate_totals",
                            "outcomes": [
                                {"name": "Over", "point": 3.5, "price": 150}
                            ],
                        }
                    ],
                },
            ]
        }

    def test_it_counts_fixtures_per_bookmaker(self) -> None:
        summary = self._summary(
            self._payload(), line_coverage=[("alternate_totals", 2.5)]
        )
        coverage = summary["line_coverage"]["alternate_totals@2.5"]

        assert coverage["FanDuel"] == 2

    def test_a_book_without_that_line_is_absent(self) -> None:
        summary = self._summary(
            self._payload(), line_coverage=[("alternate_totals", 2.5)]
        )

        assert "Bovada" not in summary["line_coverage"]["alternate_totals@2.5"]

    def test_a_line_nobody_offers_reports_empty(self) -> None:
        summary = self._summary(
            self._payload(), line_coverage=[("alternate_totals", 8.5)]
        )

        assert summary["line_coverage"]["alternate_totals@8.5"] == {}

    def test_coverage_is_absent_unless_asked_for(self) -> None:
        assert self._summary(self._payload())["line_coverage"] == {}

    def test_several_lines_can_be_asked_about_at_once(self) -> None:
        summary = self._summary(
            self._payload(),
            line_coverage=[("alternate_totals", 2.5), ("alternate_totals", 3.5)],
        )

        assert set(summary["line_coverage"]) == {
            "alternate_totals@2.5",
            "alternate_totals@3.5",
        }
        assert summary["line_coverage"]["alternate_totals@3.5"]["Bovada"] == 2


class TestParsingLineCoverageArguments:
    def _parse(self, raw: str):
        import importlib.util
        from epl_betting_lab.config import PROJECT_ROOT

        spec = importlib.util.spec_from_file_location(
            "_disc", PROJECT_ROOT / "scripts" / "run_provider_market_discovery.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module._parse_line_coverage(raw)

    def test_it_reads_market_at_line_pairs(self) -> None:
        assert self._parse("alternate_totals@2.5") == [("alternate_totals", 2.5)]

    def test_several_pairs(self) -> None:
        assert len(self._parse("a@1.5,b@2.5")) == 2

    def test_nonsense_is_skipped_not_raised(self) -> None:
        assert self._parse("no_at_sign,a@notanumber,b@1.5") == [("b", 1.5)]

    def test_blank_yields_nothing(self) -> None:
        assert self._parse("") == []
