from __future__ import annotations

import math

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
            closing_american = line.iloc[0].get("closing_american_odds", pd.NA)
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
                # Carry the sportsbook through so CLV and weekly review can
                # attribute the price. Identifier only - no edge or probability
                # calculation depends on it.
                "book": _book_of(line),
                "opening_american_odds": american,
                "opening_implied_probability": raw_grade["book_implied"],
                "closing_american_odds": closing_american,
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


#: The market-anchored rule on the 2.5 line.
#:
#: The model's probability is blended with the market's in logit space, weight
#: `MODEL_WEIGHT` on the model, and a selection is a bet only if the blend still
#: clears the market by `ANCHOR_THRESHOLD`. `a = 1` would be the old rule (pure
#: model); `a = 0` never bets. A model with nothing the market lacks earns a
#: small weight and few bets — that is the rule working, not failing.
#:
#: These two values were fixed before any held-out season was read, at the
#: conservative end of the grid: 0.5 / 0.03 had +2.2% on the training seasons
#: (183 bets) and is the setting the out-of-sample report is judged at. They
#: are not to be re-tuned on the test seasons; that is the mistake the report
#: exists to prevent.
MODEL_WEIGHT = 0.5
ANCHOR_THRESHOLD = 0.03
SELECTION_RULE = "market_anchored"


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _implied(american: float) -> float:
    a = float(american)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def market_probability_over(
    home_team: str, away_team: str, odds: pd.DataFrame, market_odds: pd.DataFrame | None
) -> tuple[float | None, str]:
    """De-vigged probability of over 2.5 as the market prices it.

    From every book's over and under when the per-book staging is on hand —
    the consensus — and otherwise from the single best over and best under
    in the card input, which is biased long because two books' best prices
    sum to less than one. The second is named as such in the row.
    """
    for frame, label in ((market_odds, "consensus"), (odds, "best-price pair")):
        if frame is None or frame.empty:
            continue
        rows = frame[(frame.home_team == home_team) & (frame.away_team == away_team) & (frame.market == "total_2_5")]
        over = rows[rows.selection == "over"]["american_odds"].map(_implied)
        under = rows[rows.selection == "under"]["american_odds"].map(_implied)
        if over.empty or under.empty:
            continue
        o, u = float(over.mean()), float(under.mean())
        if o + u <= 0:
            continue
        return o / (o + u), label
    return None, "none"


def evaluate_total_25_anchored(
    projections: pd.DataFrame,
    odds: pd.DataFrame,
    *,
    market_odds: pd.DataFrame | None = None,
    model_weight: float = MODEL_WEIGHT,
    threshold: float = ANCHOR_THRESHOLD,
    max_juice: int = -160,
) -> pd.DataFrame:
    """Over/under 2.5 rows under the market-anchored rule.

    `projections` must come from the ratings the rule was measured on
    (`TOTALS_RATINGS`); handing it the old ratings would be a different rule.
    Emits the same row shape as `evaluate_total_25`, plus `selection_rule` so
    the card can cap the stake and CLV tracking can tell the two apart.
    """
    rows = []
    for _, p in projections.iterrows():
        game_odds = odds[(odds.home_team == p.home_team) & (odds.away_team == p.away_team) & (odds.market == "total_2_5")]
        if game_odds.empty:
            continue
        p_market_over, source = market_probability_over(p.home_team, p.away_team, odds, market_odds)
        if p_market_over is None:
            continue
        for selection, prob_col in (("over", "over_2_5"), ("under", "under_2_5")):
            line = game_odds[game_odds.selection == selection]
            if line.empty:
                continue
            american = float(line.iloc[0].american_odds)
            p_model = float(p[prob_col])
            p_market = p_market_over if selection == "over" else 1.0 - p_market_over
            p_final = _sigmoid(model_weight * _logit(p_model) + (1 - model_weight) * _logit(p_market))
            lift = p_final - p_market
            price_edge = p_final - _implied(american)
            # Grade the blended probability against the price the way every
            # other market is graded, so the row carries the fair price, ROI
            # and implied fields the ranking and the renderer read. The status
            # is then overridden: this rule bets on lift, not on that edge.
            grade = grade_edge(p_final, american, min_edge=0.0, max_default_juice=max_juice)
            # Flagged on lift over the de-vigged consensus. The card then
            # applies a second gate that is NOT here: _confidence_tier zeroes
            # any row whose edge against the posted price is not positive, so a
            # row can be BETTABLE and staked at nothing. That was an accident —
            # this comment used to claim the gate had been deliberately left
            # out to match the measurement — and it made the live rule tighter
            # than the measured one. It is now resolved the other way:
            # reports/out_of_sample.score_rule applies the price gate too, so
            # the published figures describe what runs. The gate is kept
            # because a row with edge <= 0 is a price this model's own final
            # number calls negative.
            if american < 0 and american < max_juice:
                status = "PASS - too much juice"
            elif lift > threshold:
                status = "BETTABLE"
            else:
                status = "PASS"
            rows.append({
                **grade,
                "home_team": p.home_team, "away_team": p.away_team,
                "market": "total_2_5", "selection": selection,
                "american_odds": american, "book": _book_of(line),
                "opening_american_odds": american,
                "opening_implied_probability": round(_implied(american), 4),
                "closing_american_odds": line.iloc[0].get("closing_american_odds", pd.NA),
                "raw_model_prob": round(p_model, 4),
                "market_prob": round(p_market, 4),
                "market_prob_source": source,
                "calibrated_model_prob": round(p_final, 4),
                "raw_edge": round(p_model - _implied(american), 4),
                "calibrated_edge": round(price_edge, 4),
                "anchor_lift": round(lift, 4),
                "raw_status": status,
                "calibrated_status": status,
                "status": status,
                "selection_rule": SELECTION_RULE,
                "model_weight": model_weight,
                "anchor_threshold": threshold,
            })
    return pd.DataFrame(rows)
