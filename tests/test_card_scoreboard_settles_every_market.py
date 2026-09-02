"""Every market the card can stake must be settleable, or the record lies.

`settle` knew five markets while the card staked eight. The three corner
markets returned None and were counted as pending, so 23 of the first 42 best
bets — 55% of everything the card had recommended — sat in a queue that could
never resolve. The published record described a minority of the card and its
"still pending" number grew forever, which reads as a record accumulating when
it is not.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
from epl_betting_lab.reports.card_scoreboard import (
    CORNER_MARKETS,
    build_scoreboard,
    render_scoreboard,
    settle,
    settleable_markets,
)


def test_every_market_the_card_can_stake_is_settleable():
    """The control that stops this recurring.

    Read from MARKET_SELECTIONS rather than a hardcoded list, so a market
    entering card scope without a settlement rule fails here rather than
    silently accumulating unresolvable rows for three weeks.
    """
    missing = sorted(set(MARKET_SELECTIONS) - settleable_markets())
    assert not missing, f"card can stake these but cannot settle them: {missing}"


@pytest.mark.parametrize("market", sorted(MARKET_SELECTIONS))
def test_every_selection_of_every_market_returns_a_verdict(market):
    """Not just the market — each of its selections must resolve.

    A market can be "settleable" while a selection name typo'd in the strategy
    silently returns None forever.
    """
    for selection in MARKET_SELECTIONS[market]:
        verdict = settle(market, selection, 2, 1, home_corners=7, away_corners=4)
        assert verdict is not None, f"{market}/{selection} did not settle"


def test_corner_totals_settle_on_the_combined_count():
    assert settle("corners_total_9_5", "over", 0, 0, home_corners=6, away_corners=5) is True
    assert settle("corners_total_9_5", "under", 0, 0, home_corners=4, away_corners=5) is True
    assert settle("corners_total_10_5", "over", 0, 0, home_corners=6, away_corners=4) is False
    # Half-lines cannot push, so neither selection is ever void.
    for line, total in (("corners_total_9_5", 10), ("corners_total_10_5", 11)):
        over = settle(line, "over", 0, 0, home_corners=total, away_corners=0)
        under = settle(line, "under", 0, 0, home_corners=total, away_corners=0)
        assert over is not under


def test_corner_three_way_settles_on_which_side_won_the_count():
    assert settle("corners_1x2", "home", 0, 0, home_corners=7, away_corners=3) is True
    assert settle("corners_1x2", "away", 0, 0, home_corners=3, away_corners=7) is True
    assert settle("corners_1x2", "draw", 0, 0, home_corners=5, away_corners=5) is True
    assert settle("corners_1x2", "home", 0, 0, home_corners=5, away_corners=5) is False


def test_a_corner_market_without_counts_settles_nothing_rather_than_guessing():
    """The scoreline is present and the corner counts are not. Never infer."""
    assert settle("corners_1x2", "home", 3, 0) is None
    assert settle("corners_total_9_5", "over", 5, 4) is None


def test_corner_markets_are_named_once():
    """The lines live in one place so the settler and the tests cannot drift."""
    assert set(CORNER_MARKETS) == {m for m in MARKET_SELECTIONS if m.startswith("corners")}


def _card(market, selection, units=0.25, odds=-110, home="H", away="A"):
    """A card in the archive's own shape: scored rows come from `best_bets`."""
    return {
        "card_generated": True,
        "generated_at": "2026-08-21T12:00:00+00:00",
        "best_bets": [
            {"home_team": home, "away_team": away, "market": market,
             "selection": selection, "american_odds": odds, "suggested_units": units}
        ],
    }


def _results(home_goals=1, away_goals=1, hc=7, ac=3):
    return pd.DataFrame([{ "date": "2026-08-23", "home_team": "H", "away_team": "A",
                           "home_goals": home_goals, "away_goals": away_goals, "HC": hc, "AC": ac }])


def test_a_corner_bet_now_settles_instead_of_pending_forever():
    board = build_scoreboard([_card("corners_1x2", "home")], _results())
    assert len(board.settled) == 1 and board.pending == 0 and board.unsettleable == 0
    assert board.settled[0].won is True


def test_a_result_missing_corner_counts_is_unsettleable_not_pending():
    """Pending resolves with time; this never does. Counting it as pending is
    what made the record look like it was accumulating."""
    results = _results().drop(columns=["HC", "AC"])
    board = build_scoreboard([_card("corners_total_9_5", "over")], results)
    assert board.unsettleable == 1 and board.pending == 0 and not board.settled


def test_a_fixture_with_no_result_is_still_pending():
    board = build_scoreboard([_card("btts", "yes")], pd.DataFrame())
    assert board.pending == 1 and board.unsettleable == 0


def test_a_draw_no_bet_push_is_void_not_pending_and_not_unsettleable():
    board = build_scoreboard([_card("draw_no_bet", "home")], _results(1, 1))
    assert board.void == 1 and board.pending == 0 and board.unsettleable == 0


def test_the_rendered_record_names_unsettleable_rows_separately():
    board = build_scoreboard(
        [_card("btts", "yes"), _card("corners_1x2", "home", home="X", away="Y")],
        _results(1, 1),
    )
    board.unsettleable = 1  # as if a corner result arrived without counts
    text = "\n".join(render_scoreboard(board))
    assert "Cannot be settled" in text and "never resolve" in text
