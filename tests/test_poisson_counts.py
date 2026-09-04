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


#: A league whose truth is known. The match dataset is derived, not tracked,
#: so a clean checkout does not have it, and the tests below used to be
#: skipped on that — eleven skips that could never resolve in CI, which is the
#: same as eleven tests that do not exist. They now fit a league generated
#: from the model's own assumptions (Poisson counts, per-team rates with a
#: modest dispersion, home advantage in corners) so they run everywhere and
#: the expected answer is known rather than assumed. What they no longer do is
#: measure the real Premier League; that measurement lives in
#: `data/outputs/count_calibration.md` (`scripts/run_count_calibration.py`) and
#: is refreshed by the matchday workflow, not asserted here.
#:
#: Deterministic: a fixed seed, so a failure is a change in the code and not in
#: the dice. Rates are chosen to land on the league's known averages — about
#: ten corners and three and a half cards a match.
_KNOWN_TEAMS = tuple(f"Team {chr(65 + index)}" for index in range(20))


def _known_league(seed: int = 11, seasons: int = 8, dispersion: float = 0.08) -> pd.DataFrame:
    import math

    import numpy as np

    rng = np.random.RandomState(seed)
    corners_for = {team: math.exp(rng.normal(0.0, dispersion)) for team in _KNOWN_TEAMS}
    corners_against = {team: math.exp(rng.normal(0.0, dispersion)) for team in _KNOWN_TEAMS}
    cards_for = {team: math.exp(rng.normal(0.0, dispersion)) for team in _KNOWN_TEAMS}
    rows = []
    day = pd.Timestamp("2018-08-11")
    for offset in range(seasons):
        season = f"{18 + offset:02d}{19 + offset:02d}"
        fixtures = [(h, a) for h in _KNOWN_TEAMS for a in _KNOWN_TEAMS if h != a]
        rng.shuffle(fixtures)
        for index, (home, away) in enumerate(fixtures):
            if index % 10 == 0:
                day += pd.Timedelta(days=7)
            rows.append(
                {
                    "season": season,
                    "date": day,
                    "home_team": home,
                    "away_team": away,
                    "HC": rng.poisson(5.6 * corners_for[home] * corners_against[away]),
                    "AC": rng.poisson(4.6 * corners_for[away] * corners_against[home]),
                    "HY": rng.poisson(1.6 * cards_for[home]),
                    "AY": rng.poisson(1.9 * cards_for[away]),
                }
            )
        day += pd.Timedelta(days=60)
    return pd.DataFrame(rows)


