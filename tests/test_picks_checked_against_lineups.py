"""The card's picks are checked against the confirmed lineups before kick-off.

ESPN's match summary carries each side's starting eleven and bench once the
clubs name them, about an hour before kick-off. A player prop on a player who
is not starting is withdrawn from the board and named on the check; a team
pick on a side that made four or more changes from its last league eleven is
named for a second look. No credits are spent: ESPN is keyless.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from epl_betting_lab.reports import lineup_check
from epl_betting_lab.reports.lineup_check import (
    BENCH,
    NOT_IN_SQUAD,
    NOT_OUT,
    STARTING,
    build_lineup_check,
    lineups_from_summary,
    render,
    save_lineup_check,
)

NOW = datetime(2026, 10, 31, 11, 50, tzinfo=timezone.utc)
KICKOFF = "2026-10-31T12:30:00Z"

ELEVEN = ["Robert Sánchez", "Reece James", "Wesley Fofana", "Levi Colwill", "Marc Cucurella",
          "Moisés Caicedo", "Enzo Fernández", "Cole Palmer", "Pedro Neto", "Noni Madueke",
          "Nicolas Jackson"]


def _roster(team: str, starters: list[str], bench: list[str]) -> dict:
    return {"team": {"displayName": team}, "roster": [
        *({"starter": True, "athlete": {"displayName": n}} for n in starters),
        *({"starter": False, "athlete": {"displayName": n}} for n in bench),
    ]}


def _event(event_id: str, home: str, away: str, when: str, completed: bool = False) -> dict:
    return {"id": event_id, "date": when, "status": {"type": {"completed": completed}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "team": {"displayName": home}},
                {"homeAway": "away", "team": {"displayName": away}}]}]}


TODAY = {"events": [_event("1", "Chelsea", "Manchester United", KICKOFF)]}
LAST_WEEK = {"events": [_event("0", "Chelsea", "Everton", "2026-10-24T14:00Z", completed=True)]}
UNITED = ["United " + str(i) for i in range(11)]
SUMMARY = {"rosters": [
    _roster("Chelsea", ["Filip Jørgensen", "Josh Acheampong", "Tosin Adarabioyo", "Benoît Badiashile",
                        "Malo Gusto", "Roméo Lavia", "Kiernan Dewsbury-Hall", "Tyrique George",
                        "Pedro Neto", "Noni Madueke", "Nicolas Jackson"],
            ["Cole Palmer", "Enzo Fernández"]),
    _roster("Manchester United", UNITED, []),
]}
LAST_SUMMARY = {"rosters": [_roster("Chelsea", ELEVEN, []), _roster("Everton", ["E"] * 11, [])]}


def _fetch(url: str) -> dict:
    if "summary?event=1" in url:
        return SUMMARY
    if "summary?event=0" in url:
        return LAST_SUMMARY
    if "dates=20261031" in url:
        return TODAY
    if "dates=20261024" in url:
        return LAST_WEEK
    return {"events": []}


def _prop(player: str, team: str = "Chelsea") -> dict:
    return {"player": player, "team": team, "home_team": "Chelsea", "away_team": "Man United",
            "market": "player_shots_on_target", "selection": "Over@0.5", "kickoff_time": KICKOFF}


TEAM_PICK = {"home_team": "Chelsea", "away_team": "Man United", "market": "1x2",
             "selection": "home", "kickoff_time": KICKOFF}


def _check(props=(), teams=()):
    return build_lineup_check(list(props), list(teams), now=NOW, fetch=_fetch)


def test_the_eleven_and_bench_are_read_off_the_summary() -> None:
    lineups = lineups_from_summary(SUMMARY)
    assert len(lineups["Chelsea"].starters) == 11
    assert "Cole Palmer" in lineups["Chelsea"].bench
    assert lineups_from_summary({"rosters": [{"team": {"displayName": "Chelsea"}, "roster": []}]}) == {}


def test_each_prop_is_starting_benched_or_absent() -> None:
    check = _check([_prop("Pedro Neto"), _prop("Cole Palmer"), _prop("Reece James")])
    states = {p["player"]: p["state"] for p in check.props}
    assert states == {"Pedro Neto": STARTING, "Cole Palmer": BENCH, "Reece James": NOT_IN_SQUAD}
    assert {p["player"] for p in check.withdrawn} == {"Cole Palmer", "Reece James"}


def test_a_book_spelling_without_accents_still_matches() -> None:
    (row,) = _check([_prop("Enzo Fernandez")]).props
    assert row["state"] == BENCH


def test_before_the_teams_are_named_nothing_is_withdrawn() -> None:
    def early(url: str) -> dict:
        return {"rosters": []} if "summary" in url else _fetch(url)

    check = build_lineup_check([_prop("Cole Palmer")], [], now=NOW, fetch=early)
    assert check.props[0]["state"] == NOT_OUT and not check.withdrawn


def test_a_heavily_rotated_side_is_named_on_a_team_pick() -> None:
    check = _check(teams=[TEAM_PICK])
    (row,) = check.rotated
    assert row["rotated_team"] == "Chelsea" and row["changes"] == 8


def test_picks_outside_the_window_are_left_alone() -> None:
    later = {**_prop("Cole Palmer"), "kickoff_time": "2026-11-01T16:30:00Z"}
    assert _check([later]).props == []


def test_the_check_reads_plainly_and_saves_for_the_board(tmp_path) -> None:
    check = _check([_prop("Cole Palmer"), _prop("Pedro Neto")], [TEAM_PICK])
    text = render(check)
    assert "Do not bet" in text and "Cole Palmer" in text and "8 changes" in text
    paths = save_lineup_check(check, tmp_path)
    saved = json.loads(paths["json"].read_text())
    assert [p["player"] for p in saved["withdrawn"]] == ["Cole Palmer"]


def test_espn_down_is_said_not_hidden() -> None:
    def down(url: str) -> dict:
        raise lineup_check.EspnResultsError("ESPN is down")

    check = build_lineup_check([_prop("Cole Palmer")], [], now=NOW, fetch=down)
    assert "ESPN is down" in render(check) and not check.withdrawn


def test_the_board_drops_a_withdrawn_prop_and_says_why() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "build_board_json", Path(__file__).parents[1] / "web" / "build_board_json.py")
    board = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(board)
    props = {"status": "Props card ready", "picks": [
        {**_prop("Cole Palmer"), "home_team": "Chelsea", "away_team": "Man United", "american_odds": 120},
        {**_prop("Pedro Neto"), "home_team": "Chelsea", "away_team": "Man United", "american_odds": 110},
    ]}
    withdrawn = [{"player": "Cole Palmer", "home_team": "Chelsea", "away_team": "Man United",
                  "market": "player_shots_on_target", "selection": "Over@0.5", "state": BENCH}]
    block = board.props_block(props, {("Chelsea", "Man United"): "g1"}, withdrawn=withdrawn)
    assert [r["player"] for r in block["rows"]] == ["Pedro Neto"]
    assert "Cole Palmer" in block["note"] and "not starting" in block["note"]


def _workflow(name: str) -> dict:
    from pathlib import Path

    import yaml

    path = Path(__file__).parents[1] / ".github" / "workflows" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_the_check_runs_after_each_closing_snapshot_and_spends_nothing() -> None:
    from pathlib import Path

    flow = _workflow("lineup-check.yml")
    trigger = flow[True]  # PyYAML reads the key `on` as True
    assert trigger["workflow_run"]["workflows"] == ["Closing Snapshot"]
    assert "schedule" not in trigger
    assert flow["permissions"] == {"contents": "read", "actions": "read"}
    text = (Path(__file__).parents[1] / ".github" / "workflows" / "lineup-check.yml").read_text()
    assert "ODDS_API" not in text and "secrets." not in text and "git push" not in text
    runs = " ".join(s.get("run", "") for s in flow["jobs"]["check"]["steps"])
    assert "scripts/check_lineups.py" in runs


def test_the_board_rebuilds_after_the_check_and_reads_it() -> None:
    flow = _workflow("publish-board.yml")
    assert "Lineup Check" in flow[True]["workflow_run"]["workflows"]
    steps = flow["jobs"]["publish"]["steps"]
    names = [s["name"] for s in steps]
    read = names.index("Read the latest lineup check")
    assert read < names.index("Build the board")
    assert "--name lineup-check" in steps[read]["run"]
    assert steps[read].get("continue-on-error") is True


def test_the_script_reads_the_props_card_and_the_latest_archived_card(tmp_path) -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "check_lineups", Path(__file__).parents[1] / "scripts" / "check_lineups.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    archive = tmp_path / "archive" / "automated_cards"
    for day, label in (("2026-10-30", "old"), ("2026-10-31", "new")):
        (archive / day / "080000").mkdir(parents=True)
        (archive / day / "080000" / "automated_card.json").write_text(json.dumps({"label": label}))
    assert script.latest_card(archive) == {"label": "new"}
    assert script.latest_card(tmp_path / "absent") == {}
