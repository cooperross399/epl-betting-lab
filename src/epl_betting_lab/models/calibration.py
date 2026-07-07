from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from epl_betting_lab.models.value import american_to_implied


@dataclass(frozen=True)
class ShrinkageConfig:
    base_weight: float = 0.05
    high_probability_add: float = 0.40
    medium_edge_add: float = 0.35
    big_edge_add: float = 0.65
    away_1x2_add: float = 0.10
    plus_money_add: float = 0.05
    max_weight: float = 0.95
    high_probability_cutoff: float = 0.70
    medium_edge_cutoff: float = 0.08
    big_edge_cutoff: float = 0.12


DEFAULT_BASELINES = {
    ("1x2", "home"): 0.43,
    ("1x2", "draw"): 0.27,
    ("1x2", "away"): 0.30,
    ("total_2_5", "over"): 0.55,
    ("total_2_5", "under"): 0.45,
    ("btts", "yes"): 0.56,
    ("btts", "no"): 0.44,
}


def historical_baseline(matches: pd.DataFrame, market: str, selection: str) -> float:
    """Return a simple historical hit rate for a market/selection."""
    df = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    if df.empty:
        return DEFAULT_BASELINES.get((market, selection), 0.50)

    home_goals = df["home_goals"]
    away_goals = df["away_goals"]
    if market == "1x2":
        if selection == "home":
            return round(float((home_goals > away_goals).mean()), 4)
        if selection == "draw":
            return round(float((home_goals == away_goals).mean()), 4)
        if selection == "away":
            return round(float((home_goals < away_goals).mean()), 4)
    if market == "total_2_5":
        over = (home_goals + away_goals) > 2.5
        return round(float(over.mean() if selection == "over" else (~over).mean()), 4)
    if market == "btts":
        yes = (home_goals > 0) & (away_goals > 0)
        return round(float(yes.mean() if selection == "yes" else (~yes).mean()), 4)
    return DEFAULT_BASELINES.get((market, selection), 0.50)


def shrinkage_weight(
    raw_prob: float,
    market: str,
    selection: str,
    american_odds: float | None = None,
    config: ShrinkageConfig = ShrinkageConfig(),
) -> float:
    """Choose how hard to shrink a probability toward a safer target."""
    weight = config.base_weight
    implied = american_to_implied(american_odds) if american_odds is not None else None
    edge = raw_prob - implied if implied is not None else 0.0

    if raw_prob >= config.high_probability_cutoff:
        weight += config.high_probability_add
    if edge >= config.medium_edge_cutoff:
        weight += config.medium_edge_add
    if edge >= config.big_edge_cutoff:
        weight += config.big_edge_add
    if market == "1x2" and selection == "away":
        weight += config.away_1x2_add
    if american_odds is not None and float(american_odds) > 0:
        weight += config.plus_money_add
    return round(min(weight, config.max_weight), 4)


def calibrate_probability(
    raw_prob: float,
    market: str,
    selection: str,
    american_odds: float | None = None,
    historical_target: float | None = None,
    config: ShrinkageConfig = ShrinkageConfig(),
) -> dict[str, float | str]:
    """Shrink a model probability toward market price or a historical baseline."""
    raw_prob = min(max(float(raw_prob), 0.001), 0.999)
    implied = american_to_implied(american_odds) if american_odds is not None else None
    target = implied if implied is not None else historical_target
    target_source = "market implied probability" if implied is not None else "historical baseline"
    if target is None:
        target = DEFAULT_BASELINES.get((market, selection), 0.50)
        target_source = "default historical baseline"

    target = min(max(float(target), 0.001), 0.999)
    weight = shrinkage_weight(raw_prob, market, selection, american_odds, config=config)
    calibrated = raw_prob * (1 - weight) + target * weight

    return {
        "raw_model_prob": round(raw_prob, 4),
        "calibrated_model_prob": round(float(calibrated), 4),
        "calibration_target": round(target, 4),
        "calibration_weight": weight,
        "calibration_target_source": target_source,
    }
