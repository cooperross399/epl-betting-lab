"""National teams: the venue, the names, and the things that fail quietly.

Every test here guards something that does not raise when it goes wrong. A
neutral fixture priced with a home baseline produces a confident number that is
half a goal out. A tournament name matched by substring rates the wrong
competition. A scoreless row read as 0-0 invents a result.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.data.international_results import (
    COMPETITION_OF,
    InternationalResultsUnavailable,
    load_international_results,
    parse_archive,
)
from epl_betting_lab.data.international_teams import PROVIDER_TEAM_NAMES, archive_name
from epl_betting_lab.models.international_ratings import (
    MIN_MATCHES,
    build_international_pool,
    fit_international_model,
)
from epl_betting_lab.models.poisson_goals import UnratedTeam

HEADER = "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral"


def _archive(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def _many(
    team_a: str,
    team_b: str,
    n: int,
    *,
    neutral: str = "FALSE",
    home_goals: int = 2,
    away_goals: int = 1,
) -> list[str]:
    """Enough meetings for both sides to clear MIN_MATCHES.

    The scores are parameters because the first version of this helper wrote
    2-1 on every row: both baselines then came out at exactly 2.0 and 1.0, and
    the test asserting they differ was comparing a constant to itself. A
    fixture that cannot vary cannot measure anything.
    """
    return [
        f"20{15 + i // 12:02d}-{1 + i % 12:02d}-05,{team_a},{team_b},"
        f"{home_goals},{away_goals},UEFA Nations League,Town,Country,{neutral}"
        for i in range(n)
    ]


class TestTheVenueIsNotGuessed:
    def test_neutral_is_a_boolean_not_a_truthy_string(self) -> None:
        """The archive writes TRUE/FALSE. Left as strings every value is
        truthy, which marks every fixture neutral and erases home advantage
        from the entire pool — without raising anything."""
        parsed = parse_archive(
            _archive(
                "2024-06-01,Spain,France,1,0,UEFA Nations League,Madrid,Spain,FALSE",
                "2024-06-02,Italy,Germany,1,1,UEFA Nations League,Doha,Qatar,TRUE",
            )
        )

        assert parsed.matches["neutral"].dtype == bool
        assert list(parsed.matches["neutral"]) == [False, True]

    def test_the_neutral_baseline_carries_less_home_advantage(self) -> None:
        """The whole reason this module exists. Venue rows carry a two-goal
        edge to the home side and neutral rows none; if the baselines were
        pooled, the neutral fixtures would inherit an advantage no side has."""
        rows = _many("Spain", "France", 20, home_goals=3, away_goals=1) + _many(
            "Italy", "Germany", 20, neutral="TRUE", home_goals=1, away_goals=1
        )
        model = fit_international_model(
            build_international_pool(results=parse_archive(_archive(*rows)))
        )

        venue_edge = model.venue_home - model.venue_away
        neutral_edge = model.neutral_home - model.neutral_away

        assert venue_edge == pytest.approx(2.0)
        assert neutral_edge == pytest.approx(0.0)
        assert neutral_edge < venue_edge

    def test_the_venue_changes_the_price_of_the_same_fixture(self) -> None:
        """The baselines existing is not the same as them being used."""
        rows = _many("Spain", "France", 20, home_goals=3, away_goals=1) + _many(
            "Italy", "Germany", 20, neutral="TRUE", home_goals=1, away_goals=1
        )
        model = fit_international_model(
            build_international_pool(results=parse_archive(_archive(*rows)))
        )

        at_venue = model.expected_goals("Spain", "France", neutral=False)
        on_neutral = model.expected_goals("Spain", "France", neutral=True)

        assert at_venue != on_neutral
        assert at_venue[0] - at_venue[1] > on_neutral[0] - on_neutral[1], (
            "the nominal home side must not keep its advantage on neutral ground"
        )

    def test_expected_goals_will_not_assume_a_venue(self) -> None:
        """`neutral` is keyword-only with no default on purpose: a third of
        competitive internationals are on neutral ground and the wrong baseline
        is worth about half a goal, so a caller that has not decided must not
        get a silent default."""
        rows = _many("Spain", "France", 20, home_goals=3) + _many(
            "Italy", "Germany", 20, neutral="TRUE"
        )
        model = fit_international_model(
            build_international_pool(results=parse_archive(_archive(*rows)))
        )

        with pytest.raises(TypeError):
            model.expected_goals("Spain", "France")

    def test_a_pool_with_one_venue_type_refuses_to_fit(self) -> None:
        """Both baselines would be fitted on the same rows and silently agree,
        which reads as "venue does not matter here" rather than "this pool
        cannot answer the question"."""
        pool = build_international_pool(
            results=parse_archive(_archive(*_many("Spain", "France", 20)))
        )

        with pytest.raises(ValueError, match="one venue type"):
            fit_international_model(pool)


