from __future__ import annotations

import pandas as pd

from epl_betting_lab.models.goal_environment import (
    adjust_total_probability,
    build_team_goal_environment,
)


def _hot_matches() -> pd.DataFrame:
    rows = []
    for i in range(10):
        rows.append({
            "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
            "season": "2526",
            "home_team": "Open FC" if i % 2 == 0 else "Leaky Town",
            "away_team": "Leaky Town" if i % 2 == 0 else "Open FC",
            "home_goals": 3,
            "away_goals": 2,
            "HS": 18,
            "AS": 16,
            "HST": 7,
            "AST": 6,
            "HC": 8,
            "AC": 7,
        })
    for i in range(10, 18):
        rows.append({
            "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
            "season": "2526",
            "home_team": "Baseline",
            "away_team": "Steady",
            "home_goals": 1,
            "away_goals": 1,
            "HS": 10,
            "AS": 9,
            "HST": 3,
            "AST": 3,
            "HC": 4,
            "AC": 4,
        })
    return pd.DataFrame(rows)


def test_build_team_goal_environment_uses_available_event_stats() -> None:
    env = build_team_goal_environment(_hot_matches())

    open_rows = env[env["team"] == "Open FC"]
    assert not open_rows.empty
    assert open_rows["match_total_goals"].mean() == 5.0
    assert "shots_against" in env.columns
    assert "sot_against" in env.columns
    assert "corners_against" in env.columns


def test_hot_environment_reduces_under_confidence() -> None:
    result = adjust_total_probability(
        raw_model_prob=0.54,
        selection="under",
        home_team="Open FC",
        away_team="Leaky Town",
        raw_home_goals=1.25,
        raw_away_goals=1.20,
        matches=_hot_matches(),
    )

    assert result["adjusted_projected_total_goals"] > result["raw_projected_total_goals"]
    assert result["goal_environment_adjusted_model_prob"] < 0.54
    assert result["goal_environment_under_guardrail"] is True


def test_hot_environment_can_raise_over_probability() -> None:
    result = adjust_total_probability(
        raw_model_prob=0.48,
        selection="over",
        home_team="Open FC",
        away_team="Leaky Town",
        raw_home_goals=1.35,
        raw_away_goals=1.30,
        matches=_hot_matches(),
    )

    assert result["adjusted_projected_total_goals"] > result["raw_projected_total_goals"]
    assert result["goal_environment_adjusted_model_prob"] == 0.48
