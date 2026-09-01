"""Does a bet rule survive seasons it was not tuned on?

Every profit figure this project had reported came from one walk-forward pass
over all five seasons, with the shrinkage and thresholds chosen while looking
at that same pass. That is not a test; it is a fit. The 1X2 rule showed +34
units that way, and its raw form — the same model with no filter — lost 5.7
over 774 bets. The filter *was* the profit, and the filter was chosen on the
answers.

This module splits by season instead: a rule is chosen on the training seasons
and its numbers are read off the held-out ones. It reports closing-line value
first, because with a few hundred bets a season profit cannot distinguish a
5% edge from zero, while the closing line moves on every bet.

The selection rule is market-anchored: the model's probability is blended with
the de-vigged market probability in logit space, weight `a` on the model, and
a bet is flagged where the blend still clears the opening price by `threshold`.
`a = 1` is the old rule (pure model); `a = 0` never bets. A model that has no
information the market lacks earns a small `a` and few bets, and that is the
result rather than a failure of the method.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig

TRAIN_SEASONS: tuple[int, ...] = (2122, 2223, 2324, 2425)
TEST_SEASONS: tuple[int, ...] = (2526, 2627)
START_AFTER_MATCHES = 380
MIN_BETS = 20


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def walk_forward_probabilities(
    matches: pd.DataFrame,
    config: RatingConfig | None = None,
    *,
    start_after_matches: int = START_AFTER_MATCHES,
    last_n_matches_per_team: int | None = 38,
) -> pd.DataFrame:
    """Model probabilities for each match using only the matches before it.

    One row per match with the model's 1X2 and over-2.5 probabilities beside
    the opening and closing market prices, so a selection rule can be scored
    many times without refitting the model each time.
    """
    config = config or RatingConfig.legacy()
    last_n = None if config.opponent_adjusted else last_n_matches_per_team
    df = (
        matches.dropna(subset=["home_goals", "away_goals", "date"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    rows = []
    for i in range(start_after_matches, len(df)):
        game = df.iloc[i]
        probs = PoissonGoalsModel().fit(
            df.iloc[:i], last_n_matches_per_team=last_n, config=config
        ).match_probabilities(game.home_team, game.away_team)
        rows.append({
            "date": game.date, "season": game.season,
            "home_team": game.home_team, "away_team": game.away_team,
            "home_goals": int(game.home_goals), "away_goals": int(game.away_goals),
            "p_home": float(probs["home_win"]), "p_draw": float(probs["draw"]),
            "p_away": float(probs["away_win"]), "p_over": float(probs["over_2_5"]),
            "AvgH": game.get("AvgH"), "AvgD": game.get("AvgD"), "AvgA": game.get("AvgA"),
            "AvgCH": game.get("AvgCH"), "AvgCD": game.get("AvgCD"), "AvgCA": game.get("AvgCA"),
            "AvgO": game.get("Avg>2.5"), "AvgU": game.get("Avg<2.5"),
            "AvgCO": game.get("AvgC>2.5"), "AvgCU": game.get("AvgC<2.5"),
        })
    return pd.DataFrame(rows)


def selections_long(probs: pd.DataFrame, market: str) -> pd.DataFrame:
    """One row per (match, selection) with model, market, prices and outcome."""
    if market == "1x2":
        d = probs.dropna(subset=["AvgH", "AvgD", "AvgA"]).copy()
        inv = 1.0 / d[["AvgH", "AvgD", "AvgA"]]
        devig = inv.div(inv.sum(axis=1), axis=0)
        spec = [
            ("home", d["p_home"], devig["AvgH"], d["AvgH"], d.get("AvgCH"), d.home_goals > d.away_goals),
            ("draw", d["p_draw"], devig["AvgD"], d["AvgD"], d.get("AvgCD"), d.home_goals == d.away_goals),
            ("away", d["p_away"], devig["AvgA"], d["AvgA"], d.get("AvgCA"), d.home_goals < d.away_goals),
        ]
    elif market == "total_2_5":
        d = probs.dropna(subset=["AvgO", "AvgU"]).copy()
        inv_o, inv_u = 1.0 / d["AvgO"], 1.0 / d["AvgU"]
        m_over = inv_o / (inv_o + inv_u)
        over = (d.home_goals + d.away_goals) > 2.5
        spec = [
            ("over", d["p_over"], m_over, d["AvgO"], d.get("AvgCO"), over),
            ("under", 1 - d["p_over"], 1 - m_over, d["AvgU"], d.get("AvgCU"), ~over),
        ]
    else:
        raise ValueError(market)
    parts = []
    for sel, p_model, p_mkt, open_dec, close_dec, won in spec:
        parts.append(pd.DataFrame({
            "season": d["season"].values, "market": market, "selection": sel,
            "p_model": p_model.values, "p_market": p_mkt.values,
            "open_dec": open_dec.values,
            "close_dec": (close_dec.values if close_dec is not None else np.nan),
            "won": won.astype(float).values,
        }))
    out = pd.concat(parts, ignore_index=True)
    out["clv"] = 1.0 / out["close_dec"] - 1.0 / out["open_dec"]
    out["profit"] = np.where(out["won"] == 1.0, out["open_dec"] - 1.0, -1.0)
    return out


def score_rule(long: pd.DataFrame, a: float, threshold: float) -> dict | None:
    """Bets, CLV and profit for one (a, threshold) on one set of rows."""
    blended = _sigmoid(a * _logit(long["p_model"]) + (1 - a) * _logit(long["p_market"]))
    bets = long[(blended - long["p_market"]) > threshold]
    if len(bets) < MIN_BETS:
        return None
    with_close = bets.dropna(subset=["clv"])
    return {
        "bets": int(len(bets)),
        "clv_points": round(float(with_close["clv"].mean() * 100), 3) if len(with_close) else float("nan"),
        "clv_positive_rate": round(float((with_close["clv"] > 0).mean()), 3) if len(with_close) else float("nan"),
        "roi": round(float(bets["profit"].mean()), 4),
        "units": round(float(bets["profit"].sum()), 2),
    }


@dataclass(frozen=True)
class Grid:
    model_weights: Sequence[float] = (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0)
    thresholds: Sequence[float] = (0.01, 0.02, 0.03, 0.05)


def evaluate_out_of_sample(
    probs: pd.DataFrame,
    market: str,
    *,
    train_seasons: Iterable[int] = TRAIN_SEASONS,
    test_seasons: Iterable[int] = TEST_SEASONS,
    grid: Grid = Grid(),
) -> pd.DataFrame:
    """Every rule in the grid, scored on train and on held-out test seasons.

    Sorted by train CLV, because that is the only column a rule may be chosen
    on. The test columns are the answer.
    """
    long = selections_long(probs, market)
    train = long[long["season"].isin(set(train_seasons))]
    test = long[long["season"].isin(set(test_seasons))]
    rows = []
    for a in grid.model_weights:
        for threshold in grid.thresholds:
            tr, te = score_rule(train, a, threshold), score_rule(test, a, threshold)
            if tr is None or te is None:
                continue
            rows.append({
                "market": market, "model_weight": a, "threshold": threshold,
                **{f"train_{k}": v for k, v in tr.items()},
                **{f"test_{k}": v for k, v in te.items()},
            })
    out = pd.DataFrame(rows)
    return out.sort_values("train_clv_points", ascending=False).reset_index(drop=True) if not out.empty else out


def render_markdown(tables: dict[str, pd.DataFrame], *, model_name: str) -> str:
    lines = [
        f"# Out-of-sample selection — {model_name}",
        "",
        "Rules are chosen on the training seasons and read on the held-out ones. "
        "CLV is in probability points (closing implied minus opening implied; "
        "positive means the market moved toward the bet). Profit on a few hundred "
        "bets cannot separate a 5% edge from zero; CLV can.",
        "",
        f"Train seasons: {', '.join(str(s) for s in TRAIN_SEASONS)}. "
        f"Test seasons: {', '.join(str(s) for s in TEST_SEASONS)}.",
        "",
    ]
    for market, table in tables.items():
        lines += [f"## {market}", ""]
        if table.empty:
            lines += ["_No rule produced enough bets to score._", ""]
            continue
        lines += [table.head(12).to_markdown(index=False), ""]
    return "\n".join(lines)


def save_out_of_sample_reports(
    probs: pd.DataFrame, output_dir: Path, *, model_name: str, slug: str
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = {m: evaluate_out_of_sample(probs, m) for m in ("1x2", "total_2_5")}
    paths = {}
    for market, table in tables.items():
        p = output_dir / f"out_of_sample_{slug}_{market}.csv"
        table.to_csv(p, index=False); paths[market] = p
    md = output_dir / f"out_of_sample_{slug}.md"
    md.write_text(render_markdown(tables, model_name=model_name), encoding="utf-8")
    paths["markdown"] = md
    return paths
