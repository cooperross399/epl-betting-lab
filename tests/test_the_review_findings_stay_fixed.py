"""The 2026-10-26 review of the EPL pages and their builders found a set of
defects; each is pinned here so it cannot come back.

The builders and the model (this file, first half): the home edge published
on the pages is a deviation, not the multiplier; a postponed fixture is not a
0-0 in the table; Manchester United's fantasy-game spelling reaches the
match context; the availability list is refused when stale or unstamped and
the page says why; the round the list speaks for is the one recorded at the
fetch; an attacker weighs his expected goal involvement and nothing else; no
builder note names a reference site; a pass is not a pick for line movement;
a Due List void is counted apart from a push; a simulated tie is split.

The pages (second half): what the Game, Methods, Record, Tracker and Season
pages were found to do wrong, pinned by reading their source, since the
pages run only in a browser.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.models import match_context as mc
from epl_betting_lab.models.poisson_goals import CARD_RATINGS, PoissonGoalsModel, UnratedTeam
from epl_betting_lab.providers.fpl_players import AVAILABILITY_FIELDS, build_fpl_availability, round_in_progress
from epl_betting_lab.providers.team_names import is_mapped_team_name, normalize_team_name

WEB = PROJECT_ROOT / "web"
REFERENCE_SITES = ("posthockey", "kenpom", "clubelo", "fivethirtyeight", "fbref", "understat", "opta", "sofascore", "whoscored")


def _load(path: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matches(n_rounds: int = 12) -> pd.DataFrame:
    rows = []
    teams = ["Alpha", "Beta", "Gamma", "Delta"]
    day = pd.Timestamp("2026-01-03")
    for r in range(n_rounds):
        for i, h in enumerate(teams):
            for a in teams[i + 1:]:
                home, away = (h, a) if r % 2 == 0 else (a, h)
                hg = 3 if home == "Alpha" else 1
                ag = 0 if away == "Delta" and r >= n_rounds - 3 else 1
                if away == "Alpha":
                    ag, hg = 1, 1
                rows.append({"date": day, "home_team": home, "away_team": away, "home_goals": hg, "away_goals": ag})
                day += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def _lab(tmp_path: Path) -> Path:
    """A lab directory holding only the matches, as a run without the
    expected-goals table or an availability list looks."""
    processed = tmp_path / "lab" / "data" / "processed"
    processed.mkdir(parents=True)
    frame = _matches()
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame.to_csv(processed / "epl_historical_matches.csv", index=False)
    return tmp_path / "lab"


def _availability(path: Path, rows: list[dict], *, retrieved_at: str | None, round_in_progress: bool = False) -> Path:
    frame = pd.DataFrame([
        {**{k: None for k in AVAILABILITY_FIELDS}, "minutes": 900, "status": "a", "position": "FWD",
         "expected_goal_involvements": 1.0, "total_points": 10, "round_in_progress": round_in_progress,
         "retrieved_at": retrieved_at, **row}
        for row in rows
    ], columns=[c for c in AVAILABILITY_FIELDS if retrieved_at is not None or c != "retrieved_at"])
    frame.to_csv(path, index=False)
    return path


NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


# ---------- the home edge is a deviation on every page ----------

def test_the_home_edge_the_pages_read_is_the_deviation_from_one_everywhere() -> None:
    matches = _matches()
    ctx = mc.build_match_context(matches)
    B = _load(WEB / "build_board_json.py", "bbj_edge")
    model = PoissonGoalsModel().fit(matches, config=CARD_RATINGS)
    projector = B.Projector(model, model, UnratedTeam, context=ctx)
    for team in ("Alpha", "Delta"):
        edge = ctx.team(team).home_edge
        assert mc.HOME_EDGE_CLAMP[0] <= edge <= mc.HOME_EDGE_CLAMP[1]
        published = projector.ratings(team)["homeEdge"]
        assert published == pytest.approx(edge - 1.0, abs=0.001), "the board publishes the multiplier minus one"
        assert abs(published) <= mc.HOME_EDGE_CLAMP[1] - 1.0 + 1e-9, "never the multiplier itself (+98%)"
    table = {row["team"]: row for row in ctx.table()}
    assert table["Alpha"]["homeEdge"] == pytest.approx(ctx.team("Alpha").home_edge - 1.0, abs=0.001)
    assert table["Alpha"]["homeEdge"] == projector.ratings("Alpha")["homeEdge"], "ratings.json and games[].ratings agree"


# ---------- a postponed fixture is not a 0-0 ----------

def _espn_event(eid: str, state: str, completed: bool, hs, as_, kickoff: str) -> dict:
    return {
        "id": eid, "date": kickoff,
        "status": {"type": {"state": state, "completed": completed}},
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Arsenal"}, "score": hs, "form": ""},
                {"homeAway": "away", "team": {"displayName": "Fulham"}, "score": as_, "form": ""},
            ],
            "venue": {"fullName": "Emirates Stadium", "address": {"city": "London"}},
            "broadcasts": [],
        }],
    }


def test_a_postponed_fixture_carries_no_score_and_stays_to_be_played(monkeypatch) -> None:
    B = _load(WEB / "build_board_json.py", "bbj_ppd")
    payload = {"events": [
        _espn_event("1", "post", True, "2", "1", "2026-10-03T14:00Z"),
        _espn_event("2", "post", False, "0", "0", "2026-10-10T14:00Z"),   # postponed: ESPN leaves "0" on both sides
        _espn_event("3", "pre", False, "0", "0", "2026-10-17T14:00Z"),
    ]}
    monkeypatch.setattr(B, "fetch_json", lambda url: payload)
    fixtures, failed = B.fetch_fixtures(["202610"])
    assert failed == []
    by_id = {f["id"]: f for f in fixtures}
    assert by_id["1"]["completed"] is True and (by_id["1"]["homeGoals"], by_id["1"]["awayGoals"]) == (2, 1)
    assert by_id["2"]["state"] == "post" and by_id["2"]["completed"] is False
    assert "homeGoals" not in by_id["2"] and "awayGoals" not in by_id["2"], "a postponed fixture has no result"
    assert "homeGoals" not in by_id["3"]
    P = _load(WEB / "build_site_pages.py", "bsp_ppd")
    table, remaining = P.season_table(fixtures, lambda fd: (fd[:3].upper(), {"name": fd}))
    assert table["ARS"]["played"] == 1 and table["FUL"]["played"] == 1, "only the completed match is in the table"
    assert [f["id"] for f in remaining] == ["2", "3"], "the postponed fixture is still to play, and is simulated"
    # A fixture written before `completed` existed, carrying a score, is played
    # (the old files only carried a score on a final).
    legacy = [{"home": {"fd": "Arsenal"}, "away": {"fd": "Fulham"}, "state": "post", "homeGoals": 1, "awayGoals": 1}]
    table, remaining = P.season_table(legacy, lambda fd: (fd[:3].upper(), {"name": fd}))
    assert table["ARS"]["played"] == 1 and remaining == []


# ---------- the fantasy game's spellings reach the context ----------

#: The fantasy game's `teams[].name` for the twenty clubs of 2026-27 (Coventry,
#: Hull and Ipswich came up; Burnley, West Ham and Wolves went down, and are
#: checked apart because the settled record still names them). The first
#: version of this list was 2025-26's, so the three promoted clubs were never
#: run through the mapper.
FPL_SHORT_NAMES = ("Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Chelsea", "Coventry",
                   "Crystal Palace", "Everton", "Fulham", "Hull", "Ipswich", "Leeds", "Liverpool", "Man City",
                   "Man Utd", "Newcastle", "Nott'm Forest", "Sunderland", "Spurs")
RELEGATED_2026 = ("Burnley", "West Ham", "Wolves")


def test_the_club_list_is_this_seasons_twenty() -> None:
    import importlib.util as iu
    spec = iu.spec_from_file_location("board_clubs", WEB / "build_board_json.py")
    board = iu.module_from_spec(spec)
    spec.loader.exec_module(board)
    current = {fd for fd, (_abbr, _short, _c, _ink) in board.TEAMS.items()} - set(normalize_team_name(n) for n in RELEGATED_2026)
    assert len(FPL_SHORT_NAMES) == 20
    assert {normalize_team_name(n) for n in FPL_SHORT_NAMES} == current, "the fantasy spellings cover exactly the board's twenty"


@pytest.mark.parametrize("name", FPL_SHORT_NAMES + RELEGATED_2026)
def test_every_fantasy_game_short_name_maps_to_a_club_the_model_knows(name: str) -> None:
    assert is_mapped_team_name(name), name


def test_manchester_uniteds_short_name_is_manchester_united() -> None:
    assert normalize_team_name("Man Utd") == "Man United"
    assert normalize_team_name("man utd") == "Man United"


# ---------- a stale, unstamped or missing list is refused, and the note says why ----------

def test_a_missing_list_is_the_general_note(tmp_path: Path) -> None:
    frame, note = mc.read_availability(tmp_path / "none.csv", now=NOW)
    assert frame is None and note == mc.NO_LIST_NOTE
    assert mc.read_availability(None, now=NOW) == (None, mc.NO_LIST_NOTE)


def test_a_list_without_a_fetch_time_is_refused_as_of_unknown_age(tmp_path: Path) -> None:
    path = _availability(tmp_path / "fpl_availability.csv", [{"team": "Alpha", "player": "Star"}], retrieved_at=None)
    frame, note = mc.read_availability(path, now=NOW)
    assert frame is None and "no fetch time" in note and "nobody is read as missing" in note
    assert mc.load_availability(path, now=NOW) is None


def test_a_list_older_than_the_bound_is_refused_and_the_note_names_its_age(tmp_path: Path) -> None:
    stamp = (NOW - timedelta(hours=72)).isoformat(timespec="seconds")
    path = _availability(tmp_path / "fpl_availability.csv", [{"team": "Alpha", "player": "Star"}], retrieved_at=stamp)
    frame, note = mc.read_availability(path, now=NOW)
    assert frame is None
    assert "72 hours ago" in note and stamp in note and f"{mc.AVAILABILITY_MAX_AGE_HOURS:.0f}-hour bound" in note
    assert mc.AVAILABILITY_MAX_AGE_HOURS == 48
    # The context carries that reason to the card and the board.
    ctx = mc.build_match_context(_matches(), frame, availability_note=note)
    assert ctx.availability_note == note and ctx.availability_source == ""


def test_a_fresh_stamped_list_is_read_and_the_bound_is_inclusive(tmp_path: Path) -> None:
    fresh = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
    path = _availability(tmp_path / "fpl_availability.csv", [{"team": "Alpha", "player": "Star", "status": "i",
                                                               "chance_next_round": 0}], retrieved_at=fresh)
    frame, note = mc.read_availability(path, now=NOW)
    assert frame is not None and note == "" and len(frame) == 1
    assert mc.availability_stamp(frame) == fresh
    edge = (NOW - timedelta(hours=mc.AVAILABILITY_MAX_AGE_HOURS)).isoformat(timespec="seconds")
    at_bound = _availability(tmp_path / "at_bound.csv", [{"team": "Alpha", "player": "Star"}], retrieved_at=edge)
    assert mc.read_availability(at_bound, now=NOW)[0] is not None, "exactly the bound is still read"
    ctx = mc.build_match_context(_matches(), frame, availability_source=f"availability list, {fresh}")
    assert ctx.team("Alpha").missing == ("Star",) and ctx.availability_note == ""


def test_an_unreadable_or_misshapen_list_is_refused_with_its_own_note(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("a,b\n1,2\n", encoding="utf-8")
    frame, note = mc.read_availability(wrong, now=NOW)
    assert frame is None and "not in the expected shape" in note
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    frame, note = mc.read_availability(empty, now=NOW)
    assert frame is None and "could not be read" in note


# ---------- the round the list speaks for ----------

BOOTSTRAP = {
    "teams": [{"id": 1, "name": "Man Utd"}],
    "element_types": [{"id": 4, "singular_name_short": "FWD"}],
    "events": [{"id": 9, "is_current": True, "is_next": False, "finished": False},
               {"id": 10, "is_current": False, "is_next": True, "finished": False}],
    "elements": [{"id": 10, "first_name": "Bruno", "second_name": "Fernandes", "team": 1, "element_type": 4,
                  "status": "d", "chance_of_playing_this_round": 0, "chance_of_playing_next_round": 100,
                  "news": "Knock - back next week", "minutes": 900, "total_points": 60, "expected_goal_involvements": "5.0"}],
}


def test_the_fetch_records_which_round_the_fixtures_belong_to_and_when_it_ran() -> None:
    assert round_in_progress(BOOTSTRAP) is True, "the current gameweek has passed its deadline and is not finished"
    finished = {**BOOTSTRAP, "events": [{"id": 9, "is_current": True, "finished": True}, {"id": 10, "is_next": True}]}
    assert round_in_progress(finished) is False, "between gameweeks the next round is the one"
    assert round_in_progress({**BOOTSTRAP, "events": []}) is False
    table = build_fpl_availability(BOOTSTRAP, retrieved_at="2026-10-26T12:00:00+00:00")
    row = table.iloc[0]
    # The fantasy game's "Man Utd" is written under the model's own name, so
    # the context finds the club (it did not until the alias existed).
    assert row["team"] == "Man United" and int(row["chance_this_round"]) == 0 and int(row["chance_next_round"]) == 100
    # The columns the context weighs: a wrong key here would make nobody missing without a word.
    assert row["position"] == "FWD" and int(row["minutes"]) == 900 and int(row["total_points"]) == 60
    assert float(row["expected_goal_involvements"]) == 5.0 and row["player"] == "Bruno Fernandes" and row["status"] == "d"
    assert bool(row["round_in_progress"]) is True and row["retrieved_at"] == "2026-10-26T12:00:00+00:00"
    assert list(table.columns) == list(AVAILABILITY_FIELDS)


def test_the_props_card_refresh_writes_a_stamped_list_the_reader_accepts(tmp_path: Path) -> None:
    """`fetch_fpl_player_data` is the availability file's second producer, and
    the props-card refresh runs it after the dedicated fetch; its table used
    to carry no `retrieved_at`, so the public board read an unstamped list."""
    from epl_betting_lab.providers.fpl_players import FPL_AVAILABILITY_FILENAME, fetch_fpl_player_data, fetch_stamp, write_fpl_data

    def requester(url: str):
        if url.endswith("/bootstrap-static/"):
            return BOOTSTRAP
        assert "/element-summary/10/" in url, url
        return {"history": [], "history_past": []}

    result = fetch_fpl_player_data(requester=requester, today=date(2026, 10, 27), workers=1)
    assert result.players_fetched == 1 and not result.errors
    stamp = result.availability["retrieved_at"].iloc[0]
    assert stamp and datetime.fromisoformat(stamp).tzinfo is not None, "stamped, in UTC, by default"
    write_fpl_data(result, tmp_path)
    frame, note = mc.read_availability(tmp_path / FPL_AVAILABILITY_FILENAME, now=datetime.fromisoformat(stamp))
    assert frame is not None and note == "" and list(frame["team"]) == ["Man United"]
    # A given stamp is kept, and the one helper formats every producer's stamp.
    given = fetch_stamp(datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc))
    assert given == "2026-10-27T09:00:00+00:00"
    again = fetch_fpl_player_data(requester=requester, today=date(2026, 10, 27), workers=1, retrieved_at=given)
    assert set(again.availability["retrieved_at"]) == {given}
    assert fetch_stamp(datetime(2026, 10, 27, 9, 0)) == given, "a naive instant is read as UTC"


def test_the_props_card_withholds_on_this_rounds_chance_while_the_round_is_in_progress(tmp_path: Path) -> None:
    """The props card is the list's second reader; it read `chance_next_round`
    whatever the round, so a player out tonight and back next week (0 / 100)
    was priced during a gameweek in progress."""
    from epl_betting_lab.reports.player_props_card import _load_unavailable
    in_progress = tmp_path / "in_progress.csv"
    build_fpl_availability(BOOTSTRAP, retrieved_at="2026-10-26T12:00:00+00:00").to_csv(in_progress, index=False)
    (entry,) = _load_unavailable(in_progress)
    assert entry["player"] == "Bruno Fernandes" and entry["chance"] == "0" and entry["chance_next_round"] == "100"
    between = tmp_path / "between.csv"
    finished = {**BOOTSTRAP, "events": [{"id": 9, "is_current": True, "finished": True}, {"id": 10, "is_next": True}]}
    build_fpl_availability(finished, retrieved_at="2026-10-26T12:00:00+00:00").to_csv(between, index=False)
    assert _load_unavailable(between) == [], "between gameweeks the next round's 100 keeps him priced"
    # A list written before the round columns existed reads as before.
    legacy = tmp_path / "legacy.csv"
    pd.DataFrame([{"player": "Old Row", "team": "Man United", "status": "i", "chance_next_round": 25, "news": "x"}]).to_csv(legacy, index=False)
    (old,) = _load_unavailable(legacy)
    assert old["chance"] == "25" and old["chance_next_round"] == "25"


def test_a_player_out_this_round_but_back_next_is_missing_only_while_this_round_is_in_progress() -> None:
    base = {"team": "Man United", "player": "Bruno Fernandes", "position": "FWD", "status": "d",
            "chance_this_round": 0, "chance_next_round": 100, "minutes": 900, "total_points": 60,
            "expected_goal_involvements": 5.0}
    fit = {"team": "Man United", "player": "Fit", "position": "FWD", "status": "a", "chance_this_round": None,
           "chance_next_round": None, "minutes": 900, "total_points": 40, "expected_goal_involvements": 5.0}
    in_progress = pd.DataFrame([{**base, "round_in_progress": True}, {**fit, "round_in_progress": True}])
    attack, _, missing = mc.availability_factors(in_progress)["Man United"]
    assert missing == ("Bruno Fernandes",) and attack == pytest.approx(max(mc.AVAILABILITY_FLOOR, 1.0 - mc.AVAILABILITY_WEIGHT * 0.5))
    assert attack < 1.0
    between = pd.DataFrame([{**base, "round_in_progress": False}, {**fit, "round_in_progress": False}])
    assert mc.availability_factors(between)["Man United"] == (1.0, 1.0, ()), "the next round's chance is 100"
    # A list written before the column existed reads the next round, as before.
    legacy = pd.DataFrame([{k: v for k, v in base.items() if k != "chance_this_round"},
                           {k: v for k, v in fit.items() if k != "chance_this_round"}])
    assert mc.availability_factors(legacy)["Man United"] == (1.0, 1.0, ())
    # The CSV round-trip spells the flag "True"; it is still read.
    assert mc._round_in_progress(pd.DataFrame([{"round_in_progress": "True"}])) is True
    assert mc._round_in_progress(pd.DataFrame([{"round_in_progress": "False"}])) is False


def test_the_fetch_script_stamps_the_list_and_names_the_round(tmp_path: Path, monkeypatch, capsys) -> None:
    script = _load(PROJECT_ROOT / "scripts" / "fetch_fpl_availability.py", "fetch_fpl_availability_script")
    monkeypatch.setattr(script, "_default_requester", lambda url: BOOTSTRAP)
    assert script.main([str(tmp_path)]) == 0
    written = pd.read_csv(tmp_path / "fpl_availability.csv")
    stamp = mc.availability_stamp(written)
    fetched = datetime.fromisoformat(stamp)
    assert fetched.tzinfo is not None and abs((datetime.now(timezone.utc) - fetched).total_seconds()) < 300
    assert bool(written["round_in_progress"].iloc[0]) is True
    out = capsys.readouterr().out
    assert "this round" in out and stamp in out
    # Read back through the reader it is fresh, so the context sees the missing player.
    frame, note = mc.read_availability(tmp_path / "fpl_availability.csv")
    assert frame is not None and note == ""
    assert mc.availability_factors(frame)["Man United"][2] == ("Bruno Fernandes",)


def test_a_failed_fetch_is_a_warning_and_leaves_the_file(tmp_path: Path, monkeypatch, capsys) -> None:
    script = _load(PROJECT_ROOT / "scripts" / "fetch_fpl_availability.py", "fetch_fpl_availability_script_fail")

    def boom(url):
        raise OSError("timed out")

    monkeypatch.setattr(script, "_default_requester", boom)
    before = _availability(tmp_path / "fpl_availability.csv", [{"team": "Alpha", "player": "Star"}], retrieved_at="2026-10-20T00:00:00+00:00")
    text = before.read_text(encoding="utf-8")
    assert script.main([str(tmp_path)]) == 0
    assert before.read_text(encoding="utf-8") == text
    out = capsys.readouterr().out
    assert "::warning::" in out and "timed out" in out and "refused once it is older" in out


# ---------- an attacker weighs his expected goal involvement, nothing else ----------

def test_an_attacker_with_no_involvement_weighs_the_floor_not_his_points() -> None:
    squad = pd.DataFrame([
        {"team": "Alpha", "player": "Star", "position": "FWD", "status": "a", "chance_next_round": None, "minutes": 900, "total_points": 60, "expected_goal_involvements": 8.0},
        {"team": "Alpha", "player": "Holder", "position": "MID", "status": "i", "chance_next_round": 0, "minutes": 900, "total_points": 60, "expected_goal_involvements": 0.0},
    ])
    attack, conceded, missing = mc.availability_factors(squad)["Alpha"]
    assert missing == ("Holder",)
    share = mc.ATTACK_WEIGHT_FLOOR / (8.0 + mc.ATTACK_WEIGHT_FLOOR)
    assert attack == pytest.approx(1.0 - mc.AVAILABILITY_WEIGHT * share), "60 points never entered the weight"
    assert conceded == 1.0
    assert 0 < mc.ATTACK_WEIGHT_FLOOR < 0.1


# ---------- no builder note names a reference site, and the feed says whether a list was read ----------

def test_the_model_notes_and_the_ratings_feed_name_no_reference_site_and_say_whether_a_list_was_read(tmp_path: Path) -> None:
    lab = _lab(tmp_path)
    B = _load(WEB / "build_board_json.py", "bbj_notes")
    project, note = B.load_model(lab)
    assert project is not None
    lowered = note.lower()
    assert "expected-goals table" in note and "fell back to goals" in note
    assert mc.NO_LIST_NOTE in note and "full strength" in note
    for site in REFERENCE_SITES:
        assert site not in lowered, (site, note)
    feed = B.ratings_feed(lab, "2026-10-26T12:00:00Z")
    assert feed["availabilityListed"] is False and feed["availabilitySource"] is None
    assert feed["note"] == note and feed["teams"] and all("homeEdge" in t for t in feed["teams"])
    assert all(abs(t["homeEdge"]) <= mc.HOME_EDGE_CLAMP[1] - 1.0 + 1e-9 for t in feed["teams"])
    P = _load(WEB / "build_site_pages.py", "bsp_notes")
    season_src = (WEB / "build_site_pages.py").read_text(encoding="utf-8").lower()
    board_src = (WEB / "build_board_json.py").read_text(encoding="utf-8")
    for site in REFERENCE_SITES:
        assert site not in season_src, site
    # The file name the loader reads is not a page note; the notes it writes are.
    assert "Understat xG was not restored" not in board_src and "understat_team_xg.csv" in board_src
    assert P is not None
    # With a fresh, stamped list the feed says so and names the list with its fetch time.
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _availability(lab / "data" / "processed" / "fpl_availability.csv",
                  [{"team": "Alpha", "player": "Star", "status": "i", "chance_next_round": 0}], retrieved_at=stamp)
    listed = B.ratings_feed(lab, "2026-10-26T12:00:00Z")
    assert listed["availabilityListed"] is True and listed["availabilitySource"] == f"availability list, {stamp}"
    assert "full strength" not in (listed["note"] or "")
    assert next(t for t in listed["teams"] if t["name"] == "Alpha")["missing"] == ["Star"]
    # The same list three days old is refused, with the age on the page.
    old = (datetime.now(timezone.utc) - timedelta(hours=80)).isoformat(timespec="seconds")
    _availability(lab / "data" / "processed" / "fpl_availability.csv",
                  [{"team": "Alpha", "player": "Star", "status": "i", "chance_next_round": 0}], retrieved_at=old)
    stale = B.ratings_feed(lab, "2026-10-26T12:00:00Z")
    assert stale["availabilityListed"] is False and "80 hours ago" in stale["note"] and "full strength" in stale["note"]
    assert next(t for t in stale["teams"] if t["name"] == "Alpha")["missing"] == []


def test_the_card_reads_the_list_through_the_same_reader_and_carries_its_note() -> None:
    src = (PROJECT_ROOT / "src" / "epl_betting_lab" / "dashboard_actions.py").read_text(encoding="utf-8")
    assert "read_availability(availability_file)" in src and "availability_note=availability_note" in src
    assert "load_availability(" not in src
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml").read_text(encoding="utf-8")
    assert "the card's\n        # own markdown does not yet" in workflow, "the comment states what the card does not print"


# ---------- the record: a pass is not a pick, a void is not a push ----------

def _night(day: str, *, pick=None, ml=None, due=None) -> dict:
    entry = {"home": 2, "away": 0, "finish": "FT", "pickResult": pick["result"] if pick else None,
             "homeAbbr": "ARS", "awayAbbr": "FUL", "kickoff": f"{day}T14:00:00Z",
             "probs": [0.55, 0.25, 0.20], "market": [0.52, 0.26, 0.22], "overProb": 0.58, "bttsProb": 0.55}
    if pick:
        entry["pick"] = pick
    if ml:
        entry["mlHome"] = ml
    night = {"games": 1, "summary": {}, "graded": {"1": entry}, "bets": []}
    if due:
        night["dueList"] = due
    return night


def _write_nights(tmp_path: Path, nights: dict[str, dict]) -> Path:
    hist = tmp_path / "history"
    (hist / "settled").mkdir(parents=True, exist_ok=True)
    for day, night in nights.items():
        (hist / "settled" / f"{day}.json").write_text(json.dumps(night), encoding="utf-8")
    return hist


def test_line_movement_counts_best_bets_and_leans_and_never_a_pass(tmp_path: Path) -> None:
    P = _load(WEB / "build_site_pages.py", "bsp_movement")
    base = {"market": "1x2", "label": "Arsenal to win", "side": "home", "line": None, "price": -120, "result": "win"}
    hist = _write_nights(tmp_path, {
        "2026-10-17": _night("2026-10-17", pick={**base, "kind": "pass"}, ml=[-110, -125]),
    })
    assert P.track_record(hist, "2026-10-20T09:00:00Z")["movement"] == {"toward": 0, "against": 0, "flat": 0, "picks": 0}
    hist = _write_nights(tmp_path, {
        "2026-10-17": _night("2026-10-17", pick={**base, "kind": "lean"}, ml=[-110, -125]),
        "2026-10-18": _night("2026-10-18", pick={**base, "kind": "bet", "units": 0.5}, ml=[-110, -100]),
        "2026-10-19": _night("2026-10-19", pick=base, ml=[-110, -110]),  # frozen before `kind`: a best bet
    })
    assert P.track_record(hist, "2026-10-20T09:00:00Z")["movement"] == {"toward": 1, "against": 1, "flat": 1, "picks": 3}


def test_a_due_list_void_is_counted_apart_from_the_record_and_a_push(tmp_path: Path) -> None:
    S = _load(WEB / "settle_results.py", "settle_void")
    rows = [{"result": "win", "market": "goals"}, {"result": "loss", "market": "goals"}, {"result": "push", "market": "goals"},
            {"result": "void", "market": "goals"}, {"result": "void", "market": "goals"}, {"result": None, "market": "goals"}, "junk"]
    tallies = S.due_tallies(rows)
    assert (tallies["w"], tallies["l"], tallies["p"], tallies["void"], tallies["pending"]) == (1, 1, 1, 2, 1)
    assert tallies["byMarket"]["goals"] == {"w": 1, "l": 1}
    P = _load(WEB / "build_site_pages.py", "bsp_void")
    hist = _write_nights(tmp_path, {"2026-10-17": _night("2026-10-17", due={"w": 1, "l": 1, "p": 1, "void": 2})})
    assert P.track_record(hist, "2026-10-20T09:00:00Z")["dueList"] == {"entries": 2, "hitRate": 0.5, "voids": 2}
    # A night settled before `void` was written reads as no voids, never as its pushes.
    hist = _write_nights(tmp_path, {"2026-10-17": _night("2026-10-17", due={"w": 1, "l": 1, "p": 3})})
    assert P.track_record(hist, "2026-10-20T09:00:00Z")["dueList"]["voids"] == 0
    src = (WEB / "settle_results.py").read_text(encoding="utf-8")
    assert '"void": 0, "nights": 0' in src and 'for k in ("w", "l", "p", "void")' in src, "season_record sums voids too"
    # And behaviourally, through season_record itself: a kept night carrying
    # two voids (and `bets`, so it is not settled again) sums to two voids in
    # the season's Due List, beside its wins, losses and pushes.
    kept = _write_nights(tmp_path / "season", {
        "2026-10-17": _night("2026-10-17", due={"w": 1, "l": 1, "p": 1, "void": 2}),
        "2026-10-18": _night("2026-10-18", due={"w": 2, "l": 0, "p": 0, "void": 1}),
    })
    boards = [{"games": [{"id": "1", "kickoff": "2026-10-17T14:00:00Z"}, {"id": "2", "kickoff": "2026-10-18T14:00:00Z"}]}]
    season = S.season_record("epl", date(2026, 10, 27), kept, boards, None, False)
    assert (season["dueList"]["w"], season["dueList"]["l"], season["dueList"]["p"], season["dueList"]["void"]) == (3, 1, 1, 3)
    assert season["dueList"]["nights"] == 2 and season["nights"] == 2


# ---------- a simulated tie is split ----------

def _tied_table() -> tuple[dict, list[dict]]:
    """Six clubs. Able and Baker are level on points and goal difference and
    Able has scored one more goal, so Able is first in every simulation;
    Charlie is third on points; Easy and Fox play the one remaining fixture,
    which the model cannot price and so is 1-1 every time, leaving them level
    on everything; Dog is last."""
    def row(name, pts, gf, ga):
        return {"abbr": name[:3].upper(), "name": name, "fd": name, "played": 1, "won": 0, "drawn": 0, "lost": 0,
                "gf": gf, "ga": ga, "gd": gf - ga, "points": pts}
    table = {r["abbr"]: r for r in (row("Able", 3, 1, 1), row("Baker", 3, 0, 0), row("Charlie", 2, 0, 0),
                                    row("Dog", 0, 0, 0), row("Easy", 0, 0, 0), row("Fox", 0, 0, 0))}
    remaining = [{"home": {"fd": "Easy"}, "away": {"fd": "Fox"}, "_home_abbr": "EAS", "_away_abbr": "FOX"}]
    return table, remaining


@pytest.mark.parametrize("numpy_available", [True, False])
def test_clubs_level_on_everything_split_the_finish_and_nothing_else_moves(monkeypatch, numpy_available: bool) -> None:
    P = _load(WEB / "build_site_pages.py", f"bsp_tie_{numpy_available}")
    if not numpy_available:
        monkeypatch.setitem(sys.modules, "numpy", None)
    table, remaining = _tied_table()
    sim = P.simulate_season(table, remaining, lambda h, a: None, sims=2000, seed=7)
    assert sim["unpriced"] == 1
    teams = sim["teams"]
    # Easy and Fox finish fourth or fifth, and which is which is a coin flip
    # each simulation rather than always the one named first.
    assert teams["EAS"]["top4"] == pytest.approx(0.5, abs=0.06)
    assert teams["FOX"]["top4"] == pytest.approx(0.5, abs=0.06)
    assert teams["EAS"]["top4"] + teams["FOX"]["top4"] == pytest.approx(1.0, abs=1e-6)
    # Goals scored still separate Able from Baker, and points separate the rest: no jitter crosses a real gap.
    assert teams["ABL"]["title"] == 1.0 and teams["BAK"]["title"] == 0.0
    assert teams["CHA"]["top4"] == 1.0 and teams["CHA"]["relegation"] == 0.0
    assert teams["DOG"]["relegation"] == 1.0 and teams["EAS"]["relegation"] == 1.0 and teams["FOX"]["relegation"] == 1.0


# ---------- the record settles the day the game was played ----------

def test_a_graded_file_is_written_per_kickoff_day_so_a_multi_day_board_has_each_days_finals(tmp_path: Path) -> None:
    S = _load(WEB / "settle_results.py", "settle_days")
    hist = tmp_path / "history"
    for day, gid in ((date(2026, 10, 17), "401"), (date(2026, 10, 18), "402")):
        night = S.night_record({"games": [{}], "summary": {}, "graded": {gid: {"home": 1, "away": 0, "finish": "FT", "pickResult": "win", "probs": [0.5, 0.3, 0.2]}}, "bets": []})
        S.write_graded(hist, day, night)
    assert set(json.loads((hist / S.GRADED_DIR / "2026-10-17.json").read_text(encoding="utf-8"))) == {"401"}
    assert set(json.loads((hist / S.GRADED_DIR / "2026-10-18.json").read_text(encoding="utf-8"))) == {"402"}


def test_a_resettlement_that_grades_less_than_the_kept_night_does_not_replace_it(tmp_path: Path, monkeypatch) -> None:
    S = _load(WEB / "settle_results.py", "settle_stale")
    hist = tmp_path / "history"
    (hist / S.SETTLED_DIR).mkdir(parents=True)
    kept = {"resultsDate": "2026-10-17", "games": 1, "summary": {}, "dueList": {"w": 1, "l": 0, "p": 0},
            "graded": {"401": {"home": 2, "away": 0, "finish": "FT", "pickResult": "win", "probs": [0.5, 0.3, 0.2]}}}
    path = hist / S.SETTLED_DIR / "2026-10-17.json"
    path.write_text(json.dumps(kept), encoding="utf-8")  # kept before `bets` existed, so it is settled again
    boards = [{"games": [{"id": "401", "kickoff": "2026-10-17T14:00:00Z", "home": {"abbr": "ARS"}, "away": {"abbr": "FUL"}}]}]
    # The scoreboard answers, with nothing final for a match played ten days ago.
    monkeypatch.setattr(S, "settle_day", lambda *a, **k: ({"games": [], "summary": {}, "graded": {}, "bets": []}, False))
    record = S.season_record("epl", date(2026, 10, 27), hist, boards, None, False)
    assert json.loads(path.read_text(encoding="utf-8"))["graded"] == kept["graded"], "the kept night stands"
    assert record["nights"] == 1 and record["dueList"]["w"] == 1
    # One that grades as much replaces it, and the file gains the pages' rows.
    fresh_graded = {"401": {"home": 2, "away": 0, "finish": "FT", "pickResult": "win", "probs": [0.5, 0.3, 0.2]}}
    monkeypatch.setattr(S, "settle_day", lambda *a, **k: ({"games": [{}], "summary": {}, "graded": fresh_graded, "bets": [{"units": 0.5}]}, False))
    S.season_record("epl", date(2026, 10, 27), hist, boards, None, False)
    assert json.loads(path.read_text(encoding="utf-8"))["bets"] == [{"units": 0.5}]
    assert S._games_settled({"games": 3}) == 3 and S._games_settled({"games": [{}, {}]}) == 2 and S._games_settled({"graded": {"1": {}}, "games": 0}) == 1


def test_the_home_edge_layer_moves_the_home_side_the_way_its_own_edge_says() -> None:
    """The layers are asserted against the model, not only against `factors()`:
    Alpha wins big at home, so its home-edge layer raises the home win chance,
    and with the sides swapped Delta's own (smaller) edge is what applies."""
    matches = _matches()
    model = PoissonGoalsModel().fit(matches)
    ctx = mc.build_match_context(matches, parts=("home_edge",))
    assert ctx.team("Alpha").home_edge > ctx.team("Delta").home_edge

    def layers(home, away):
        xh, xa = model.expected_goals(home, away)
        return ctx.layers(home, away, xh, xa, lambda h, a: model.probabilities_from_xg(home, away, h, a))

    alpha_home = layers("Alpha", "Delta")
    step = {row["key"]: row for row in alpha_home}
    assert step["home_edge"]["homeWin"] > step["strength"]["homeWin"], "Alpha's edge above the league's lifts Alpha at home"
    assert step["home_edge"]["delta"] == pytest.approx(step["home_edge"]["homeWin"] - step["strength"]["homeWin"], abs=1e-9)
    delta_home = {row["key"]: row for row in layers("Delta", "Alpha")}
    lift_alpha = step["home_edge"]["homeWin"] - step["strength"]["homeWin"]
    lift_delta = delta_home["home_edge"]["homeWin"] - delta_home["strength"]["homeWin"]
    assert lift_delta < lift_alpha, "swapping the sides applies the other club's edge, not the same one"


