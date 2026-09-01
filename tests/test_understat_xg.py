"""Understat team xG reaches the ratings in Football-Data naming."""

from __future__ import annotations

import numpy as np
import pandas as pd

from epl_betting_lab.data.fetch_understat_xg import (
    UNDERSTAT_TO_FOOTBALL_DATA,
    build_team_xg,
    football_data_name,
    rows_from_payload,
)
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig


PAYLOAD = {"dates": [
    {"id": "1", "datetime": "2026-08-16 19:00:00", "isResult": True,
     "h": {"title": "Manchester United"}, "a": {"title": "Fulham"},
     "goals": {"h": "1", "a": "0"}, "xG": {"h": "2.04", "a": "0.42"}},
    {"id": "2", "datetime": "2026-08-17 15:00:00", "isResult": False,
     "h": {"title": "Wolverhampton Wanderers"}, "a": {"title": "Nottingham Forest"},
     "goals": {"h": None, "a": None}, "xG": {"h": None, "a": None}},
]}


def test_the_five_renames_land_on_football_data_spelling():
    assert football_data_name("Manchester United") == "Man United"
    assert football_data_name("Nottingham Forest") == "Nott'm Forest"
    assert football_data_name("Fulham") == "Fulham"
    assert len(UNDERSTAT_TO_FOOTBALL_DATA) == 5


def test_only_played_matches_carry_xg():
    table = build_team_xg(rows_from_payload(PAYLOAD))
    assert len(table) == 1
    row = table.iloc[0]
    assert row.home_team == "Man United" and row.away_team == "Fulham"
    assert row.home_xg == 2.04 and row.away_xg == 0.42
    assert row.date == pd.Timestamp("2026-08-16")


def _frame(with_xg: bool):
    rows = []
    dates = pd.date_range("2026-01-01", periods=12, freq="7D")
    for i, d in enumerate(dates):
        h, a = ("A", "B") if i % 2 == 0 else ("B", "A")
        # A is unlucky: creates far more than it scores. B is the reverse.
        rows.append({"date": d, "home_team": h, "away_team": a,
                     "home_goals": 1 if h == "A" else 2, "away_goals": 2 if a == "B" else 1,
                     "home_xg": (2.5 if h == "A" else 0.8) if with_xg else np.nan,
                     "away_xg": (0.8 if a == "B" else 2.5) if with_xg else np.nan})
    return pd.DataFrame(rows)


def test_xg_ratings_see_the_chances_not_the_luck():
    goals = PoissonGoalsModel().fit(_frame(True), config=RatingConfig(opponent_adjusted=True, goal_source="goals")).team_strengths
    xg = PoissonGoalsModel().fit(_frame(True), config=RatingConfig(opponent_adjusted=True, goal_source="xg")).team_strengths
    assert goals["B"].attack > goals["A"].attack   # by results
    assert xg["A"].attack > xg["B"].attack         # by chances


def test_missing_xg_falls_back_to_goals_rather_than_dropping_the_match():
    with_goals_only = PoissonGoalsModel().fit(_frame(False), config=RatingConfig(opponent_adjusted=True, goal_source="xg")).team_strengths
    plain = PoissonGoalsModel().fit(_frame(False), config=RatingConfig(opponent_adjusted=True, goal_source="goals")).team_strengths
    assert with_goals_only == plain


def test_blend_sits_between_goals_and_xg():
    cfg = lambda src, w=0.5: RatingConfig(opponent_adjusted=True, goal_source=src, xg_weight=w)
    g = PoissonGoalsModel().fit(_frame(True), config=cfg("goals")).team_strengths["A"].attack
    x = PoissonGoalsModel().fit(_frame(True), config=cfg("xg")).team_strengths["A"].attack
    b = PoissonGoalsModel().fit(_frame(True), config=cfg("blend", 0.5)).team_strengths["A"].attack
    assert min(g, x) < b < max(g, x)
