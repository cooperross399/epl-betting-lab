"""Player props reach the public board, in the shape the shared page renders.

Cooper, 2026-10-19: "I want props and every other market we have looked into
included in the model's card and on the website." The card already printed a
props section once the policy approved one; the board never read the props
card at all, and the shared page's EPL adapter had no props view.

`web/build_board_json.py` now turns `player_props_card.json` into the
`props` block of board.json (the schema the NHL props tab already reads), and
`web/lib/sports.js` gives EPL that same tab. Held-by-policy and missing-staging
states are carried as words, never as an empty "no value" board.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _board():
    spec = importlib.util.spec_from_file_location("build_board_json_props", WEB / "build_board_json.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _card(picks, status="Props card ready", note="no edge"):
    return {"status": status, "note": note, "picks": picks}


def _pick(**over):
    pick = {
        "date": "2026-10-25", "kickoff_time": "2026-10-25T14:00:00Z",
        "home_team": "Newcastle", "away_team": "Liverpool",
        "market": "player_shots_on_target", "player": "Alexander Isak", "team": "Newcastle",
        "selection": "Over@0.5", "model_probability": 0.81, "implied_probability": 0.4,
        "edge": 0.41, "american_odds": 150.0, "book": "FanDuel", "units": 0.1,
    }
    pick.update(over)
    return pick


GAMES = {("Newcastle", "Liverpool"): "g1"}


def test_a_pick_becomes_a_props_row_on_its_game() -> None:
    board = _board()
    block = board.props_block(_card([_pick()]), GAMES)

    assert block["status"] == "ok"
    (row,) = block["rows"]
    assert row["gameId"] == "g1"
    assert row["player"] == "Alexander Isak"
    assert row["team"] == board.team_entry("Newcastle")[0]
    assert row["opp"] == board.team_entry("Liverpool")[0]
    assert row["market"] == "shots_on_target"
    assert (row["line"], row["side"]) == (0.5, "over")
    assert row["price"] == 150 and row["book"] == "FanDuel"
    assert row["kind"] == "bet" and row["units"] == 0.1
    assert row["edgePct"] == 41.0


def test_anytime_scorer_reads_as_over_half_a_goal() -> None:
    board = _board()
    block = board.props_block(
        _card([_pick(market="player_goal_scorer_anytime", selection="Yes")]), GAMES
    )
    (row,) = block["rows"]
    assert (row["market"], row["line"], row["side"]) == ("goals", 0.5, "over")


def test_a_pick_on_a_fixture_not_on_the_board_is_dropped() -> None:
    board = _board()
    block = board.props_block(_card([_pick(home_team="Arsenal", away_team="Chelsea")]), GAMES)
    assert block["rows"] == []


def test_held_and_unstaged_say_why_rather_than_showing_nothing() -> None:
    board = _board()
    held = board.props_block(_card([], status="Held by policy", note="held"), GAMES)
    assert held["status"] == "abstain" and held["note"] == "held"
    unstaged = board.props_block(_card([], status="No props staging evidence", note="none"), GAMES)
    assert unstaged["status"] == "no_lines" and unstaged["note"] == "none"


def test_no_props_card_means_no_props_block(tmp_path: Path) -> None:
    board = _board()
    assert board.load_props_card(tmp_path) is None
    path = tmp_path / board.PROPS_CARD_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_card([_pick()])), encoding="utf-8")
    assert board.load_props_card(tmp_path)["picks"][0]["player"] == "Alexander Isak"


_DRIVER = r"""
import { readFileSync } from "node:fs";
import { ADAPTERS } from "./lib/sports.js";
const data = JSON.parse(readFileSync(process.argv[2], "utf8"));
process.stdout.write(JSON.stringify(ADAPTERS.epl.props ? ADAPTERS.epl.props(data) : null));
"""


def test_the_shared_page_renders_epl_props(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node, "node is not on PATH; this test renders the page's own adapter."
    board = _board()
    payload = {
        "teams": {}, "games": [{"id": "g1", "home": {"abbr": "NEW"}, "away": {"abbr": "LIV"}}],
        "props": board.props_block(_card([_pick()]), GAMES),
    }
    (tmp_path / "lib").mkdir()
    for name in ("sports.js", "format.js"):
        shutil.copyfile(WEB / "lib" / name, tmp_path / "lib" / name)
    (tmp_path / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (tmp_path / "render.mjs").write_text(_DRIVER, encoding="utf-8")
    (tmp_path / "board.json").write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run([node, str(tmp_path / "render.mjs"), str(tmp_path / "board.json")],
                            capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    view = json.loads(result.stdout)

    assert view is not None, "the EPL adapter has no props view"
    assert view["status"] == "ok"
    (row,) = view["rows"]
    assert row["marketTitle"] == "Shots on target"
    assert row["label"] == "Over 0.5 shots on target"
    assert row["kindLabel"] == "Best bet"
