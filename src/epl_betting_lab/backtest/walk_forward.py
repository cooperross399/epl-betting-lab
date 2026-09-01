from __future__ import annotations

import pandas as pd

from epl_betting_lab.config import MIN_EDGE, MAX_DEFAULT_JUICE
from epl_betting_lab.models.calibration import (
    historical_baseline,
    calibrate_probability,
    min_calibrated_edge,
    ShrinkageConfig,
)
from epl_betting_lab.models.goal_environment import adjust_total_probability
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig
from epl_betting_lab.models.value import decimal_to_american, grade_edge


def _settle_1x2(selection: str, home_goals: int, away_goals: int) -> bool:
    if selection == "home":
        return home_goals > away_goals
    if selection == "draw":
        return home_goals == away_goals
    if selection == "away":
        return home_goals < away_goals
    raise ValueError(selection)


def _settle_total_25(selection: str, home_goals: int, away_goals: int) -> bool:
    total = home_goals + away_goals
    if selection == "over":
        return total > 2.5
    if selection == "under":
        return total < 2.5
    raise ValueError(selection)


def _settle_btts(selection: str, home_goals: int, away_goals: int) -> bool:
    yes = home_goals > 0 and away_goals > 0
    if selection == "yes":
        return yes
    if selection == "no":
        return not yes
    raise ValueError(selection)


def _profit(win: bool, decimal_odds: float) -> float:
    return (decimal_odds - 1) if win else -1.0


