"""A pick the market has moved against since its first price is halved.

The CBB lab's `models/line_move.py` (2026-10-30): a lean the market moved
against since the event's first capture is halved before the edge bar reads
it; a move with the lean changes nothing. Here the first capture is the
earliest observation in the price feed for that selection, the latest is the
newest one, and each is the median implied probability across books.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.line_move import MIN_MOVE, move_against
from epl_betting_lab.reports.thursday_best_bets import LEAN_TIER, build_thursday_best_bets


def _feed(path: Path, first: float, latest: float) -> Path:
    rows = []
    for observed, odds in (("2026-10-29T10:00:00+00:00", first), ("2026-10-31T10:00:00+00:00", latest)):
        for book in ("FanDuel", "BetMGM"):
            rows.append({
                "competition": "E0", "commence_time": "2026-10-31T15:00:00Z", "observed_at": observed,
                "provider_event_id": "x", "date": "2026-10-31", "home_team": "Newcastle",
                "away_team": "Everton", "market": "draw_no_bet", "selection": "home",
                "book": book, "american_odds": odds,
            })
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _bet(edge=0.06):
    return {
        "home_team": "Newcastle", "away_team": "Everton", "market": "draw_no_bet",
        "selection": "home", "status": "BETTABLE", "american_odds": -110,
        "raw_model_prob": 0.6, "calibrated_model_prob": 0.6, "model_prob": 0.6,
        "raw_edge": edge, "calibrated_edge": edge, "edge": edge,
        "fair_american": -150, "book": "FanDuel",
    }


def test_a_price_that_drifted_out_is_a_move_against(tmp_path: Path):
    feed = pd.read_csv(_feed(tmp_path / "f.csv", first=-150, latest=-110))
    moved, first, latest = move_against(feed, "Newcastle", "Everton", "draw_no_bet", "home")
    assert moved and first > latest + MIN_MOVE


def test_a_price_that_shortened_is_not(tmp_path: Path):
    feed = pd.read_csv(_feed(tmp_path / "f.csv", first=-110, latest=-150))
    assert not move_against(feed, "Newcastle", "Everton", "draw_no_bet", "home")[0]


def test_no_history_is_no_move():
    assert not move_against(pd.DataFrame(), "Newcastle", "Everton", "draw_no_bet", "home")[0]


def test_the_card_halves_a_pick_the_market_moved_against(tmp_path: Path):
    feed = _feed(tmp_path / "f.csv", first=-150, latest=-110)
    report = build_thursday_best_bets(
        pd.DataFrame([_bet(0.06)]), trust_weights_path=tmp_path / "none.json", price_feed_path=feed
    )
    row = report.iloc[0]
    # 6% halved is 3%, under the 3.5% bar.
    assert row["section"] == "Leans"
    assert row["confidence_tier"] == LEAN_TIER
    assert "moved against" in row["qualifies_reason"]


def test_a_big_edge_survives_the_halving(tmp_path: Path):
    feed = _feed(tmp_path / "f.csv", first=-150, latest=-110)
    report = build_thursday_best_bets(
        pd.DataFrame([_bet(0.10)]), trust_weights_path=tmp_path / "none.json", price_feed_path=feed
    )
    assert report.iloc[0]["section"] == "Best bets"
