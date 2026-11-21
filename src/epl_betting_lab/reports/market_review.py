"""Where the card loses money, and whether two declared fixes would have helped.

Cooper, 2026-11-21: *"reevaluate any markets where we are losing
money/bets and see how we can improve"*.

Two parts.

1. **The live record, cut by market, side and price band**, from the card's
   own archive and `build_scoreboard`, at the price each pick was first
   published. This is the only out-of-sample evidence, and at 180 settled
   picks no cell of it can separate a 5% edge from zero.

2. **Two fixes, declared before any price was read for this review, scored
   on prices the card did not choose:**

   - `cap_200`: no best bet at +200 or longer (the live +200 to +500 band went
     4-21 against about 6.6 wins the prices implied). Rows past the cap are
     refused exactly as `MAX_DEFAULT_PRICE` refuses them past +600 today.
   - `anchored`: the 2.5 line's market-anchored rule, constants unchanged
     (`MODEL_WEIGHT` 0.5, `ANCHOR_THRESHOLD` 0.03, the price gate), applied to
     the result markets. A pick must beat the de-vigged market on a blend of
     the model and the market, not on the model alone, which is the rule the
     totals and corner totals already run.
   - `anchored_cap_200`: both.

   Scored on (a) the bought 2025/26 season of draw-no-bet, double chance and
   BTTS prices at bettable books, walk-forward, capped at the card's eight
   per round (`derived_market_backtest`), and (b) Football-Data's 1X2 history
   on the old ratings the card runs, read only on the seasons the 1X2 rule was
   not chosen on, with closing-line value. Nothing here buys a price.

A fix ships only if it does not lose more than the card's current rule on
either set and does not give up closing-line value on the 1X2 set. None of it
is evidence of an edge.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

from epl_betting_lab.config import MAX_DEFAULT_JUICE, MIN_EDGE
from epl_betting_lab.models.calibration import (
    ShrinkageConfig,
    calibrate_probability,
    min_calibrated_edge,
)
from epl_betting_lab.models.value import grade_edge
from epl_betting_lab.reports.derived_market_backtest import (
    american_to_profit,
    bootstrap_interval,
)
from epl_betting_lab.reports.out_of_sample import TEST_SEASONS, TRAIN_SEASONS
from epl_betting_lab.reports.thursday_best_bets import MAX_BEST_BETS_DEFAULT
from epl_betting_lab.strategies.totals import ANCHOR_THRESHOLD, MODEL_WEIGHT

#: The price from which `cap_200` refuses a best bet.
CAP_PRICE = 200
RULES = ("card", "cap_200", "anchored", "anchored_cap_200")
#: Second round (declared 2026-11-21 after the first run showed the old
#: ratings price the home side about 2.4 points under the de-vigged market
#: over 1,620 matches, and under what happened): the card's own rule on 1X2
#: probabilities re-weighted per outcome so that, on the rule seasons only,
#: the average home, draw and away probability equals how often each
#: happened. Read on the held-out seasons and on the bought 2025/26 prices.
SIDE_RULES = ("side_fix", "side_fix_cap_200")


def _logit(p: np.ndarray | float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def implied(american: float) -> float:
    a = float(american)
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def decimal_to_american(dec: float) -> float:
    return (dec - 1.0) * 100.0 if dec >= 2.0 else -100.0 / (dec - 1.0)


def price_band(american: float) -> str:
    a = float(american)
    if a <= -150:
        return "-150 or shorter"
    if a < 100:
        return "-149 to -101"
    if a < 150:
        return "+100 to +149"
    if a < 200:
        return "+150 to +199"
    if a <= 500:
        return "+200 to +500"
    return "longer than +500"


# ---------- part 1: the live record ----------


def live_frame(scored: Iterable[object]) -> pd.DataFrame:
    """One row per settled live pick, from `Scoreboard.scored`."""
    rows = []
    for s in scored:
        if not getattr(s, "settled", False):
            continue
        rows.append(
            {
                "market": s.market,
                "selection": s.selection,
                "american_odds": float(s.american_odds),
                "won": bool(s.won) if s.won is not None else False,
                "push": bool(s.pushed),
                "staked": float(s.stake_units),
                "profit": float(s.profit_units),
                "implied": implied(s.american_odds),
            }
        )
    return pd.DataFrame(rows)


def live_table(live: pd.DataFrame, by: Sequence[str]) -> pd.DataFrame:
    """Record, units, return and wins against the wins the prices implied."""
    if live.empty:
        return pd.DataFrame()
    out = []
    for key, g in live.groupby(list(by), sort=True):
        decided = g[~g["push"]]
        staked = g["staked"].sum()
        out.append(
            {
                **dict(zip(by, key if isinstance(key, tuple) else (key,))),
                "picks": len(g),
                "w": int(decided["won"].sum()),
                "l": int((~decided["won"]).sum()),
                "p": int(g["push"].sum()),
                "units": round(float(g["profit"].sum()), 2),
                "staked": round(float(staked), 2),
                "return_pct": round(100 * float(g["profit"].sum()) / staked, 1) if staked else None,
                "wins_priced_in": round(float(decided["implied"].sum()), 1),
            }
        )
    return pd.DataFrame(out).sort_values("units")


# ---------- part 2: the fixes ----------


def with_market_probability(scored: pd.DataFrame) -> pd.DataFrame:
    """Add `p_market`: each selection's de-vigged share of its fixture's market.

    De-vigged from the best takeable price of every selection in the same
    fixture and market. Double chance's three selections cover each outcome
    twice, so they are normalised to sum to two. A fixture missing a side has
    no fair price and gets NaN, so no anchored rule can bet it.
    """
    frame = scored.copy()
    frame["_inv"] = [implied(a) for a in frame["american_odds"]]
    key = ["date", "home_team", "away_team", "market"]
    total = frame.groupby(key)["_inv"].transform("sum")
    count = frame.groupby(key)["_inv"].transform("count")
    need = frame["market"].map({"double_chance": 3}).fillna(2)
    target = frame["market"].map({"double_chance": 2.0}).fillna(1.0)
    frame["p_market"] = np.where(count == need, frame["_inv"] / total * target, np.nan)
    return frame.drop(columns=["_inv"])


def select(frame: pd.DataFrame, rule: str, *, model_column: str) -> pd.Series:
    """Which rows a rule bets, before the per-round cap."""
    price = frame["american_odds"].astype(float)
    in_range = price >= MAX_DEFAULT_JUICE
    if rule in ("card", "cap_200"):
        chosen = frame["status"].astype(str).str.upper() == "BETTABLE"
    else:
        p_market = frame["p_market"].astype(float)
        blended = _sigmoid(
            MODEL_WEIGHT * _logit(frame[model_column]) + (1 - MODEL_WEIGHT) * _logit(p_market)
        )
        frame["anchored_edge"] = blended - np.array([implied(a) for a in price])
        chosen = (
            p_market.notna()
            & ((blended - p_market) > ANCHOR_THRESHOLD)
            & (frame["anchored_edge"] > 0)
            & in_range
            & (price <= 600)
        )
    if rule.endswith("cap_200"):
        chosen &= price < CAP_PRICE
    return chosen.fillna(False)


def cap_per_round(bets: pd.DataFrame, edge_column: str) -> pd.DataFrame:
    """At most `MAX_BEST_BETS_DEFAULT` per week, highest edge first."""
    if bets.empty:
        return bets
    ranked = bets.assign(_round=pd.to_datetime(bets["date"]).dt.to_period("W"))
    return (
        ranked.sort_values(edge_column, ascending=False)
        .groupby("_round", sort=False, group_keys=False)
        .head(MAX_BEST_BETS_DEFAULT)
        .drop(columns=["_round"])
    )


def ladder_return(bets: pd.DataFrame) -> tuple[float, float]:
    """(units, risked) at the 1u ladder, so the figures read like the site's."""
    from epl_betting_lab import staking

    units = risked = 0.0
    for a, won, push in zip(bets["american_odds"], bets["won"], bets["push"]):
        graded = staking.graded(a, "push" if push else "win" if won else "loss")
        if graded:
            units += graded[0]
            risked += graded[1]
    return units, risked


