from __future__ import annotations

import pandas as pd

from epl_betting_lab.config import MIN_EDGE, MAX_DEFAULT_JUICE
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
            grade = grade_edge(float(model_prob), american, min_edge=min_edge, max_default_juice=max_juice)
            if grade["status"] != "BETTABLE":
                continue

            if market == "1x2":
                won = _settle_1x2(selection, int(game.home_goals), int(game.away_goals))
            elif market == "total_2_5":
                won = _settle_total_25(selection, int(game.home_goals), int(game.away_goals))
            else:
                continue

            bets.append({
                "date": game.date,
                "season": game.season,
                "home_team": game.home_team,
                "away_team": game.away_team,
                "score": f"{int(game.home_goals)}-{int(game.away_goals)}",
                "market": market,
                "selection": selection,
                "decimal_odds": round(float(dec_odds), 3),
                "american_odds": american,
                "model_prob": grade["model_prob"],
                "book_implied": grade["book_implied"],
                "edge": grade["edge"],
                "ev_per_unit": grade["ev_per_unit"],
                "won": won,
                "profit_units": round(_profit(won, float(dec_odds)), 3),
            })

    return pd.DataFrame(bets)


def summarize_backtest(bets: pd.DataFrame) -> pd.DataFrame:
    if bets.empty:
        return pd.DataFrame(columns=["market", "bets", "wins", "losses", "win_rate", "profit_units", "roi"])
    grouped = bets.groupby("market").agg(
        bets=("won", "size"),
        wins=("won", "sum"),
        profit_units=("profit_units", "sum"),
    ).reset_index()
    grouped["losses"] = grouped["bets"] - grouped["wins"]
    grouped["win_rate"] = (grouped["wins"] / grouped["bets"]).round(3)
    grouped["profit_units"] = grouped["profit_units"].round(3)
    grouped["roi"] = (grouped["profit_units"] / grouped["bets"]).round(3)
    return grouped.sort_values("profit_units", ascending=False)
