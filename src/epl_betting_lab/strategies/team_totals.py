"""Team totals: one team's goals over or under one half line.

Each market is one team at one line -- `team_total_home_1_5`,
`team_total_away_0_5` -- because a book sets a different line per team on the
same fixture. A single market carrying "the" line could never be complete; one
market per team and line is complete wherever the alternate ladder posts it,
and incomplete (so excluded, never approximated) wherever it does not.

Priced off each side's own Poisson marginal from the same fit as the 2.5 line
and BTTS (the opponent-adjusted, xG-blended ratings), so a team total cannot
disagree with the match total on the same card. Never measured against real
prices: there is no demonstrated edge here, and none is claimed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.staging_provider_policy import entry_is_complete_approval
from epl_betting_lab.strategies.derived_result import evaluate_derived_market

#: market -> {selection: column on the projection row}
TEAM_TOTAL_MARKETS: dict[str, dict[str, str]] = {
    f"team_total_{side}_{tag}": {
        "over": f"team_total_{side}_over_{tag}",
        "under": f"team_total_{side}_under_{tag}",
    }
    for side in ("home", "away")
    for tag in ("0_5", "1_5", "2_5")
}


def team_total_side_and_line(market: str) -> tuple[str, float] | None:
    """`team_total_away_0_5` -> ("away", 0.5); None for any other market."""
    parts = market.split("_")
    if len(parts) != 5 or parts[:2] != ["team", "total"] or parts[2] not in ("home", "away"):
        return None
    try:
        return parts[2], float(f"{parts[3]}.{parts[4]}")
    except ValueError:
        return None


def evaluate_team_totals(
    projections: pd.DataFrame,
    odds: pd.DataFrame,
    min_edge: float = 0.035,
    max_juice: int = -160,
) -> pd.DataFrame:
    """Grade every team-total line the odds carry. No price, no row."""
    frames = [
        evaluate_derived_market(
            market, projections, odds, min_edge=min_edge, max_juice=max_juice,
            selections=mapping,
        )
        for market, mapping in TEAM_TOTAL_MARKETS.items()
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(
        ["status", "edge"], ascending=[True, False]
    )


def approved_team_total_markets(policy_path: Path | None = None) -> list[str]:
    """Team-total markets the reviewed policy approves. Empty means none is.

    The per-event request asks for team totals only when this is non-empty, so
    no credit is spent on a market the card may not use.
    """
    path = Path(policy_path) if policy_path else (
        PROJECT_ROOT / "data" / "manual" / "staging_provider_policy.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    entries = payload.get("provider_allowlist_entries")
    if not isinstance(entries, Mapping):
        return []
    approved: set[str] = set()
    for entry in entries.values():
        if not isinstance(entry, Mapping) or not entry_is_complete_approval(entry):
            continue
        markets = entry.get("required_markets")
        if isinstance(markets, list):
            approved.update(str(item).strip() for item in markets)
    return [market for market in TEAM_TOTAL_MARKETS if market in approved]
