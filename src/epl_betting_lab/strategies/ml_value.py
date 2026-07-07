from __future__ import annotations

import pandas as pd

from epl_betting_lab.models.value import grade_edge


def evaluate_1x2_value(projections: pd.DataFrame, odds: pd.DataFrame, min_edge: float = 0.035, max_juice: int = -160) -> pd.DataFrame:
    """Compare model 1X2 probabilities to market odds.

    odds columns expected:
    date, home_team, away_team, market, selection, american_odds

    For 1X2, selection should be one of: home, draw, away.
    """
    rows = []
    for _, p in projections.iterrows():
        game_odds = odds[(odds.home_team == p.home_team) & (odds.away_team == p.away_team) & (odds.market == "1x2")]
        for selection, prob_col in [("home", "home_win"), ("draw", "draw"), ("away", "away_win")]:
            line = game_odds[game_odds.selection == selection]
            if line.empty:
                continue
            american = float(line.iloc[0].american_odds)
            grade = grade_edge(float(p[prob_col]), american, min_edge=min_edge, max_default_juice=max_juice)
            rows.append({
                "home_team": p.home_team,
                "away_team": p.away_team,
                "market": "1x2",
                "selection": selection,
                "american_odds": american,
                **grade,
            })
    return pd.DataFrame(rows).sort_values(["status", "edge"], ascending=[True, False]) if rows else pd.DataFrame()
