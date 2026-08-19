"""Reading provider outcome names, written against a live probe.

The Odds API names these outcomes after the teams rather than after positions,
so the same market reads differently for every fixture. The shapes here are
copied from an actual response, not invented:

    double_chance   "Arsenal or Draw" / "Coventry City or Draw" /
                    "Arsenal or Coventry City"
    draw_no_bet     "Arsenal" / "Coventry City"
    corners_1x2     "Arsenal" / "Coventry City" / "Draw"
    corners totals  "Over"/"Under" with the line in `point`
"""

from __future__ import annotations

import pytest

from epl_betting_lab.providers.derived_market_parsing import (
    UnrecognizedOutcomeError,
    double_chance_selection,
    matches_line,
    selection_for,
    team_selection,
    total_selection,
)


HOME, AWAY = "Arsenal", "Coventry City"


class TestDoubleChance:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Arsenal or Draw", "home_or_draw"),
            ("Coventry City or Draw", "draw_or_away"),
            ("Arsenal or Coventry City", "home_or_away"),
            ("Draw or Arsenal", "home_or_draw"),
        ],
    )
    def test_real_outcome_names_resolve(self, name: str, expected: str) -> None:
        assert double_chance_selection(name, HOME, AWAY) == expected

    def test_spacing_and_case_do_not_matter(self) -> None:
        assert (
            double_chance_selection("  ARSENAL   or   draw ", HOME, AWAY)
            == "home_or_draw"
        )

    def test_a_name_that_is_not_a_pair_is_refused(self) -> None:
        with pytest.raises(UnrecognizedOutcomeError, match="two outcomes"):
            double_chance_selection("Arsenal", HOME, AWAY)

    def test_a_team_that_is_not_in_this_fixture_is_refused(self) -> None:
        """A spelling mismatch silently drops one side of the market."""
        with pytest.raises(UnrecognizedOutcomeError, match="drops one side"):
            double_chance_selection("Coventry or Draw", HOME, AWAY)


class TestTeamOutcomes:
    @pytest.mark.parametrize(
        "name,expected",
        [("Arsenal", "home"), ("Coventry City", "away"), ("Draw", "draw")],
    )
    def test_team_names_and_draw_resolve(self, name: str, expected: str) -> None:
        assert team_selection(name, HOME, AWAY) == expected

    def test_an_unknown_team_is_refused(self) -> None:
        with pytest.raises(UnrecognizedOutcomeError):
            team_selection("Chelsea", HOME, AWAY)


class TestTotals:
    @pytest.mark.parametrize("name,expected", [("Over", "over"), ("UNDER", "under")])
    def test_over_and_under_resolve(self, name: str, expected: str) -> None:
        assert total_selection(name) == expected

    def test_anything_else_is_refused(self) -> None:
        with pytest.raises(UnrecognizedOutcomeError):
            total_selection("Push")

    def test_the_named_line_matches(self) -> None:
        assert matches_line({"point": 9.5}, 9.5) is True

    def test_another_line_on_the_ladder_does_not(self) -> None:
        """A book sends the whole ladder in one market."""
        assert matches_line({"point": 8.5}, 9.5) is False

    def test_a_missing_point_does_not_match(self) -> None:
        assert matches_line({}, 9.5) is False

    def test_an_unparseable_point_does_not_match(self) -> None:
        assert matches_line({"point": "nine and a half"}, 9.5) is False