def score(bets: pd.DataFrame) -> dict[str, object]:
    if bets.empty:
        return {"bets": 0}
    low, high, above = bootstrap_interval(bets)
    units, risked = ladder_return(bets)
    out = {
        "bets": int(len(bets)),
        "roi_pct": round(float(bets["profit"].mean()) * 100, 2),
        "ci_low_pct": round(low, 1),
        "ci_high_pct": round(high, 1),
        "ladder_units": round(units, 2),
        "ladder_risked": round(risked, 2),
    }
    if "clv" in bets.columns and bets["clv"].notna().any():
        out["clv_points"] = round(float(bets["clv"].mean()) * 100, 3)
    return out


def derived_rules(scored: pd.DataFrame) -> pd.DataFrame:
    """Every rule on the bought draw-no-bet, double-chance and BTTS prices."""
    frame = with_market_probability(
        scored[scored["market"].isin(["draw_no_bet", "double_chance", "btts"])]
    )
    frame["profit"] = [
        0.0 if bool(p) else american_to_profit(float(a), bool(w))
        for a, w, p in zip(frame["american_odds"], frame["won"], frame["push"])
    ]
    rows = []
    for rule in RULES:
        chosen = select(frame, rule, model_column="calibrated_model_prob")
        edge = "anchored_edge" if rule.startswith("anchored") else "calibrated_edge"
        bets = cap_per_round(frame[chosen].copy(), edge)
        for market, group in [("ALL", bets)] + list(bets.groupby("market", sort=True)):
            rows.append({"rule": rule, "market": market, **score(group)})
    return pd.DataFrame(rows)


