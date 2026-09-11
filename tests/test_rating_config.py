"""Opponent-adjusted, time-decayed team ratings."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from epl_betting_lab.models.poisson_goals import UnratedTeam, PoissonGoalsModel, RatingConfig


def _matches(rows, start="2026-01-01"):
    dates = pd.date_range(start, periods=len(rows), freq="7D")
    return pd.DataFrame(
        [{"date": d, "home_team": h, "away_team": a, "home_goals": hg, "away_goals": ag}
         for d, (h, a, hg, ag) in zip(dates, rows)]
    )


def _round_robin(strength: dict[str, float], rounds: int = 4, seed: int = 0):
    """A synthetic league where goals follow known attack strengths."""
    rng = np.random.default_rng(seed)
    teams = list(strength)
    rows = []
    for _ in range(rounds):
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                rows.append((h, a, rng.poisson(1.4 * strength[h] / strength[a]), rng.poisson(1.1 * strength[a] / strength[h])))
    return _matches(rows)


def test_legacy_is_the_default_so_nothing_changes_unasked():
    df = _round_robin({"A": 1.0, "B": 1.0, "C": 1.0})
    plain = PoissonGoalsModel().fit(df)
    explicit = PoissonGoalsModel().fit(df, config=RatingConfig.legacy())
    assert plain.team_strengths == explicit.team_strengths


def test_adjusted_ratings_recover_a_known_ordering():
    df = _round_robin({"Strong": 1.6, "Mid": 1.0, "Weak": 0.6}, rounds=12)
    model = PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True))
    s = model.team_strengths
    assert s["Strong"].attack > s["Mid"].attack > s["Weak"].attack
    assert s["Strong"].defense < s["Mid"].defense < s["Weak"].defense


def test_schedule_strength_no_longer_flatters_a_team():
    """Two teams score identically, one only against the weakest side.

    The raw ratio rates them the same. The adjusted fit must not.
    """
    rows = []
    # Padded and Tested each score exactly 2 a game and concede 1, so their raw
    # goals-per-game are identical by construction. Padded only ever meets
    # Weak; Tested only ever meets Strong. Strong and Weak play each other so
    # the fit can learn which of them is which.
    for _ in range(10):
        rows += [("Padded", "Weak", 2, 1), ("Weak", "Padded", 1, 2),
                 ("Tested", "Strong", 2, 1), ("Strong", "Tested", 1, 2),
                 ("Strong", "Weak", 4, 0), ("Weak", "Strong", 0, 4)]
    df = _matches(rows)
    legacy = PoissonGoalsModel().fit(df).team_strengths
    adjusted = PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True)).team_strengths
    # Legacy: goals per game are equal, so the two attacks are equal.
    assert legacy["Padded"].attack == pytest.approx(legacy["Tested"].attack)
    # Adjusted: scoring against Strong is worth more than scoring against Weak.
    assert adjusted["Tested"].attack > adjusted["Padded"].attack


def test_time_decay_makes_recent_form_count_for_more():
    """A team that was bad, then became good — recency should show it."""
    old = [("Riser", "X", 0, 3), ("X", "Riser", 3, 0)] * 8
    new = [("Riser", "X", 3, 0), ("X", "Riser", 0, 3)] * 4
    df = _matches(old + new)
    flat = PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True)).team_strengths
    decayed = PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True, half_life_days=30)).team_strengths
    assert decayed["Riser"].attack > flat["Riser"].attack


def test_a_team_with_no_history_is_shrunk_to_average_not_ignored():
    df = _round_robin({"A": 1.3, "B": 0.8}, rounds=6)
    model = PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True))
    # The prior is still available and still the same contract — it is now
    # asked for out loud, because the model cannot tell a promoted club (this
    # competition, no history yet) from a club in another competition entirely,
    # and the second is where an average-side substitution goes badly wrong.
    home_xg, away_xg = model.expected_goals("A", "Promoted", allow_unrated=True)
    assert home_xg > 0 and away_xg > 0

    with pytest.raises(UnratedTeam):
        model.expected_goals("A", "Promoted")


def test_expected_goals_stay_in_a_sane_range():
    df = _round_robin({"A": 1.5, "B": 1.0, "C": 0.7, "D": 1.1}, rounds=8)
    model = PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True, half_life_days=180))
    for h in "ABCD":
        for a in "ABCD":
            if h != a:
                hx, ax = model.expected_goals(h, a)
                assert 0.2 < hx < 5 and 0.2 < ax < 5


def test_more_prior_matches_means_more_shrinkage():
    df = _round_robin({"A": 1.6, "B": 0.6}, rounds=3)
    loose = PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True, prior_matches=1)).team_strengths
    tight = PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True, prior_matches=40)).team_strengths
    assert abs(tight["A"].attack - 1) < abs(loose["A"].attack - 1)


class TestAModelWillNotPriceATeamItHasNeverSeen:
    """Fitted on the Premier League and asked for a League Two side, the model
    used to substitute `TeamStrength(1.0, 1.0)` — an exactly average club — and
    say nothing. Measured on the real data, it priced AFC Wimbledon to beat
    Liverpool at 27.0% and Grimsby to beat Man City at 11.5%: fair prices of
    +271 and +770 against a market nearer +1200. It would have read the gap as
    several hundred points of edge and staked it, on exactly the fixtures a cup
    competition is made of.

    The model cannot tell that from a promoted club, which is a member of this
    competition with no history in it yet and turns up one to three times every
    August. It sees a training frame, not a league. So the caller has to say,
    and refusing by default means adding a competition fails loudly instead of
    pricing confidently.
    """

    def _league(self) -> PoissonGoalsModel:
        df = _round_robin({"A": 1.6, "B": 1.0, "C": 0.7}, rounds=8)
        return PoissonGoalsModel().fit(df, config=RatingConfig(opponent_adjusted=True))

    def test_an_unseen_team_is_refused(self) -> None:
        with pytest.raises(UnratedTeam, match="no fitted rating"):
            self._league().match_probabilities("A", "Grimsby")

    def test_it_is_refused_from_either_side_of_the_fixture(self) -> None:
        model = self._league()
        with pytest.raises(UnratedTeam):
            model.match_probabilities("Grimsby", "A")

    def test_the_message_names_the_team_and_the_pool(self) -> None:
        """A refusal that does not say which team stalls whoever reads it."""
        try:
            self._league().expected_goals("A", "Grimsby")
        except UnratedTeam as exc:
            assert "Grimsby" in str(exc)
            assert "3 teams" in str(exc)
        else:
            raise AssertionError("expected a refusal")

    def test_a_fixture_between_two_rated_teams_is_untouched(self) -> None:
        """The guard must not refuse the ordinary case — this project has found
        several that did, and they pass their own tests while making the
        feature unusable."""
        probabilities = self._league().match_probabilities("A", "B")
        assert 0.0 < probabilities["home_win"] < 1.0

    def test_the_prior_is_still_available_when_asked_for(self) -> None:
        """A promoted club's league-average prior is reasonable and every
        season needs it. It is the silence that was wrong, not the number."""
        probabilities = self._league().match_probabilities(
            "A", "Promoted", allow_unrated=True
        )
        assert 0.0 < probabilities["home_win"] < 1.0

    def test_it_is_a_key_error_so_existing_handlers_still_catch_it(self) -> None:
        with pytest.raises(KeyError):
            self._league().expected_goals("A", "Grimsby")
