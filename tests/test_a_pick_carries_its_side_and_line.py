"""The board's pick carries the side and line the page's live status reads.

`web/lib/live.js::pickStatusFor` judges an EPL pick against the live score
from `pick.side` and, for a total, `pick.line`. Corner markets must carry no
side: live.js reads any market containing "1x2" as the match result, so a
`corners_1x2` pick with a side would be graded on goals.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BUILDER = Path(__file__).resolve().parents[1] / "web" / "build_board_json.py"


def _builder():
    spec = importlib.util.spec_from_file_location("build_board_json_side_line", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pick(market: str, selection: str) -> dict:
    card = {"best_bets": [{"home_team": "Arsenal", "away_team": "Everton", "market": market,
                           "selection": selection, "american_odds": "120", "calibrated_edge": "0.05"}]}
    return _builder().pick_for(card, "Arsenal", "Everton")


@pytest.mark.parametrize(("market", "selection", "side", "line"), [
    ("1x2", "home", "home", None),
    ("1x2", "draw", "draw", None),
    ("draw_no_bet", "away", "away", None),
    ("total_2_5", "under", "under", 2.5),
    ("btts", "yes", "yes", None),
    ("btts", "no", "no", None),
])
def test_a_goal_market_pick_names_its_side(market, selection, side, line) -> None:
    pick = _pick(market, selection)
    assert (pick["side"], pick["line"]) == (side, line), pick


@pytest.mark.parametrize(("market", "selection"), [
    ("corners_1x2", "home"),
    ("corners_total_9_5", "over"),
    ("double_chance", "home_or_draw"),
])
def test_a_market_with_no_live_rule_carries_no_side(market, selection) -> None:
    pick = _pick(market, selection)
    assert pick["side"] is None and pick["line"] is None, pick
