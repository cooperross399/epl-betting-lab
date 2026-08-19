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
        """A team from another match must not resolve to a side of this one."""
        with pytest.raises(UnrecognizedOutcomeError, match="drops one side"):
            double_chance_selection("Chelsea or Draw", HOME, AWAY)

    def test_a_reviewed_alias_of_this_fixture_resolves(self) -> None:
        """"Coventry" and "Coventry City" are the same club, not a mismatch."""
        assert (
            double_chance_selection("Coventry or Draw", HOME, AWAY)
            == "draw_or_away"
        )


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


class TestCountersSurviveANewMarket:
    """A hardcoded counter took the whole refresh down the first time five
    markets were added. The fetch worked, the normaliser worked, and the run
    died on `market_counts[normalized_market] += 1` because the dict had been
    initialised with exactly three keys."""

    def test_the_counter_is_built_from_the_market_registry(self) -> None:
        """Not from a literal, so adding a market cannot raise a KeyError."""
        from epl_betting_lab.config import PROJECT_ROOT

        source = (
            PROJECT_ROOT
            / "src/epl_betting_lab/providers/odds_api_staging_provider.py"
        ).read_text(encoding="utf-8")

        assert '{"1x2": 0, "total_2_5": 0, "btts": 0}' not in source
        assert source.count("{market: 0 for market in MARKET_SELECTIONS}") >= 2

    def test_counting_cannot_raise_on_an_unexpected_market(self) -> None:
        from epl_betting_lab.config import PROJECT_ROOT

        source = (
            PROJECT_ROOT
            / "src/epl_betting_lab/providers/odds_api_staging_provider.py"
        ).read_text(encoding="utf-8")

        assert "market_counts[normalized_market] += 1" not in source
        assert "market_counts.get(normalized_market, 0) + 1" in source

    def test_the_report_lists_whatever_markets_were_counted(self) -> None:
        """It named three markets explicitly, so new ones would be invisible."""
        from epl_betting_lab.config import PROJECT_ROOT

        source = (
            PROJECT_ROOT
            / "src/epl_betting_lab/providers/odds_api_staging_provider.py"
        ).read_text(encoding="utf-8")

        assert "summary['market_counts']['1x2']" not in source


class TestProviderSpellingsResolve:
    """The provider and the project do not spell every team the same way.

    The provider writes "Coventry City" where the project writes "Coventry".
    Matching on the project name alone rejected a real outcome, and because an
    unplaceable name raises, that did not drop one selection — it blocked the
    entire live run. The h2h path had always compared both spellings; these
    markets now do the same.
    """

    PROJECT_HOME, PROJECT_AWAY = "Arsenal", "Coventry"
    PROVIDER_HOME, PROVIDER_AWAY = "Arsenal", "Coventry City"

    def _resolve(self, market: str, outcome: dict) -> str | None:
        return selection_for(
            market,
            outcome,
            self.PROJECT_HOME,
            self.PROJECT_AWAY,
            self.PROVIDER_HOME,
            self.PROVIDER_AWAY,
        )

    def test_double_chance_accepts_the_provider_spelling(self) -> None:
        assert self._resolve("double_chance", {"name": "Coventry City or Draw"}) == (
            "draw_or_away"
        )

    def test_draw_no_bet_accepts_the_provider_spelling(self) -> None:
        assert self._resolve("draw_no_bet", {"name": "Coventry City"}) == "away"

    def test_corners_accepts_the_provider_spelling(self) -> None:
        assert self._resolve("corners_1x2", {"name": "Coventry City"}) == "away"

    def test_the_project_spelling_still_works(self) -> None:
        assert self._resolve("draw_no_bet", {"name": "Coventry"}) == "away"

    def test_the_home_side_is_unaffected(self) -> None:
        assert self._resolve("draw_no_bet", {"name": "Arsenal"}) == "home"

    def test_a_genuinely_unknown_team_is_still_refused(self) -> None:
        """Looser matching must not become no matching."""
        with pytest.raises(UnrecognizedOutcomeError):
            self._resolve("draw_no_bet", {"name": "Chelsea"})

    def test_a_tie_reads_as_a_draw(self) -> None:
        assert self._resolve("corners_1x2", {"name": "Tie"}) == "draw"

    def test_the_provider_names_are_optional(self) -> None:
        """Callers that already normalised should not have to pass them twice."""
        assert (
            selection_for("draw_no_bet", {"name": "Arsenal"}, "Arsenal", "Coventry")
            == "home"
        )

    def test_the_provider_passes_both_spellings_through(self) -> None:
        from epl_betting_lab.config import PROJECT_ROOT

        source = (
            PROJECT_ROOT
            / "src/epl_betting_lab/providers/odds_api_staging_provider.py"
        ).read_text(encoding="utf-8")

        assert "provider_home_team," in source
        assert "provider_away_team," in source


class TestDuplicateRowsAreTreatedByMarket:
    """A repeat means different things in different markets.

    In 1X2, totals or BTTS it means the response is not what it claims to be,
    and those prices decide real bets — so the run stops. In an alternate-lines
    market a book sometimes lists the same corner line twice while assembling a
    ladder; refusing the whole run over that threw away every market including
    the ones that were fine.
    """

    def _source(self) -> str:
        from epl_betting_lab.config import PROJECT_ROOT

        return (
            PROJECT_ROOT
            / "src/epl_betting_lab/providers/odds_api_staging_provider.py"
        ).read_text(encoding="utf-8")

    def test_the_core_markets_still_stop_the_run(self) -> None:
        from epl_betting_lab.providers.odds_api_staging_provider import CORE_MARKETS

        assert CORE_MARKETS == frozenset({"1x2", "total_2_5", "btts"})
        assert "if normalized_market in CORE_MARKETS:" in self._source()
        assert "raise MalformedProviderResponseError(" in self._source()

    def test_the_derived_markets_keep_the_first_price(self) -> None:
        source = self._source()

        assert "duplicate_counts[normalized_market] = (" in source
        assert "continue" in source

    def test_repeats_are_reported_not_swallowed(self) -> None:
        """Tolerating something quietly is how it stops being noticed."""
        source = self._source()

        assert "The first price was kept and the repeats ignored" in source
        assert "no price was guessed" in source

    def test_no_core_market_is_in_the_derived_set(self) -> None:
        """Otherwise a core repeat would take the tolerant path."""
        from epl_betting_lab.providers.odds_api_staging_provider import (
            CORE_MARKETS,
            DERIVED_PROVIDER_MARKETS,
        )

        derived = {t for targets in DERIVED_PROVIDER_MARKETS.values() for t in targets}
        assert not (derived & CORE_MARKETS)
