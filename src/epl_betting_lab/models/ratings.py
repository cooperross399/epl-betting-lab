from __future__ import annotations

import pandas as pd


def simple_form_table(matches: pd.DataFrame, last_n: int = 6) -> pd.DataFrame:
    """Return recent form table with points, goals, and goal difference."""
    df = matches.dropna(subset=["home_goals", "away_goals"]).sort_values("date").copy()
    teams = sorted(set(df["home_team"]).union(set(df["away_team"])))
    rows = []

    for team in teams:
        games = df[(df.home_team == team) | (df.away_team == team)].tail(last_n)
        pts = gf = ga = wins = draws = losses = 0
        for _, g in games.iterrows():
            is_home = g.home_team == team
            scored = int(g.home_goals if is_home else g.away_goals)
            allowed = int(g.away_goals if is_home else g.home_goals)
            gf += scored
            ga += allowed
            if scored > allowed:
                pts += 3
                wins += 1
            elif scored == allowed:
                pts += 1
                draws += 1
            else:
                losses += 1
        rows.append({
            "team": team,
            "matches": len(games),
            "points": pts,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": gf,
            "goals_against": ga,
            "goal_diff": gf - ga,
            "points_per_match": round(pts / len(games), 2) if len(games) else 0,
        })
    return pd.DataFrame(rows).sort_values(["points_per_match", "goal_diff"], ascending=False)
