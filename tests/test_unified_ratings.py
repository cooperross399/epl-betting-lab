"""One scale across four divisions, and the honesty about what it buys.

The measurement this module exists for is a negative one: a club's rating does
not survive a promotion. These tests pin the machinery that produced it, so the
finding cannot quietly stop being true.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, TeamStrength
from epl_betting_lab.models.unified_ratings import (
    CARRIED_RATING_SHARE,
    DIVISIONS,
    UNIFIED_RATINGS,
    CarryResult,
    build_pool,
    division_by_season,
    division_changes,
    measure_carry,
    scale_by_division,
)


def _pool() -> pd.DataFrame:
    """Two divisions, two seasons, with one club promoted between them."""
    rows = []
    for season, fixtures in {
        "2425": [
            ("E0", "Alpha", "Bravo"), ("E0", "Bravo", "Alpha"),
            ("E1", "Charlie", "Delta"), ("E1", "Delta", "Charlie"),
        ],
        "2526": [
            ("E0", "Alpha", "Charlie"), ("E0", "Charlie", "Alpha"),
            ("E1", "Bravo", "Delta"), ("E1", "Delta", "Bravo"),
        ],
    }.items():
        for index, (division, home, away) in enumerate(fixtures):
            rows.append(
                {
                    "season": season,
                    "division": division,
                    "date": pd.Timestamp(f"20{season[:2]}-08-{10 + index:02d}"),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": 2,
                    "away_goals": 1,
                }
            )
    return pd.DataFrame(rows)


class TestTheDivisionTravelsOnTheRow:
    def test_pooling_is_the_one_place_it_is_intended(self) -> None:
        """The dataset builder refuses to write one division's matches into
        another's file, because a rating fitted across divisions with no common
        scale is wrong in a way nothing downstream reports. Here the pooling is
        the point, so the division is carried rather than lost."""
        pool = _pool()
        assert set(pool["division"]) == {"E0", "E1"}
        assert len(pool) == 8

    def test_a_missing_dataset_is_named_rather_than_skipped(self, monkeypatch, tmp_path) -> None:
        """Silently building a three-division pool and calling it four would
        put the missing division's clubs nowhere and nothing would say so."""
        monkeypatch.setattr(
            "epl_betting_lab.models.unified_ratings.processed_path_for",
            lambda division: tmp_path / f"{division}.csv",
        )
        with pytest.raises(FileNotFoundError, match="No dataset for E0"):
            build_pool(("E0",))


class TestPromotionIsTheOnlyBridge:
    def test_a_club_that_changes_division_is_found(self) -> None:
        moves = division_changes(_pool())
        assert ("Charlie", "E1", "E0", "2526") in moves
        assert ("Bravo", "E0", "E1", "2526") in moves

    def test_a_club_that_stays_put_is_not(self) -> None:
        assert not [m for m in division_changes(_pool()) if m[0] == "Alpha"]

    def test_each_club_gets_one_division_per_season(self) -> None:
        seen = division_by_season(_pool())
        assert not seen.duplicated(["season", "team"]).any()


class TestTheScaleMustComeOutMonotone:
    def _model(self, attacks: dict[str, float]) -> PoissonGoalsModel:
        model = PoissonGoalsModel()
        model.team_strengths = {
            team: TeamStrength(attack, 1.0 / attack) for team, attack in attacks.items()
        }
        model.avg_home_goals, model.avg_away_goals = 1.5, 1.2
        return model

    # In the final season Alpha and Charlie play E0; Bravo and Delta play E1.
    # Both tests set all four deliberately, because a fixture that puts one
    # strong and one weak club in each division gives identical means and then
    # neither passes nor fails for the reason it claims.
    def test_a_sensible_fit_is_ordered_by_division(self) -> None:
        scale = scale_by_division(
            self._model({"Alpha": 1.4, "Charlie": 1.3, "Bravo": 0.8, "Delta": 0.7}),
            _pool(),
        )
        attacks = scale["attack"].tolist()
        assert attacks == sorted(attacks, reverse=True), scale
        assert attacks[0] > attacks[1]

    def test_the_check_can_fail(self) -> None:
        """A monotonicity check that cannot fail would pass on the pooled
        unadjusted ratings, which rate the bottom division level with the top.
        """
        scale = scale_by_division(
            self._model({"Alpha": 0.7, "Charlie": 0.7, "Bravo": 1.4, "Delta": 1.4}),
            _pool(),
        )
        attacks = scale["attack"].tolist()
        assert attacks != sorted(attacks, reverse=True), scale
        assert attacks[0] < attacks[1]


class TestTheConfigurationIsTheOneThatCanSeeADivisionGap:
    def test_it_is_opponent_adjusted(self) -> None:
        """An unadjusted ratio is a team's goals against the league average, and
        it has no way to know the league changed."""
        assert UNIFIED_RATINGS.opponent_adjusted is True

    def test_it_asks_for_goals_not_a_blend(self) -> None:
        """Understat publishes no xG below the Premier League, so a blend here
        would silently be this same goals fit wearing another name."""
        assert UNIFIED_RATINGS.goal_source == "goals"


class TestWhatACarriedRatingIsWorth:
    def test_the_measured_share_is_recorded_not_chosen(self) -> None:
        assert 0.0 <= CARRIED_RATING_SHARE <= 1.0
        # Measured at 0.15 against a full carry of 1.0. A value near 1 would
        # mean a rating survives a promotion intact, which it does not.
        assert CARRIED_RATING_SHARE < 0.5

    def test_the_interval_resamples_clubs_not_matches(self) -> None:
        """A club's matches all share its rating, so resampling matches would
        treat them as independent and report an interval that is too narrow."""
        result = CarryResult(
            shares=(0.0, 1.0),
            rmse={0.0: 1.0, 1.0: 1.2},
            per_club={0.0: [1.0, 1.0], 1.0: [4.0, 4.0]},
            matches=40,
            clubs=2,
        )
        low, high = result.interval(draws=200)
        # Both clubs identical, so every resample gives the same gap: 2.0 - 1.0.
        assert low == pytest.approx(1.0) and high == pytest.approx(1.0)

    def test_an_empty_measurement_reports_nothing_rather_than_zero(self) -> None:
        low, high = CarryResult(shares=(), rmse={}).interval()
        assert np.isnan(low) and np.isnan(high)

    def test_a_pool_with_no_history_produces_no_measurement(self) -> None:
        """Fitting on a handful of matches and reporting an RMSE would be a
        number with nothing behind it."""
        result = measure_carry(_pool(), min_history=2000)
        assert result.matches == 0
        assert result.clubs == 0


class TestTheDivisionsAreNamedOnceAndInOrder:
    def test_strongest_first(self) -> None:
        assert DIVISIONS == ("E0", "E1", "E2", "E3")