def one_x_two_frame(probs: pd.DataFrame) -> pd.DataFrame:
    """The 1X2 rows the card would grade, from `walk_forward_probabilities`.

    The card's own rule (`evaluate_1x2_value`): calibrate the model toward the
    price, grade the edge against the opening average price.
    """
    d = probs.dropna(subset=["AvgH", "AvgD", "AvgA"]).copy()
    inv = 1.0 / d[["AvgH", "AvgD", "AvgA"]]
    devig = inv.div(inv.sum(axis=1), axis=0)
    parts = []
    for sel, p_col, odds_col, close_col, won in (
        ("home", "p_home", "AvgH", "AvgCH", d.home_goals > d.away_goals),
        ("draw", "p_draw", "AvgD", "AvgCD", d.home_goals == d.away_goals),
        ("away", "p_away", "AvgA", "AvgCA", d.home_goals < d.away_goals),
    ):
        part = pd.DataFrame(
            {
                "date": d["date"].values,
                "season": d["season"].values,
                "home_team": d["home_team"].values,
                "away_team": d["away_team"].values,
                "market": "1x2",
                "selection": sel,
                "p_model": d[p_col].values,
                "p_market": devig[odds_col].values,
                "open_dec": d[odds_col].values,
                "close_dec": d[close_col].values if close_col in d else np.nan,
                "won": won.values,
                "push": False,
            }
        )
        parts.append(part)
    frame = pd.concat(parts, ignore_index=True)
    frame["american_odds"] = [decimal_to_american(x) for x in frame["open_dec"]]
    frame["clv"] = 1.0 / frame["close_dec"] - 1.0 / frame["open_dec"]
    frame["profit"] = np.where(frame["won"], frame["open_dec"] - 1.0, -1.0)
    config = ShrinkageConfig()
    calibrated, status, edge = [], [], []
    for p, a, sel in zip(frame["p_model"], frame["american_odds"], frame["selection"]):
        cal = float(calibrate_probability(p, "1x2", sel, american_odds=a, config=config)["calibrated_model_prob"])
        grade = grade_edge(
            cal, a, min_edge=min_calibrated_edge("1x2", sel, MIN_EDGE, config),
            max_default_juice=MAX_DEFAULT_JUICE,
        )
        calibrated.append(cal)
        status.append(grade["status"])
        edge.append(grade["edge"])
    frame["calibrated_model_prob"] = calibrated
    frame["calibrated_edge"] = edge
    frame["status"] = status
    return frame


