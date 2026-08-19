"""Grade corner and card markets against the prices offered.

The probabilities come from `PoissonCountModel`, fitted on columns the project
already downloads every week and previously discarded. The grading is the same
shape as every other strategy here, so a corners row and a 1X2 row on the same
card mean the same thing by the same rules.

The minimum edge for cards is deliberately higher than the default. Bookings
cluster rather than arriving independently, and the strongest single driver of
how many a match produces — which referee is appointed — is not in the data at
all. A model missing a variable that large should be asked for more edge before
it is believed, not less.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from epl_betting_lab.models.calibration import (
    ShrinkageConfig,
    calibrate_probability,
    min_calibrated_edge,
)
from epl_betting_lab.models.poisson_counts import PoissonCountModel
from epl_betting_lab.models.value import grade_edge


#: market -> (counted event, line, kind). `kind` is "total" or "1x2".
COUNT_MARKETS: dict[str, tuple[str, float | None, str]] = {
    "corners_1x2": ("corners", None, "1x2"),
    "corners_total_9_5": ("corners", 9.5, "total"),
    "corners_total_10_5": ("corners", 10.5, "total"),
    # Cards are modelled but not registered as a market: no book offers them in
    # the `us` region. Kept here so the market can be enabled the day one does,
    # without rebuilding the model.
    "cards_total_3_5": ("cards", 3.5, "total"),
    "cards_total_4_5": ("cards", 4.5, "total"),
}

#: Markets this module can price but which no reachable book offers, so they
#: are deliberately absent from MARKET_SELECTIONS.
UNAVAILABLE_MARKETS: frozenset[str] = frozenset(
    {"cards_total_3_5", "cards_total_4_5"}
)

#: Extra edge demanded before a card market is believed. See the module note.
CARDS_MIN_EDGE = 0.06


def minimum_edge_for(market: str, default_min_edge: float) -> float:
    """Cards are asked for more edge because a large variable is missing."""
    event, _, _ = COUNT_MARKETS.get(market, ("", None, ""))
    if event == "cards":
        return max(default_min_edge, CARDS_MIN_EDGE)
    return default_min_edge


def _book_of(line: pd.DataFrame) -> str:
    if line.empty:
        return ""
    value = line.iloc[0].get("book", "")
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def probabilities_for(
    market: str, model: PoissonCountModel, home_team: str, away_team: str
) -> dict[str, float]:
    """Selection -> probability for one market and one fixture."""
    _, line, kind = COUNT_MARKETS[market]
    if kind == "1x2":
        outcomes = model.match_probabilities(home_team, away_team)
        return {
            "home": outcomes["home"],
            "draw": outcomes["draw"],
            "away": outcomes["away"],
        }
    over = model.total_over_probability(home_team, away_team, float(line))
    return {"over": round(over, 4), "under": round(1.0 - over, 4)}


def evaluate_count_market(
    market: str,
    models: Mapping[str, PoissonCountModel],
    fixtures: pd.DataFrame,
    odds: pd.DataFrame,
    min_edge: float = 0.035,
    max_juice: int = -160,
) -> pd.DataFrame:
    """Grade one counted market for every fixture that has a price."""
    if market not in COUNT_MARKETS or fixtures.empty or odds.empty:
        return pd.DataFrame()
    event, _, _ = COUNT_MARKETS[market]
    model = models.get(event)
    if model is None:
        return pd.DataFrame()

    market_min_edge = minimum_edge_for(market, min_edge)
    rows: list[dict[str, object]] = []
    for _, fixture in fixtures.iterrows():
        home_team = fixture["home_team"]
        away_team = fixture["away_team"]
        game_odds = odds[
            (odds.home_team == home_team)
            & (odds.away_team == away_team)
            & (odds.market == market)
        ]
        if game_odds.empty:
            continue
        probabilities = probabilities_for(market, model, home_team, away_team)
        for selection, raw_prob in probabilities.items():
            line = game_odds[game_odds.selection == selection]
            if line.empty:
                continue
            american = float(line.iloc[0].american_odds)
            raw_grade = grade_edge(
                raw_prob,
                american,
                min_edge=market_min_edge,
                max_default_juice=max_juice,
            )
            config = ShrinkageConfig()
            calibration = calibrate_probability(
                raw_prob, market, selection, american_odds=american, config=config
            )
            grade = grade_edge(
                float(calibration["calibrated_model_prob"]),
                american,
                min_edge=max(
                    market_min_edge,
                    min_calibrated_edge(market, selection, market_min_edge, config),
                ),
                max_default_juice=max_juice,
            )
            rows.append(
                {
                    "home_team": home_team,
                    "away_team": away_team,
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
                    "calibrated_min_edge": market_min_edge,
                    **calibration,
                    **grade,
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["status", "edge"], ascending=[True, False])


def fit_count_models(matches: pd.DataFrame) -> dict[str, PoissonCountModel]:
    """One fitted model per counted event the markets need."""
    events = {event for event, _, _ in COUNT_MARKETS.values()}
    models: dict[str, PoissonCountModel] = {}
    for event in sorted(events):
        try:
            models[event] = PoissonCountModel.for_event(event).fit(matches)
        except (KeyError, ValueError):
            # A column absent from this dataset means the event cannot be
            # modelled from it. That is a missing market, not a broken run.
            continue
    return models
