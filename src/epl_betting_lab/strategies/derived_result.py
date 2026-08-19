"""Double chance and draw-no-bet, both read off the 1X2 distribution.

Neither needs a new model or a new data source. The Poisson fit already
produces the whole scoreline distribution, and these are two more ways of
grouping the same three outcomes — so their numbers cannot disagree with the
1X2 numbers on the same card. They are the same numbers, combined.

Two things about these markets are worth knowing before reading a card:

**Draw-no-bet is conditional, not additive.** A draw voids the bet and returns
the stake, so the fair probability is P(home | not a draw), not P(home).
Pricing it as P(home) would overprice both sides at once, which is the mistake
the market invites.

**The favourite side is usually refused as too juiced.** Double chance on a
home favourite prices around -400, and the project rejects anything worse than
-160 by default. That is the configured preference working, not a fault — but
it means these behave as underdog markets here, which is the opposite of how
they are normally used. The count of candidates refused for price is reported
so a thin section reads as "priced too short", never as "nothing was found".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from epl_betting_lab.models.calibration import (
    ShrinkageConfig,
    calibrate_probability,
    min_calibrated_edge,
)
from epl_betting_lab.models.value import grade_edge


#: market -> {selection: column on the projection row}
DERIVED_MARKETS: dict[str, dict[str, str]] = {
    "double_chance": {
        "home_or_draw": "double_chance_home_or_draw",
        "draw_or_away": "double_chance_draw_or_away",
        "home_or_away": "double_chance_home_or_away",
    },
    "draw_no_bet": {
        "home": "draw_no_bet_home",
        "away": "draw_no_bet_away",
    },
}


def _book_of(line: pd.DataFrame) -> str:
    """Sportsbook name for a priced line, blank when the source omitted it."""
    if line.empty:
        return ""
    value = line.iloc[0].get("book", "")
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def evaluate_derived_market(
    market: str,
    projections: pd.DataFrame,
    odds: pd.DataFrame,
    min_edge: float = 0.035,
    max_juice: int = -160,
    selections: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Grade one derived market against the prices actually offered."""
    mapping = dict(selections or DERIVED_MARKETS.get(market, {}))
    if not mapping or projections.empty or odds.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for _, projection in projections.iterrows():
        game_odds = odds[
            (odds.home_team == projection.home_team)
            & (odds.away_team == projection.away_team)
            & (odds.market == market)
        ]
        for selection, prob_column in mapping.items():
            line = game_odds[game_odds.selection == selection]
            if line.empty or prob_column not in projection:
                continue
            american = float(line.iloc[0].american_odds)
            raw_prob = float(projection[prob_column])
            raw_grade = grade_edge(
                raw_prob, american, min_edge=min_edge, max_default_juice=max_juice
            )
            config = ShrinkageConfig()
            calibration = calibrate_probability(
                raw_prob, market, selection, american_odds=american, config=config
            )
            grade = grade_edge(
                float(calibration["calibrated_model_prob"]),
                american,
                min_edge=min_calibrated_edge(market, selection, min_edge, config),
                max_default_juice=max_juice,
            )
            rows.append(
                {
                    "home_team": projection.home_team,
                    "away_team": projection.away_team,
                    "market": market,
                    "selection": selection,
                    "american_odds": american,
                    "book": _book_of(line),
                    "opening_american_odds": american,
                    "opening_implied_probability": raw_grade["book_implied"],
                    "closing_american_odds": line.iloc[0].get(
                        "closing_american_odds", pd.NA
                    ),
                    "raw_model_prob": raw_grade["model_prob"],
                    "calibrated_model_prob": grade["model_prob"],
                    "raw_edge": raw_grade["edge"],
                    "calibrated_edge": grade["edge"],
                    "raw_status": raw_grade["status"],
                    "calibrated_status": grade["status"],
                    "calibrated_min_edge": min_calibrated_edge(
                        market, selection, min_edge, config
                    ),
                    **calibration,
                    **grade,
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["status", "edge"], ascending=[True, False])


def evaluate_double_chance(
    projections: pd.DataFrame,
    odds: pd.DataFrame,
    min_edge: float = 0.035,
    max_juice: int = -160,
) -> pd.DataFrame:
    return evaluate_derived_market(
        "double_chance", projections, odds, min_edge=min_edge, max_juice=max_juice
    )


def evaluate_draw_no_bet(
    projections: pd.DataFrame,
    odds: pd.DataFrame,
    min_edge: float = 0.035,
    max_juice: int = -160,
) -> pd.DataFrame:
    return evaluate_derived_market(
        "draw_no_bet", projections, odds, min_edge=min_edge, max_juice=max_juice
    )


def price_refusal_summary(graded: pd.DataFrame) -> dict[str, int]:
    """How many candidates were refused purely on price.

    A section that is empty because everything was too short to take is a
    different fact from a section that is empty because nothing was found, and
    a reader cannot tell them apart from the absence alone.
    """
    if graded.empty or "status" not in graded.columns:
        return {"considered": 0, "refused_for_price": 0}
    refused = int((graded["status"] == "PASS - too much juice").sum())
    return {"considered": int(len(graded)), "refused_for_price": refused}