# ---------- the pages, pinned by their source ----------

def _page(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def _node(script: str) -> object:
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, timeout=60).stdout
    return json.loads(out.strip().splitlines()[-1])


def test_the_game_page_reads_each_kickoff_days_finals_and_defaults_an_old_picks_kind() -> None:
    src = _page("Game.dc.html")
    assert "history/graded/${day}.json" in src and 'String(x.kickoff || "").slice(0, 10)' in src
    assert "graded/${archived.date}.json" not in src, "the board's date alone misses a Sunday final on a Saturday board"
    lines = re.search(r"(const p0 = g\.pick[^\n]*\n[^\n]*const p = p0[^\n]*;)", src).group(1)
    kinds = _node("const run = (g) => { " + lines + " return p.kind; };"
                  'console.log(JSON.stringify([run({pick: {label: "Arsenal to win", price: -120}}), run({pick: {kind: "pass", label: "x"}}),'
                  ' run({pick: {kind: "lean", label: "y"}}), run({}), run({pick: {kind: "bet", label: "z"}})]));')
    assert kinds == ["bet", "none", "lean", "none", "bet"], "a pick frozen before `kind` existed was a best bet; a pass is no pick"
    assert 'g.tv && g.tv !== "—"' in src, "the producer's dash placeholder is not a broadcaster"


