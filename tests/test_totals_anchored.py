"""The market-anchored 2.5 rule: blended with the price, capped small."""

from __future__ import annotations

import pandas as pd

from epl_betting_lab.strategies.totals import (
    ANCHOR_THRESHOLD,
    MODEL_WEIGHT,
    evaluate_total_25_anchored,
    market_probability_over,
)


def _odds(over=-110, under=-110, books=("FanDuel",)):
    rows = []
    for b in books:
        rows += [{"home_team": "H", "away_team": "A", "market": "total_2_5", "selection": "over", "american_odds": over, "book": b},
                 {"home_team": "H", "away_team": "A", "market": "total_2_5", "selection": "under", "american_odds": under, "book": b}]
    return pd.DataFrame(rows)


def _proj(p_over):
    return pd.DataFrame([{"home_team": "H", "away_team": "A", "over_2_5": p_over, "under_2_5": 1 - p_over}])


def test_the_fixed_parameters_are_the_conservative_end_of_the_grid():
    assert MODEL_WEIGHT == 0.5 and ANCHOR_THRESHOLD == 0.03


def test_consensus_is_preferred_and_named():
    p, source = market_probability_over("H", "A", _odds(), _odds(over=-120, under=+100, books=("FanDuel", "DraftKings")))
    assert source == "consensus" and 0.45 < p < 0.6
    p2, source2 = market_probability_over("H", "A", _odds(), None)
    assert source2 == "best-price pair" and abs(p2 - 0.5) < 1e-9


def test_a_model_that_agrees_with_the_market_never_bets():
    rows = evaluate_total_25_anchored(_proj(0.5238), _odds())   # -110/-110 de-vigs to 0.5
    assert set(rows.status) == {"PASS"}
    assert (rows.selection_rule == "market_anchored").all()


def test_a_strong_disagreement_is_halved_by_the_anchor_before_it_counts():
    # Model says 70% over; market says 50%. Blend at a=0.5 in logit space lands
    # near 60%, which clears the 3% threshold — but with an edge far short of 20.
    rows = evaluate_total_25_anchored(_proj(0.70), _odds())
    over = rows[rows.selection == "over"].iloc[0]
    assert over.status == "BETTABLE"
    assert 0.55 < over.calibrated_model_prob < 0.65
    assert over.anchor_lift > ANCHOR_THRESHOLD


def test_a_small_disagreement_does_not_clear_the_threshold():
    rows = evaluate_total_25_anchored(_proj(0.54), _odds())
    assert (rows.status == "PASS").all()


def test_heavy_juice_is_refused_even_with_lift():
    rows = evaluate_total_25_anchored(_proj(0.80), _odds(over=-200, under=+160), max_juice=-160)
    assert rows[rows.selection == "over"].iloc[0].status == "PASS - too much juice"


def test_the_card_caps_anchored_rows_at_the_smallest_stake():
    from epl_betting_lab.reports.thursday_best_bets import _confidence_tier
    row = pd.Series({"status": "BETTABLE", "market": "total_2_5", "selection": "over",
                     "ranking_score": 90.0, "calibrated_edge": 0.08, "selection_rule": "market_anchored"})
    assert _confidence_tier(row) == "C"
    plain = row.copy(); plain["selection_rule"] = ""
    assert _confidence_tier(plain) == "A"