def one_x_two_rules(probs: pd.DataFrame) -> pd.DataFrame:
    """Every rule on 1X2, by season block, with closing-line value."""
    frame = one_x_two_frame(probs)
    rows = []
    for block, seasons in (("train", TRAIN_SEASONS), ("test", TEST_SEASONS)):
        part = frame[frame["season"].isin(set(seasons))].copy()
        for rule in RULES:
            chosen = select(part, rule, model_column="calibrated_model_prob")
            edge = "anchored_edge" if rule.startswith("anchored") else "calibrated_edge"
            bets = cap_per_round(part[chosen].copy(), edge)
            rows.append({"block": block, "rule": rule, "market": "1x2", **score(bets)})
            for sel, group in bets.groupby("selection", sort=True):
                rows.append({"block": block, "rule": rule, "market": f"1x2 {sel}", **score(group)})
    return pd.DataFrame(rows)


def fit_side_weights(probs: pd.DataFrame, *, iterations: int = 200) -> tuple[float, float, float]:
    """Per-outcome weights (home, draw, away), fitted by iterative scaling.

    After re-weighting and renormalising each match, the mean probability of
    each outcome equals its observed frequency in `probs`. Three numbers,
    fitted on the rule seasons only, so the held-out read is honest.
    """
    p = probs[["p_home", "p_draw", "p_away"]].to_numpy(dtype=float)
    observed = np.array([
        (probs.home_goals > probs.away_goals).mean(),
        (probs.home_goals == probs.away_goals).mean(),
        (probs.home_goals < probs.away_goals).mean(),
    ])
    w = np.ones(3)
    for _ in range(iterations):
        q = p * w
        q /= q.sum(axis=1, keepdims=True)
        w *= observed / q.mean(axis=0)
        w /= w[0]
    return tuple(float(x) for x in w)  # type: ignore[return-value]


def reweight(h: float, d: float, a: float, weights: Sequence[float]) -> tuple[float, float, float]:
    q = np.array([h, d, a]) * np.asarray(weights)
    q = q / q.sum()
    return float(q[0]), float(q[1]), float(q[2])


def log_loss_1x2(probs: pd.DataFrame, weights: Sequence[float] | None = None) -> float:
    p = probs[["p_home", "p_draw", "p_away"]].to_numpy(dtype=float)
    if weights is not None:
        p = p * np.asarray(weights)
        p = p / p.sum(axis=1, keepdims=True)
    outcome = np.select(
        [probs.home_goals > probs.away_goals, probs.home_goals == probs.away_goals], [0, 1], 2
    )
    return float(-np.log(np.clip(p[np.arange(len(p)), outcome], 1e-9, 1)).mean())


def market_log_loss_1x2(probs: pd.DataFrame) -> float:
    d = probs.dropna(subset=["AvgH", "AvgD", "AvgA"])
    inv = 1.0 / d[["AvgH", "AvgD", "AvgA"]].to_numpy(dtype=float)
    p = inv / inv.sum(axis=1, keepdims=True)
    outcome = np.select([d.home_goals > d.away_goals, d.home_goals == d.away_goals], [0, 1], 2)
    return float(-np.log(np.clip(p[np.arange(len(p)), outcome], 1e-9, 1)).mean())


def side_fix_1x2(probs: pd.DataFrame) -> tuple[pd.DataFrame, tuple[float, float, float]]:
    """The card's 1X2 rule on re-weighted probabilities, by season block."""
    train = probs[probs["season"].isin(set(TRAIN_SEASONS))]
    weights = fit_side_weights(train)
    adjusted = probs.copy()
    triples = [reweight(h, d, a, weights) for h, d, a in zip(probs.p_home, probs.p_draw, probs.p_away)]
    adjusted[["p_home", "p_draw", "p_away"]] = np.array(triples)
    frame = one_x_two_frame(adjusted)
    rows = []
    for block, seasons in (("train", TRAIN_SEASONS), ("test", TEST_SEASONS)):
        part = frame[frame["season"].isin(set(seasons))].copy()
        sub = probs[probs["season"].isin(set(seasons))]
        for rule in SIDE_RULES:
            chosen = select(part, "cap_200" if rule.endswith("cap_200") else "card", model_column="calibrated_model_prob")
            bets = cap_per_round(part[chosen].copy(), "calibrated_edge")
            rows.append({"block": block, "rule": rule, "market": "1x2", **score(bets)})
            for sel, group in bets.groupby("selection", sort=True):
                rows.append({"block": block, "rule": rule, "market": f"1x2 {sel}", **score(group)})
        rows.append({
            "block": block, "rule": "log loss", "market": "model / re-weighted / market",
            "bets": len(sub),
            "roi_pct": round(log_loss_1x2(sub), 4),
            "ci_low_pct": round(log_loss_1x2(sub, weights), 4),
            "ci_high_pct": round(market_log_loss_1x2(sub), 4),
        })
    return pd.DataFrame(rows), weights