def _valid_decimal_odds(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    value = float(value)
    return value if value > 1 else None


def _closing(game: pd.Series, *columns: str) -> object:
    """The first closing price present, preferring the market average.

    Football-Data marks closing columns with a C. They were absent from the
    processed dataset until 2026-08-28, so this used to be handed a `CloseH`
    that never existed and every CLV figure was silently blank.
    """
    for column in columns:
        value = game.get(column)
        if value is not None and pd.notna(value):
            return value
    return None


def run_walk_forward_backtest(
    matches: pd.DataFrame,
    start_after_matches: int = 380,
    min_edge: float = MIN_EDGE,
    max_juice: int = MAX_DEFAULT_JUICE,
    last_n_fit_matches_per_team: int | None = 38,
    calibration_config: ShrinkageConfig = ShrinkageConfig(),
    rating_config: RatingConfig | None = None,
) -> pd.DataFrame:
    """Walk-forward backtest using only matches before each test game.

    The starter project tests basic 1X2, totals 2.5, and BTTS where odds columns exist.
    Stake is 1 unit per flagged bet.
    """
    rating_config = rating_config or RatingConfig.legacy()
    df = matches.dropna(subset=["home_goals", "away_goals", "date"]).sort_values("date").reset_index(drop=True)
    bets = []

    for i in range(start_after_matches, len(df)):
        train = df.iloc[:i].copy()
        game = df.iloc[i]
        # An opponent-adjusted fit reads the whole training window and
        # weights it by age itself, so the blunt last-N cut-off is dropped.
        model = PoissonGoalsModel().fit(
            train,
            last_n_matches_per_team=(
                None if rating_config.opponent_adjusted else last_n_fit_matches_per_team
            ),
            config=rating_config,
        )
        probs = model.match_probabilities(game.home_team, game.away_team)
        projected_home_goals = float(probs["home_xg"])
        projected_away_goals = float(probs["away_xg"])
        projected_total_goals = projected_home_goals + projected_away_goals
        favorite_strength = max(float(probs["home_win"]), float(probs["away_win"]))
        actual_total_goals = int(game.home_goals) + int(game.away_goals)

        candidates = []
        # 1X2 odds: prefer Avg columns, fall back to B365.
        candidates.extend([
            ("1x2", "home", probs["home_win"], game.get("AvgH") if pd.notna(game.get("AvgH")) else game.get("B365H"), _closing(game, "AvgCH", "B365CH")),
            ("1x2", "draw", probs["draw"], game.get("AvgD") if pd.notna(game.get("AvgD")) else game.get("B365D"), _closing(game, "AvgCD", "B365CD")),
            ("1x2", "away", probs["away_win"], game.get("AvgA") if pd.notna(game.get("AvgA")) else game.get("B365A"), _closing(game, "AvgCA", "B365CA")),
        ])
        candidates.extend([
            ("total_2_5", "over", probs["over_2_5"], game.get("Avg>2.5") if pd.notna(game.get("Avg>2.5")) else game.get("B365>2.5"), _closing(game, "AvgC>2.5", "B365C>2.5")),
            ("total_2_5", "under", probs["under_2_5"], game.get("Avg<2.5") if pd.notna(game.get("Avg<2.5")) else game.get("B365<2.5"), _closing(game, "AvgC<2.5", "B365C<2.5")),
        ])

        for market, selection, model_prob, dec_odds, close_dec_odds in candidates:
            dec_odds = _valid_decimal_odds(dec_odds)
            if dec_odds is None:
                continue
            close_dec_odds = _valid_decimal_odds(close_dec_odds)
            american = decimal_to_american(float(dec_odds))
            closing_american = decimal_to_american(close_dec_odds) if close_dec_odds is not None else pd.NA
            raw_grade = grade_edge(float(model_prob), american, min_edge=min_edge, max_default_juice=max_juice)
            generic_calibration = calibrate_probability(
                float(model_prob),
                market,
                selection,
                american_odds=american,
                historical_target=historical_baseline(train, market, selection),
                config=ShrinkageConfig.generic(),
            )
            generic_grade = grade_edge(
                float(generic_calibration["calibrated_model_prob"]),
                american,
                min_edge=min_edge,
                max_default_juice=max_juice,
            )
            calibration = calibrate_probability(
                float(model_prob),
                market,
                selection,
                american_odds=american,
                historical_target=historical_baseline(train, market, selection),
                config=calibration_config,
            )
            goal_environment = {}
            adjusted_model_prob = float(model_prob)
            if market == "total_2_5":
                goal_environment = adjust_total_probability(
                    float(model_prob),
                    selection,
                    game.home_team,
                    game.away_team,
                    projected_home_goals,
                    projected_away_goals,
                    train,
                )
                adjusted_model_prob = float(goal_environment["goal_environment_adjusted_model_prob"])
            adjusted_calibration = calibrate_probability(
                adjusted_model_prob,
                market,
                selection,
                american_odds=american,
                historical_target=historical_baseline(train, market, selection),
                config=calibration_config,
            )
            calibrated_grade = grade_edge(
                float(calibration["calibrated_model_prob"]),
                american,
                min_edge=min_calibrated_edge(market, selection, min_edge, calibration_config),
                max_default_juice=max_juice,
            )
            adjusted_grade = grade_edge(
                float(adjusted_calibration["calibrated_model_prob"]),
                american,
                min_edge=min_calibrated_edge(market, selection, min_edge, calibration_config),
                max_default_juice=max_juice,
            )
            if goal_environment.get("goal_environment_under_guardrail") and adjusted_grade["status"] in {"BETTABLE", "LEAN"}:
                adjusted_grade = {**adjusted_grade, "status": "PASS - hot goal environment"}
            raw_would_bet = raw_grade["status"] == "BETTABLE"
            generic_calibrated_would_bet = generic_grade["status"] == "BETTABLE"
            calibrated_would_bet = calibrated_grade["status"] == "BETTABLE"
            goal_environment_adjusted_would_bet = adjusted_grade["status"] == "BETTABLE"
            if market == "total_2_5" and goal_environment_adjusted_would_bet and not calibrated_would_bet:
                adjusted_grade = {**adjusted_grade, "status": "PASS - needs pre-adjustment edge"}
                goal_environment_adjusted_would_bet = False
            if not raw_would_bet and not generic_calibrated_would_bet and not calibrated_would_bet and not goal_environment_adjusted_would_bet:
                continue

            if market == "1x2":
                won = _settle_1x2(selection, int(game.home_goals), int(game.away_goals))
            elif market == "total_2_5":
                won = _settle_total_25(selection, int(game.home_goals), int(game.away_goals))
            else:
                continue

            profit = round(_profit(won, float(dec_odds)), 3)

            bets.append({
                "date": game.date,
                "season": game.season,
                "home_team": game.home_team,
                "away_team": game.away_team,
                "score": f"{int(game.home_goals)}-{int(game.away_goals)}",
                "projected_home_goals": round(projected_home_goals, 3),
                "projected_away_goals": round(projected_away_goals, 3),
                "projected_total_goals": round(projected_total_goals, 3),
                "favorite_strength": round(favorite_strength, 4),
                "actual_total_goals": actual_total_goals,
                "market": market,
                "selection": selection,
                "decimal_odds": round(float(dec_odds), 3),
                "american_odds": american,
                "opening_american_odds": american,
                "opening_implied_probability": raw_grade["book_implied"],
                "closing_american_odds": closing_american,
                "raw_model_prob": raw_grade["model_prob"],
                "generic_calibrated_model_prob": generic_grade["model_prob"],
                "calibrated_model_prob": calibrated_grade["model_prob"],
                "goal_environment_adjusted_model_prob": round(adjusted_model_prob, 4),
                "goal_environment_adjusted_calibrated_model_prob": adjusted_grade["model_prob"],
                "model_prob": adjusted_grade["model_prob"],
                "book_implied": adjusted_grade["book_implied"],
                "raw_edge": raw_grade["edge"],
                "generic_calibrated_edge": generic_grade["edge"],
                "calibrated_edge": calibrated_grade["edge"],
                "goal_environment_adjusted_edge": adjusted_grade["edge"],
                "edge": adjusted_grade["edge"],
                "raw_ev_per_unit": raw_grade["ev_per_unit"],
                "generic_calibrated_ev_per_unit": generic_grade["ev_per_unit"],
                "calibrated_ev_per_unit": calibrated_grade["ev_per_unit"],
                "goal_environment_adjusted_ev_per_unit": adjusted_grade["ev_per_unit"],
                "ev_per_unit": adjusted_grade["ev_per_unit"],
                "raw_fair_american": raw_grade["fair_american"],
                "generic_calibrated_fair_american": generic_grade["fair_american"],
                "calibrated_fair_american": calibrated_grade["fair_american"],
                "goal_environment_adjusted_fair_american": adjusted_grade["fair_american"],
                "fair_american": adjusted_grade["fair_american"],
                "raw_status": raw_grade["status"],
                "generic_calibrated_status": generic_grade["status"],
                "calibrated_status": calibrated_grade["status"],
                "goal_environment_adjusted_status": adjusted_grade["status"],
                "status": adjusted_grade["status"],
                "generic_calibrated_min_edge": min_edge,
                "calibrated_min_edge": min_calibrated_edge(market, selection, min_edge, calibration_config),
                "calibration_target": adjusted_calibration["calibration_target"],
                "calibration_weight": adjusted_calibration["calibration_weight"],
                "calibration_target_source": adjusted_calibration["calibration_target_source"],
                "pre_goal_environment_calibration_target": calibration["calibration_target"],
                "pre_goal_environment_calibration_weight": calibration["calibration_weight"],
                "pre_goal_environment_calibration_target_source": calibration["calibration_target_source"],
                **goal_environment,
                "raw_would_bet": raw_would_bet,
                "generic_calibrated_would_bet": generic_calibrated_would_bet,
                "calibrated_would_bet": calibrated_would_bet,
                "goal_environment_adjusted_would_bet": goal_environment_adjusted_would_bet,
                "won": won,
                "raw_profit_units": profit if raw_would_bet else 0.0,
                "generic_calibrated_profit_units": profit if generic_calibrated_would_bet else 0.0,
                "calibrated_profit_units": profit if calibrated_would_bet else 0.0,
                "goal_environment_adjusted_profit_units": profit if goal_environment_adjusted_would_bet else 0.0,
                "profit_units": profit if goal_environment_adjusted_would_bet else 0.0,
            })

    return pd.DataFrame(bets)


def summarize_backtest(bets: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "market", "raw_bets", "raw_wins", "raw_profit_units", "raw_roi",
        "generic_calibrated_bets", "generic_calibrated_wins", "generic_calibrated_profit_units", "generic_calibrated_roi",
        "calibrated_bets", "calibrated_wins", "calibrated_profit_units", "calibrated_roi",
        "goal_environment_adjusted_bets", "goal_environment_adjusted_wins", "goal_environment_adjusted_profit_units", "goal_environment_adjusted_roi",
        "bets_filtered_out", "goal_environment_bets_filtered_out", "bets", "wins", "losses", "win_rate", "profit_units", "roi",
    ]
    if bets.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for market, group in bets.groupby("market"):
        raw = group[group.get("raw_would_bet", False) == True]
        generic = group[group.get("generic_calibrated_would_bet", False) == True]
        calibrated = group[group.get("calibrated_would_bet", True) == True]
        adjusted = group[group.get("goal_environment_adjusted_would_bet", group.get("calibrated_would_bet", True)) == True]
        raw_bets = len(raw)
        generic_bets = len(generic)
        calibrated_bets = len(calibrated)
        adjusted_bets = len(adjusted)
        raw_wins = int(raw["won"].sum()) if raw_bets else 0
        generic_wins = int(generic["won"].sum()) if generic_bets else 0
        calibrated_wins = int(calibrated["won"].sum()) if calibrated_bets else 0
        adjusted_wins = int(adjusted["won"].sum()) if adjusted_bets else 0
        raw_profit = round(float(raw["raw_profit_units"].sum()), 3) if raw_bets else 0.0
        generic_profit = round(float(generic["generic_calibrated_profit_units"].sum()), 3) if generic_bets else 0.0
        calibrated_profit = round(float(calibrated["calibrated_profit_units"].sum()), 3) if calibrated_bets else 0.0
        adjusted_profit_col = "goal_environment_adjusted_profit_units" if "goal_environment_adjusted_profit_units" in adjusted.columns else "calibrated_profit_units"
        adjusted_profit = round(float(adjusted[adjusted_profit_col].sum()), 3) if adjusted_bets else 0.0
        rows.append({
            "market": market,
            "raw_bets": raw_bets,
            "raw_wins": raw_wins,
            "raw_profit_units": raw_profit,
            "raw_roi": round(raw_profit / raw_bets, 3) if raw_bets else 0.0,
            "generic_calibrated_bets": generic_bets,
            "generic_calibrated_wins": generic_wins,
            "generic_calibrated_profit_units": generic_profit,
            "generic_calibrated_roi": round(generic_profit / generic_bets, 3) if generic_bets else 0.0,
            "calibrated_bets": calibrated_bets,
            "calibrated_wins": calibrated_wins,
            "calibrated_profit_units": calibrated_profit,
            "calibrated_roi": round(calibrated_profit / calibrated_bets, 3) if calibrated_bets else 0.0,
            "goal_environment_adjusted_bets": adjusted_bets,
            "goal_environment_adjusted_wins": adjusted_wins,
            "goal_environment_adjusted_profit_units": adjusted_profit,
            "goal_environment_adjusted_roi": round(adjusted_profit / adjusted_bets, 3) if adjusted_bets else 0.0,
            "bets_filtered_out": raw_bets - calibrated_bets,
            "goal_environment_bets_filtered_out": raw_bets - adjusted_bets,
            "bets": adjusted_bets,
            "wins": adjusted_wins,
            "losses": adjusted_bets - adjusted_wins,
            "win_rate": round(adjusted_wins / adjusted_bets, 3) if adjusted_bets else 0.0,
            "profit_units": adjusted_profit,
            "roi": round(adjusted_profit / adjusted_bets, 3) if adjusted_bets else 0.0,
        })
    return pd.DataFrame(rows, columns=columns).sort_values("calibrated_profit_units", ascending=False)
