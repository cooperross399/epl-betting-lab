from __future__ import annotations

import pandas as pd


def _book_of(line: pd.DataFrame) -> str:
    """Sportsbook name for a priced line, blank when the source omitted it."""
    if line.empty:
        return ""
    value = line.iloc[0].get("book", "")
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()

from epl_betting_lab.models.calibration import ShrinkageConfig, calibrate_probability, min_calibrated_edge
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
            closing_american = line.iloc[0].get("closing_american_odds", pd.NA)
            raw_prob = float(p[prob_col])
            raw_grade = grade_edge(raw_prob, american, min_edge=min_edge, max_default_juice=max_juice)
            config = ShrinkageConfig()
            calibration = calibrate_probability(raw_prob, "1x2", selection, american_odds=american, config=config)
            grade = grade_edge(
                float(calibration["calibrated_model_prob"]),
                american,
                min_edge=min_calibrated_edge("1x2", selection, min_edge, config),
                max_default_juice=max_juice,
            )
            rows.append({
                "home_team": p.home_team,
                "away_team": p.away_team,
                "market": "1x2",
                "selection": selection,
                "american_odds": american,
                # Carry the sportsbook through so CLV and weekly review can
                # attribute the price. Identifier only - no edge or probability
                # calculation depends on it.
                "book": _book_of(line),
                "opening_american_odds": american,
                "opening_implied_probability": raw_grade["book_implied"],
                "closing_american_odds": closing_american,
                "raw_model_prob": raw_grade["model_prob"],
                "calibrated_model_prob": grade["model_prob"],
                "raw_edge": raw_grade["edge"],
                "calibrated_edge": grade["edge"],
                "raw_status": raw_grade["status"],
                "calibrated_status": grade["status"],
                "calibrated_min_edge": min_calibrated_edge("1x2", selection, min_edge, config),
                **calibration,
                **grade,
            })
    return pd.DataFrame(rows).sort_values(["status", "edge"], ascending=[True, False]) if rows else pd.DataFrame()
