"""One match is one bet, however many markets see it.

The CBB lab's rule: spread, moneyline, team total and game total are one event
seen several ways, and staking them as independent bets doubles the exposure
on one result without adding information. The 2026-10-31 10:36 UTC card staked
Newcastle draw-no-bet home AND 1X2 home, and Spurs home under 1.5 AND Palace
over 1.5. The card now keeps the highest-ranked best bet per match; the rest of
that match's best bets are shown as leans, unstaked, with the reason, and the
freed slots go to other matches.
"""

from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.thursday_best_bets import (
    LEAN_TIER,
    build_thursday_best_bets,
)


def _row(home, away, market, selection, edge, odds=110):
    return {
        "home_team": home,
        "away_team": away,
        "market": market,
        "selection": selection,
        "status": "BETTABLE",
        "american_odds": odds,
        "raw_model_prob": 0.55,
        "calibrated_model_prob": 0.55,
        "model_prob": 0.55,
        "raw_edge": edge,
        "calibrated_edge": edge,
        "edge": edge,
        "fair_american": -120,
        "book": "FanDuel",
    }


def _card():
    rows = [
        _row("Newcastle", "Everton", "draw_no_bet", "home", 0.09),
        _row("Newcastle", "Everton", "1x2", "home", 0.08),
        _row("Tottenham", "Crystal Palace", "team_total_home_1_5", "under", 0.07),
        _row("Tottenham", "Crystal Palace", "team_total_away_1_5", "over", 0.06),
        _row("Chelsea", "Man United", "double_chance", "draw_or_away", 0.05),
    ]
    return build_thursday_best_bets(pd.DataFrame(rows), max_best_bets=3)


def test_each_match_has_at_most_one_best_bet():
    report = _card()
    best = report[report["section"] == "Best bets"]
    assert not best.duplicated(["home_team", "away_team"]).any()
    assert len(best) == 3
    # The freed slot went to a different match, not to a second Newcastle bet.
    assert set(best["home_team"]) == {"Newcastle", "Tottenham", "Chelsea"}


def test_the_highest_ranked_bet_on_a_match_is_the_one_kept():
    best = _card().query("section == 'Best bets'")
    newcastle = best[best["home_team"] == "Newcastle"]
    assert newcastle["market"].tolist() == ["draw_no_bet"]


def test_the_others_are_shown_unstaked_with_the_reason():
    report = _card()
    moved = report[(report["section"] == "Leans") & (report["home_team"].isin(["Newcastle", "Tottenham"]))]
    assert set(moved["market"]) == {"1x2", "team_total_away_1_5"}
    assert (moved["suggested_units"] == 0).all()
    assert (moved["confidence_tier"] == LEAN_TIER).all()
    assert moved["qualifies_reason"].str.contains("same match").all()


def _prop(player, market, selection, edge):
    from epl_betting_lab.reports.player_props_card import PropPick

    return PropPick(
        date="2026-10-31", kickoff_time="", home_team="Chelsea", away_team="Man United",
        market=market, player=player, team="Man United", selection=selection,
        model_probability=0.3, implied_probability=0.2, edge=edge, american_odds=300.0,
        book="BetRivers", units=0.1, model_player=player,
    )


def test_one_prop_per_player_per_match():
    """Henderson anytime + shots on target + shots is one player's afternoon,
    three ways: a goal is a shot on target is a shot. One stake, the best edge."""
    from epl_betting_lab.reports.player_props_card import _one_stake_per_player

    picks = [
        _prop("Jordan Henderson", "player_goal_scorer_anytime", "Yes", 0.09),
        _prop("Jordan Henderson", "player_shots_on_target", "Over@0.5", 0.12),
        _prop("Jordan Henderson", "player_shots", "Over@1.5", 0.10),
        _prop("Bruno Fernandes", "player_shots", "Over@1.5", 0.08),
    ]
    kept = _one_stake_per_player(picks)
    assert sorted((p.player, p.market) for p in kept) == [
        ("Bruno Fernandes", "player_shots"),
        ("Jordan Henderson", "player_shots_on_target"),
    ]


def test_the_props_card_applies_the_player_rule():
    import inspect

    from epl_betting_lab.reports import player_props_card

    source = inspect.getsource(player_props_card.build_player_props_card)
    assert "_one_stake_per_player(" in source
