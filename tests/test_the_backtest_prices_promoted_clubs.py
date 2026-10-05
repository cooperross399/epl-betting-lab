"""The league's own walk-forward must price a promoted club.

The unrated-team guard (#286) refuses a team the fit never saw, which is right
for a cup tie against a club from another league. The backtest trains on one
league's history, so an unseen team there is always a promoted club. Without
`allow_unrated=True` the Weekly Lab Check crashed on the first fixture of the
second season (Nott'm Forest, promoted 2022-23), every week from 2026-09-14.
"""
from __future__ import annotations

import pandas as pd

from epl_betting_lab.backtest.walk_forward import run_walk_forward_backtest
from epl_betting_lab.models.poisson_goals import UnratedTeam
from epl_betting_lab.reports.btts_calibration import RatingsUnderTest, walk_forward_btts
from epl_betting_lab.reports.out_of_sample import walk_forward_probabilities


def _two_seasons() -> pd.DataFrame:
    """Season one among A-D; season two adds a promoted club, E."""
    first = ["A", "B", "C", "D"]
    second = ["A", "B", "C", "E"]
    rows = []
    day = pd.Timestamp("2021-08-14")
    for season, teams in (("2122", first), ("2223", second)):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                rows.append({
                    "season": season, "date": day, "home_team": home, "away_team": away,
                    "home_goals": (len(home) + len(away) + day.day) % 4,
                    "away_goals": day.day % 3,
                    "AvgH": 2.4, "AvgD": 3.3, "AvgA": 3.1,
                    "Avg>2.5": 1.95, "Avg<2.5": 1.9,
                    "HS": 13, "AS": 10, "HST": 5, "AST": 4, "HC": 6, "AC": 4,
                })
                day += pd.Timedelta(days=3)
    return pd.DataFrame(rows)


def test_the_backtest_reaches_a_promoted_club() -> None:
    matches = _two_seasons()
    start = int((matches["season"] == "2122").sum())

    try:
        run_walk_forward_backtest(matches, start_after_matches=start)
    except UnratedTeam as refusal:  # pragma: no cover - the regression
        raise AssertionError(f"the backtest refused a promoted club: {refusal}") from refusal


def test_the_out_of_sample_and_btts_walks_reach_one_too() -> None:
    matches = _two_seasons()
    start = int((matches["season"] == "2122").sum())

    probs = walk_forward_probabilities(matches, start_after_matches=start)
    assert "E" in set(probs["home_team"]).union(probs["away_team"])
    btts = walk_forward_btts(matches, RatingsUnderTest("legacy", None, 38), start_after_matches=start)
    assert len(btts) == len(matches) - start
