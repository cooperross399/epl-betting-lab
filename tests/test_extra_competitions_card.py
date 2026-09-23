"""Selections beyond the Premier League, and the three faults found by looking.

The first run of this card printed every evaluated row. Among them was a
draw-no-bet at -39.5% edge, presented in the same table as a selection. It also
declined twelve of eighteen Champions League fixtures as unrateable while every
club in them sat in the pool, because the odds provider spells them a third way.
And it reported no corner model while every European league carries corner
counts on 100% of rows.

None of the three raised anything. Each is pinned below.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.data.european_clubs import PROVIDER_CLUB_NAMES, provider_name
from epl_betting_lab.reports.extra_competitions_card import (
    COMPETITIONS,
    EXCLUDED_MARKETS,
    EXTRA_UNITS,
    MAX_EXTRA_BETS,
    ExtraCard,
    build_extra_card,
    latest_prices,
    render_extra_card,
)


def _feed(competition: str = "UCL") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competition": [competition] * 4,
            "observed_at": [
                "2026-09-15T10:00:00Z",
                "2026-09-15T10:00:00Z",
                "2026-09-15T13:00:00Z",
                "2026-09-15T13:00:00Z",
            ],
            "provider_event_id": ["e1"] * 4,
            "date": ["2026-09-16"] * 4,
            "home_team": ["Paris Saint Germain"] * 4,
            "away_team": ["Inter Milan"] * 4,
            "market": ["btts"] * 4,
            "selection": ["yes"] * 4,
            "book": ["A", "B", "A", "B"],
            "american_odds": [100, 120, 105, 150],
        }
    )


class TestTheProviderNamesClubsItsOwnWay:
    def test_paris_saint_germain_resolves(self) -> None:
        """A third source, a third spelling. openfootball writes
        `Paris Saint-Germain FC`, Football-Data `Paris SG`, the provider
        `Paris Saint Germain` — and a name that was never written down is
        declined, which is correct behaviour producing a wrong outcome."""
        assert provider_name("Paris Saint Germain") == "Paris SG"
        assert provider_name("Inter Milan") == "Inter"
        assert provider_name("Atlético Madrid") == "Ath Madrid"

    def test_an_unmapped_name_passes_through(self) -> None:
        """Clubs whose names already agree need no entry, and one that is
        genuinely unrateable must stay visibly so rather than be invented."""
        assert provider_name("Arsenal") == "Arsenal"
        assert provider_name("Bodø/Glimt") == "Bodø/Glimt"

    def test_the_map_never_points_two_names_at_a_contradiction(self) -> None:
        """`Sporting CP` and `Sporting Lisbon` are the same club; if they
        resolved differently the pool would rate one fixture twice."""
        assert PROVIDER_CLUB_NAMES["Sporting CP"] == PROVIDER_CLUB_NAMES["Sporting Lisbon"]
        assert PROVIDER_CLUB_NAMES["Paris Saint Germain"] == PROVIDER_CLUB_NAMES["Paris Saint-Germain"]

    def test_prices_are_read_under_the_domestic_name(self) -> None:
        prices = latest_prices(_feed(), "UCL")
        assert set(prices["home_team"]) == {"Paris SG"}
        assert set(prices["away_team"]) == {"Inter"}


class TestOnlyTheNewestObservationAndTheBestPrice:
    def test_it_takes_the_latest_snapshot(self) -> None:
        prices = latest_prices(_feed(), "UCL")
        assert len(prices) == 1

    def test_and_the_longest_price_at_that_moment(self) -> None:
        prices = latest_prices(_feed(), "UCL")
        assert int(prices.iloc[0]["american_odds"]) == 150

    def test_another_competition_is_not_mixed_in(self) -> None:
        assert latest_prices(_feed("EFLC"), "UCL").empty


class TestOnlyWhatTheRulesPass:
    def _selections(self, statuses: list[str], edges: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "home_team": ["H"] * len(statuses),
                "away_team": ["A"] * len(statuses),
                "market": ["btts"] * len(statuses),
                "selection": ["yes"] * len(statuses),
                "american_odds": [110] * len(statuses),
                "book": ["X"] * len(statuses),
                "status": statuses,
                "calibrated_edge": edges,
                "competition": ["UCL"] * len(statuses),
                "suggested_units": [EXTRA_UNITS] * len(statuses),
            }
        )

    def test_a_negative_edge_never_reaches_the_table(self) -> None:
        """The first run offered a -39.5% draw-no-bet as a selection, in the
        same table and the same format as a real one."""
        card = ExtraCard(self._selections(["BETTABLE"], [0.05]), priced=1)
        report = "\n".join(render_extra_card({"UCL": card}))
        assert "+5.0%" in report
        assert "-39" not in report

    def test_the_stake_is_the_smallest_the_card_has(self) -> None:
        """Sized to the evidence behind these prices, which is none."""
        assert EXTRA_UNITS == 0.1

    def test_a_competition_cannot_crowd_the_card(self) -> None:
        assert MAX_EXTRA_BETS <= 8

    def test_1x2_stays_out(self) -> None:
        """Excluded from the Premier League card for losing out of sample, and
        there is no reason it would do better where the model knows less."""
        assert "1x2" in EXCLUDED_MARKETS


class TestItDeclinesRatherThanGuesses:
    def test_an_empty_card_says_so_and_says_why(self) -> None:
        card = ExtraCard(
            pd.DataFrame(),
            notes=["No UEFA Champions League price on file."],
            priced=1,
        )
        report = "\n".join(render_extra_card({"UCL": card}))
        assert "_No selection this run._" in report
        assert "No UEFA Champions League price on file." in report

    def test_the_report_carries_the_measurement_beside_the_bets(self) -> None:
        """A table of selections with no note reads as a recommendation. The
        EFL Cup was measured and the measurement was negative; that belongs
        next to the prices, not in a file nobody opens."""
        card = ExtraCard(pd.DataFrame(), priced=1)
        report = "\n".join(render_extra_card({"EFLC": card, "UCL": card}))
        assert "has been shown not to" in report
        assert "does **not** survive a division change" in report
        assert "overrates clubs who dominate" in report


class TestEachCompetitionUsesThePoolThatCanSeeIt:
    def test_the_cup_is_english_and_the_champions_league_is_not(self) -> None:
        """The English pool cannot rate Real Madrid; the European pool cannot
        rate Grimsby. Pointing either at the wrong one produces refusals that
        look like missing prices."""
        assert COMPETITIONS["EFLC"].pool == "english"
        assert COMPETITIONS["UCL"].pool == "european"

    def test_every_competition_has_a_note(self) -> None:
        for spec in COMPETITIONS.values():
            assert spec.note.strip()


class TestItIsWiredWithoutPuttingTheCardAtRisk:
    """The Premier League card must not depend on fourteen league datasets and
    a public-domain results repository being reachable. A run where the cup
    section cannot be built loses the section and keeps the card."""

    def _workflow(self) -> str:
        from epl_betting_lab.config import PROJECT_ROOT

        return (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

    def test_the_section_is_built_before_the_reports(self) -> None:
        text = self._workflow()
        assert text.index("- name: Build the cup and European section") < text.index(
            "- name: Rebuild every report"
        )

    def test_the_observation_feed_is_restored_first(self) -> None:
        """It holds the prices the section is built from, and it lives on the
        price-feed branch rather than in the repository."""
        text = self._workflow()
        assert text.index("- name: Restore the price feed") < text.index(
            "- name: Build the cup and European section"
        )
        block = text.split("- name: Restore the price feed", 1)[1].split("- name:", 1)[0]
        assert "price_feed_extra.csv" in block

    def test_the_restore_cannot_empty_a_feed_it_fails_to_find(self) -> None:
        """`>` truncates its target before the command on its left runs. That
        emptied 1,203 freshly collected observations once already."""
        block = self._workflow().split("- name: Restore the price feed", 1)[1]
        block = block.split("- name:", 1)[0]
        assert "mktemp" in block
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "git show" in stripped:
                assert "> data/processed/" not in stripped, stripped

    def test_building_the_section_cannot_fail_the_run(self) -> None:
        block = self._workflow().split(
            "- name: Build the cup and European section", 1
        )[1].split("- name:", 1)[0]
        assert "continue-on-error: true" in block
        # A bounded step: fourteen feeds on a bad day must not eat the job's
        # twenty minutes and take the card down with them.
        assert "timeout-minutes:" in block

    def test_it_spends_no_provider_quota(self) -> None:
        """Prices come from the observation feed the Closing Snapshot already
        collected; every rating input is a free CSV."""
        block = self._workflow().split(
            "- name: Build the cup and European section", 1
        )[1].split("- name:", 1)[0]
        assert "ODDS_API_KEY" not in block
        assert "secrets." not in block
        assert "--live" not in block

    def test_a_missing_section_is_simply_absent_not_fatal(self, tmp_path) -> None:
        """The card reads a file. No file, no section, no error."""
        import importlib.util

        from epl_betting_lab.config import PROJECT_ROOT

        spec = importlib.util.spec_from_file_location(
            "build_extra_card", PROJECT_ROOT / "scripts" / "build_extra_card.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import sys

        argv = ["build_extra_card.py", "--feed", str(tmp_path / "absent.csv"),
                "--out", str(tmp_path / "out.md")]
        old = sys.argv
        try:
            sys.argv = argv
            assert module.main() == 0
        finally:
            sys.argv = old
        assert not (tmp_path / "out.md").exists()


class TestACompetitionEarnsItsSection:
    """The Conference League priced none of its eighteen fixtures: its clubs
    play in Cyprus, Lithuania, Gibraltar and Andorra, and Football-Data
    publishes none of those. Printing its heading above eighteen lines of
    declines every run teaches the reader to skip the section that also carries
    the competitions that do have something to say.

    Stated as a condition rather than a list, so a competition returns on its
    own the run its coverage improves and nobody has to remember to check.
    """

    def _card(self, priced: int, unrated: int) -> ExtraCard:
        return ExtraCard(
            pd.DataFrame(),
            priced=priced,
            unrated=[f"A{i} v B{i}" for i in range(unrated)],
        )

    def test_a_competition_that_prices_nothing_is_not_carded(self) -> None:
        assert not self._card(priced=0, unrated=18).carded

    def test_one_priceable_fixture_is_enough(self) -> None:
        """Not a threshold anybody chose. A competition that can price
        something has something to say; one that cannot, cannot."""
        assert self._card(priced=1, unrated=17).carded

    def test_the_fixture_count_is_priced_plus_declined(self) -> None:
        """`0 of 0` says the competition had no fixtures. `0 of 18` says none
        of its eighteen could be rated. A quiet week and a coverage wall, told
        apart by the one number that distinguishes them — and the early return
        dropped the declined list, so it read 0 of 0."""
        assert self._card(priced=0, unrated=18).fixtures == 18
        assert self._card(priced=3, unrated=15).fixtures == 18

    def test_a_fitted_competition_is_named_not_silently_absent(self) -> None:
        report = "\n".join(
            render_extra_card({"UECL": self._card(priced=0, unrated=18)})
        )
        assert "Fitted but not bet" in report
        assert "0 of 18 fixtures rateable" in report
        assert "bridge the countries" in report
        # And its heading does not appear, which is the point.
        assert "### UEFA Europa Conference League" not in report

    def test_a_carded_competition_still_gets_its_heading(self) -> None:
        """The guard must not hide a competition that can price fixtures but
        happened to find no selection this run — that is a quiet week, and the
        reader should see the heading and the reason."""
        card = ExtraCard(pd.DataFrame(), notes=["No selection cleared the rules."], priced=5)
        report = "\n".join(render_extra_card({"UCL": card}))
        assert "### UEFA Champions League" in report
        assert "_No selection this run._" in report

    def test_the_conference_league_is_still_fitted(self) -> None:
        """Not carding it must not stop it bridging the countries, which is
        most of what it is for."""
        from epl_betting_lab.data.european_results import COMPETITION_FILES

        assert "UECL" in COMPETITION_FILES


def _stub_international_pool(monkeypatch) -> None:
    """A tiny offline pool, so no test reaches the network.

    `build_international_pool` fetches an archive over HTTP. A test that did
    that would be slow, would fail on a laptop with no connection, and would be
    measuring GitHub's availability rather than this module.
    """
    from epl_betting_lab.data.international_results import parse_archive
    from epl_betting_lab.models import international_ratings

    header = (
        "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral"
    )
    rows = [
        f"20{15 + i // 12:02d}-{1 + i % 12:02d}-05,{home},{away},{hg},{ag},"
        f"{tournament},Town,Country,{neutral}"
        # Deliberately close sides. An earlier version had Spain beating France
        # 3-1 twenty times, which put draw-no-bet home at 0.857 — a probability
        # the shrinkage treats as an extreme claim, cutting a 57-point raw edge
        # to 2.9. Tests then measured the shrinkage rather than the thing they
        # named. Real fixtures are nearer even than that.
        # More than one competition on purpose. With only Nations League rows
        # the competition's baseline IS the pool's, the override becomes a
        # no-op, and every test of it passes whether or not the card applies
        # it. The friendlies below are high-scoring and home-heavy, which is
        # what they are in the real archive (+0.767 goals of home advantage
        # against the Nations League's +0.346).
        for home, away, hg, ag, neutral, tournament in (
            ("Spain", "France", 2, 1, "FALSE", "UEFA Nations League"),
            ("France", "Spain", 1, 1, "FALSE", "UEFA Nations League"),
            ("Italy", "Germany", 1, 1, "TRUE", "UEFA Nations League"),
            ("Portugal", "Spain", 1, 1, "FALSE", "UEFA Nations League"),
            ("Spain", "Portugal", 1, 2, "FALSE", "UEFA Nations League"),
            ("Spain", "France", 4, 0, "FALSE", "Friendly"),
            ("Portugal", "Spain", 3, 1, "FALSE", "Friendly"),
            ("France", "Portugal", 3, 0, "FALSE", "Friendly"),
            ("Germany", "Italy", 4, 1, "FALSE", "Friendly"),
        )
        # Enough rows per (competition, venue) to clear MIN_BASELINE_MATCHES.
        # At twenty the stub had no competition baselines at all, so every test
        # of the override ran against a None and proved nothing.
        for i in range(60)
    ]
    results = parse_archive("\n".join([header, *rows]) + "\n")
    monkeypatch.setattr(
        international_ratings,
        "load_international_results",
        lambda **kwargs: results,
    )
    monkeypatch.setattr(
        "epl_betting_lab.reports.extra_competitions_card.build_international_pool",
        lambda **kwargs: international_ratings.build_international_pool(results=results),
    )


# --- the declined fixtures have to reach the card ---------------------------


class TestEveryReturnCarriesTheDeclinedFixtures:
    """`unrated` was added to the coverage-wall return and missed on three
    others, so a competition where nothing cleared reported every priced
    fixture and none of the declined ones — the same "0 of 0 fixtures rateable"
    fault the early return exists to prevent, surviving on the paths a quiet
    week actually takes. Of the five returns in `build_extra_card`, two had it.
    """

    @staticmethod
    def _feed(*fixtures, odds: int = -110) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "competition": "UNL",
                    "home_team": home,
                    "away_team": away,
                    "market": "btts",
                    "selection": selection,
                    "american_odds": odds,
                    "book": "Book",
                    "observed_at": "2026-09-22T12:00:00Z",
                }
                for home, away in fixtures
                for selection in ("yes", "no")
            ]
        )

    def test_a_declined_fixture_is_reported_when_nothing_clears(
        self, monkeypatch
    ) -> None:
        """The common case. A price at -110 both ways clears no rule, and that
        return is one of the three that used to drop the count."""
        _stub_international_pool(monkeypatch)

        # Priced so short that no edge can clear, which is what forces the
        # "nothing cleared" return rather than the final one. At -110 this
        # fixture does clear, and the test then exercises a path that always
        # carried `unrated` and proves nothing.
        card = build_extra_card(
            self._feed(("Spain", "France"), ("Atlantis", "Portugal"), odds=-5000),
            "UNL",
        )

        assert card.selections.empty, "the fixture was meant to clear nothing"
        assert any("cleared the rules" in note for note in card.notes), (
            "this test only guards the return it names if it reaches it"
        )
        assert card.unrated == ["Atlantis v Portugal"], (
            "the declined fixture vanished from a card that priced one of two"
        )

    def test_a_declined_fixture_survives_a_competition_with_no_bettable_market(
        self, monkeypatch
    ) -> None:
        """The other return, and the one a new competition is most likely to
        take. A provider that quotes a competition but not the markets this
        card bets leaves every evaluator empty, and that return is reached
        before any selection exists to be filtered. Its message differs from
        the "none of N cleared" one, which is why a test matching only the
        shared words passes without ever reaching here.
        """
        _stub_international_pool(monkeypatch)
        feed = self._feed(("Spain", "France"), ("Atlantis", "Portugal"))
        # `1x2` is excluded from this card, so nothing evaluates it.
        feed["market"] = "1x2"
        feed["selection"] = "home"

        card = build_extra_card(feed, "UNL")

        assert card.notes[-1] == "No selection cleared the rules.", (
            "this test guards the plain return; it reached a different one"
        )
        assert card.unrated == ["Atlantis v Portugal"]

    def test_the_count_distinguishes_a_quiet_week_from_a_coverage_wall(
        self, monkeypatch
    ) -> None:
        _stub_international_pool(monkeypatch)

        priced_nothing = build_extra_card(
            self._feed(("Atlantis", "Utopia"), odds=-5000), "UNL"
        )
        priced_one = build_extra_card(
            self._feed(("Spain", "France"), odds=-5000), "UNL"
        )

        assert priced_nothing.priced == 0 and priced_nothing.unrated
        assert priced_one.priced == 1 and not priced_one.unrated


# --- the intro must not count its own sections ------------------------------


class TestTheIntroDoesNotGoStaleWhenACompetitionIsAdded:
    """It read "Neither competition below has been shown to beat a price" and
    was written when there were two. The Europa League, the Conference League
    and the Nations League were added underneath it, and it went out on a card
    carrying five sections telling the reader there were two.

    Asserted behaviourally rather than by grepping for counting words. A list
    of banned spellings misses the one nobody thought of; rendering the same
    card with a different number of sections and requiring the intro not to
    move catches any wording that depends on the count, however it is phrased.
    """

    @staticmethod
    def _intro(cards: dict) -> list[str]:
        rendered = render_extra_card(cards)
        return rendered[: rendered.index("### " + COMPETITIONS[next(iter(cards))].name)]

    @staticmethod
    def _card() -> ExtraCard:
        return ExtraCard(
            pd.DataFrame(
                [
                    {
                        "home_team": "A",
                        "away_team": "B",
                        "market": "btts",
                        "selection": "yes",
                        "american_odds": 100,
                        "book": "Book",
                        "calibrated_edge": 0.05,
                        "suggested_units": 0.1,
                    }
                ]
            ),
            [],
            priced=1,
        )

    def test_the_intro_is_the_same_for_one_section_as_for_every_section(self) -> None:
        keys = list(COMPETITIONS)
        assert len(keys) >= 2, "this test needs at least two competitions to compare"

        one = self._intro({keys[0]: self._card()})
        many = self._intro({key: self._card() for key in keys})

        assert one == many, (
            "the introduction changes with the number of sections, so it is "
            "carrying a count that goes stale the next time one is added"
        )

    def test_the_intro_names_no_competition(self) -> None:
        """Naming one rots the same way a count does — the sentence outlives
        the competition it mentions."""
        intro = "\n".join(self._intro({key: self._card() for key in COMPETITIONS}))

        for spec in COMPETITIONS.values():
            assert spec.name not in intro, (
                f"the introduction names {spec.name}, which has to be revisited "
                "whenever that competition is removed or renamed"
            )


class TestTheInternationalCardSaysHowStaleItsRatingsAre:
    """The results archive behind the international pool runs about a month
    behind, so by a window's third matchday the fit has not seen the first two.
    A card that does not say so reads as current: on 2026-09-23 the archive
    ended 2026-08-26 while this card was pricing that day's fixtures.
    """

    @staticmethod
    def _feed() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "competition": "UNL",
                    "home_team": "Spain",
                    "away_team": "France",
                    "market": "btts",
                    "selection": selection,
                    "american_odds": -110,
                    "book": "Book",
                    "observed_at": "2026-09-22T12:00:00Z",
                }
                for selection in ("yes", "no")
            ]
        )

    def test_the_cut_off_date_is_on_the_card(self, monkeypatch) -> None:
        _stub_international_pool(monkeypatch)

        card = build_extra_card(self._feed(), "UNL")

        stale = [note for note in card.notes if "no result after" in note]
        assert stale, "the card does not say how old its ratings are"
        assert "archive runs about a month behind" in stale[0]

    def test_a_club_competition_does_not_claim_a_stale_archive(
        self, monkeypatch
    ) -> None:
        """The note belongs to the international pool. The European pools are
        rebuilt from Football-Data every run and are not a month behind.

        `_pool_for` is stubbed rather than passing an empty feed: an empty feed
        returns before the notes are built at all, so the first version of this
        test passed with the condition replaced by `if True` — it never reached
        the branch it names.
        """
        from epl_betting_lab.data.international_results import parse_archive
        from epl_betting_lab.models import international_ratings

        header = (
            "date,home_team,away_team,home_score,away_score,tournament,city,"
            "country,neutral"
        )
        rows = [
            f"2024-{1 + i % 12:02d}-05,Spain,France,2,1,UEFA Nations League,"
            f"Town,Country,FALSE"
            for i in range(20)
        ]
        matches = parse_archive("\n".join([header, *rows]) + "\n").matches
        monkeypatch.setattr(
            "epl_betting_lab.reports.extra_competitions_card._pool_for",
            lambda spec: (matches, international_ratings.INTERNATIONAL_RATINGS, None),
        )

        card = build_extra_card(
            self._feed().assign(competition="UCL"), "UCL"
        )

        assert card.priced, "the stub did not price anything, so no note was reachable"
        assert not [note for note in card.notes if "no result after" in note]


class TestTheInternationalPoolDoesNotBetTheGoalsLevel:
    """Measured against the de-vigged market across 45 live Nations League
    fixtures, the model put P(over 2.5) at 0.418 where the market said 0.499 —
    eight points low, the same direction on every fixture. Every "under" and
    every "BTTS no" it produced was that standing gap rather than anything
    about the fixture, and three of the first four selections this section ever
    made were low-scoring bets.

    The result markets survive because they turn on the strength difference
    rather than the level, and a competition-specific baseline closed most of
    the separate bias there (draw-no-bet +0.051 -> +0.021).
    """

    @staticmethod
    def _feed(market: str, selections) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "competition": "UNL",
                    "home_team": "Spain",
                    "away_team": "France",
                    "market": market,
                    "selection": selection,
                    "american_odds": 250,
                    "book": "Book",
                    "observed_at": "2026-09-22T12:00:00Z",
                }
                for selection in selections
            ]
        )

    @staticmethod
    def _bettable(market: str, selection: str):
        """A stand-in evaluator that returns one selection the card would take.

        The evaluators are patched rather than fed a clever price, because on a
        small fixture they cannot produce a selection at all: the anchored
        totals rule needs a market probability it cannot derive from one book
        and returns no rows, and the BTTS shrinkage cuts even a 30-point raw
        edge to 1.5 points, below every threshold. Both facts made the first
        version of this test pass on a feed that could never have produced a
        selection — so it stayed green with the exclusion deleted.

        On the real feed these markets do clear: the first international card
        ever built took an under 2.5 and two BTTS-no.
        """

        def evaluator(projections, odds, *args, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "home_team": "Spain",
                        "away_team": "France",
                        "market": market,
                        "selection": selection,
                        "american_odds": 120,
                        "book": "Book",
                        "status": "BETTABLE",
                        "calibrated_edge": 0.09,
                        "raw_edge": 0.09,
                    }
                ]
            )

        return evaluator

    @pytest.mark.parametrize(
        "market, selection, target",
        [
            ("total_2_5", "under", "evaluate_total_25_anchored"),
            ("btts", "no", "evaluate_btts"),
        ],
    )
    def test_a_goals_level_market_produces_no_selection(
        self, market, selection, target, monkeypatch
    ) -> None:
        _stub_international_pool(monkeypatch)
        monkeypatch.setattr(
            f"epl_betting_lab.reports.extra_competitions_card.{target}",
            self._bettable(market, selection),
        )

        card = build_extra_card(self._feed(market, (selection,)), "UNL")

        assert card.selections.empty, (
            f"{market} reached the card; it is priced by a standing eight-point "
            "gap against the market, not by the fixture"
        )

    @pytest.mark.parametrize(
        "market, selection, target",
        [
            ("total_2_5", "under", "evaluate_total_25_anchored"),
            ("btts", "no", "evaluate_btts"),
        ],
    )
    def test_the_same_selection_survives_when_the_market_is_allowed(
        self, market, selection, target, monkeypatch
    ) -> None:
        """The control, and the reason the test above means anything. Without
        it the exclusion could be deleted with the suite still green."""
        _stub_international_pool(monkeypatch)
        monkeypatch.setattr(
            f"epl_betting_lab.reports.extra_competitions_card.{target}",
            self._bettable(market, selection),
        )
        monkeypatch.setattr(
            "epl_betting_lab.reports.extra_competitions_card.POOL_EXCLUDED_MARKETS",
            {},
        )

        card = build_extra_card(self._feed(market, (selection,)), "UNL")

        assert set(card.selections["market"]) == {market}, (
            "the selection could not survive even with the exclusion removed, "
            "so the test above guards nothing"
        )

    def test_the_card_says_which_markets_it_withheld(self, monkeypatch) -> None:
        """Withholding silently would read as the provider not quoting them."""
        _stub_international_pool(monkeypatch)

        card = build_extra_card(self._feed("total_2_5", ("over", "under")), "UNL")

        assert any("total_2_5" in note and "not bet here" in note for note in card.notes)

    def test_a_result_market_is_still_bet(self, monkeypatch) -> None:
        """The exclusion must be the two goals-level markets, not the section.

        The price is derived from the model rather than written down. A fixed
        long price made this test pass for the wrong reason at first: it implied
        a 57-point raw edge, which the shrinkage correctly cut to 2.9 points and
        graded LEAN, so the section produced nothing and the test read that as
        the exclusion being too wide. A modest edge is what a real card sees.
        """
        _stub_international_pool(monkeypatch)
        from epl_betting_lab.reports.extra_competitions_card import _pool_for
        from epl_betting_lab.models.poisson_goals import PoissonGoalsModel

        matches, config, baseline = _pool_for(COMPETITIONS["UNL"])
        model = PoissonGoalsModel().fit(matches, config=config)
        if baseline is not None:
            model.avg_home_goals, model.avg_away_goals = baseline
        probability = model.match_probabilities("Spain", "France")["draw_no_bet_home"]
        # A price implying twelve points less than the model says.
        implied = max(probability - 0.12, 0.05)
        american = int(round(100 * (1 - implied) / implied))

        feed = self._feed("draw_no_bet", ("home", "away"))
        feed.loc[feed["selection"] == "home", "american_odds"] = american

        card = build_extra_card(feed, "UNL")

        assert not card.selections.empty, (
            "barring the goals markets also silenced the result markets"
        )
        assert set(card.selections["market"]) == {"draw_no_bet"}

    def test_a_club_competition_still_bets_the_goals_markets(self) -> None:
        """The bar belongs to the international pool. The Champions League has
        a measured European scale behind its totals."""
        from epl_betting_lab.reports.extra_competitions_card import (
            POOL_EXCLUDED_MARKETS,
        )

        assert POOL_EXCLUDED_MARKETS.get("european") is None
        assert POOL_EXCLUDED_MARKETS.get("english") is None
        assert POOL_EXCLUDED_MARKETS["international"] == frozenset({"total_2_5", "btts"})


class TestTheCardPricesWithTheCompetitionsOwnBaseline:
    """`PoissonGoalsModel` takes its baselines from the mean of the frame it is
    fitted on. For a domestic league that is right — every row is one
    competition at a real venue. For the international pool it is neither: the
    frame mixes competitions whose home advantage runs from +0.35 to +0.77 and
    mixes real-venue rows with neutral ones.
    """

    def test_the_override_is_the_competitions_real_venue_baseline(self) -> None:
        from epl_betting_lab.models.international_ratings import (
            build_international_pool,
            fit_international_model,
        )
        from epl_betting_lab.reports.extra_competitions_card import _pool_for

        matches, _config, baseline = _pool_for(COMPETITIONS["UNL"])
        fitted = fit_international_model(build_international_pool())

        assert baseline is not None, "the card is still pricing off the pooled mean"
        assert baseline == fitted.competition_baselines[("UNL", False)]
        assert baseline != fitted.competition_baselines.get(("UNL", True)), (
            "the neutral baseline is being used for a fixture priced at a venue"
        )
        pooled = (fitted.venue_home, fitted.venue_away)
        assert baseline != pooled, (
            "the competition's baseline equals the pool's, so nothing is corrected"
        )

    def test_a_club_competition_has_no_override(self, monkeypatch) -> None:
        """The club pools are built from fetched datasets that do not exist on
        a clean checkout, so they are stubbed. The assertion is about the
        branch, not about the data: a club competition must come back with no
        baseline override, because its frame really is one competition at real
        venues and the fitted mean is the right number for it.
        """
        from types import SimpleNamespace

        from epl_betting_lab.reports.extra_competitions_card import _pool_for

        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01"]),
                "home_team": ["A"],
                "away_team": ["B"],
                "home_goals": [1],
                "away_goals": [1],
            }
        )
        monkeypatch.setattr(
            "epl_betting_lab.reports.extra_competitions_card.build_european_pool",
            lambda: SimpleNamespace(matches=frame),
        )
        monkeypatch.setattr(
            "epl_betting_lab.reports.extra_competitions_card.build_pool",
            lambda: frame,
        )

        for key in ("UCL", "EFLC"):
            _matches, _config, baseline = _pool_for(COMPETITIONS[key])
            assert baseline is None, f"{key} is being handed an override it should not get"


class TestTheCardActuallyAppliesTheBaseline:
    """`_pool_for` returning the right number and the card using it are two
    different facts, and only the first was tested — so deleting the line that
    applies it left the whole suite green. The same producer/consumer gap that
    let a task filename be renamed on one side only.
    """

    @staticmethod
    def _capture(store: dict):
        def evaluator(projections, odds, *args, **kwargs):
            store["projections"] = projections.copy()
            return pd.DataFrame()

        return evaluator

    def test_the_priced_expected_goals_come_from_the_competition_baseline(
        self, monkeypatch
    ) -> None:
        from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
        from epl_betting_lab.reports.extra_competitions_card import _pool_for

        _stub_international_pool(monkeypatch)
        matches, config, baseline = _pool_for(COMPETITIONS["UNL"])
        assert baseline is not None

        without = PoissonGoalsModel().fit(matches, config=config)
        pooled_xg = without.expected_goals("Spain", "France")[0]
        with_override = PoissonGoalsModel().fit(matches, config=config)
        with_override.avg_home_goals, with_override.avg_away_goals = baseline
        corrected_xg = with_override.expected_goals("Spain", "France")[0]
        assert pooled_xg != pytest.approx(corrected_xg), (
            "the stub pool cannot tell the two baselines apart, so this test "
            "would pass either way"
        )

        store: dict = {}
        monkeypatch.setattr(
            "epl_betting_lab.reports.extra_competitions_card.evaluate_draw_no_bet",
            self._capture(store),
        )
        build_extra_card(
            pd.DataFrame(
                [
                    {
                        "competition": "UNL",
                        "home_team": "Spain",
                        "away_team": "France",
                        "market": "draw_no_bet",
                        "selection": selection,
                        "american_odds": 120,
                        "book": "Book",
                        "observed_at": "2026-09-22T12:00:00Z",
                    }
                    for selection in ("home", "away")
                ]
            ),
            "UNL",
        )

        priced = store["projections"].iloc[0]["home_xg"]
        assert priced == pytest.approx(corrected_xg), (
            "the card priced off the pooled baseline, not the competition's"
        )
