from __future__ import annotations

import pandas as pd

from epl_betting_lab.config import MIN_EDGE, MAX_DEFAULT_JUICE
from epl_betting_lab.models.calibration import (
    historical_baseline,
    calibrate_probability,
    min_calibrated_edge,
    ShrinkageConfig,
)
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
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


def run_walk_forward_backtest(
    matches: pd.DataFrame,
    start_after_matches: int = 380,
    min_edge: float = MIN_EDGE,
    max_juice: int = MAX_DEFAULT_JUICE,
    last_n_fit_matches_per_team: int | None = 38,
    calibration_config: ShrinkageConfig = ShrinkageConfig(),
) -> pd.DataFrame:
    """Walk-forward backtest using only matches before each test game.

    The starter project tests basic 1X2, totals 2.5, and BTTS where odds columns exist.
    Stake is 1 unit per flagged bet.
    """
    df = matches.dropna(subset=["home_goals", "away_goals", "date"]).sort_values("date").reset_index(drop=True)
    bets = []

    for i in range(start_after_matches, len(df)):
        train = df.iloc[:i].copy()
        game = df.iloc[i]
        model = PoissonGoalsModel().fit(train, last_n_matches_per_team=last_n_fit_matches_per_team)
        probs = model.match_probabilities(game.home_team, game.away_team)
        projected_home_goals = float(probs["home_xg"])
        projected_away_goals = float(probs["away_xg"])
        projected_total_goals = projected_home_goals + projected_away_goals
        favorite_strength = max(float(probs["home_win"]), float(probs["away_win"]))
        actual_total_goals = int(game.home_goals) + int(game.away_goals)

        candidates = []
        # 1X2 odds: prefer Avg columns, fall back to B365.
        candidates.extend([
            ("1x2", "home", probs["home_win"], game.get("AvgH") if pd.notna(game.get("AvgH")) else game.get("B365H")),
            ("1x2", "draw", probs["draw"], game.get("AvgD") if pd.notna(game.get("AvgD")) else game.get("B365D")),
            ("1x2", "away", probs["away_win"], game.get("AvgA") if pd.notna(game.get("AvgA")) else game.get("B365A")),
        ])
        candidates.extend([
            ("total_2_5", "over", probs["over_2_5"], game.get("Avg>2.5") if pd.notna(game.get("Avg>2.5")) else game.get("B365>2.5")),
            ("total_2_5", "under", probs["under_2_5"], game.get("Avg<2.5") if pd.notna(game.get("Avg<2.5")) else game.get("B365<2.5")),
        ])

        for market, selection, model_prob, dec_odds in candidates:
            if dec_odds is None or pd.isna(dec_odds) or float(dec_odds) <= 1:
                continue
            american = decimal_to_american(float(dec_odds))
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
            calibrated_grade = grade_edge(
                float(calibration["calibrated_model_prob"]),
                american,
                min_edge=min_calibrated_edge(market, selection, min_edge, calibration_config),
                max_default_juice=max_juice,
            )
            raw_would_bet = raw_grade["status"] == "BETTABLE"
            generic_calibrated_would_bet = generic_grade["status"] == "BETTABLE"
            calibrated_would_bet = calibrated_grade["status"] == "BETTABLE"
            if not raw_would_bet and not generic_calibrated_would_bet and not calibrated_would_bet:
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
                "raw_model_prob": raw_grade["model_prob"],
                "generic_calibrated_model_prob": generic_grade["model_prob"],
                "calibrated_model_prob": calibrated_grade["model_prob"],
                "model_prob": calibrated_grade["model_prob"],
                "book_implied": calibrated_grade["book_implied"],
                "raw_edge": raw_grade["edge"],
                "generic_calibrated_edge": generic_grade["edge"],
                "calibrated_edge": calibrated_grade["edge"],
                "edge": calibrated_grade["edge"],
                "raw_ev_per_unit": raw_grade["ev_per_unit"],
                "generic_calibrated_ev_per_unit": generic_grade["ev_per_unit"],
                "calibrated_ev_per_unit": calibrated_grade["ev_per_unit"],
                "ev_per_unit": calibrated_grade["ev_per_unit"],
                "raw_fair_american": raw_grade["fair_american"],
                "generic_calibrated_fair_american": generic_grade["fair_american"],
                "calibrated_fair_american": calibrated_grade["fair_american"],
                "fair_american": calibrated_grade["fair_american"],
                "raw_status": raw_grade["status"],
                "generic_calibrated_status": generic_grade["status"],
                "calibrated_status": calibrated_grade["status"],
                "status": calibrated_grade["status"],
                "generic_calibrated_min_edge": min_edge,
                "calibrated_min_edge": min_calibrated_edge(market, selection, min_edge, calibration_config),
                **calibration,
                "raw_would_bet": raw_would_bet,
                "generic_calibrated_would_bet": generic_calibrated_would_bet,
                "calibrated_would_bet": calibrated_would_bet,
                "won": won,
                "raw_profit_units": profit if raw_would_bet else 0.0,
                "generic_calibrated_profit_units": profit if generic_calibrated_would_bet else 0.0,
                "calibrated_profit_units": profit if calibrated_would_bet else 0.0,
                "profit_units": profit if calibrated_would_bet else 0.0,
            })

    return pd.DataFrame(bets)


def summarize_backtest(bets: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "market", "raw_bets", "raw_wins", "raw_profit_units", "raw_roi",
        "generic_calibrated_bets", "generic_calibrated_wins", "generic_calibrated_profit_units", "generic_calibrated_roi",
        "calibrated_bets", "calibrated_wins", "calibrated_profit_units", "calibrated_roi",
        "bets_filtered_out", "bets", "wins", "losses", "win_rate", "profit_units", "roi",
    ]
    if bets.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for market, group in bets.groupby("market"):
        raw = group[group.get("raw_would_bet", False) == True]
        generic = group[group.get("generic_calibrated_would_bet", False) == True]
        calibrated = group[group.get("calibrated_would_bet", True) == True]
        raw_bets = len(raw)
        generic_bets = len(generic)
        calibrated_bets = len(calibrated)
        raw_wins = int(raw["won"].sum()) if raw_bets else 0
        generic_wins = int(generic["won"].sum()) if generic_bets else 0
        calibrated_wins = int(calibrated["won"].sum()) if calibrated_bets else 0
        raw_profit = round(float(raw["raw_profit_units"].sum()), 3) if raw_bets else 0.0
        generic_profit = round(float(generic["generic_calibrated_profit_units"].sum()), 3) if generic_bets else 0.0
        calibrated_profit = round(float(calibrated["calibrated_profit_units"].sum()), 3) if calibrated_bets else 0.0
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
            "bets_filtered_out": raw_bets - calibrated_bets,
            "bets": calibrated_bets,
            "wins": calibrated_wins,
            "losses": calibrated_bets - calibrated_wins,
            "win_rate": round(calibrated_wins / calibrated_bets, 3) if calibrated_bets else 0.0,
            "profit_units": calibrated_profit,
            "roi": round(calibrated_profit / calibrated_bets, 3) if calibrated_bets else 0.0,
        })
    return pd.DataFrame(rows, columns=columns).sort_values("calibrated_profit_units", ascending=False)
