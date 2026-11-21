"""Every EPL stake is the Due List ladder on a 1u base (2026-11-21).

Cooper: "use the due list ladder style pricing but with 1u as the main instead
of .25u" and "records/profits on the website for EPL". Up to +199 a bet is 1u
on a plus price, or enough to win 1u on a minus price; +200 to +500 0.6u;
+501 to +1500 0.4u; longer 0.2u. A push or void returns 0; a pick with no
usable price is graded and staked nothing.

These pin the card's Units column, the site's settlement and the site's
tracker to the same numbers, so the card and the record cannot drift apart.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab import staking

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_ladder", ROOT / "web" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETTLE = _load("settle_results")
PAGES = _load("build_site_pages")

# (price, result, units won/lost, units risked)
CASES = [
    (-150, "win", 1.0, 1.5),      # risk 1.5u to win 1u
    (-150, "loss", -1.5, 1.5),
    (-110, "win", 1.0, 1.1),
    (150, "win", 1.5, 1.0),       # 1u on a plus price under +200
    (199, "loss", -1.0, 1.0),
    (200, "win", 1.2, 0.6),
    (300, "win", 1.8, 0.6),       # +300 at 0.6u
    (300, "loss", -0.6, 0.6),
    (500, "win", 3.0, 0.6),
    (501, "win", 2.004, 0.4),
    (1000, "win", 4.0, 0.4),      # +1000 at 0.4u
    (1000, "loss", -0.4, 0.4),
    (1500, "loss", -0.4, 0.4),
    (1501, "loss", -0.2, 0.2),
    (2500, "win", 5.0, 0.2),
    (-150, "push", 0.0, 1.5),
]


@pytest.mark.parametrize("price,result,units,risked", CASES)
def test_the_ladder(price, result, units, risked):
    assert staking.graded(price, result) == (pytest.approx(units), pytest.approx(risked))


@pytest.mark.parametrize("price,result,units,risked", CASES)
def test_the_site_settles_on_the_same_ladder(price, result, units, risked):
    assert SETTLE.quarter(price, result) == (pytest.approx(units), pytest.approx(risked))
    row = PAGES.restake({"price": price, "result": result, "staked": 0.1, "units": 0.0})
    assert (row["units"], row["staked"]) == (pytest.approx(units), pytest.approx(risked))
    restated = SETTLE.restake({"price": price, "result": result, "staked": 0.1, "units": 0.0})
    assert (restated["units"], restated["staked"]) == (pytest.approx(units), pytest.approx(risked))


def test_a_void_returns_nothing_and_risks_nothing():
    assert staking.graded(-150, "void") == (0.0, 0.0)
    assert SETTLE.quarter(-150, "void") is None or SETTLE.quarter(-150, "void") == (0.0, 0.0)


def test_no_price_is_never_staked():
    for price in (None, "", 50, -99, float("nan"), True):
        assert staking.graded(price, "win") is None
        assert SETTLE.quarter(price, "win") is None
        assert staking.card_units("C", price) == 0.0


def test_a_straight_up_call_risks_one_unit_flat_under_plus_200():
    assert staking.flat(-800, "win") == (pytest.approx(0.125), pytest.approx(1.0))
    assert staking.flat(-150, "loss") == (pytest.approx(-1.0), pytest.approx(1.0))
    assert staking.flat(150, "win") == (pytest.approx(1.5), pytest.approx(1.0))
    assert staking.flat(300, "win") == (pytest.approx(1.8), pytest.approx(0.6))
    assert SETTLE.flat(-800, "win") == (pytest.approx(0.125), pytest.approx(1.0))
    assert SETTLE.flat(1000, "loss") == (pytest.approx(-0.4), pytest.approx(0.4))


def test_the_site_constants_read_one_unit():
    assert SETTLE.TRACKED_STAKE == 1.0 and PAGES.TRACKED_STAKE == 1.0
    assert SETTLE.DUE_STAKE == 1.0
    assert SETTLE.STAKE_RULE == PAGES.STAKE_RULE == staking.STAKE_RULE


@pytest.mark.parametrize("tier,price,units", [
    ("C", -150, 1.5), ("C", 120, 1.0), ("C", 300, 0.6), ("C", 1000, 0.4), ("C", 2000, 0.2),
    ("B", 150, 2.5), ("A", -110, 5.5), ("Lean (no stake)", -150, 0.0), ("Pass/Avoid", 300, 0.0),
])
def test_the_card_units_column(tier, price, units):
    from epl_betting_lab.reports.thursday_best_bets import _suggested_units

    assert staking.card_units(tier, price) == pytest.approx(units)
    assert _suggested_units(tier, price) == pytest.approx(units)


def test_the_card_report_carries_the_ladder():
    from epl_betting_lab.reports.thursday_best_bets import build_thursday_best_bets

    base = {"home_team": "Arsenal", "away_team": "Coventry", "market": "1x2", "selection": "home",
            "status": "BETTABLE", "raw_model_prob": 0.75, "calibrated_model_prob": 0.72, "model_prob": 0.72,
            "book_implied": 0.6, "raw_edge": 0.15, "calibrated_edge": 0.12, "edge": 0.12,
            "ev_per_unit": 0.1, "fair_american": -257, "book": "DraftKings", "notes": ""}
    rows = [{**base, "american_odds": -150},
            {**base, "home_team": "Spurs", "away_team": "Hull", "american_odds": 300, "fair_american": 200,
             "book_implied": 0.25, "calibrated_model_prob": 0.4, "model_prob": 0.4}]
    report = build_thursday_best_bets(pd.DataFrame(rows), market_reliability={})
    best = report[report["section"] == "Best bets"].set_index("home_team")
    assert best.loc["Arsenal", "suggested_units"] == pytest.approx(1.5)
    assert best.loc["Spurs", "suggested_units"] == pytest.approx(0.6)


def test_the_props_and_beyond_cards_use_the_ladder():
    from epl_betting_lab.reports import extra_competitions_card, player_props_card

    assert player_props_card.props_units(-150) == pytest.approx(1.5)
    assert player_props_card.props_units(300) == pytest.approx(0.6)
    assert extra_competitions_card.extra_units(1000) == pytest.approx(0.4)


# ---------- the site's records: units, staked, return on every record ----------

DAY = "2026-10-17"
TEAMS = {"ARS": {"name": "Arsenal"}, "FUL": {"name": "Fulham"}, "CHE": {"name": "Chelsea"}, "EVE": {"name": "Everton"}}


def _game(gid, home, away, *, probs, over, pick, prices, total):
    return {"id": gid, "kickoff": f"{DAY}T14:00Z",
            "home": {"abbr": home, "winProb": probs[0]}, "away": {"abbr": away, "winProb": probs[2]},
            "drawProb": probs[1], "total": {"line": 2.5, "overProb": over, **total},
            "matchResult": prices, "pick": pick}


def _settle(tmp_path, games, finals):
    hist = tmp_path / "history"
    hist.mkdir(exist_ok=True)
    board = {"season": "2026-27", "generatedAt": "2026-10-15T09:00:00Z", "windowStart": DAY, "teams": TEAMS, "games": games}
    (hist / f"{DAY}.json").write_text(json.dumps(board), encoding="utf-8")
    (tmp_path / "board.json").write_text(json.dumps({**board, "record": {}}), encoding="utf-8")
    module = _load("settle_results")

    def _finals(sport, d):
        if d.isoformat() != DAY:
            raise urllib.error.HTTPError("https://site.api.espn.com/", 403, "Forbidden", None, None)
        return finals

    module.finals = _finals
    module.match_summary = lambda sport, gid: None
    assert module.main(["--data", str(tmp_path), "--sport", "epl", "--date", DAY]) == 0
    results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    board = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))
    return results, board


def test_every_record_carries_units_staked_and_return(tmp_path):
    """Arsenal 2-1 Fulham: the best bet (Arsenal at -150) wins 1u on 1.5u; the
    model's favourite (home, -150) wins 0.667u on a flat 1u; over 2.5 (+300 on
    the board's frozen price) wins 1.8u on 0.6u.
    Chelsea 1-1 Everton: the lean (Chelsea +1000) loses 0.4u; the favoured side
    (Chelsea at +120) loses 1u, because a draw it did not name is a loss; the
    model's under 2.5 wins but has no price on the board: graded, unpriced."""
    games = [
        _game("g1", "ARS", "FUL", probs=(0.6, 0.25, 0.15), over=0.6,
              pick={"kind": "bet", "market": "1x2", "label": "Arsenal", "side": "home", "price": -150},
              prices={"home": -150, "draw": 260, "away": 400}, total={"over": 300, "under": -400}),
        _game("g2", "CHE", "EVE", probs=(0.45, 0.3, 0.25), over=0.4,
              pick={"kind": "lean", "market": "1x2", "label": "Chelsea", "side": "home", "price": 1000},
              prices={"home": 120, "draw": 230, "away": 250}, total={}),
    ]
    finals = {"g1": {"home": 2, "away": 1, "finish": "REG"}, "g2": {"home": 1, "away": 1, "finish": "REG"}}
    results, board = _settle(tmp_path, games, finals)

    night = results["summary"]["money"]
    assert night["picks"]["units"] == pytest.approx(1.0) and night["picks"]["staked"] == pytest.approx(1.5)
    assert night["leans"]["units"] == pytest.approx(-0.4) and night["leans"]["staked"] == pytest.approx(0.4)
    assert night["straightUp"]["units"] == pytest.approx(0.6667 - 1.0, abs=1e-3)
    assert night["straightUp"]["staked"] == pytest.approx(2.0)
    assert night["totals"]["units"] == pytest.approx(1.8) and night["totals"]["staked"] == pytest.approx(0.6)
    assert night["totals"]["unpriced"] == 1 and night["totals"]["priced"] == 1

    money = board["record"]["season"]["money"]
    for key in ("picks", "leans", "straightUp", "totals"):
        m = money[key]
        assert {"w", "l", "p", "units", "staked", "returnPct", "stake"} <= set(m), key
        assert m["stake"] == 1.0
    assert money["picks"]["returnPct"] == pytest.approx(66.7, abs=0.1)
    assert money["totals"]["w"] == 2 and money["totals"]["l"] == 0


def test_a_night_kept_under_the_old_rule_is_settled_again():
    assert SETTLE.GRADING >= 2
    stale = {"summary": {}, "bets": [], "stakeRule": "0.25u, to win 0.25u on a minus price"}
    assert SETTLE.is_stale(stale)
    assert not SETTLE.is_stale({"summary": {"money": {}}, "bets": [], "stakeRule": SETTLE.STAKE_RULE, "grading": SETTLE.GRADING})


def test_the_pages_fall_back_to_one_unit():
    for page in ("Record.dc.html", "Results.dc.html", "Board.dc.html"):
        text = (ROOT / "web" / page).read_text(encoding="utf-8")
        if page == "Record.dc.html":
            assert "0.25u" not in text, page
    smooth = (ROOT / "web" / "smooth_pages.py").read_text(encoding="utf-8")
    assert "?? 0.25" not in smooth.split("PATCHES")[0] + "".join(
        new for pairs in _load("smooth_pages").PATCHES.values() for _, new in pairs)