def side_fix_derived(scored: pd.DataFrame, weights: Sequence[float]) -> pd.DataFrame:
    """Draw no bet and double chance on the bought prices, re-weighted.

    Each fixture's home/draw/away is recovered from the raw double-chance
    probabilities the backtest priced (home_or_draw + draw_or_away - 1 is the
    draw), re-weighted, and every row graded again by the card's own
    `evaluate_derived_market` arithmetic. A fixture without both double-chance
    sides priced is left out of both rules, so the comparison is like for like.
    """
    from epl_betting_lab.strategies.derived_result import evaluate_derived_market

    frame = scored[scored["market"].isin(["draw_no_bet", "double_chance"])].copy()
    key = ["date", "home_team", "away_team"]
    dc = frame[frame["market"] == "double_chance"].pivot_table(
        index=key, columns="selection", values="raw_model_prob", aggfunc="first"
    )
    if not {"home_or_draw", "draw_or_away"} <= set(dc.columns):
        return pd.DataFrame()
    dc = dc.dropna(subset=["home_or_draw", "draw_or_away"])
    draw = dc["home_or_draw"] + dc["draw_or_away"] - 1
    home = dc["home_or_draw"] - draw
    away = dc["draw_or_away"] - draw
    projections = []
    for (date, ht, at), h, d, a in zip(dc.index, home, draw, away):
        h2, d2, a2 = reweight(max(h, 1e-4), max(d, 1e-4), max(a, 1e-4), weights)
        projections.append({
            "date": date, "home_team": ht, "away_team": at,
            "double_chance_home_or_draw": h2 + d2, "double_chance_draw_or_away": d2 + a2,
            "double_chance_home_or_away": h2 + a2,
            "draw_no_bet_home": h2 / (h2 + a2), "draw_no_bet_away": a2 / (h2 + a2),
        })
    proj = pd.DataFrame(projections)
    kept = frame.merge(proj[key], on=key)
    outcome = (
        kept.drop_duplicates(subset=key + ["market", "selection"])
        .set_index(key + ["market", "selection"])[["won", "push"]]
    )
    rows = []
    for (date, ht, at), p_rows in proj.groupby(key):
        odds = kept[(kept.date == date) & (kept.home_team == ht) & (kept.away_team == at)]
        for market in ("draw_no_bet", "double_chance"):
            graded = evaluate_derived_market(
                market, p_rows, odds[odds.market == market][["home_team", "away_team", "market", "selection", "american_odds", "book"]],
                min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE,
            )
            if graded.empty:
                continue
            graded["date"] = date
            rows.extend(graded.to_dict("records"))
    regraded = pd.DataFrame(rows)
    if regraded.empty:
        return pd.DataFrame()
    regraded = regraded.join(outcome, on=key + ["market", "selection"])
    regraded["profit"] = [
        0.0 if bool(p) else american_to_profit(float(a), bool(w))
        for a, w, p in zip(regraded["american_odds"], regraded["won"], regraded["push"])
    ]
    base = kept.copy()
    base["profit"] = [
        0.0 if bool(p) else american_to_profit(float(a), bool(w))
        for a, w, p in zip(base["american_odds"], base["won"], base["push"])
    ]
    out = []
    for name, data in (("card (same fixtures)", base), ("side_fix", regraded)):
        for cap in (False, True):
            label = name + (" + cap_200" if cap else "")
            chosen = select(data, "cap_200" if cap else "card", model_column="calibrated_model_prob")
            bets = cap_per_round(data[chosen].copy(), "calibrated_edge")
            for market, group in [("ALL", bets)] + list(bets.groupby("market", sort=True)):
                out.append({"rule": label, "market": market, **score(group)})
    return pd.DataFrame(out)


