from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class GoalEnvironmentConfig:
    recent_matches: int = 8
    high_event_total_margin: float = 0.35
    low_event_total_margin: float = 0.30
    high_over_rate_margin: float = 0.08
    high_goals_allowed_margin: float = 0.25
    high_shots_allowed_margin: float = 1.50
    high_sot_allowed_margin: float = 0.50
    high_corners_allowed_margin: float = 0.75
    near_total_low: float = 2.25
    near_total_high: float = 2.75
    max_upward_adjustment: float = 0.45
    max_downward_adjustment: float = -0.20


def _available_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="Float64")
    return pd.to_numeric(df[column], errors="coerce")


def build_team_goal_environment(matches: pd.DataFrame) -> pd.DataFrame:
    """Return one row per team per match with goals and optional event stats."""
    if matches.empty:
        return pd.DataFrame()

    df = matches.dropna(subset=["home_team", "away_team", "home_goals", "away_goals"]).copy()
    if df.empty:
        return pd.DataFrame()

    home_goals = pd.to_numeric(df["home_goals"], errors="coerce")
    away_goals = pd.to_numeric(df["away_goals"], errors="coerce")
    match_total = home_goals + away_goals

    base = {
        "date": df["date"] if "date" in df.columns else pd.RangeIndex(len(df)),
        "season": df["season"] if "season" in df.columns else pd.NA,
        "match_total_goals": match_total,
        "over_2_5": match_total > 2.5,
    }
    home = pd.DataFrame({
        **base,
        "team": df["home_team"],
        "opponent": df["away_team"],
        "venue": "home",
        "goals_for": home_goals,
        "goals_against": away_goals,
        "shots_for": _available_numeric(df, "HS"),
        "shots_against": _available_numeric(df, "AS"),
        "sot_for": _available_numeric(df, "HST"),
        "sot_against": _available_numeric(df, "AST"),
        "corners_for": _available_numeric(df, "HC"),
        "corners_against": _available_numeric(df, "AC"),
    })
    away = pd.DataFrame({
        **base,
        "team": df["away_team"],
        "opponent": df["home_team"],
        "venue": "away",
        "goals_for": away_goals,
        "goals_against": home_goals,
        "shots_for": _available_numeric(df, "AS"),
        "shots_against": _available_numeric(df, "HS"),
        "sot_for": _available_numeric(df, "AST"),
        "sot_against": _available_numeric(df, "HST"),
        "corners_for": _available_numeric(df, "AC"),
        "corners_against": _available_numeric(df, "HC"),
    })
    return pd.concat([home, away], ignore_index=True).sort_values("date")


def _mean_or_na(series: pd.Series) -> float | pd.NA:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return float(clean.mean()) if not clean.empty else pd.NA


def _team_profile(team_rows: pd.DataFrame, config: GoalEnvironmentConfig) -> dict[str, float | int | str | pd.NA]:
    recent = team_rows.tail(config.recent_matches)
    if recent.empty:
        return {
            "recent_matches": 0,
            "avg_total_goals": pd.NA,
            "over_2_5_rate": pd.NA,
            "goals_against": pd.NA,
            "shots_against": pd.NA,
            "sot_against": pd.NA,
            "corners_against": pd.NA,
        }
    return {
        "recent_matches": int(len(recent)),
        "avg_total_goals": _mean_or_na(recent["match_total_goals"]),
        "over_2_5_rate": float(recent["over_2_5"].mean()),
        "goals_against": _mean_or_na(recent["goals_against"]),
        "shots_against": _mean_or_na(recent["shots_against"]),
        "sot_against": _mean_or_na(recent["sot_against"]),
        "corners_against": _mean_or_na(recent["corners_against"]),
    }


def _league_baselines(team_env: pd.DataFrame) -> dict[str, float]:
    return {
        "avg_total_goals": float(team_env["match_total_goals"].mean()) if not team_env.empty else 2.75,
        "over_2_5_rate": float(team_env["over_2_5"].mean()) if not team_env.empty else 0.52,
        "goals_against": float(team_env["goals_against"].mean()) if not team_env.empty else 1.35,
        "shots_against": float(team_env["shots_against"].mean()) if "shots_against" in team_env else 12.0,
        "sot_against": float(team_env["sot_against"].mean()) if "sot_against" in team_env else 4.0,
        "corners_against": float(team_env["corners_against"].mean()) if "corners_against" in team_env else 5.0,
    }