class TestTheCompetitionIsDeclaredNotMatched:
    def test_a_qualifying_round_is_not_its_tournament(self) -> None:
        """"CONCACAF Nations League qualification" contains "CONCACAF Nations
        League". A substring match would file qualifiers as the competition
        itself, and they are a different fixture population."""
        assert COMPETITION_OF["CONCACAF Nations League"] == "CNL"
        assert COMPETITION_OF["CONCACAF Nations League qualification"] == "CNLQ"
        assert COMPETITION_OF["UEFA Euro"] != COMPETITION_OF["UEFA Euro qualification"]

    def test_an_unlisted_tournament_is_kept_under_one_code(self) -> None:
        """Regional cups are real matches between rateable sides and inform a
        rating. Dropping them would quietly shrink the pool."""
        parsed = parse_archive(
            _archive("2024-06-01,Fiji,Samoa,1,0,Pacific Games,Suva,Fiji,FALSE")
        )

        assert list(parsed.matches["competition"]) == ["OTHER"]

    def test_friendlies_are_separable_from_the_competitive_record(self) -> None:
        parsed = parse_archive(
            _archive(
                "2024-06-01,Spain,France,1,0,Friendly,Madrid,Spain,FALSE",
                "2024-06-05,Italy,Germany,1,1,UEFA Nations League,Rome,Italy,FALSE",
            )
        )

        assert len(parsed.matches) == 2
        assert list(parsed.competitive["competition"]) == ["UNL"]


class TestAnArchiveThatChangedShapeIsNotAnEmptySeason:
    def test_a_missing_column_raises_rather_than_parsing_every_row_wrong(self) -> None:
        text = "date,home_team,away_team,home_score,away_score,tournament\n"
        with pytest.raises(InternationalResultsUnavailable, match="shape has changed"):
            parse_archive(text)

    def test_a_fetch_failure_raises_rather_than_returning_no_teams(self) -> None:
        def broken() -> str:
            raise InternationalResultsUnavailable("404")

        with pytest.raises(InternationalResultsUnavailable):
            load_international_results(fetcher=broken)

    def test_a_match_with_no_score_is_dropped_not_read_as_a_draw(self) -> None:
        """A fixture with no result is not 0-0, and filling it would put a
        drawn match into every team's record."""
        parsed = parse_archive(
            _archive(
                "2026-11-01,Spain,France,,,UEFA Nations League,Madrid,Spain,FALSE",
                "2024-06-05,Italy,Germany,1,1,UEFA Nations League,Rome,Italy,FALSE",
            )
        )

        assert len(parsed.matches) == 1
        assert parsed.matches.iloc[0]["home_team"] == "Italy"


class TestTeamsTheModelHasNotSeen:
    def test_a_team_below_the_threshold_is_refused_not_averaged(self) -> None:
        rows = (
            _many("Spain", "France", 20, home_goals=3)
            + _many("Italy", "Germany", 20, neutral="TRUE")
            + ["2024-06-09,Spain,Tuvalu,9,0,Friendly,Madrid,Spain,FALSE"]
        )
        pool = build_international_pool(results=parse_archive(_archive(*rows)))
        model = fit_international_model(pool)

        assert "Tuvalu" not in pool.rateable
        with pytest.raises(UnratedTeam, match=str(MIN_MATCHES)):
            model.expected_goals("Spain", "Tuvalu", neutral=False)


class TestTheProviderSpellsCountriesItsOwnWay:
    def test_an_unmapped_name_falls_through_unchanged(self) -> None:
        assert archive_name("Spain") == "Spain"

    def test_the_one_name_the_provider_spells_differently(self) -> None:
        """Observed across 1,162 Nations League price observations, not
        guessed. The guessable ones — Czechia, Ireland, Türkiye — would all
        have been wrong: the provider agrees with the archive on every one of
        them, and disagrees only here."""
        assert archive_name("Bosnia & Herzegovina") == "Bosnia and Herzegovina"

    def test_the_names_that_look_risky_need_no_entry(self) -> None:
        """Guarding against a future well-meaning addition. Mapping these would
        point a real fixture at a country the pool does not have."""
        for name in ("Czech Republic", "Republic of Ireland", "Turkey", "North Macedonia"):
            assert archive_name(name) == name
            assert name not in PROVIDER_TEAM_NAMES

    def test_national_teams_do_not_share_the_club_name_map(self) -> None:
        """Two vocabularies in one dictionary is how a word came to mean the
        provider in one table and the results feed in another."""
        from epl_betting_lab.data import european_clubs

        assert PROVIDER_TEAM_NAMES is not european_clubs.PROVIDER_CLUB_NAMES


class TestThePoolSaysHowStaleItIs:
    """The source archive runs about a month behind. Read on 2026-09-23 it
    ended 2026-08-26 and held no September fixtures at all — not even the
    matches the card was pricing that day. Two things followed: the ratings
    never include the current window, and an absence in the archive was read as
    evidence a competition had stopped being played, which it cannot support.
    """

    @staticmethod
    def _pool():
        rows = _many("Spain", "France", 20, home_goals=3) + _many(
            "Italy", "Germany", 20, neutral="TRUE"
        )
        return build_international_pool(results=parse_archive(_archive(*rows)))

    def test_the_pool_reports_its_most_recent_result(self) -> None:
        pool = self._pool()

        assert pool.latest_result is not None
        assert pool.latest_result == pool.matches["date"].max()

    def test_an_empty_pool_reports_no_date_rather_than_today(self) -> None:
        """A pool with nothing in it is not a pool that is up to date."""
        empty = build_international_pool(results=parse_archive(_archive()))

        assert empty.latest_result is None
        assert empty.days_behind() is None

    def test_days_behind_counts_from_the_last_result(self) -> None:
        pool = self._pool()
        latest = pool.latest_result

        assert pool.days_behind(latest) == 0
        assert pool.days_behind(latest + pd.Timedelta(days=28)) == 28
