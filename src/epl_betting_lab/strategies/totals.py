from __future__ import annotations

import pandas as pd

from epl_betting_lab.models.calibration import ShrinkageConfig, calibrate_probability, min_calibrated_edge
from epl_betting_lab.models.goal_environment import adjust_total_probability
from epl_betting_lab.models.value import grade_edge


def evaluate_total_25(
    projections: pd.DataFrame,
    odds: pd.DataFrame,
    min_edge: float = 0.035,
    max_juice: int = -160,
    matches: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Evaluate over/under 2.5 odds against model probabilities."""
    rows = []
    for _, p in projections.iterrows():
        game_odds = odds[(odds.home_team == p.home_team) & (odds.away_team == p.away_team) & (odds.market == "total_2_5")]
        for selection, prob_col in [("over", "over_2_5"), ("under", "under_2_5")]:
            line = game_odds[game_odds.selection == selection]
            if line.empty:
                continue
            american = float(line.iloc[0].american_odds)
            raw_prob = float(p[prob_col])
            raw_grade = grade_edge(raw_prob, american, min_edge=min_edge, max_default_juice=max_juice)
            config = ShrinkageConfig()
            pre_adjustment_calibration = calibrate_probability(raw_prob, "total_2_5", selection, american_odds=american, config=config)
            pre_adjustment_grade = grade_edge(
                float(pre_adjustment_calibration["calibrated_model_prob"]),
                american,
                min_edge=min_calibrated_edge("total_2_5", selection, min_edge, config),
                max_default_juice=max_juice,
            )
            goal_environment = {}
            adjusted_prob = raw_prob
            if matches is not None and {"home_xg", "away_xg"}.issubset(projections.columns):
                goal_environment = adjust_total_probability(
                    raw_prob,
                    selection,
                    p.home_team,
                    p.away_team,
                    float(p.home_xg),
                    float(p.away_xg),
                    matches,
                )
                adjusted_prob = float(goal_environment["goal_environment_adjusted_model_prob"])
            calibration = calibrate_probability(adjusted_prob, "total_2_5", selection, american_odds=american, config=config)
            grade = grade_edge(
                float(calibration["calibrated_model_prob"]),
                american,
                min_edge=min_calibrated_edge("total_2_5", selection, min_edge, config),
                max_default_juice=max_juice,
            )
            if goal_environment.get("goal_environment_under_guardrail") and grade["status"] in {"BETTABLE", "LEAN"}:
                grade = {**grade, "status": "PASS - hot goal environment"}
            if pre_adjustment_grade["status"] != "BETTABLE" and grade["status"] == "BETTABLE":
                grade = {**grade, "status": "PASS - needs pre-adjustment edge"}
            rows.append({
                "home_team": p.home_team,
                "away_team": p.away_team,
                "market": "total_2_5",
                "selection": selection,
                "american_odds": american,
                "raw_model_prob": raw_grade["model_prob"],
                "goal_environment_adjusted_model_prob": round(adjusted_prob, 4),
                "calibrated_model_prob": grade["model_prob"],
                "raw_edge": raw_grade["edge"],
                "calibrated_edge": grade["edge"],
                "raw_status": raw_grade["status"],
                "calibrated_status": grade["status"],
                "pre_goal_environment_calibrated_status": pre_adjustment_grade["status"],
                "calibrated_min_edge": min_calibrated_edge("total_2_5", selection, min_edge, config),
                **goal_environment,
                "calibration_target": calibration["calibration_target"],
                "calibration_weight": calibration["calibration_weight"],
                "calibration_target_source": calibration["calibration_target_source"],
                "pre_goal_environment_calibration_target": pre_adjustment_calibration["calibration_target"],
                "pre_goal_environment_calibration_weight": pre_adjustment_calibration["calibration_weight"],
                "pre_goal_environment_calibration_target_source": pre_adjustment_calibration["calibration_target_source"],
                **grade,
            })
    return pd.DataFrame(rows).sort_values(["status", "edge"], ascending=[True, False]) if rows else pd.DataFrame()
