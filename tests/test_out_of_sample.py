"""Bet rules are judged on seasons they were not chosen on."""

from __future__ import annotations

import numpy as np
import pandas as pd

from epl_betting_lab.reports.out_of_sample import (
    MIN_BETS,
    Grid,
    evaluate_out_of_sample,
    render_markdown,
    score_rule,
    selections_long,
)


def _probs(n=400, seed=1, overround=1.05):
    rng = np.random.default_rng(seed)
    p = rng.dirichlet([4, 3, 3], size=n)
    seasons = np.where(np.arange(n) < n // 2, 2324, 2526)
    hg = rng.poisson(1.4, n); ag = rng.poisson(1.1, n)
    frame = pd.DataFrame({
        "season": seasons, "home_goals": hg, "away_goals": ag,
        "p_home": p[:, 0], "p_draw": p[:, 1], "p_away": p[:, 2], "p_over": rng.uniform(0.35, 0.7, n),
    })
    for col, prob in (("AvgH", p[:, 0]), ("AvgD", p[:, 1]), ("AvgA", p[:, 2])):
        frame[col] = 1 / np.clip(prob * overround, 0.03, 0.97)     # overround on the price
        frame["AvgC" + col[-1]] = frame[col] * rng.uniform(0.97, 1.03, n)
    frame["AvgO"] = 1 / (frame["p_over"] * overround); frame["AvgU"] = 1 / ((1 - frame["p_over"]) * overround)
    frame["AvgCO"] = frame["AvgO"]; frame["AvgCU"] = frame["AvgU"]
    return frame


def test_long_form_has_one_row_per_selection_and_devigged_market():
    long = selections_long(_probs(), "1x2")
    assert len(long) == 400 * 3
    per_match = long.groupby(long.index // 1).size()  # no accidental duplication
    market_sum = long.groupby(long.index % 400)["p_market"].sum()
    assert np.allclose(long[long.selection == "home"]["p_market"].values
                       + long[long.selection == "draw"]["p_market"].values
                       + long[long.selection == "away"]["p_market"].values, 1.0)


def test_won_and_profit_follow_the_price():
    long = selections_long(_probs(), "1x2")
    won = long[long.won == 1.0]; lost = long[long.won == 0.0]
    assert (won.profit == won.open_dec - 1).all()
    assert (lost.profit == -1.0).all()


def test_a_zero_model_weight_never_bets():
    long = selections_long(_probs(), "1x2")
    assert score_rule(long, a=0.0, threshold=0.01) is None


def _qualifying(n, edge=0.20):
    """`n` rows that clear any sane threshold, and nothing else.

    Built directly rather than through `selections_long`, because that
    fixture's prices are derived FROM its probabilities: de-vigged,
    `p_market` equals `p_model` exactly, so no row can ever show an edge.
    A threshold of 0.5 against it selects zero rows, and `score_rule`
    returned None for having no bets at all rather than too few.
    """
    market = 0.40
    return pd.DataFrame({
        "p_model": [market + edge] * n,
        "p_market": [market] * n,
        "open_dec": [1 / market] * n,
        "profit": [0.5] * n,
        "clv": [0.01] * n,
        "won": [1.0] * n,
    })


def test_one_bet_under_the_floor_is_none():
    """The floor, tested at the floor. It was not tested at all.

    Dropping `MIN_BETS` to 1 passed all 2,440 tests. The held-out report
    would then publish ROI, units and CLV for grid cells backed by a single
    bet, in the same sorted table as cells backed by hundreds and with no
    marker — in the report whose whole purpose is to stop a number with
    nothing behind it being read as evidence.
    """
    assert score_rule(_qualifying(MIN_BETS - 1), a=1.0, threshold=0.05) is None


def test_and_one_bet_over_it_is_a_number():
    """The control. Without it, a rule that always returned None would pass."""
    scored = score_rule(_qualifying(MIN_BETS), a=1.0, threshold=0.05)

    assert scored is not None
    assert scored["bets"] == MIN_BETS


def test_no_qualifying_bets_is_also_none():
    """Zero and "too few" are different reasons for the same answer.

    The old test believed it was checking the second and was checking the
    first, so this keeps the first covered under its own name.
    """
    assert score_rule(_qualifying(0), a=1.0, threshold=0.05) is None
    assert MIN_BETS == 20


def test_evaluation_is_sorted_by_train_clv_and_carries_test_columns():
    # Thresholds at 0 with the price gate off, so the grid is populated: the
    # fixture prices carry a 5% overround and nothing beats them.
    table = evaluate_out_of_sample(_probs(overround=1.0), "1x2", train_seasons=(2324,), test_seasons=(2526,),
                                   grid=Grid(model_weights=(0.5, 1.0), thresholds=(0.0, 0.01)))
    assert not table.empty
    assert list(table["train_clv_points"]) == sorted(table["train_clv_points"], reverse=True)
    for col in ("test_bets", "test_clv_points", "test_roi", "test_units", "test_clv_positive_rate"):
        assert col in table.columns


def test_totals_market_is_scored_too():
    table = evaluate_out_of_sample(_probs(overround=1.0), "total_2_5", train_seasons=(2324,), test_seasons=(2526,),
                                   grid=Grid(model_weights=(1.0,), thresholds=(0.0,)))
    assert not table.empty and set(table["market"]) == {"total_2_5"}


def test_markdown_names_the_seasons_and_leads_with_clv():
    md = render_markdown({"1x2": evaluate_out_of_sample(_probs(), "1x2", train_seasons=(2324,), test_seasons=(2526,))},
                         model_name="synthetic")
    assert "Train seasons" in md and "Test seasons" in md and "CLV" in md


def test_the_price_gate_is_on_by_default_and_is_the_rule_the_card_runs():
    """Scoring without it measured a rule nobody runs.

    The strategy flags on lift over the de-vigged consensus; the card then
    zeroes any row whose edge against the posted price is not positive
    (`_confidence_tier`, `edge <= 0`). So the live rule was strictly tighter
    than the published measurement. On the 2026-09-02 slate the largest lift
    was +0.024 against an edge of -0.009, so this is common, not a corner case.
    """
    long = selections_long(_probs(), "1x2")   # 5% overround: nothing beats the price
    assert score_rule(long, a=1.0, threshold=0.0) is None
    loose = score_rule(long, a=1.0, threshold=0.0, require_price_edge=False)
    assert loose is not None and loose["bets"] > 0


def test_the_cost_of_the_gate_is_reported_not_asserted():
    table = evaluate_out_of_sample(_probs(overround=1.0), "1x2", train_seasons=(2324,), test_seasons=(2526,),
                                   grid=Grid(model_weights=(1.0,), thresholds=(0.0,)))
    assert "test_bets_no_price_gate" in table.columns
    assert "test_units_no_price_gate" in table.columns
