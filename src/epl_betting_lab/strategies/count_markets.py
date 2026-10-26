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
from epl_betting_lab.strategies.totals import (
    ANCHOR_THRESHOLD,
    MODEL_WEIGHT,
    SELECTION_RULE,
    _implied,
    _logit,
    _sigmoid,
    market_probability_over,
)


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

#: Events whose total lines are priced under the market-anchored rule, the
#: 2.5 line's rule with the 2.5 line's constants (`strategies.totals`).
#:
#: Held out on 2025/26-2026/27 the corner model's log loss at 9.5 was 0.6908
#: against 0.6916 for one league-wide rate: team corner rates barely beat the
#: average, so a corner "edge" was mostly the price disagreeing with an average.
#: On the 2025/26 corner prices bought at bettable books, the 0.5 blend was the
#: most accurate of model, market and blend (log loss 0.6819 against 0.6826
#: and 0.6840 over 760 lines) and bet 181 times at +6.6% against the old
#: rule's 178 at +5.4%, both intervals wide. The constants were not tuned on
#: those prices. Cards keep the old rule: no book offers them.
ANCHORED_EVENTS: frozenset[str] = frozenset({"corners"})


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
    market_odds: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Grade one counted market for every fixture that has a price.

    A total line of an event in `ANCHORED_EVENTS` is graded under the
    market-anchored rule against `market_odds`, the per-book prices; every
    other market keeps the calibrated-edge rule.
    """
    if market not in COUNT_MARKETS or fixtures.empty or odds.empty:
        return pd.DataFrame()
    event, _, kind = COUNT_MARKETS[market]
    model = models.get(event)
    if model is None:
        return pd.DataFrame()
    if event in ANCHORED_EVENTS and kind == "total":
        return _evaluate_anchored_total(market, model, fixtures, odds, market_odds, max_juice)

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


def _evaluate_anchored_total(
    market: str,
    model: PoissonCountModel,
    fixtures: pd.DataFrame,
    odds: pd.DataFrame,
    market_odds: pd.DataFrame | None,
    max_juice: int,
) -> pd.DataFrame:
    """A total line under the market-anchored rule; see `ANCHORED_EVENTS`."""
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
        p_market_over, source = market_probability_over(
            home_team, away_team, odds, market_odds, market=market
        )
        if p_market_over is None:
            continue
        probabilities = probabilities_for(market, model, home_team, away_team)
        for selection, p_model in probabilities.items():
            line = game_odds[game_odds.selection == selection]
            if line.empty:
                continue
            american = float(line.iloc[0].american_odds)
            p_market = p_market_over if selection == "over" else 1.0 - p_market_over
            p_final = _sigmoid(
                MODEL_WEIGHT * _logit(p_model) + (1 - MODEL_WEIGHT) * _logit(p_market)
            )
            lift = p_final - p_market
            grade = grade_edge(p_final, american, min_edge=0.0, max_default_juice=max_juice)
            # Lift over the consensus decides, and the posted price must still
            # pay: a row the blend calls negative at this price is not staked.
            if str(grade["status"]).startswith("PASS - "):
                status = grade["status"]
            elif lift > ANCHOR_THRESHOLD and grade["edge"] > 0:
                status = "BETTABLE"
            else:
                status = "PASS"
            rows.append(
                {
                    **grade,
                    "home_team": home_team,
                    "away_team": away_team,
                    "market": market,
                    "selection": selection,
                    "american_odds": american,
                    "book": _book_of(line),
                    "opening_american_odds": american,
                    "opening_implied_probability": round(_implied(american), 4),
                    "closing_american_odds": line.iloc[0].get(
                        "closing_american_odds", pd.NA
                    ),
                    "raw_model_prob": round(float(p_model), 4),
                    "market_prob": round(p_market, 4),
                    "market_prob_source": source,
                    "calibrated_model_prob": round(p_final, 4),
                    "raw_edge": round(float(p_model) - _implied(american), 4),
                    "calibrated_edge": grade["edge"],
                    "anchor_lift": round(lift, 4),
                    "raw_status": status,
                    "calibrated_status": status,
                    "status": status,
                    "selection_rule": SELECTION_RULE,
                    "model_weight": MODEL_WEIGHT,
                    "anchor_threshold": ANCHOR_THRESHOLD,
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
