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
    for frame in lean:
        if frame is not None and not frame.empty:
            lines += ["## Model against the de-vigged market, every priced row", "", frame.to_markdown(index=False), ""]
    if notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in notes] + [""]
    return "\n".join(lines)