def test_the_methods_page_states_the_bars_the_card_uses() -> None:
    from epl_betting_lab.config import MIN_EDGE
    from epl_betting_lab.reports.player_props_card import PROPS_EDGE_THRESHOLD
    src = _page("Methods.dc.html")
    team = re.search(r"a team-market pick needs ([\d.]+) points", src)
    prop = re.search(r"a player prop needs (\d+)\.", src)
    assert team and float(team.group(1)) == pytest.approx(MIN_EDGE * 100)
    assert prop and int(prop.group(1)) == round(PROPS_EDGE_THRESHOLD * 100)


def test_the_record_page_colours_the_predicted_rate_and_tells_unreachable_from_empty() -> None:
    src = _page("Record.dc.html")
    assert "actualColor: b.predicted >= b.interval[0] && b.predicted <= b.interval[1]" in src
    assert "actualColor: b.actual >= b.interval[0]" not in src, "the observed rate is always inside its own interval"
    assert '{{ emptyTitle }}' in src and '{{ emptyNote }}' in src
    assert 'emptyTitle: "Record unreachable"' in src and 'emptyTitle: "No matchday settled yet"' in src
    tracker = _page("Tracker.dc.html")
    assert '{{ emptyTitle }}' in tracker and 'emptyTitle: "Results unreachable"' in tracker and 'emptyTitle: "No bet has been graded yet"' in tracker


