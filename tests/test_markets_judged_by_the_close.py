"""Each market is judged by the closing line once it has enough bets to judge.

Profit needs about 1,500 bets to separate a 5% edge from zero; closing-line
value speaks per bet. Once a market has 50 picks with a closing consensus
captured, its mean CLV and a 95% interval decide one of three readings:
behind the close (the whole interval below zero: a market to cut), ahead of it
(the whole interval above zero: a market that may earn more than the floor
stake), or no signal yet. Below 50 it says how many it has. Cutting or raising
stays Cooper's call; the card says which markets the evidence points at.
"""

from __future__ import annotations

import json

import pandas as pd

from epl_betting_lab.reports import live_clv
from epl_betting_lab.reports.live_clv import (
    AHEAD,
    BEHIND,
    MIN_PICKS_FOR_VERDICT,
    NO_SIGNAL,
    TOO_FEW,
    market_verdicts,
    render_verdicts,
)


def _frame(market: str, clv: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "market": market, "state": live_clv.CAPTURED,
        "clv_points_best": clv, "clv_points_consensus": clv,
    })


def _verdict(clv: list[float], market: str = "corners_total_9_5") -> dict:
    (row,) = market_verdicts(_frame(market, clv))
    return row


def test_fifty_picks_behind_the_close_are_flagged_to_cut() -> None:
    row = _verdict([-1.5, -0.5] * 25)
    assert MIN_PICKS_FOR_VERDICT == 50
    assert row["verdict"] == BEHIND
    assert row["picks"] == 50 and row["clv_mean"] == -1.0
    assert row["clv_high"] < 0


def test_fifty_picks_ahead_of_the_close_are_flagged_as_earning() -> None:
    assert _verdict([1.5, 0.5] * 25)["verdict"] == AHEAD


def test_an_interval_holding_zero_is_no_signal() -> None:
    assert _verdict([3.0, -3.2] * 25)["verdict"] == NO_SIGNAL


def test_forty_nine_picks_are_not_judged_however_bad() -> None:
    row = _verdict([-5.0] * 49)
    assert row["verdict"] == TOO_FEW and row["picks"] == 49


def test_only_captured_consensus_readings_count() -> None:
    frame = pd.concat([
        _frame("btts", [-1.0, -0.8] * 25),
        pd.DataFrame({"market": ["btts"] * 30, "state": [live_clv.NOT_PLAYED] * 30,
                      "clv_points_best": [None] * 30, "clv_points_consensus": [None] * 30}),
    ], ignore_index=True)
    (row,) = market_verdicts(frame)
    assert row["picks"] == 50


def test_the_card_names_what_to_cut_and_what_is_earning() -> None:
    frame = pd.concat([
        _frame("corners_total_10_5", [-1.5, -0.5] * 25),
        _frame("btts", [1.5, 0.5] * 25),
        _frame("1x2", [-2.0] * 10),
    ], ignore_index=True)
    text = "\n".join(render_verdicts(market_verdicts(frame)))
    assert "corners_total_10_5" in text and "cut" in text.lower()
    assert "btts" in text
    assert "1x2" in text and "10 of 50" in text


def test_the_report_writes_the_verdicts_the_card_reads(tmp_path) -> None:
    paths = live_clv.save_live_clv_reports([], pd.DataFrame(), tmp_path)
    assert json.loads(paths["verdicts"].read_text()) == []


def test_the_card_prints_the_check(tmp_path) -> None:
    from epl_betting_lab.reports.card_notification import closing_line_check

    (tmp_path / live_clv.VERDICTS_FILENAME).write_text(json.dumps(
        market_verdicts(_frame("corners_total_10_5", [-1.5, -0.5] * 25))))
    text = "\n".join(closing_line_check(tmp_path))
    assert "corners_total_10_5" in text
    assert closing_line_check(tmp_path / "absent") == []