class TestAgainstAKnownLeague:
    """The fit has to land near the league's averages to be worth anything."""

    @pytest.fixture(scope="class")
    def models(self) -> dict[str, PoissonCountModel]:
        return fit_count_models(_known_league())

    def test_the_known_league_has_the_shape_of_the_real_one(self) -> None:
        league = _known_league()

        assert len(league) == 8 * 380
        assert 9.0 < (league["HC"] + league["AC"]).mean() < 11.0
        assert 3.0 < (league["HY"] + league["AY"]).mean() < 4.0

    def test_corners_and_cards_both_fit(
        self, models: dict[str, PoissonCountModel]
    ) -> None:
        assert {"corners", "cards"} <= set(models)

    def test_corners_land_in_a_plausible_range(
        self, models: dict[str, PoissonCountModel]
    ) -> None:
        """A Premier League match averages roughly ten corners."""
        home, away = models["corners"].expected_counts("Team A", "Team B")
        assert 7.0 < home + away < 14.0

    def test_cards_land_in_a_plausible_range(
        self, models: dict[str, PoissonCountModel]
    ) -> None:
        home, away = models["cards"].expected_counts("Team A", "Team B")
        assert 1.5 < home + away < 8.0

    def test_every_registered_count_market_can_be_priced(
        self, models: dict[str, PoissonCountModel]
    ) -> None:
        for market, (event, _, _) in COUNT_MARKETS.items():
            probabilities = probabilities_for(
                market, models[event], "Team A", "Team B"
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

    def test_the_strategy_and_registry_agree_on_selections(self) -> None:
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

        from epl_betting_lab.strategies.count_markets import UNAVAILABLE_MARKETS

        models = fit_count_models(_known_league())
        for market, (event, _, _) in COUNT_MARKETS.items():
            if market in UNAVAILABLE_MARKETS:
                continue
            priced = set(probabilities_for(market, models[event], "Team A", "Team B"))
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


class TestShrinkage:
    """Team strengths are pulled toward the league average by evidence.

    A ratio from a season of matches is a noisy estimate, and multiplying two
    of them — one side's generating, the other's conceding — compounds it. Left
    raw, the model predicted 74% where 59% happened and 26% where 48% did: too
    spread out in both directions. Shrinkage weights each strength by how much
    evidence stands behind it.
    """

    def _frame(self, team_matches: int) -> pd.DataFrame:
        rows = []
        # A league of ordinary teams, plus one outlier with `team_matches` games.
        for i in range(200):
            rows.append(
                {"home_team": f"T{i % 10}", "away_team": f"T{(i + 1) % 10}",
                 "HC": 5, "AC": 5, "HY": 2, "AY": 2}
            )
        for i in range(team_matches):
            rows.append(
                {"home_team": "Outlier", "away_team": f"T{i % 10}",
                 "HC": 15, "AC": 5, "HY": 2, "AY": 2}
            )
        return pd.DataFrame(rows)

    def test_a_team_with_little_evidence_stays_near_average(self) -> None:
        model = PoissonCountModel("HC", "AC").fit(self._frame(8))
        strength = model.team_strengths["Outlier"].generates

        assert strength < 1.4, "eight matches should not buy a large claim"

    def test_a_team_with_much_evidence_keeps_more_of_it(self) -> None:
        few = PoissonCountModel("HC", "AC").fit(self._frame(8))
        many = PoissonCountModel("HC", "AC").fit(self._frame(150))

        assert (
            many.team_strengths["Outlier"].generates
            > few.team_strengths["Outlier"].generates
        )

    def test_shrinkage_never_crosses_the_average(self) -> None:
        """It pulls toward 1.0; it must not overshoot past it."""
        model = PoissonCountModel("HC", "AC").fit(self._frame(30))

        assert model.team_strengths["Outlier"].generates > 1.0

    def test_disabling_shrinkage_restores_the_raw_ratio(self) -> None:
        raw = PoissonCountModel("HC", "AC", shrinkage_matches=0).fit(self._frame(60))
        shrunk = PoissonCountModel("HC", "AC").fit(self._frame(60))

        assert (
            raw.team_strengths["Outlier"].generates
            > shrunk.team_strengths["Outlier"].generates
        )

    def test_the_half_weight_point_is_documented_not_arbitrary(self) -> None:
        assert PoissonCountModel.SHRINKAGE_MATCHES == 60


class TestCalibrationOnAKnownLeague:
    """The calibration machinery, checked where the right answer is known.

    Four tests here used to measure the REAL dataset — the 9.5 line's worst
    gap fell from 15.2% to under 5% when shrinkage was added, the 10.5 line's
    from 21.6% to under 15%, and the three-way sat under 5% — and every one of
    them was skipped in CI because the dataset is not tracked. A skip that can
    never resolve is a test that does not exist wearing a test's name, so
    those assertions are gone from here. The real-league numbers are produced
    by `scripts/run_count_calibration.py` into
    `data/outputs/count_calibration.md` on every matchday run, which is where
    a regression in them is read.

    What CAN be asserted everywhere is that on a league generated from the
    model's own assumptions the walk-forward is calibrated to within sampling
    noise, band by band. The bound is statistical rather than a fixed
    percentage because a band of 60 matches cannot be held to 5 points: the
    standard error of an observed rate is sqrt(p(1-p)/n), and every judged
    band must sit within three of them. The sample size is in every message.
    """

    @staticmethod
    def _assert_calibrated_within_noise(summary) -> None:
        import math

        judged = [row for row in summary if row.judged]
        assert len(judged) >= 3, [row.bucket for row in summary]
        for row in judged:
            standard_error = math.sqrt(row.predicted * (1.0 - row.predicted) / row.matches)
            assert abs(row.gap) <= 3.0 * standard_error, (
                f"band {row.bucket}: predicted {row.predicted:.3f}, observed "
                f"{row.observed:.3f}, gap {row.gap:+.3f} over n={row.matches} "
                f"matches is {abs(row.gap) / standard_error:.1f} standard errors"
            )

    def test_the_walk_forward_predicts_every_match_after_the_history_floor(self) -> None:
        from epl_betting_lab.reports.count_model_calibration import walk_forward_predictions

        league = _known_league()
        predictions = walk_forward_predictions(league, event="corners", line=9.5)

        # 200 matches of history before the first prediction; one row per match after.
        assert len(predictions) == len(league) - 200
        assert predictions["predicted_over"].between(0.0, 1.0).all()
        assert (predictions["went_over"] == (predictions["actual_total"] > 9.5)).all()

    @pytest.mark.parametrize("line", [9.5, 10.5])
    def test_the_totals_line_is_calibrated_within_sampling_noise(self, line: float) -> None:
        from epl_betting_lab.reports.count_model_calibration import (
            summarize_calibration,
            walk_forward_predictions,
        )

        predictions = walk_forward_predictions(_known_league(), event="corners", line=line)
        summary = summarize_calibration(predictions)

        assert sum(row.matches for row in summary) == len(predictions)
        self._assert_calibrated_within_noise(summary)

    def test_the_corner_three_way_is_calibrated_within_sampling_noise(self) -> None:
        """A different question from a total: a model can be right about how
        many and wrong about which side."""
        from epl_betting_lab.reports.count_model_calibration import (
            summarize_calibration,
            walk_forward_three_way,
        )

        predictions = walk_forward_three_way(_known_league(), event="corners")
        summary = summarize_calibration(predictions)

        assert len(predictions) == len(_known_league()) - 200
        self._assert_calibrated_within_noise(summary)

    def test_worst_gap_judges_only_bands_with_enough_matches(self) -> None:
        """A clean gap across thin bands would not mean much, and a wild gap
        in a thin band must not fail a model that is fine where it counts."""
        from epl_betting_lab.reports.count_model_calibration import (
            MIN_MATCHES_TO_JUDGE,
            CalibrationRow,
            worst_gap,
        )

        thin = CalibrationRow("under 30%", MIN_MATCHES_TO_JUDGE - 1, 0.2, 0.9)
        judged = CalibrationRow("45-55%", MIN_MATCHES_TO_JUDGE, 0.5, 0.52)

        assert not thin.judged and judged.judged
        assert worst_gap([thin, judged]) == pytest.approx(0.02)
        assert worst_gap([thin]) == 0.0


class TestEveryLiveProbeRunsWithoutAnArchive:
    """The archive guard has blocked two probes in turn.

    Each live probe fetches for itself, so none of them needs an archived bulk
    response. The guard was widened once for event discovery and then blocked
    the historical probe the same way, which is what a list of special cases
    does. It now asks whether anything is going to read the archive at all.
    """

    def _source(self) -> str:
        from epl_betting_lab.config import PROJECT_ROOT

        return (
            PROJECT_ROOT / "scripts" / "run_provider_market_discovery.py"
        ).read_text(encoding="utf-8")

    def test_the_guard_asks_one_question(self) -> None:
        source = self._source()

        assert "live_probe = bool(" in source
        assert "if raw_path is None and not live_probe:" in source

    def test_every_probe_flag_is_counted(self) -> None:
        source = self._source()
        guard = source.split("live_probe = bool(", 1)[1].split(")", 1)[0]

        for flag in ("probe_totals_regions", "check_event_markets", "historical_probe"):
            assert flag in guard, flag


class TestTheDiscoveryScriptResolvesEveryNameItCalls:
    """compileall parses; it does not resolve names.

    A helper was added to the module and used in the script without being
    imported. That is a NameError at the moment of use — invisible to the
    compile check, invisible to every test that did not run that branch, and
    it surfaced as a failed dispatch after the credential had been read.
    """

    def _module(self):
        import importlib.util

        from epl_betting_lab.config import PROJECT_ROOT

        spec = importlib.util.spec_from_file_location(
            "_discovery_cli",
            PROJECT_ROOT / "scripts" / "run_provider_market_discovery.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_discovery_helper_the_script_calls_is_imported(self) -> None:
        import re

        module = self._module()
        source = open(module.__file__, encoding="utf-8").read()
        called = set(re.findall(r"\b(probe_[a-z_]+|fetch_[a-z_]+|summarize_[a-z_]+|discover_[a-z_]+|save_[a-z_]+)\(", source))

        missing = [name for name in called if not hasattr(module, name)]

        assert not missing, f"called but not imported: {missing}"


class TestHistoricalProbeResponseShapes:
    """A slate returns a list; one event returns an object.

    Reading only the list shape reported "no events, no markets" for a request
    that had succeeded and been charged for — indistinguishable from the market
    being unavailable, which is the question the probe exists to answer.
    """

    def _probe(self, payload, **kwargs):
        from epl_betting_lab.reports.provider_market_discovery import (
            probe_historical_odds,
        )

        class _Response:
            status_code = 200
            headers = {"x-requests-last": "10", "x-requests-remaining": "100"}

            def json(self):
                return payload

        return probe_historical_odds(
            api_key="k",
            when="2025-08-16T12:00:00Z",
            requester=lambda *a, **k: _Response(),
            **kwargs,
        )

    def _event(self, market="btts"):
        return {
            "id": "e1",
            "home_team": "Aston Villa",
            "away_team": "Newcastle",
            "bookmakers": [{"title": "FanDuel", "markets": [{"key": market}]}],
        }

    def test_a_slate_snapshot_is_read(self) -> None:
        out = self._probe({"data": [self._event("h2h"), self._event("h2h")]})

        assert out["event_count"] == 2
        assert out["markets_seen"] == ["h2h"]

    def test_a_single_event_snapshot_is_read(self) -> None:
        out = self._probe({"data": self._event("btts")}, event_id="e1")

        assert out["event_count"] == 1
        assert out["markets_seen"] == ["btts"]

    def test_the_per_event_endpoint_is_addressed_by_id(self) -> None:
        from epl_betting_lab.reports.provider_market_discovery import (
            probe_historical_odds,
        )

        seen = {}

        class _Response:
            status_code = 200
            headers = {}

            def json(self):
                return {"data": {}}

        def _request(url, params=None, timeout=None):
            seen["url"] = url
            return _Response()

        probe_historical_odds(
            api_key="k", when="x", requester=_request, event_id="abc123"
        )

        assert "/events/abc123/odds" in seen["url"]

    def test_without_an_id_the_slate_endpoint_is_used(self) -> None:
        from epl_betting_lab.reports.provider_market_discovery import (
            probe_historical_odds,
        )

        seen = {}

        class _Response:
            status_code = 200
            headers = {}

            def json(self):
                return {"data": []}

        def _request(url, params=None, timeout=None):
            seen["url"] = url
            return _Response()

        probe_historical_odds(api_key="k", when="x", requester=_request)

        assert "/events/" not in seen["url"]