def test_the_tracker_page_guards_missing_prices_and_units_and_labels_the_axis_short() -> None:
    src = _page("Tracker.dc.html")
    band = re.search(r"const band = (\(p\) => \(.*?\));\n", src).group(1)
    bands = _node(f"const band = {band}; console.log(JSON.stringify([band(null), band(undefined), band(NaN), band(-150), band(120), band(-250), band(300)]));")
    assert bands == [None, None, None, "−199 to −111", "+111 to +199", "−200 and shorter", "+200 and longer"]
    assert "rows.filter((r) => band(r.price) !== null)" in src, "a bet with no price is in no band"
    assert 'numeric(r.price) ? F.fmtOdds(r.price) : "—"' in src and 'numeric(r.units) ? u2(r.units) : "—"' in src
    assert "F.fmtDateOnly(dt).replace" not in src
    short = re.search(r"const shortDay = (\(dt\) => [^\n]*?);\n", src).group(1)
    label = _node(f'const shortDay = {short}; console.log(JSON.stringify(shortDay("2026-10-17")));')
    assert "17" in label and len(label) <= 8, label


def test_the_season_sort_cycles_natural_then_reversed_then_off() -> None:
    src = _page("Season.dc.html")
    body = re.search(r"sortBy\(k\) \{(.*?)\n  \}", src, re.S).group(1)
    natural = re.search(r"const natural = (.*?);\n", body).group(1)
    reducer = re.search(r"this\.setState\((\(s\) => \(.*\))\);", body).group(1)
    script = (f"const run = (k, clicks) => {{ let s = {{ sortKey: '', dir: 1 }}; const out = []; for (let i = 0; i < clicks; i++) "
              f"{{ const natural = {natural}; const f = {reducer}; s = {{ ...s, ...f(s) }}; out.push([s.sortKey, s.dir]); }} return out; }};"
              'console.log(JSON.stringify({ points: run("points", 4), name: run("name", 4) }));')
    cycles = _node(script)
    assert cycles["points"] == [["points", -1], ["points", 1], ["", -1], ["points", -1]], "descending-first columns reverse before they switch off"
    assert cycles["name"] == [["name", 1], ["name", -1], ["", 1], ["name", 1]]