def _is_number(value: object) -> bool:
    return not pd.isna(value)


def _profile_scores(profile: dict[str, object], baselines: dict[str, float], config: GoalEnvironmentConfig) -> tuple[float, float, list[str]]:
    hot = 0.0
    cold = 0.0
    reasons: list[str] = []

    avg_total = profile["avg_total_goals"]
    if _is_number(avg_total):
        avg_total = float(avg_total)
        if avg_total >= baselines["avg_total_goals"] + config.high_event_total_margin:
            hot += 1.0
            reasons.append("recent high-total games")
        elif avg_total <= baselines["avg_total_goals"] - config.low_event_total_margin:
            cold += 0.75
            reasons.append("recent low-total games")

    over_rate = profile["over_2_5_rate"]
    if _is_number(over_rate):
        over_rate = float(over_rate)
        if over_rate >= baselines["over_2_5_rate"] + config.high_over_rate_margin:
            hot += 1.0
            reasons.append("recent overs running hot")
        elif over_rate <= baselines["over_2_5_rate"] - config.high_over_rate_margin:
            cold += 0.75
            reasons.append("recent unders running cold")

    goals_against = profile["goals_against"]
    if _is_number(goals_against) and float(goals_against) >= baselines["goals_against"] + config.high_goals_allowed_margin:
        hot += 1.0
        reasons.append("recent goals allowed pressure")

    shots_against = profile["shots_against"]
    if _is_number(shots_against) and float(shots_against) >= baselines["shots_against"] + config.high_shots_allowed_margin:
        hot += 0.50
        reasons.append("recent shots allowed pressure")

    sot_against = profile["sot_against"]
    if _is_number(sot_against) and float(sot_against) >= baselines["sot_against"] + config.high_sot_allowed_margin:
        hot += 0.50
        reasons.append("recent shots on target allowed pressure")

    corners_against = profile["corners_against"]
    if _is_number(corners_against) and float(corners_against) >= baselines["corners_against"] + config.high_corners_allowed_margin:
        hot += 0.25
        reasons.append("recent corners allowed pressure")

    return hot, cold, reasons


def _poisson_over_25(total_goals: float) -> float:
    total_goals = max(float(total_goals), 0.10)
    under_or_push_low = sum(math.exp(-total_goals) * total_goals**k / math.factorial(k) for k in range(3))
    return min(max(1 - under_or_push_low, 0.001), 0.999)


