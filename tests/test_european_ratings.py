"""The bridge between countries, and the names that make it possible.

Every test here guards something that fails silently. A wrong name rates a
different club. A missing date files a tie before the ratings that should have
predicted it. An unlinked pool gives each country its own scale and says nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from epl_betting_lab.config import COUNTRY_TO_LEAGUE
from epl_betting_lab.data.european_clubs import EUROPEAN_CLUB_NAMES, domestic_name
from epl_betting_lab.data.european_results import (
    EuropeanResultsUnavailable,
    load_european_ties,
    parse_season,
)
from epl_betting_lab.models.european_ratings import BridgeResult, build_european_pool

SEASON_TEXT = """= UEFA Champions League 2023/24

▪ Group, Matchday 1
  Tue Sep 19 2023
    18:45  AC Milan (ITA)          v Newcastle United FC (ENG)  0-0
           Paris Saint-Germain FC (FRA) v Borussia Dortmund (GER)  2-0 (0-0)
  Wed Sep 20 2023
    21:00  FK Shakhtar Donetsk (UKR) v FC Porto (POR)           1-3 (1-3)
           Real Madrid CF (ESP)    v 1. FC Union Berlin (GER)  1-0 (0-0)
"""


class TestTheNamesAreWrittenDownNotGuessed:
    def test_paris_saint_germain_is_not_paris_fc(self) -> None:
        """The entry the whole module exists for. Normalising the strings
        proposes `Paris FC` — a different, recently promoted club — and a wrong
        name does not fail, it silently rates somebody else. On 46 European
        appearances."""
        assert domestic_name("Paris Saint-Germain FC", "FRA") == "Paris SG"
        assert domestic_name("Paris Saint-Germain", "FRA") == "Paris SG"

    def test_the_two_madrid_clubs_are_not_swapped(self) -> None:
        """Football-Data writes both as `Ath`, one word apart."""
        assert domestic_name("Club Atlético de Madrid", "ESP") == "Ath Madrid"
        assert domestic_name("Atlético Madrid", "ESP") == "Ath Madrid"
        assert domestic_name("Athletic Club", "ESP") == "Ath Bilbao"

    def test_one_club_written_two_ways_maps_to_one_name(self) -> None:
        """openfootball is not self-consistent across seasons."""
        assert domestic_name("Bayern München", "GER") == domestic_name(
            "FC Bayern München", "GER"
        )
        assert domestic_name("Tottenham Hotspur", "ENG") == domestic_name(
            "Tottenham Hotspur FC", "ENG"
        )

    def test_monaco_plays_in_france(self) -> None:
        """openfootball files it under its own country; without the entry a
        Ligue 1 club sits unrated and 20 appearances resolve to nothing."""
        assert COUNTRY_TO_LEAGUE["MCO"] == "F1"
        assert domestic_name("AS Monaco FC", "MCO") == "Monaco"

    def test_a_country_with_no_feed_resolves_to_nothing(self) -> None:
        """Returning the name unchanged would let it flow into a rating lookup
        and miss, which is the same outcome by a longer road."""
        assert domestic_name("FK Shakhtar Donetsk", "UKR") is None

    def test_every_mapped_country_has_a_league(self) -> None:
        for country in EUROPEAN_CLUB_NAMES:
            assert country in COUNTRY_TO_LEAGUE, country


class TestParsingATie:
    def test_both_clubs_are_resolved_to_domestic_names(self) -> None:
        parsed = parse_season(SEASON_TEXT, "2023-24")
        rows = parsed.matches
        assert ("Milan", "Newcastle") in set(zip(rows["home_team"], rows["away_team"]))
        assert ("Paris SG", "Dortmund") in set(zip(rows["home_team"], rows["away_team"]))

    def test_a_tie_with_an_unrateable_club_is_dropped_and_counted(self) -> None:
        """Shakhtar are Ukrainian and Football-Data publishes no Ukrainian
        league. The tie cannot be used and the appearance is recorded, because
        coverage is a fact worth reporting rather than a parse failure."""
        parsed = parse_season(SEASON_TEXT, "2023-24")
        assert "Porto" not in set(parsed.matches["home_team"]) | set(
            parsed.matches["away_team"]
        )
        assert ("FK Shakhtar Donetsk", "UKR") in parsed.unresolved

    def test_the_date_comes_from_the_header_above_the_match(self) -> None:
        parsed = parse_season(SEASON_TEXT, "2023-24")
        first = parsed.matches.iloc[0]
        assert first["date"] == pd.Timestamp("2023-09-19")
        last = parsed.matches.iloc[-1]
        assert last["date"] == pd.Timestamp("2023-09-20")

    def test_a_match_with_no_date_header_is_dropped(self) -> None:
        """Filing it under the season's first day would place a tie before the
        ratings that should have predicted it, leaking the result into its own
        forecast."""
        headerless = "    18:45  AC Milan (ITA) v Newcastle United FC (ENG)  0-0\n"
        assert parse_season(headerless, "2023-24").matches.empty

    def test_the_score_is_read_not_the_half_time_score(self) -> None:
        parsed = parse_season(SEASON_TEXT, "2023-24")
        psg = parsed.matches[parsed.matches["home_team"] == "Paris SG"].iloc[0]
        assert (psg["home_goals"], psg["away_goals"]) == (2, 0)


class TestAFailedFetchIsNotAnEmptySeason:
    def test_every_season_failing_raises(self) -> None:
        """An empty frame would remove every bridge and leave the countries
        unlinked, which looks exactly like a season nobody played."""

        def broken(season: str) -> str:
            raise EuropeanResultsUnavailable(f"{season} is not there")

        with pytest.raises(EuropeanResultsUnavailable, match="no country can be linked"):
            load_european_ties(("2023-24",), fetcher=broken)

    def test_one_season_failing_costs_only_its_own_bridges(self) -> None:
        def sometimes(season: str) -> str:
            if season == "2024-25":
                raise EuropeanResultsUnavailable("not published yet")
            return SEASON_TEXT

        parsed = load_european_ties(("2023-24", "2024-25"), fetcher=sometimes)
        assert not parsed.matches.empty
        assert set(parsed.matches["season"]) == {"2023-24"}


class TestTheBridgeInterval:
    def test_it_resamples_ties_not_innings(self) -> None:
        """A tie's two innings share one match and one pair of ratings."""
        result = BridgeResult(
            joint_rmse=1.0,
            naive_rmse=2.0,
            ties=2,
            per_tie=np.array([[1.0, 4.0], [1.0, 4.0]]),
        )
        low, high = result.interval(draws=200)
        assert low == pytest.approx(-1.0) and high == pytest.approx(-1.0)

    def test_an_empty_measurement_reports_nothing_rather_than_zero(self) -> None:
        low, high = BridgeResult(float("nan"), float("nan"), 0).interval()
        assert np.isnan(low) and np.isnan(high)

    def test_improvement_is_a_percentage_of_the_naive_baseline(self) -> None:
        assert BridgeResult(0.9, 1.0, 10).improvement == pytest.approx(10.0)


class TestBuildingThePool:
    def test_a_missing_league_is_named_rather_than_skipped(self, monkeypatch, tmp_path) -> None:
        """Quietly building ten leagues and calling it eleven would leave one
        country's clubs unrated with nothing saying so."""
        monkeypatch.setattr(
            "epl_betting_lab.models.european_ratings.processed_path_for",
            lambda code: tmp_path / f"{code}.csv",
        )
        with pytest.raises(FileNotFoundError, match="No dataset for"):
            build_european_pool({"ENG": "E0"})
