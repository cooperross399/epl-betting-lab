"""Props and Due List prices bought after a round's first build reach the record.

The site grades only the board frozen the first time its date is built
(`web/site_history.py`). Props and Due List prices are bought later in the
week, so until 2026-11-21 every frozen board read props `no_lines` and every
Due List entry unpriced: "Props best bets · season: Not tallied yet" and the
Due List posting 0.00u, while the live board carried both. A later build may
now ADD to the frozen copy for fixtures not yet kicked off, and change nothing
it already holds.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from epl_betting_lab.config import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "web" / "site_history.py"


def _module():
    spec = importlib.util.spec_from_file_location("site_history_late", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _game(gid: str, kickoff: str, started: bool, drought: list) -> dict:
    return {"id": gid, "kickoff": kickoff, "started": started,
            "home": {"abbr": "BHA"}, "away": {"abbr": "HUL"}, "drought": drought}


def _prop(gid: str, player: str, price: int) -> dict:
    return {"gameId": gid, "player": player, "team": "BHA", "market": "shots_on_target",
            "side": "over", "line": 0.5, "price": price, "book": "FanDuel", "kind": "bet", "units": 1}


def _due(pid: str, price) -> dict:
    return {"player": f"P{pid}", "playerId": pid, "team": "BHA", "market": "goals", "line": 0.5,
            "price": price, "book": "DraftKings" if price is not None else "", "heavyJuice": False}


FUTURE, PAST = "2099-01-01T15:00Z", "2000-01-01T15:00Z"


def _run(tmp_path: Path, frozen: dict, board: dict) -> dict:
    hist = tmp_path / "history"
    hist.mkdir(parents=True)
    (hist / "2026-11-21.json").write_text(json.dumps(frozen))
    (tmp_path / "board.json").write_text(json.dumps(board))
    assert _module().main(["--data", str(tmp_path)]) == 0
    return json.loads((hist / "2026-11-21.json").read_text())


def _frozen() -> dict:
    return {"windowStart": "2026-11-21", "props": {"status": "no_lines", "rows": []},
            "games": [_game("1", FUTURE, False, [_due("a", None), _due("b", 150)]),
                      _game("2", PAST, False, [_due("c", None)])]}


def _live() -> dict:
    return {"windowStart": "2026-11-21", "generatedAt": "2026-11-21T15:00:00+00:00",
            "props": {"status": "ok", "rows": [_prop("1", "Danny Welbeck", 120), _prop("2", "Late Man", 200)]},
            "games": [_game("1", FUTURE, False, [_due("a", 300), _due("b", 999), _due("d", 400)]),
                      _game("2", PAST, True, [_due("c", 250), _due("e", 500)])]}


def test_a_fixture_not_yet_started_gains_its_props_and_due_prices(tmp_path) -> None:
    kept = _run(tmp_path, _frozen(), _live())
    assert kept["props"]["status"] == "ok"
    assert [r["player"] for r in kept["props"]["rows"]] == ["Danny Welbeck"]
    due = {e["playerId"]: e for e in kept["games"][0]["drought"]}
    assert due["a"]["price"] == 300 and due["a"]["book"] == "DraftKings"
    assert due["d"]["price"] == 400


def test_nothing_already_frozen_moves(tmp_path) -> None:
    frozen = _frozen()
    frozen["props"] = {"status": "ok", "rows": [_prop("1", "Danny Welbeck", 105)]}
    kept = _run(tmp_path, frozen, _live())
    assert [r["price"] for r in kept["props"]["rows"]] == [105]
    due = {e["playerId"]: e for e in kept["games"][0]["drought"]}
    assert due["b"]["price"] == 150


def test_a_started_fixture_is_never_touched(tmp_path) -> None:
    kept = _run(tmp_path, _frozen(), _live())
    assert all(r["gameId"] != "2" for r in kept["props"]["rows"])
    second = kept["games"][1]["drought"]
    assert [e["playerId"] for e in second] == ["c"] and second[0]["price"] is None


def test_a_kickoff_in_the_past_counts_as_started_even_unflagged(tmp_path) -> None:
    live = _live()
    live["games"][1]["started"] = False
    kept = _run(tmp_path, _frozen(), live)
    assert kept["games"][1]["drought"][0]["price"] is None
    assert all(r["gameId"] != "2" for r in kept["props"]["rows"])


def test_the_settler_grades_what_was_merged(tmp_path) -> None:
    """The record reads props off the frozen board, so the merged rows are what it grades."""
    spec = importlib.util.spec_from_file_location("settle_late", PROJECT_ROOT / "web" / "settle_results.py")
    settle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settle)
    kept = _run(tmp_path, _frozen(), _live())
    rows = settle.published_props([kept], {"1": {}})
    assert [r["player"] for r in rows] == ["Danny Welbeck"]
