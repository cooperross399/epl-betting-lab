from __future__ import annotations

import pandas as pd

from epl_betting_lab.config import BANKROLL_UNIT_DOLLARS


def confidence_tier(edge: float, ev_per_unit: float) -> str:
    if edge >= 0.08 and ev_per_unit >= 0.08:
        return "A"
    if edge >= 0.055 and ev_per_unit >= 0.04:
        return "B"
    if edge >= 0.035 and ev_per_unit > 0:
        return "C"
    return "Lean/Pass"


def build_weekly_card(candidates: pd.DataFrame, max_plays: int = 8) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    df = candidates.copy()
    df = df[df["status"].isin(["BETTABLE", "LEAN"])].copy()
    if df.empty:
        return df
    df["confidence"] = df.apply(lambda r: confidence_tier(float(r.edge), float(r.ev_per_unit)), axis=1)
    df["suggested_units"] = df["confidence"].map({"A": 0.75, "B": 0.5, "C": 0.25, "Lean/Pass": 0.1}).fillna(0.1)
    df["suggested_wager_$"] = (df["suggested_units"] * BANKROLL_UNIT_DOLLARS).round(2)
    df = df.sort_values(["confidence", "edge", "ev_per_unit"], ascending=[True, False, False]).head(max_plays)
    return df


def card_to_markdown(card: pd.DataFrame) -> str:
    if card.empty:
        return "No bettable EPL edges found with the current inputs."

    lines = ["# EPL Weekly Betting Card", ""]
    for _, r in card.iterrows():
        matchup = f"{r.home_team} vs {r.away_team}"
        lines.append(f"## {matchup}")
        lines.append(f"**Play:** {r.market} — {r.selection} ({int(r.american_odds):+d})")
        lines.append(f"**Confidence:** {r.confidence} | **Suggested:** {r.suggested_units}u / ${r["suggested_wager_$"]}")
        raw_prob = getattr(r, "raw_model_prob", r.model_prob)
        calibrated_prob = getattr(r, "calibrated_model_prob", r.model_prob)
        raw_edge = getattr(r, "raw_edge", r.edge)
        calibrated_edge = getattr(r, "calibrated_edge", r.edge)
        lines.append(
            f"**Model:** raw {raw_prob:.1%} / calibrated {calibrated_prob:.1%} | "
            f"**Book implied:** {r.book_implied:.1%}"
        )
        lines.append(f"**Edge:** raw {raw_edge:.1%} / calibrated {calibrated_edge:.1%}")
        lines.append(f"**Fair price:** {int(r.fair_american):+d}")
        lines.append("")
    return "\n".join(lines)
