"""The season's four records, summed from the days the record has settled.

The shared board's strip reads `record.picks`, `record.straightUp`,
`record.totals` and `record.leans` in the NHL lab's shape, and shows a dash
with "Not tallied yet" for any that is absent. `web/settle_results.py` now
sums them from every day a published fixture kicked off (`season_record`),
keeps each settled day under history/settled/, and writes the season into
results.json (`seasonRecord`) and onto board.json's `record`.

What these pin, each a way the record could say something nobody counted:

* before a day has settled there is no season at all -- not 0-0;
* a lean is graded and kept in `leans`, never in `picks`;
* a day the settler could not read is in `missingNights`, not counted 0-0;
* the favoured side is the 1X2 favourite, draw included: a draw is a loss
  unless the draw was favoured;
* the Due List is graded from the match's squads -- goals or assists when he
  played, `void` when he did not -- and is never a unit or a stake.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTLE = PROJECT_ROOT / "web" / "settle_results.py"

SPORT = "epl"
DAY1, DAY2 = "2026-10-17", "2026-10-18"

TEAMS = {
    "ARS": {"name": "Arsenal"}, "FUL": {"name": "Fulham"},
    "CHE": {"name": "Chelsea"}, "EVE": {"name": "Everton"},
}


def _module():
    spec = importlib.util.spec_from_file_location("settle_results_season", SETTLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _game(gid, day, home, away, *, probs=(0.6, 0.25, 0.15), over=0.6, pick=None, drought=None):
    game = {
        "id": gid, "kickoff": f"{day}T14:00Z",
        "home": {"abbr": home, "winProb": probs[0]}, "away": {"abbr": away, "winProb": probs[2]},
        "drawProb": probs[1], "total": {"overProb": over}, "pick": pick,
    }
    if drought is not None:
        game["drought"] = drought
    return game


def _write(tmp_path: Path, games: list[dict], *, record: dict | None = None) -> Path:
    hist = tmp_path / "history"
    hist.mkdir(exist_ok=True)
    board = {"season": "2026-27", "generatedAt": "2026-10-15T09:00:00Z", "windowLabel": f"{DAY1} through {DAY2}",
             "windowStart": DAY1, "teams": TEAMS, "games": games}
    (hist / f"{DAY1}.json").write_text(json.dumps(board), encoding="utf-8")
    # The live board this morning, which carries the record the page reads.
    live = {**board, "record": record if record is not None else {"settled": 3, "won": 1, "void": 0, "roiPct": -12.0}}
    (tmp_path / "board.json").write_text(json.dumps(live), encoding="utf-8")
    return hist


def _run(tmp_path: Path, day: str, finals_by_day: dict, *, summaries: dict | None = None) -> tuple[dict, dict]:
    """Settle `day`. A day missing from `finals_by_day` answers 403, as the real outage did."""
    module = _module()

    def _finals(sport, d):
        key = d.isoformat()
        if key not in finals_by_day:
            raise urllib.error.HTTPError("https://site.api.espn.com/", 403, "Forbidden", None, None)
        return finals_by_day[key]

    module.finals = _finals
    module.match_summary = lambda sport, gid: (summaries or {}).get(gid)
    assert module.main(["--data", str(tmp_path), "--sport", SPORT, "--date", day]) == 0
    results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    board = json.loads((tmp_path / "board.json").read_text(encoding="utf-8"))
    return results, board


def _final(home: int, away: int) -> dict:
    return {"home": home, "away": away, "finish": "REG"}


BET_OVER = {"kind": "bet", "market": "total_2_5", "label": "Over 2.5", "price": -110}
LEAN_BTTS = {"kind": "lean", "market": "btts", "label": "Both teams score", "price": 105}


def test_there_is_no_season_record_until_a_day_has_settled(tmp_path) -> None:
    """A fixture kicked off and has no final yet: nothing has been tallied."""
    _write(tmp_path, [_game("g1", DAY1, "ARS", "FUL", pick=BET_OVER)])
    results, board = _run(tmp_path, DAY1, {DAY1: {}})

    assert "seasonRecord" not in results, "a season nobody has tallied was published"
    record = board["record"]
    for key in ("picks", "straightUp", "totals", "leans", "season", "dueList"):
        assert key not in record, f"record.{key} published before any day settled"
    # The keys the board publishes today are kept: the page ignores them, the
    # card's own record still reads them.
    assert record["settled"] == 3 and record["roiPct"] == -12.0


def test_no_board_means_no_season_either(tmp_path) -> None:
    (tmp_path / "history").mkdir()
    module = _module()
    assert module.main(["--data", str(tmp_path), "--sport", SPORT, "--date", DAY1]) == 0
    results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert "seasonRecord" not in results


def test_a_lean_is_graded_but_never_counted_in_picks(tmp_path) -> None:
    """Arsenal 2-1 Fulham: the lean (both score) wins, the best bet (over) wins.
    Chelsea 0-0 Everton: the best bet loses. Picks are the two bets; the lean is apart."""
    _write(tmp_path, [
        _game("g1", DAY1, "ARS", "FUL", pick=LEAN_BTTS),
        _game("g2", DAY1, "CHE", "EVE", pick=BET_OVER),
    ])
    results, board = _run(tmp_path, DAY1, {DAY1: {"g1": _final(2, 1), "g2": _final(0, 0)}})

    assert results["summary"]["picks"] == {"w": 0, "l": 1, "p": 0}
    assert results["summary"]["leans"] == {"w": 1, "l": 0, "p": 0}
    season = results["seasonRecord"]
    assert season["picks"] == {"w": 0, "l": 1, "p": 0}, "a lean was counted as a best bet"
    assert season["leans"] == {"w": 1, "l": 0, "p": 0}
    assert board["record"]["picks"] == {"w": 0, "l": 1, "p": 0}
    assert board["record"]["leans"] == {"w": 1, "l": 0, "p": 0}
    assert season["nights"] == 1 and season["firstDate"] == DAY1 and season["missingNights"] == 0
    assert season["season"] == {"nights": 1, "firstDate": DAY1, "lastDate": DAY1, "missingNights": 0}
    assert board["record"]["season"]["nights"] == 1


def test_a_day_the_settler_skipped_is_in_missing_nights(tmp_path) -> None:
    """DAY1 was never settled and its scoreboard does not answer now either.

    It is left out of every tally and counted, never read as a 0-0 day; the
    next run that can read it settles it and keeps it.
    """
    _write(tmp_path, [
        _game("g1", DAY1, "ARS", "FUL", pick=BET_OVER),
        _game("g2", DAY2, "CHE", "EVE", pick=BET_OVER),
    ])
    results, board = _run(tmp_path, DAY2, {DAY2: {"g2": _final(3, 1)}})

    season = results["seasonRecord"]
    assert season["missingNights"] == 1
    assert season["nights"] == 1 and season["firstDate"] == DAY2
    assert season["picks"] == {"w": 1, "l": 0, "p": 0}
    assert board["record"]["season"]["missingNights"] == 1

    # The next morning DAY1's finals answer: it is settled, counted and kept.
    results, _ = _run(tmp_path, DAY2, {DAY1: {"g1": _final(0, 1)}, DAY2: {"g2": _final(3, 1)}})
    season = results["seasonRecord"]
    assert season["missingNights"] == 0 and season["nights"] == 2
    assert season["picks"] == {"w": 1, "l": 1, "p": 0}
    assert (tmp_path / "history" / "settled" / f"{DAY1}.json").is_file()


def test_a_kept_day_is_read_back_without_fetching_its_finals_again(tmp_path) -> None:
    _write(tmp_path, [
        _game("g1", DAY1, "ARS", "FUL", pick=BET_OVER),
        _game("g2", DAY2, "CHE", "EVE", pick=BET_OVER),
    ])
    _run(tmp_path, DAY2, {DAY1: {"g1": _final(2, 2)}, DAY2: {"g2": _final(1, 0)}})
    # DAY1's scoreboard is gone now; the kept copy still counts.
    results, _ = _run(tmp_path, DAY2, {DAY2: {"g2": _final(1, 0)}})
    season = results["seasonRecord"]
    assert season["missingNights"] == 0 and season["nights"] == 2
    assert season["picks"] == {"w": 1, "l": 1, "p": 0}


def test_the_favoured_side_counts_a_draw_as_a_loss_unless_the_draw_was_favoured(tmp_path) -> None:
    _write(tmp_path, [
        _game("g1", DAY1, "ARS", "FUL", probs=(0.30, 0.40, 0.30), over=0.4),   # draw favoured, 1-1: win
        _game("g2", DAY1, "CHE", "EVE", probs=(0.55, 0.25, 0.20), over=0.6),   # home favoured, 1-1: loss
    ])
    results, board = _run(tmp_path, DAY1, {DAY1: {"g1": _final(1, 1), "g2": _final(1, 1)}})
    assert results["summary"]["straightUp"] == {"w": 1, "l": 1}
    assert results["summary"]["result"] == {"w": 1, "l": 1}, "the key published today is kept"
    assert results["seasonRecord"]["straightUp"] == {"w": 1, "l": 1}
    # Over 2.5 at 0.4 is an under call; two goals each time: g1 under wins, g2 over loses.
    assert results["seasonRecord"]["totals"] == {"w": 1, "l": 1, "p": 0}
    assert board["record"]["totals"] == {"w": 1, "l": 1, "p": 0}


def test_a_fixture_with_no_probabilities_has_no_favoured_side(tmp_path) -> None:
    """An unrated club publishes no projection; that is not a call for the home side."""
    game = _game("g1", DAY1, "ARS", "FUL")
    game["home"].pop("winProb"), game["away"].pop("winProb"), game.pop("drawProb")
    _write(tmp_path, [game])
    results, _ = _run(tmp_path, DAY1, {DAY1: {"g1": _final(1, 0)}})
    assert results["summary"]["straightUp"] == {"w": 0, "l": 0}


def _entry(player, pid, team, market="goals", price=None) -> dict:
    return {"player": player, "playerId": pid, "team": team, "market": market, "line": 0.5,
            "drought": 9, "price": price, "book": "FanDuel" if price else "", "heavyJuice": False, "lastSeason": 12}


def _squad(side: str, players: list[tuple[str, str, int, int, int]]) -> dict:
    return {"homeAway": side, "roster": [
        {"athlete": {"id": pid, "displayName": name},
         "stats": [{"name": "appearances", "value": apps}, {"name": "totalGoals", "value": goals},
                   {"name": "goalAssists", "value": assists}]}
        for name, pid, apps, goals, assists in players
    ]}


def test_the_due_list_is_graded_on_goals_and_assists_and_void_when_he_did_not_play(tmp_path) -> None:
    drought = [
        _entry("Bukayo Saka", "1", "ARS", price=180),               # scored: win, actual 1
        _entry("Martin Odegaard", "2", "ARS", market="assists"),    # played, no assist: loss
        _entry("Raul Jimenez", "3", "FUL"),                         # on the bench: void
        _entry("Emile Smith Rowe", "4", "FUL", market="assists"),   # not in the squad: void
    ]
    _write(tmp_path, [_game("g1", DAY1, "ARS", "FUL", drought=drought)])
    summary = {"rosters": [
        _squad("home", [("Bukayo Saka", "1", 1, 1, 0), ("Martin Odegaard", "2", 1, 0, 0)]),
        _squad("away", [("Raul Jimenez", "3", 0, 0, 0)]),
    ]}
    results, board = _run(tmp_path, DAY1, {DAY1: {"g1": _final(2, 0)}}, summaries={"g1": summary})

    due = results["dueList"]
    by = {r["player"]: r for r in due["rows"]}
    assert (by["Bukayo Saka"]["result"], by["Bukayo Saka"]["actual"]) == ("win", 1)
    assert (by["Martin Odegaard"]["result"], by["Martin Odegaard"]["actual"]) == ("loss", 0)
    assert by["Raul Jimenez"]["result"] == "void" and by["Raul Jimenez"]["actual"] is None
    assert by["Emile Smith Rowe"]["result"] == "void"
    assert by["Bukayo Saka"]["opp"] == "FUL" and by["Raul Jimenez"]["opp"] == "ARS"
    for row in due["rows"]:
        assert {"player", "team", "opp", "market", "line", "drought", "price", "book", "heavyJuice", "actual", "result"} <= set(row)
    assert due["summary"] == {"w": 1, "l": 1, "p": 0}
    # Since 2026-10-31 the Due List is tracked at 0.25u an entry, as the NHL
    # board does (Cooper chose it): Saka's +180 win is staked, Odegaard had
    # no price, so he is graded but not posted.
    assert by["Bukayo Saka"]["units"] == 0.45 and by["Martin Odegaard"]["units"] is None
    assert board["record"]["dueList"] == {"w": 1, "l": 1, "p": 0, "nights": 1,
                                          "stake": 0.25, "units": 0.45, "staked": 1, "returnPct": 180.0}
    assert due["season"]["byMarket"] == {"goals": {"w": 1, "l": 0}, "assists": {"w": 0, "l": 1}}
    # Never in the picks.
    assert results["summary"]["picks"] == {"w": 0, "l": 0, "p": 0}


def test_a_due_list_entry_with_no_squads_is_ungraded_not_void(tmp_path) -> None:
    """The summary did not answer: that says nothing about whether he played."""
    _write(tmp_path, [_game("g1", DAY1, "ARS", "FUL", drought=[_entry("Bukayo Saka", "1", "ARS")])])
    results, board = _run(tmp_path, DAY1, {DAY1: {"g1": _final(2, 0)}}, summaries={})
    (row,) = results["dueList"]["rows"]
    assert row["result"] is None and row["actual"] is None
    assert "summary" not in results["dueList"]
    assert "dueList" not in board["record"], "a Due List tally nobody made was published"


def test_a_board_without_the_list_publishes_no_due_list(tmp_path) -> None:
    _write(tmp_path, [_game("g1", DAY1, "ARS", "FUL", pick=BET_OVER)])
    results, board = _run(tmp_path, DAY1, {DAY1: {"g1": _final(2, 1)}})
    assert "dueList" not in results and "dueList" not in board["record"]
