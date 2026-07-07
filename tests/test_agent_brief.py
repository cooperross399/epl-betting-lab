from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.agent_brief import build_market_trends, filter_current_season, render_agent_brief


def _sample_matches() -> pd.DataFrame:
    return pd.DataFrame([
        {"season": "2627", "date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry City", "home_goals": 2, "away_goals": 0},
        {"season": "2627", "date": "2026-08-22", "home_team": "Liverpool", "away_team": "Newcastle United", "home_goals": 2, "away_goals": 2},
        {"season": "2526", "date": "2026-05-01", "home_team": "Chelsea", "away_team": "Fulham", "home_goals": 1, "away_goals": 0},
    ])


def test_filter_current_season() -> None:
    current = filter_current_season(_sample_matches(), "2627")
    assert len(current) == 2
    assert set(current["season"]) == {"2627"}


def test_build_market_trends() -> None:
    trends = build_market_trends(filter_current_season(_sample_matches(), "2627"))
    assert trends["matches"] == 2
    assert trends["avg_goals"] == 3.0
    assert trends["home_win_rate"] == 0.5
    assert trends["draw_rate"] == 0.5
    assert trends["btts_rate"] == 0.5


def test_render_agent_brief_contains_checklist() -> None:
    markdown, team_form, team_profile = render_agent_brief(_sample_matches(), current_season="2627")
    assert "Agent Weekly Brief" in markdown
    assert "Codex next-step checklist" in markdown
    assert not team_form.empty
    assert not team_profile.empty