class TestSelectionFor:
    def test_it_reads_each_market(self) -> None:
        assert (
            selection_for("double_chance", {"name": "Arsenal or Draw"}, HOME, AWAY)
            == "home_or_draw"
        )
        assert selection_for("draw_no_bet", {"name": "Arsenal"}, HOME, AWAY) == "home"
        assert selection_for("corners_1x2", {"name": "Draw"}, HOME, AWAY) == "draw"

    def test_a_totals_outcome_on_the_named_line_resolves(self) -> None:
        selection = selection_for(
            "corners_total_9_5", {"name": "Over", "point": 9.5}, HOME, AWAY
        )
        assert selection == "over"

    def test_a_totals_outcome_off_the_named_line_is_skipped(self) -> None:
        """Taking whichever line arrived would price a different bet."""
        selection = selection_for(
            "corners_total_9_5", {"name": "Over", "point": 8.5}, HOME, AWAY
        )
        assert selection is None

    def test_the_ten_and_a_half_market_reads_its_own_line(self) -> None:
        assert (
            selection_for(
                "corners_total_10_5", {"name": "Under", "point": 10.5}, HOME, AWAY
            )
            == "under"
        )
        assert (
            selection_for(
                "corners_total_10_5", {"name": "Under", "point": 9.5}, HOME, AWAY
            )
            is None
        )

    def test_a_market_with_no_parser_is_refused(self) -> None:
        with pytest.raises(UnrecognizedOutcomeError, match="No parser"):
            selection_for("player_shots", {"name": "Saka"}, HOME, AWAY)

    def test_every_registered_derived_market_has_a_parser(self) -> None:
        """A market on the card with no parser would price nothing, silently."""
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

        samples = {
            "double_chance": {"name": "Arsenal or Draw"},
            "draw_no_bet": {"name": "Arsenal"},
            "corners_1x2": {"name": "Arsenal"},
            "corners_total_9_5": {"name": "Over", "point": 9.5},
            "corners_total_10_5": {"name": "Over", "point": 10.5},
        }
        for market in samples:
            assert market in MARKET_SELECTIONS, market
            assert selection_for(market, samples[market], HOME, AWAY) is not None

    def test_each_parser_returns_a_registered_selection(self) -> None:
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

        cases = [
            ("double_chance", {"name": "Coventry City or Draw"}),
            ("draw_no_bet", {"name": "Coventry City"}),
            ("corners_1x2", {"name": "Draw"}),
            ("corners_total_9_5", {"name": "Under", "point": 9.5}),
        ]
        for market, outcome in cases:
            selection = selection_for(market, outcome, HOME, AWAY)
            assert selection in MARKET_SELECTIONS[market], (market, selection)


class TestTheProviderNormalisesThem:
    """The provider has to turn a real response into project rows.

    Shapes copied from a live probe. The risk being covered is a market that
    parses to nothing: the request succeeds, the outcomes are ignored, and the
    market never reaches a card without anything reporting a problem.
    """

    def _maps(self):
        from epl_betting_lab.providers.odds_api_staging_provider import (
            ACCEPTED_PROVIDER_MARKETS,
            DEFAULT_EVENT_MARKETS,
            DERIVED_PROVIDER_MARKETS,
            _derived_project_market,
        )

        return (
            ACCEPTED_PROVIDER_MARKETS,
            DEFAULT_EVENT_MARKETS,
            DERIVED_PROVIDER_MARKETS,
            _derived_project_market,
        )

    def test_the_original_three_markets_are_still_accepted(self) -> None:
        accepted, _, _, _ = self._maps()
        assert {"h2h", "totals", "btts"} <= accepted

    def test_the_new_provider_keys_are_accepted(self) -> None:
        accepted, _, derived, _ = self._maps()
        assert set(derived) <= accepted
        assert "double_chance" in accepted

    def test_a_live_run_requests_them(self) -> None:
        _, default_markets, derived, _ = self._maps()
        assert "btts" in default_markets
        assert set(derived) <= set(default_markets)

    def test_one_provider_market_can_feed_two_project_markets(self) -> None:
        """A corners response carries the ladder from 4.5 to 15.5."""
        _, _, derived, _ = self._maps()
        assert derived["alternate_totals_corners"] == (
            "corners_total_9_5",
            "corners_total_10_5",
        )

    def test_the_line_decides_which_market_an_outcome_belongs_to(self) -> None:
        _, _, _, route = self._maps()
        assert (
            route("alternate_totals_corners", {"name": "Over", "point": 9.5})
            == "corners_total_9_5"
        )
        assert (
            route("alternate_totals_corners", {"name": "Over", "point": 10.5})
            == "corners_total_10_5"
        )

    def test_a_line_nobody_models_is_not_an_error(self) -> None:
        """Most of the ladder is simply not ours."""
        _, _, _, route = self._maps()
        assert route("alternate_totals_corners", {"name": "Over", "point": 15.5}) is None

    def test_a_single_market_needs_no_line(self) -> None:
        _, _, _, route = self._maps()
        assert route("double_chance", {"name": "Arsenal or Draw"}) == "double_chance"

    def test_every_routed_market_is_one_the_project_knows(self) -> None:
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

        _, _, derived, _ = self._maps()
        for targets in derived.values():
            for target in targets:
                assert target in MARKET_SELECTIONS, target

    def test_every_registered_derived_market_has_a_provider_source(self) -> None:
        """A market on the card with no way to fetch a price is a dead entry."""
        from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

        _, _, derived, _ = self._maps()
        sourced = {target for targets in derived.values() for target in targets}
        sourced |= {"1x2", "total_2_5", "btts"}

        assert set(MARKET_SELECTIONS) == sourced