def model_minus_market(frame: pd.DataFrame, model_column: str) -> pd.DataFrame:
    """Mean model probability, market probability and hit rate by selection.

    A model that leans one way (away sides, long prices) shows here before
    any rule is read.
    """
    f = frame.dropna(subset=["p_market"]).copy()
    f["band"] = [price_band(a) for a in f["american_odds"]]
    rows = []
    for key, g in f.groupby(["market", "selection"], sort=True):
        rows.append(
            {
                "market": key[0],
                "selection": key[1],
                "rows": len(g),
                "model": round(float(g[model_column].mean()), 4),
                "market_fair": round(float(g["p_market"].mean()), 4),
                "happened": round(float(g["won"].astype(float).mean()), 4),
            }
        )
    return pd.DataFrame(rows)


def render(
    live: pd.DataFrame,
    derived: pd.DataFrame | None,
    one_x_two: pd.DataFrame | None,
    lean: Sequence[pd.DataFrame],
    notes: Sequence[str],
    side: Sequence[tuple[str, pd.DataFrame | None]] = (),
) -> str:
    lines = [
        "# Market review",
        "",
        "Where the card loses, and whether two fixes declared before this review read any price "
        "would have helped. `cap_200`: no best bet at +200 or longer. `anchored`: the 2.5 line's "
        f"market-anchored rule (model weight {MODEL_WEIGHT}, lift {ANCHOR_THRESHOLD}, price gate) on the "
        "result markets. No market here shows a demonstrated edge.",
        "",
    ]
    if not live.empty:
        for by, title in (
            (["market"], "Live record by market"),
            (["market", "selection"], "Live record by market and side"),
            (["band"], "Live record by price band"),
        ):
            frame = live.assign(band=[price_band(a) for a in live["american_odds"]])
            lines += [f"## {title}", "", live_table(frame, by).to_markdown(index=False), ""]
    for frame, title in (
        (derived, "Bought 2025/26 prices: draw no bet, double chance, BTTS (walk-forward, 8 per round)"),
        (one_x_two, "1X2 on Football-Data, old ratings: rule seasons (train) and held-out seasons (test)"),
    ):
        if frame is not None and not frame.empty:
            lines += [f"## {title}", "", frame.to_markdown(index=False), ""]
    for title, frame in side:
        if frame is not None and not frame.empty:
            lines += [f"## {title}", "", frame.to_markdown(index=False), ""]
    for frame in lean:
        if frame is not None and not frame.empty:
            lines += ["## Model against the de-vigged market, every priced row", "", frame.to_markdown(index=False), ""]
    if notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in notes] + [""]
    return "\n".join(lines)


# --- Where the home tilt comes from, and one structural fix (2026-11-21) ---
#
# Cooper, after the first review: "do whatever is best and will lead to more
# profits". The re-weighting above patched the symptom and failed on the rule
# seasons. This looks for the cause. The old ratings price a club with no
# history in the frame - a promoted side - as exactly league average, and
# promoted sides are on average the weakest in the league, so every fixture
# against one is priced too kindly to them. Declared before the run: the
# candidate rates an unrated club as the mean of the three lowest-rated clubs
# in the same fit (a relegation-level side; no constant, nothing fitted on any
# test season), and it ships only under the review's rule.

PROMOTED_PRIOR_RANK = 3


def promoted_prior(model) -> "object":
    from epl_betting_lab.models.poisson_goals import TeamStrength

    ranked = sorted(model.team_strengths.values(), key=lambda s: s.attack / s.defense)
    weakest = ranked[:PROMOTED_PRIOR_RANK]
    if not weakest:
        return TeamStrength(1.0, 1.0)
    return TeamStrength(
        attack=float(np.mean([s.attack for s in weakest])),
        defense=float(np.mean([s.defense for s in weakest])),
    )


