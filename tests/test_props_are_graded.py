"""Every player prop the board published is graded once its match is played.

Until 2026-10-19 the props card put picks on the board (shots, shots on target,
assists, anytime scorer, booked, sent off, tackles, goalkeeper saves) and
nothing ever settled one: `settle_results.py` graded the team pick and the Due
List, and the EPL adapter had no `propResults`, so the Results page had no
props section at all. A pick that is never graded is a record that cannot
exist.

ESPN's match summary carries each player's shots, shots on target, goals,
assists, cards and saves. Tackles are not in it; they come from the Fantasy
Premier League per-match logs the props card already fetches.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTLE = PROJECT_ROOT / "web" / "settle_results.py"
SPORTS_JS = PROJECT_ROOT / "web" / "lib" / "sports.js"
PUBLISH = PROJECT_ROOT / ".github" / "workflows" / "publish-board.yml"
MATCHDAY = PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"

DAY = date(2026, 10, 18)
GID = "401879268"


def _module():
    spec = importlib.util.spec_from_file_location("settle_results_props", SETTLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prop(player, market, side, line, price=110, units=0.1, team="NFO", opp="ARS", **extra):
    return {"gameId": GID, "player": player, "team": team, "opp": opp, "market": market,
            "side": side, "line": line, "price": price, "book": "DraftKings",
            "kind": "bet", "units": units, **extra}


def _board(rows, generated="2026-10-17T09:00:00Z"):
    return {
        "season": "2026-27", "generatedAt": generated, "windowLabel": "2026-10-17 through 2026-10-19",
        "teams": {"NFO": {"name": "Nott'm Forest"}, "ARS": {"name": "Arsenal"}},
        "games": [{"id": GID, "kickoff": "2026-10-18T15:30Z",
                   "home": {"abbr": "NFO", "winProb": 0.3}, "away": {"abbr": "ARS", "winProb": 0.45},
                   "drawProb": 0.25, "total": {"overProb": 0.5}, "pick": None}],
        "props": {"status": "ok", "note": "", "rows": rows},
    }


def _player(pid, name, appeared=1, **stats):
    base = {"appearances": float(appeared), "totalShots": 0.0, "shotsOnTarget": 0.0, "totalGoals": 0.0,
            "goalAssists": 0.0, "yellowCards": 0.0, "redCards": 0.0, "saves": 0.0}
    base.update({k: float(v) for k, v in stats.items()})
    return {"athlete": {"id": pid, "displayName": name}, "stats": [{"name": k, "value": v} for k, v in base.items()]}


SUMMARY = {
    "rosters": [
        {"homeAway": "home", "roster": [
            _player("1", "Chris Wood", totalShots=4, shotsOnTarget=1),
            _player("2", "Matz Sels", saves=5),
            _player("3", "Elliot Anderson", yellowCards=1),
            _player("4", "Murillo", appeared=0),
            _player("5", "Morgan Gibbs-White", totalShots=2),
        ]},
        {"homeAway": "away", "roster": [
            _player("10", "Bukayo Saka", totalShots=3, shotsOnTarget=2, goalAssists=1),
            _player("11", "Martin Ødegaard", totalGoals=1, shotsOnTarget=1, totalShots=1),
        ]},
    ]
}


@pytest.fixture
def settle(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "finals", lambda sport, day: {GID: {"home": 0, "away": 1, "finish": "REG"}})
    monkeypatch.setattr(module, "match_summary", lambda sport, gid: SUMMARY)
    return module


def _graded(settle, rows, **kwargs):
    results, waiting = settle.settle_day("epl", DAY, [_board(rows)], **kwargs)
    return results["props"], waiting


def _result(props, player, market):
    (row,) = [r for r in props["rows"] if r["player"] == player and r["market"] == market]
    return row


def test_each_espn_stat_settles_its_market(settle) -> None:
    rows = [
        _prop("Chris Wood", "shots", "over", 2.5),                 # 4 -> win
        _prop("Chris Wood", "shots_on_target", "over", 1.5),       # 1 -> loss
        _prop("Bukayo Saka", "assists", "over", 0.5, team="ARS", opp="NFO"),  # 1 -> win
        _prop("Bukayo Saka", "goals", "over", 0.5, team="ARS", opp="NFO"),    # 0 -> loss
        _prop("Elliot Anderson", "booked", "over", 0.5),            # yellow -> win
        _prop("Elliot Anderson", "sent_off", "over", 0.5),          # no red -> loss
        _prop("Matz Sels", "goalie_saves", "over", 3.5),            # 5 -> win
    ]
    props, _ = _graded(settle, rows)
    got = {(r["player"], r["market"]): (r["actual"], r["result"]) for r in props["rows"]}
    assert got == {
        ("Chris Wood", "shots"): (4, "win"),
        ("Chris Wood", "shots_on_target"): (1, "loss"),
        ("Bukayo Saka", "assists"): (1, "win"),
        ("Bukayo Saka", "goals"): (0, "loss"),
        ("Elliot Anderson", "booked"): (1, "win"),
        ("Elliot Anderson", "sent_off"): (0, "loss"),
        ("Matz Sels", "goalie_saves"): (5, "win"),
    }


def test_units_are_won_at_the_published_price(settle) -> None:
    props, _ = _graded(settle, [
        _prop("Chris Wood", "shots", "over", 2.5, price=150),
        _prop("Chris Wood", "shots_on_target", "over", 1.5, price=-120),
    ])
    assert _result(props, "Chris Wood", "shots")["profitUnits"] == pytest.approx(0.15)
    assert _result(props, "Chris Wood", "shots_on_target")["profitUnits"] == pytest.approx(-0.1)
    assert props["summary"]["w"] == 1 and props["summary"]["l"] == 1
    assert props["summary"]["units"] == pytest.approx(0.05)


def test_an_unused_substitute_is_void_and_costs_nothing(settle) -> None:
    props, _ = _graded(settle, [_prop("Murillo", "booked", "over", 0.5)])
    row = _result(props, "Murillo", "booked")
    assert row["result"] == "void" and row["profitUnits"] == 0
    assert props["summary"]["w"] + props["summary"]["l"] + props["summary"]["p"] == 0


def test_accents_do_not_stop_a_player_being_found(settle) -> None:
    props, _ = _graded(settle, [_prop("Martin Odegaard", "goals", "over", 0.5, team="ARS", opp="NFO")])
    assert _result(props, "Martin Odegaard", "goals")["result"] == "win"


def test_a_player_the_feed_does_not_name_is_ungraded_not_void(settle) -> None:
    """A name that does not match is not proof he did not play."""
    props, waiting = _graded(settle, [_prop("Somebody Else", "shots", "over", 0.5)])
    assert _result(props, "Somebody Else", "shots")["result"] is None
    assert props["summary"]["ungraded"] == 1
    assert waiting is True


def test_tackles_come_from_the_fpl_logs(settle, tmp_path) -> None:
    logs = tmp_path / "fpl_match_logs.csv"
    logs.write_text(
        "date,match_id,team,opponent,venue,player,player_id,position,minutes,tackles,saves,yellow_cards,red_cards\n"
        "2026-10-18,77,Nott'm Forest,Arsenal,home,Elliot Anderson,9,MID,90,4,0,1,0\n",
        encoding="utf-8",
    )
    rows = [_prop("Elliot Anderson", "tackles", "over", 2.5), _prop("Chris Wood", "tackles", "over", 0.5)]
    props, _ = _graded(settle, rows, fpl_logs=settle.load_fpl_logs(logs))
    assert (_result(props, "Elliot Anderson", "tackles")["actual"], _result(props, "Elliot Anderson", "tackles")["result"]) == (4, "win")
    # Played per ESPN, absent from FPL: unanswered, never a zero.
    assert _result(props, "Chris Wood", "tackles")["result"] is None


def test_tackles_without_fpl_logs_stay_ungraded(settle) -> None:
    props, _ = _graded(settle, [_prop("Elliot Anderson", "tackles", "over", 2.5)])
    assert _result(props, "Elliot Anderson", "tackles")["result"] is None


def test_the_first_published_price_is_the_one_graded(settle) -> None:
    early = _board([_prop("Chris Wood", "shots", "over", 2.5, price=150)], generated="2026-10-17T09:00:00Z")
    late = _board([_prop("Chris Wood", "shots", "over", 2.5, price=-200)], generated="2026-10-18T09:00:00Z")
    results, _ = settle.settle_day("epl", DAY, [early, late])
    (row,) = results["props"]["rows"]
    assert row["price"] == 150


def test_a_lean_is_shown_but_never_counted(settle) -> None:
    props, _ = _graded(settle, [_prop("Chris Wood", "shots", "over", 2.5, kind="lean")])
    assert _result(props, "Chris Wood", "shots")["result"] == "win"
    assert props["summary"]["w"] == 0


def test_a_board_without_props_writes_no_props_block(settle) -> None:
    board = _board([])
    board.pop("props")
    results, _ = settle.settle_day("epl", DAY, [board])
    assert "props" not in results


def test_the_season_sums_the_props(settle, tmp_path) -> None:
    rows = [_prop("Chris Wood", "shots", "over", 2.5), _prop("Chris Wood", "shots_on_target", "over", 1.5)]
    boards = [_board(rows)]
    latest, waiting = settle.settle_day("epl", DAY, boards)
    season = settle.season_record("epl", DAY, tmp_path, boards, latest, waiting)
    assert season["props"]["w"] == 1 and season["props"]["l"] == 1
    assert season["props"]["nights"] == 1
    data = tmp_path / "data"
    data.mkdir()
    (data / "board.json").write_text(json.dumps({"record": {}}), encoding="utf-8")
    settle.write_season(data, latest, season)
    assert latest["props"]["season"]["w"] == 1


def test_the_results_page_reads_epl_props() -> None:
    text = SPORTS_JS.read_text(encoding="utf-8")
    adapters = text.split("export const ADAPTERS", 1)[1]
    epl = adapters.split("epl:", 1)[1].split("}", 1)[0]
    # The adapter may hand the shared grader straight through or wrap it with
    # EPL's own prop labels; either way the Results page grades EPL props
    # with nhlPropResults.
    assert re.search(r"propResults:\s*(nhlPropResults\b|\(d\)\s*=>\s*nhlPropResults\(d\b)", epl), epl


def test_the_publish_passes_the_fpl_logs_and_matchday_keeps_them() -> None:
    assert "--fpl-logs" in PUBLISH.read_text(encoding="utf-8")
    state = MATCHDAY.read_text(encoding="utf-8").split("name: matchday-state", 1)[1].split("retention-days", 1)[0]
    assert "data/processed/fpl_match_logs.csv" in state