def adjust_total_probability(
    raw_model_prob: float,
    selection: str,
    home_team: str,
    away_team: str,
    raw_home_goals: float,
    raw_away_goals: float,
    matches: pd.DataFrame,
    config: GoalEnvironmentConfig = GoalEnvironmentConfig(),
) -> dict[str, object]:
    """Apply a conservative totals-only goal-environment adjustment.

    The Poisson model remains the source of the raw projection. This layer only
    nudges the total-goals expectation before total_2_5 betting decisions.
    """
    raw_total = float(raw_home_goals) + float(raw_away_goals)
    team_env = build_team_goal_environment(matches)
    if team_env.empty:
        return {
            "raw_projected_home_goals": round(float(raw_home_goals), 3),
            "raw_projected_away_goals": round(float(raw_away_goals), 3),
            "raw_projected_total_goals": round(raw_total, 3),
            "adjusted_projected_home_goals": round(float(raw_home_goals), 3),
            "adjusted_projected_away_goals": round(float(raw_away_goals), 3),
            "adjusted_projected_total_goals": round(raw_total, 3),
            "goal_environment_goal_adjustment": 0.0,
            "goal_environment_hot_score": 0.0,
            "goal_environment_cold_score": 0.0,
            "goal_environment_under_guardrail": False,
            "goal_environment_reason": "no historical goal-environment data",
            "goal_environment_adjusted_model_prob": round(float(raw_model_prob), 4),
        }

    baselines = _league_baselines(team_env)
    home_profile = _team_profile(team_env[team_env["team"] == home_team], config)
    away_profile = _team_profile(team_env[team_env["team"] == away_team], config)
    home_hot, home_cold, home_reasons = _profile_scores(home_profile, baselines, config)
    away_hot, away_cold, away_reasons = _profile_scores(away_profile, baselines, config)
    hot_score = home_hot + away_hot
    cold_score = home_cold + away_cold

    goal_adjustment = 0.07 * hot_score - 0.05 * cold_score
    both_high_event = home_hot >= 2.0 and away_hot >= 2.0
    concession_pressure = 0
    for profile in [home_profile, away_profile]:
        goals_against = profile["goals_against"]
        if _is_number(goals_against) and float(goals_against) >= baselines["goals_against"] + config.high_goals_allowed_margin:
            concession_pressure += 1

    if both_high_event:
        goal_adjustment += 0.12
    if concession_pressure:
        goal_adjustment += 0.05 * concession_pressure
    near_total = config.near_total_low <= raw_total <= config.near_total_high
    if near_total and hot_score >= 2.5:
        goal_adjustment += 0.10

    goal_adjustment = min(max(goal_adjustment, config.max_downward_adjustment), config.max_upward_adjustment)
    adjusted_total = max(raw_total + goal_adjustment, 0.50)
    scale = adjusted_total / raw_total if raw_total > 0 else 1.0
    adjusted_home_goals = float(raw_home_goals) * scale
    adjusted_away_goals = float(raw_away_goals) * scale
    adjusted_over = _poisson_over_25(adjusted_total)
    # Conservative first pass: use the environment layer to distrust unders in
    # hot games, not to manufacture extra over confidence.
    adjusted_prob = float(raw_model_prob) if selection == "over" else 1 - adjusted_over

    under_guardrail = bool(
        selection == "under"
        and (
            both_high_event
            or concession_pressure >= 1
            or (near_total and hot_score >= 2.5)
        )
    )
    reasons = home_reasons + away_reasons
    if near_total and hot_score >= 2.5:
        reasons.append("raw total near 2.5 with hot recent environments")
    if both_high_event:
        reasons.append("both teams recently high-event")

    return {
        "raw_projected_home_goals": round(float(raw_home_goals), 3),
        "raw_projected_away_goals": round(float(raw_away_goals), 3),
        "raw_projected_total_goals": round(raw_total, 3),
        "adjusted_projected_home_goals": round(adjusted_home_goals, 3),
        "adjusted_projected_away_goals": round(adjusted_away_goals, 3),
        "adjusted_projected_total_goals": round(adjusted_total, 3),
        "goal_environment_goal_adjustment": round(goal_adjustment, 3),
        "goal_environment_hot_score": round(hot_score, 2),
        "goal_environment_cold_score": round(cold_score, 2),
        "goal_environment_under_guardrail": under_guardrail,
        "goal_environment_reason": "; ".join(dict.fromkeys(reasons)) if reasons else "neutral recent goal environment",
        "goal_environment_adjusted_model_prob": round(float(adjusted_prob), 4),
        "home_recent_avg_total_goals": round(float(home_profile["avg_total_goals"]), 3) if _is_number(home_profile["avg_total_goals"]) else pd.NA,
        "away_recent_avg_total_goals": round(float(away_profile["avg_total_goals"]), 3) if _is_number(away_profile["avg_total_goals"]) else pd.NA,
        "home_recent_over_2_5_rate": round(float(home_profile["over_2_5_rate"]), 3) if _is_number(home_profile["over_2_5_rate"]) else pd.NA,
        "away_recent_over_2_5_rate": round(float(away_profile["over_2_5_rate"]), 3) if _is_number(away_profile["over_2_5_rate"]) else pd.NA,
        "home_recent_goals_against": round(float(home_profile["goals_against"]), 3) if _is_number(home_profile["goals_against"]) else pd.NA,
        "away_recent_goals_against": round(float(away_profile["goals_against"]), 3) if _is_number(away_profile["goals_against"]) else pd.NA,
        "home_recent_shots_against": round(float(home_profile["shots_against"]), 3) if _is_number(home_profile["shots_against"]) else pd.NA,
        "away_recent_shots_against": round(float(away_profile["shots_against"]), 3) if _is_number(away_profile["shots_against"]) else pd.NA,
    }
