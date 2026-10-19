"""Open prices, the 1X2 prices and line movement on the EPL board.

The shared page shows Open / Current / Fair for each market and draws a
sparkline from `lineHistory`. Until now the EPL board published current
prices only. The open price and the line now come from the lab's own record
of every price it observed (`reports/price_feed.py`, the `price-feed` branch,
restored to `data/processed/price_feed.csv`):

* open = the first capture in the week before kick-off, at the best bettable
  book -- a reference book such as Pinnacle is never a price here;
* `lineHistory[gameId][key]` = one point per capture, and no series at all
  from a single capture;
* with no feed on disk, or no capture of a selection, the open key is ABSENT.
  Nothing is filled in.

`matchResult {home, draw, away}` carries the 1X2 prices beside the fair ones,
whether or not the card selects from that market.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

KICKOFF = "2026-10-24T14:00Z"
FIXTURES = [
    {"id": "g1", "kickoff": KICKOFF, "date": "2026-10-24", "venue": "", "city": "", "tv": "", "state": "pre",
     "home": {"fd": "Arsenal", "form": ""}, "away": {"fd": "Fulham", "form": ""}},
    {"id": "g2", "kickoff": "2026-10-25T14:00Z", "date": "2026-10-25", "venue": "", "city": "", "tv": "", "state": "pre",
     "home": {"fd": "Chelsea", "form": ""}, "away": {"fd": "Everton", "form": ""}},
]
CARD = {
    "card_generated": True, "window_label": "2026-10-24 through 2026-10-26",
    "best_bets": [{"home_team": "Arsenal", "away_team": "Fulham", "market": "1x2", "selection": "home",
                   "american_odds": 150, "book": "FanDuel", "calibrated_edge": 0.05}],
}


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _feed(lab: Path, rows: list[tuple[str, str, str, str, int]]) -> None:
    """(observed_at, market, selection, book, price) for Arsenal v Fulham."""
    path = lab / "data" / "processed" / "price_feed.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh)
        out.writerow(["observed_at", "provider_event_id", "date", "home_team", "away_team",
                      "market", "selection", "book", "american_odds"])
        for seen, market, selection, book, price in rows:
            out.writerow([seen, "abc12345", "2026-10-24", "Arsenal", "Fulham", market, selection, book, price])


def _build(lab: Path) -> dict:
    board = _module("build_board_json_open", WEB / "build_board_json.py")
    board.read_card = lambda lab, today: (CARD, "test card")
    board.fetch_fixtures = lambda months: ([dict(f) for f in FIXTURES], [])
    board.load_model = lambda lab: (None, "not fitted in this test")
    board.load_record = lambda lab: {"settled": 0, "won": 0}
    from datetime import date
    return board.build(lab, date(2026, 10, 22))


FEED = [
    ("2026-10-16T09:00:00+00:00", "total_2_5", "over", "FanDuel", 200),     # eight days out: not this week
    ("2026-10-18T09:00:00+00:00", "total_2_5", "over", "FanDuel", -110),
    ("2026-10-18T09:00:00+00:00", "total_2_5", "over", "DraftKings", -105),  # best bettable at that capture
    ("2026-10-18T09:00:00+00:00", "total_2_5", "over", "Pinnacle", 300),     # reference, never a price
    ("2026-10-18T09:00:00+00:00", "total_2_5", "under", "FanDuel", -110),
    ("2026-10-20T09:00:00+00:00", "total_2_5", "over", "FanDuel", -120),
    ("2026-10-20T09:00:00+00:00", "btts", "yes", "FanDuel", 100),            # one capture only
    ("2026-10-24T15:00:00+00:00", "total_2_5", "over", "FanDuel", 500),      # after kick-off
]


def test_open_is_the_first_capture_this_week_at_the_best_bettable_book(tmp_path) -> None:
    _feed(tmp_path, FEED)
    built = _build(tmp_path)
    g1, g2 = built["games"]

    assert g1["total"]["openOver"] == -105
    assert g1["total"]["openUnder"] == -110
    assert g1["btts"]["openYes"] == 100
    assert "openNo" not in g1["btts"], "a selection never captured has no open price"
    assert "openHome" not in g1["drawNoBet"] and "openAway" not in g1["drawNoBet"]
    for block, keys in (("total", ("openOver", "openUnder")), ("btts", ("openYes", "openNo")),
                        ("drawNoBet", ("openHome", "openAway"))):
        for key in keys:
            assert key not in g2[block], f"{block}.{key} published for a fixture the feed never priced"


def test_line_history_is_one_point_per_capture_and_none_from_a_single_capture(tmp_path) -> None:
    _feed(tmp_path, FEED)
    built = _build(tmp_path)

    assert built["lineHistory"] == {"g1": {"total_over": [
        {"t": "2026-10-18T09:00:00Z", "v": -105}, {"t": "2026-10-20T09:00:00Z", "v": -120},
    ]}}, "btts_yes has one capture and must be omitted; g2 has none"


def test_with_no_feed_there_is_no_open_price_and_no_captured_line(tmp_path) -> None:
    built = _build(tmp_path)
    assert "lineHistory" not in built
    for game in built["games"]:
        assert not [k for block in ("total", "btts", "drawNoBet") for k in game[block] if k.startswith("open")]


def test_the_match_result_prices_are_published_beside_the_fair_ones(tmp_path) -> None:
    built = _build(tmp_path)
    g1, g2 = built["games"]
    assert g1["matchResult"] == {"home": 150, "draw": None, "away": None}
    assert g2["matchResult"] == {"home": None, "draw": None, "away": None}
    # The keys published before this change are all still there.
    for key in ("result", "total", "btts", "drawNoBet", "pick"):
        assert key in g1


def test_site_history_keeps_the_captured_line_over_the_per_build_one(tmp_path) -> None:
    history = _module("site_history_open", WEB / "site_history.py")
    captured = [{"t": "2026-10-18T09:00:00Z", "v": -105}, {"t": "2026-10-20T09:00:00Z", "v": -120}]

    def _board(stamp: str, over: int, yes: int) -> None:
        (tmp_path / "board.json").write_text(json.dumps({
            "generatedAt": stamp, "windowStart": "2026-10-24",
            "games": [{"id": "g1", "total": {"over": over}, "btts": {"yes": yes}}],
            "lineHistory": {"g1": {"total_over": captured}},
        }), encoding="utf-8")
        assert history.main(["--data", str(tmp_path)]) == 0

    _board("2026-10-21T09:00:00Z", -115, 100)
    _board("2026-10-22T09:00:00Z", -125, 110)
    published = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))["lineHistory"]["g1"]
    assert published["total_over"] == captured, "the per-build series replaced the captured one"
    assert [p["v"] for p in published["btts_yes"]] == [100, 110], "a key with no capture keeps its per-build series"
