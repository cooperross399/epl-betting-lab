"""The market review's arithmetic (2026-11-21, Cooper: "reevaluate any markets
where we are losing money/bets and see how we can improve")."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from epl_betting_lab.reports import market_review as review


def _row(market, selection, price, **extra):
    return {"date": "2025-10-04", "home_team": "Arsenal", "away_team": "Fulham",
            "market": market, "selection": selection, "american_odds": price, **extra}


def test_the_fair_price_is_de_vigged_within_the_fixture():
    frame = review.with_market_probability(pd.DataFrame([
        _row("draw_no_bet", "home", -110), _row("draw_no_bet", "away", -110),
        _row("double_chance", "home_or_draw", -300), _row("double_chance", "draw_or_away", 150),
        _row("double_chance", "home_or_away", -400),
        _row("btts", "yes", -120),  # no "no" side: no fair price
    ]))
    fair = dict(zip(zip(frame["market"], frame["selection"]), frame["p_market"]))
    assert fair[("draw_no_bet", "home")] == pytest.approx(0.5)
    dc = [fair[("double_chance", s)] for s in ("home_or_draw", "draw_or_away", "home_or_away")]
    assert sum(dc) == pytest.approx(2.0)
    assert pd.isna(fair[("btts", "yes")])


def test_cap_200_refuses_plus_200_and_longer():
    frame = pd.DataFrame([
        _row("draw_no_bet", "away", 199, status="BETTABLE"),
        _row("draw_no_bet", "away", 200, status="BETTABLE"),
        _row("draw_no_bet", "away", 450, status="BETTABLE"),
    ])
    assert review.select(frame, "card", model_column="p").tolist() == [True, True, True]
    assert review.select(frame, "cap_200", model_column="p").tolist() == [True, False, False]


def test_anchored_needs_lift_over_the_market_and_a_price_edge():
    frame = pd.DataFrame([
        # model 0.60 vs fair 0.50: blend ~0.55, lift 0.05, beats -110 (0.524)
        _row("draw_no_bet", "home", -110, p=0.60, p_market=0.50),
        # model 0.54 vs fair 0.50: lift ~0.02, under the 0.03 bar
        _row("draw_no_bet", "home", -110, p=0.54, p_market=0.50),
        # no fair price
        _row("draw_no_bet", "home", -110, p=0.70, p_market=float("nan")),
    ])
    assert review.select(frame, "anchored", model_column="p").tolist() == [True, False, False]


def test_the_live_table_counts_wins_against_what_the_prices_implied():
    picks = [
        SimpleNamespace(settled=True, market="corners_1x2", selection="away", american_odds=300,
                        won=False, pushed=False, stake_units=0.6, profit_units=-0.6),
        SimpleNamespace(settled=True, market="corners_1x2", selection="away", american_odds=300,
                        won=True, pushed=False, stake_units=0.6, profit_units=1.8),
        SimpleNamespace(settled=True, market="draw_no_bet", selection="home", american_odds=-120,
                        won=None, pushed=True, stake_units=1.2, profit_units=0.0),
        SimpleNamespace(settled=False, market="btts", selection="yes", american_odds=100,
                        won=None, pushed=False, stake_units=1.0, profit_units=0.0),
    ]
    table = review.live_table(review.live_frame(picks), ["market"]).set_index("market")
    assert (table.loc["corners_1x2", "w"], table.loc["corners_1x2", "l"]) == (1, 1)
    assert table.loc["corners_1x2", "units"] == pytest.approx(1.2)
    assert table.loc["corners_1x2", "wins_priced_in"] == pytest.approx(0.5)
    assert table.loc["draw_no_bet", "p"] == 1 and "btts" not in table.index


@pytest.mark.parametrize("price,band", [(-160, "-150 or shorter"), (-120, "-149 to -101"),
                                        (120, "+100 to +149"), (199, "+150 to +199"),
                                        (200, "+200 to +500"), (501, "longer than +500")])
def test_price_bands(price, band):
    assert review.price_band(price) == band


def _matches(n_home, n_draw, n_away, p=(0.40, 0.25, 0.35)):
    rows = []
    for goals in [(2, 0)] * n_home + [(1, 1)] * n_draw + [(0, 1)] * n_away:
        rows.append({"p_home": p[0], "p_draw": p[1], "p_away": p[2],
                     "home_goals": goals[0], "away_goals": goals[1]})
    return pd.DataFrame(rows)


def test_side_weights_make_the_average_match_what_happened():
    probs = _matches(45, 25, 30)
    weights = review.fit_side_weights(probs)
    adjusted = [review.reweight(0.40, 0.25, 0.35, weights)]
    assert adjusted[0][0] == pytest.approx(0.45, abs=1e-6)
    assert adjusted[0][1] == pytest.approx(0.25, abs=1e-6)
    assert sum(adjusted[0]) == pytest.approx(1.0)
    assert review.log_loss_1x2(probs, weights) < review.log_loss_1x2(probs)


def test_side_fix_regrades_draw_no_bet_from_the_double_chance_triple():
    fixture = {"date": "2025-10-04", "home_team": "Arsenal", "away_team": "Fulham", "book": "fanduel"}
    rows = []
    # model triple 0.40 / 0.25 / 0.35
    for market, sel, p, price, won in (
        ("double_chance", "home_or_draw", 0.65, -150, True),
        ("double_chance", "draw_or_away", 0.60, -120, False),
        ("double_chance", "home_or_away", 0.75, -300, True),
        ("draw_no_bet", "home", 0.40 / 0.75, -150, True),
        ("draw_no_bet", "away", 0.35 / 0.75, 120, False),
    ):
        rows.append({**fixture, "market": market, "selection": sel, "raw_model_prob": p,
                     "calibrated_model_prob": p, "calibrated_edge": 0.0, "status": "PASS",
                     "american_odds": price, "won": won, "push": False})
    out = review.side_fix_derived(pd.DataFrame(rows), (1.0, 1.0, 1.0))
    assert set(out["rule"]) >= {"card (same fixtures)", "side_fix"}