def walk_forward_with_prior(matches: pd.DataFrame, *, start_after: int = 380, last_n: int = 38) -> pd.DataFrame:
    """Legacy walk-forward, twice per match: league-average prior and the
    relegation-level prior for an unrated club. Flags which side was unrated."""
    from epl_betting_lab.models.poisson_goals import PoissonGoalsModel

    df = (
        matches.dropna(subset=["home_goals", "away_goals", "date"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    rows = []
    for i in range(start_after, len(df)):
        game = df.iloc[i]
        model = PoissonGoalsModel().fit(df.iloc[:i], last_n_matches_per_team=last_n)
        base = model.match_probabilities(game.home_team, game.away_team, allow_unrated=True)
        home_new = game.home_team not in model.team_strengths
        away_new = game.away_team not in model.team_strengths
        if home_new or away_new:
            prior = promoted_prior(model)
            for team in (game.home_team, game.away_team):
                model.team_strengths.setdefault(team, prior)
            fixed = model.match_probabilities(game.home_team, game.away_team)
        else:
            fixed = base
        row = {
            "date": game.date, "season": game.season,
            "home_team": game.home_team, "away_team": game.away_team,
            "home_goals": int(game.home_goals), "away_goals": int(game.away_goals),
            "unrated": "home" if home_new else "away" if away_new else "none",
            "p_home": float(base["home_win"]), "p_draw": float(base["draw"]), "p_away": float(base["away_win"]),
            "fix_home": float(fixed["home_win"]), "fix_draw": float(fixed["draw"]), "fix_away": float(fixed["away_win"]),
        }
        for col in ("AvgH", "AvgD", "AvgA", "AvgCH", "AvgCD", "AvgCA"):
            row[col] = game.get(col)
        rows.append(row)
    return pd.DataFrame(rows)


def tilt_breakdown(probs: pd.DataFrame) -> pd.DataFrame:
    """Home probability: model, fixed model, market and what happened, by
    whether a side had no rating and by month of the season."""
    d = probs.dropna(subset=["AvgH", "AvgD", "AvgA"]).copy()
    inv = 1.0 / d[["AvgH", "AvgD", "AvgA"]].to_numpy(dtype=float)
    d["m_home"] = inv[:, 0] / inv.sum(axis=1)
    d["m_away"] = inv[:, 2] / inv.sum(axis=1)
    d["won_home"] = (d.home_goals > d.away_goals).astype(float)
    d["won_away"] = (d.home_goals < d.away_goals).astype(float)
    d["month"] = pd.to_datetime(d["date"]).dt.month
    d["window"] = np.where(d["month"].isin([8, 9, 10]), "Aug-Oct", "Nov-May")
    rows = []
    for by in ("unrated", "window"):
        for key, g in d.groupby(by):
            rows.append({
                "cut": f"{by}={key}", "matches": len(g),
                "home model": round(g.p_home.mean(), 4), "home fixed": round(g.fix_home.mean(), 4),
                "home market": round(g.m_home.mean(), 4), "home happened": round(g.won_home.mean(), 4),
                "away model": round(g.p_away.mean(), 4), "away fixed": round(g.fix_away.mean(), 4),
                "away market": round(g.m_away.mean(), 4), "away happened": round(g.won_away.mean(), 4),
            })
    return pd.DataFrame(rows)


def promoted_prior_rules(probs: pd.DataFrame) -> pd.DataFrame:
    """The card's 1X2 rule on the current and the fixed probabilities, by block."""
    fixed = probs.copy()
    fixed[["p_home", "p_draw", "p_away"]] = probs[["fix_home", "fix_draw", "fix_away"]].to_numpy()
    rows = []
    for name, frame in (("card", one_x_two_frame(probs)), ("promoted_prior", one_x_two_frame(fixed))):
        for block, seasons in (("train", TRAIN_SEASONS), ("test", TEST_SEASONS)):
            part = frame[frame["season"].isin(set(seasons))].copy()
            sub = (probs if name == "card" else fixed)
            sub = sub[sub["season"].isin(set(seasons))]
            bets = cap_per_round(part[select(part, "card", model_column="calibrated_model_prob")].copy(), "calibrated_edge")
            rows.append({"block": block, "rule": name, "market": "1x2", **score(bets),
                         "log_loss": round(log_loss_1x2(sub), 4)})
            for sel, group in bets.groupby("selection", sort=True):
                rows.append({"block": block, "rule": name, "market": f"1x2 {sel}", **score(group)})
    return pd.DataFrame(rows)
