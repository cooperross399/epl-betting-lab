"""Every pick carries a "bet down to" price (Cooper, 2026-11-01).

"Lets always include a 'bet down to' number. implement that across all
models/cards." The Premier League card has printed one since September; the
card comment the routines read, the props card, the cup and European section,
the game page and the tracker did not. These pin each surface, and the rules
the number is read by:

- it is the price at which the edge falls to the bar that decided the pick,
  so a pick's own price is never shorter than its printed limit;
- a lean is read against the lean bar, not the bet bar it did not clear;
- card-count markets keep their higher bar;
- a best bet the trust weight or a line move shrank needs the shrunk edge;
- it is never printed worse than the juice limit, because no shorter price is
  ever bet.
"""

from __future__ import annotations

import importlib.util

import pandas as pd
import pytest

from epl_betting_lab.config import MAX_DEFAULT_JUICE, PROJECT_ROOT
from epl_betting_lab.models.value import (
    LEAN_EDGE,
    american_to_implied,
    bet_down_to_american,
    grade_edge,
)
from epl_betting_lab.reports.thursday_best_bets import _bet_down_to


def _row(**fields) -> pd.Series:
    return pd.Series({"market": "btts", "selection": "yes", **fields})


class TestTheHelper:
    def test_the_limit_leaves_exactly_the_bar(self) -> None:
        limit = bet_down_to_american(0.60, 0.05)
        assert american_to_implied(limit) == pytest.approx(0.55, abs=0.003)

    def test_never_worse_than_the_floor(self) -> None:
        # p - bar = 0.75 is -300; the card never takes a price worse than -160.
        assert bet_down_to_american(0.785, 0.035, floor=MAX_DEFAULT_JUICE) == MAX_DEFAULT_JUICE

    @pytest.mark.parametrize("probability", [None, float("nan"), 0.01, 1.2])
    def test_no_number_when_no_price_can_clear(self, probability) -> None:
        assert bet_down_to_american(probability, 0.035) is None


class TestTheCardRule:
    def test_a_bettable_row_is_never_already_past_its_limit(self) -> None:
        checked = 0
        for probability in (0.40, 0.55, 0.62, 0.70):
            for price in (-155, -120, +100, +140, +220):
                if grade_edge(probability, price, min_edge=0.045)["status"] != "BETTABLE":
                    continue
                checked += 1
                limit = _bet_down_to(_row(calibrated_model_prob=probability, status="BETTABLE"))
                assert american_to_implied(limit) >= american_to_implied(price) - 1e-9, (probability, price, limit)
        assert checked >= 5, "too few bettable combinations to mean anything"

    def test_a_lean_reads_the_lean_bar(self) -> None:
        # p = 0.55 at +100 is a 5-point edge on paper; at 0.52 it is a lean.
        lean = _bet_down_to(_row(calibrated_model_prob=0.52, status="LEAN"))
        assert american_to_implied(lean) == pytest.approx(0.52 - LEAN_EDGE, abs=0.003)
        # It is at least as short as +100, the price the lean was listed at.
        assert american_to_implied(lean) >= american_to_implied(100)

    def test_card_count_markets_keep_their_higher_bar(self) -> None:
        cards = _bet_down_to(
            pd.Series({"market": "cards_total_4_5", "selection": "over", "calibrated_model_prob": 0.60})
        )
        corners = _bet_down_to(
            pd.Series({"market": "corners_total_9_5", "selection": "over", "calibrated_model_prob": 0.60})
        )
        assert american_to_implied(cards) <= 0.60 - 0.06 + 0.003
        assert american_to_implied(cards) < american_to_implied(corners)

    def test_an_anchored_row_stands_until_fair(self) -> None:
        anchored = _bet_down_to(
            pd.Series({"market": "corners_total_9_5", "selection": "over",
                       "selection_rule": "market_anchored", "calibrated_model_prob": 0.45})
        )
        assert american_to_implied(anchored) == pytest.approx(0.45, abs=0.003)

    def test_a_shrunk_best_bet_needs_the_shrunk_edge(self) -> None:
        row = _row(calibrated_model_prob=0.60, status="BETTABLE")
        whole, halved = _bet_down_to(row), _bet_down_to(row, trust=0.5)
        # Half the edge has to clear the same bar, so it needs a better price.
        assert american_to_implied(halved) < american_to_implied(whole)


def test_the_card_comment_prints_it() -> None:
    from epl_betting_lab.reports.card_notification import _rows

    table = "\n".join(_rows([{
        "home_team": "Arsenal", "away_team": "Chelsea", "market": "btts", "selection": "yes",
        "confidence_tier": "C", "calibrated_edge": 0.06, "american_odds": 110,
        "bet_down_to_american": -105, "book": "FanDuel", "suggested_units": 0.1,
    }]))
    assert "Bet down to" in table
    # The SOCCER CARD routine's kickoff filter reads these by position: Tier
    # is the fourth cell, and Edge, Price, Book and Units are the last four.
    line = next(x for x in table.splitlines() if x.startswith("| Arsenal"))
    row = [c.strip() for c in line.strip().strip("|").split("|")]
    assert row[3] == "C" and row[4] == "-105"
    assert row[-4:] == ["+6.0%", "+110", "FanDuel", "0.1"]


def test_the_props_card_prints_it() -> None:
    from epl_betting_lab.reports.player_props_card import (
        PROPS_EDGE_THRESHOLD,
        READY_STATUS,
        PropPick,
        render_player_props_markdown,
    )

    pick = PropPick(
        date="2026-11-07", kickoff_time="", home_team="Arsenal", away_team="Chelsea",
        market="player_shots_on_target", player="Bukayo Saka", team="Arsenal",
        selection="Over 0.5", model_probability=0.70, implied_probability=0.55,
        edge=0.15, american_odds=-122, book="FanDuel", units=0.1,
        bet_down_to_american=bet_down_to_american(0.70, PROPS_EDGE_THRESHOLD),
    )
    assert pick.bet_down_to_american is not None
    text = render_player_props_markdown({"status": READY_STATUS, "picks": [pick.__dict__]})
    assert "Bet down to" in text


def _load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, PROJECT_ROOT / "web" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_board_and_the_tracker_carry_it() -> None:
    settle = _load("settle_results.py", "settle_bet_down_to")
    props_block = _load("build_board_json.py", "board_bet_down_to").props_block

    block = props_block(
        {"status": "Props card ready", "picks": [{
            "home_team": "Arsenal", "away_team": "Chelsea", "market": "player_shots_on_target",
            "player": "Bukayo Saka", "team": "Arsenal", "selection": "Over@0.5",
            "american_odds": -122, "book": "FanDuel", "model_probability": 0.7, "edge": 0.15,
            "units": 0.1, "bet_down_to_american": -213,
        }]},
        {("Arsenal", "Chelsea"): "g1"},
    )
    assert block["rows"][0]["betDownTo"] == -213

    from datetime import date

    rows = settle.bet_rows(
        date(2026, 11, 7),
        [{"id": "g1", "home": {"abbr": "ARS"}, "away": {"abbr": "CHE"},
          "pick": {"kind": "bet", "market": "btts", "label": "Both teams score", "side": "yes",
                   "price": 110, "betDownTo": -105, "units": 0.1, "result": "win"}}],
        {},
        [],
    )
    assert rows[0]["betDownTo"] == -105
