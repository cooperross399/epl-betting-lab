"""The EPL site carries every page the NHL site does, built from feeds its
own builders write, and the card prices the match context those pages show.

Five pages beside the shared four: Season, Record (Track record), Tracker
(All results), Methods and Game. Each is an EPL page (its theme flag, its
own data) that loads the shared scripts by the names `web/hash_assets.py`
rewrites, and none names a reference site: the model is described in plain
English on the page, however it was arrived at.

The feeds: `web/build_site_pages.py` writes record.json, tracker.json and
season.json after settlement, from the `graded` and `bets` each settled night
now keeps (`web/settle_results.night_record`), and `web/build_board_json.py`
writes ratings.json from the same fit as the board. The publish workflow runs
the builder after settlement and tells the shared tab strip which pages this
site publishes.

The context (`models/match_context.py`): home edge, last five and who is
missing, each a multiplier on the expected goals and nothing else, so every
market on a fixture moves together; `MatchContext.layers` ends exactly at
the card's number, which is what the Game page's step table relies on.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.models import match_context as mc
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel

WEB = PROJECT_ROOT / "web"
SAMPLE = WEB / "data" / "sample"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-board.yml"

PAGES = {
    "Season.dc.html": "season.json",
    "Record.dc.html": "record.json",
    "Tracker.dc.html": "tracker.json",
    "Methods.dc.html": "ratings.json",
    "Game.dc.html": "board.json",
}
#: The pages the shared tab strip can show, in lib/sports.js's vocabulary.
PAGE_KEYS = ["season", "record", "tracker", "methods", "game"]
#: Reference sites the model was built in the light of. The page explains the
#: model; it does not cite them.
REFERENCE_SITES = ("posthockey", "kenpom", "clubelo", "fivethirtyeight", "538", "fbref", "understat", "opta", "sofascore", "whoscored")


def _load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, WEB / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- the pages ----------

@pytest.mark.parametrize("page", sorted(PAGES))
def test_each_page_is_an_epl_page_that_loads_the_shared_scripts_and_its_own_feed(page: str) -> None:
    text = (WEB / page).read_text(encoding="utf-8")
    assert 'setAttribute("data-sport","epl")' in text, page
    assert 'html[data-sport="epl"]' in text, page
    assert '"./support.js"' in text, page
    assert 'import("./lib/sports.js")' in text, page
    assert f"./data/{PAGES[page]}" in text, (page, PAGES[page])
    # Off the site the page reads a sample, so the preview never shows a live feed as its own.
    assert "./data/sample/" in text, page
    assert "onSite()" in text, page


@pytest.mark.parametrize("page", sorted(PAGES))
def test_no_page_names_a_reference_site(page: str) -> None:
    text = (WEB / page).read_text(encoding="utf-8").lower()
    for site in REFERENCE_SITES:
        assert site not in text, (page, site)


def test_the_tab_strip_links_every_page_from_every_page() -> None:
    for page in PAGES:
        text = (WEB / page).read_text(encoding="utf-8")
        for target in ("Board.dc.html", "Board.dc.html#props", "Results.dc.html", "Season.dc.html", "Record.dc.html", "Tracker.dc.html"):
            assert target in text, (page, target)
        assert "Methods.dc.html" in text, page


def test_the_methods_page_explains_each_context_layer_in_plain_words() -> None:
    text = (WEB / "Methods.dc.html").read_text(encoding="utf-8")
    for entry_id in ("strength", "home-edge", "form", "availability", "proj-goals", "result", "fair", "edge", "bet-lean", "graded"):
        assert f'id: "{entry_id}"' in text, entry_id
    # The honest line every page here carries.
    assert "no market shows a demonstrated edge" in text.lower()


# ---------- the sample feeds the pages preview ----------

def test_the_sample_feeds_exist_and_carry_what_the_pages_read() -> None:
    board = json.loads((SAMPLE / "board_game.json").read_text(encoding="utf-8"))
    ids = {g["id"] for g in board["games"]}
    assert {"401751", "401752", "401753", "401754"} <= ids
    for g in board["games"]:
        assert [f["key"] for f in g["factors"]] == list(mc.LAYER_KEYS), g["id"]
        assert g["factors"][-1]["homeWin"] == pytest.approx(g["home"]["winProb"], abs=0.001), g["id"]
        assert {"attack", "defence", "homeEdge", "formAttack", "formDefence", "attackAvailable", "missing"} <= set(g["ratings"]["home"])
        assert set(g["matchResult"]) == {"home", "draw", "away"}
    record = json.loads((SAMPLE / "record.json").read_text(encoding="utf-8"))
    assert record["nights"] > 0 and len(record["buckets"]) == len(_load("build_site_pages.py", "bsp_sample_check").RECORD_BUCKETS)
    assert {"over25", "btts"} <= set(record["markets"])
    assert record["brier"]["baseline"] == pytest.approx(2 / 3, abs=0.001)
    empty = json.loads((SAMPLE / "record_empty.json").read_text(encoding="utf-8"))
    assert empty["nights"] == 0 and empty["games"] == 0 and empty["brier"] is None
    tracker = json.loads((SAMPLE / "tracker.json").read_text(encoding="utf-8"))
    assert tracker["rows"] and tracker["dueStake"] is None
    assert {r["group"] for r in tracker["rows"]} == {"team", "props"}
    assert json.loads((SAMPLE / "tracker_empty.json").read_text(encoding="utf-8"))["rows"] == []
    season = json.loads((SAMPLE / "season.json").read_text(encoding="utf-8"))
    assert len(season["teams"]) == 20 and season["projected"]
    assert sum(t["title"] for t in season["teams"]) == pytest.approx(1.0, abs=0.01)
    for t in season["teams"]:
        assert t["p10"] <= t["projPoints"] <= t["p90"]
    assert json.loads((SAMPLE / "season_empty.json").read_text(encoding="utf-8"))["teams"] == []
    ratings = json.loads((SAMPLE / "ratings.json").read_text(encoding="utf-8"))
    assert len(ratings["teams"]) == 20 and any(t["missing"] for t in ratings["teams"])
    nolist = json.loads((SAMPLE / "ratings_nolist.json").read_text(encoding="utf-8"))
    assert not any(t["missing"] for t in nolist["teams"]) and nolist["availabilityListed"] is False


# ---------- the workflow ----------

def _build_step() -> str:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in list(spec["jobs"].values())[0]["steps"]:
        if step.get("name") == "Build the board":
            return "\n".join(line for line in step["run"].splitlines() if not line.strip().startswith("#"))
    raise AssertionError("no 'Build the board' step")


def test_the_publish_step_builds_the_feeds_after_settlement_and_lists_the_pages() -> None:
    script = _build_step()
    settle = script.index("web/settle_results.py")
    pages = script.index("web/build_site_pages.py --lab . --out dist/data")
    assert settle < pages, "record.json and tracker.json read the nights settle_results keeps, so the builder runs after it"
    m = re.search(r"printf '(\{.*\})' > dist/site\.json", script)
    assert m, script
    site = json.loads(m.group(1))
    assert site == {"sport": "epl", "pages": PAGE_KEYS}


# ---------- the feeds, through the builders ----------

def _night(day: str, *, probs=(0.55, 0.25, 0.20), final=(2, 0), pick=None, ml=None, bets=None, due=None) -> dict:
    entry = {
        "home": final[0], "away": final[1], "finish": "FT", "pickResult": pick["result"] if pick else None,
        "homeAbbr": "ARS", "awayAbbr": "FUL", "kickoff": f"{day}T14:00:00Z",
        "probs": list(probs), "market": [0.52, 0.26, 0.22], "overProb": 0.58, "bttsProb": 0.55,
    }
    if pick:
        entry["pick"] = pick
    if ml:
        entry["mlHome"] = ml
    night = {"games": 1, "summary": {}, "graded": {"1": entry}, "bets": bets or []}
    if due:
        night["dueList"] = due
    return night


def _write_nights(tmp_path: Path, nights: dict[str, dict]) -> Path:
    hist = tmp_path / "history"
    (hist / "settled").mkdir(parents=True)
    for day, night in nights.items():
        (hist / "settled" / f"{day}.json").write_text(json.dumps(night), encoding="utf-8")
    return hist


def test_record_json_files_the_favourite_by_bucket_and_reads_the_market_from_the_frozen_prices(tmp_path: Path) -> None:
    P = _load("build_site_pages.py", "bsp_record")
    pick = {"kind": "bet", "market": "1x2", "label": "Arsenal to win", "side": "home", "line": None, "price": -120, "units": 0.5, "result": "win"}
    hist = _write_nights(tmp_path, {
        "2026-10-17": _night("2026-10-17", probs=(0.55, 0.25, 0.20), final=(2, 0), pick=pick, ml=[-110, -125]),
        "2026-10-18": _night("2026-10-18", probs=(0.20, 0.25, 0.55), final=(1, 1)),
        "2026-10-19": {"games": 0, "summary": {}},  # a night with nothing graded is not a night
    })
    out = P.track_record(hist, "2026-10-20T09:00:00Z")
    assert out["nights"] == 2 and out["games"] == 2
    filed = {(b["low"], b["high"]): b for b in out["buckets"]}
    assert filed[(0.50, 0.55)]["games"] == 0
    assert filed[(0.55, 0.60)]["games"] == 2 and filed[(0.55, 0.60)]["actual"] == 0.5
    assert filed[(0.55, 0.60)]["interval"][0] < 0.5 < filed[(0.55, 0.60)]["interval"][1]
    assert out["brier"]["games"] == 2 and out["brier"]["baseline"] == P.BRIER_BASELINE
    # The home price shortened from -110 to -125 after a home pick: the market followed.
    assert out["movement"] == {"toward": 1, "against": 0, "flat": 0, "picks": 1}
    assert out["markets"]["over25"]["games"] == 2 and out["markets"]["btts"]["games"] == 2
    assert "dueList" not in out


def test_record_json_counts_the_due_list_as_a_hit_rate_and_never_a_stake(tmp_path: Path) -> None:
    P = _load("build_site_pages.py", "bsp_due")
    # A push (`p`) is graded and is not a void; a void is an entry whose
    # player did not play, which `settle_results.due_tallies` counts apart.
    hist = _write_nights(tmp_path, {"2026-10-17": _night("2026-10-17", due={"w": 3, "l": 1, "p": 1, "void": 2})})
    out = P.track_record(hist, "2026-10-20T09:00:00Z")
    assert out["dueList"] == {"entries": 4, "hitRate": 0.75, "voids": 2}
    assert "units" not in json.dumps(out["dueList"])


def test_tracker_json_sums_every_graded_best_bet_and_nothing_else(tmp_path: Path) -> None:
    P = _load("build_site_pages.py", "bsp_tracker")
    bets = [
        {"date": "2026-10-17", "group": "team", "market": "1x2", "label": "Arsenal to win", "team": "ARS", "teams": ["ARS", "FUL"],
         "side": "home", "line": None, "price": -120, "result": "win", "staked": 0.5, "units": 0.4167, "gameId": "1", "kickoff": "2026-10-17T14:00:00Z"},
        {"date": "2026-10-17", "group": "props", "market": "shots", "propType": "shots", "label": "Bukayo Saka over 2.5", "player": "Bukayo Saka",
         "team": "ARS", "opp": "FUL", "side": "over", "line": 2.5, "price": 120, "result": "loss", "staked": 0.25, "units": -0.25, "gameId": "1"},
        {"date": "2026-10-17", "group": "team", "market": "1x2", "label": "ungraded", "teams": ["ARS", "FUL"], "price": -120, "result": None, "staked": 0.5, "units": None},
        {"date": "2026-10-17", "group": "team", "market": "1x2", "label": "void", "teams": ["ARS", "FUL"], "price": -120, "result": "void", "staked": 0.5, "units": 0},
    ]
    hist = _write_nights(tmp_path, {"2026-10-17": _night("2026-10-17", bets=bets)})
    out = P.tracker(hist, "2026-10-20T09:00:00Z")
    assert out["overall"]["bets"] == 2 and out["overall"]["w"] == 1 and out["overall"]["l"] == 1
    assert out["overall"]["staked"] == 0.75 and out["overall"]["units"] == pytest.approx(0.1667, abs=0.0001)
    assert [g["key"] for g in out["byGroup"]] == ["team", "props"]
    assert {g["label"] for g in out["byTeam"]} == {"ARS", "FUL"}, "a team pick counts under both clubs; the prop under its player's club"
    assert out["byPlayer"][0]["label"] == "Bukayo Saka (ARS)"
    assert {g["label"] for g in out["byPrice"]} == {"−199 to −111", "+111 to +199"}
    assert out["byMonth"][0]["label"] == "October 2026"
    assert out["dueStake"] is None and out["teamPickDefaultUnits"] == 1.0
    assert len(out["rows"]) == 2


def test_an_empty_history_gives_empty_feeds_not_zeros_dressed_as_a_record(tmp_path: Path) -> None:
    P = _load("build_site_pages.py", "bsp_empty")
    hist = tmp_path / "history"
    (hist / "settled").mkdir(parents=True)
    record = P.track_record(hist, "2026-08-01T09:00:00Z")
    assert record["nights"] == 0 and record["brier"] is None and record["markets"] == {}
    assert all(b["games"] == 0 and b["actual"] is None for b in record["buckets"])
    track = P.tracker(hist, "2026-08-01T09:00:00Z")
    assert track["rows"] == [] and track["firstDate"] is None and track["byGroup"] == []


def _fixture(day: str, home: str, away: str, hg=None, ag=None) -> dict:
    f = {"home": {"fd": home}, "away": {"fd": away}, "date": day, "state": "post" if hg is not None else "pre"}
    if hg is not None:
        f.update(homeGoals=hg, awayGoals=ag)
    return f


def test_the_season_table_and_its_projection_add_up(tmp_path: Path) -> None:
    P = _load("build_site_pages.py", "bsp_season")
    names = {"Arsenal": "ARS", "Fulham": "FUL", "Chelsea": "CHE", "Everton": "EVE"}
    entry = lambda fd: (names[fd], {"name": fd})  # noqa: E731
    fixtures = [
        _fixture("2026-08-15", "Arsenal", "Fulham", 2, 0), _fixture("2026-08-15", "Chelsea", "Everton", 1, 1),
        _fixture("2026-08-22", "Fulham", "Chelsea", 0, 3), _fixture("2026-08-22", "Everton", "Arsenal", 1, 1),
        _fixture("2026-08-29", "Arsenal", "Chelsea"), _fixture("2026-08-29", "Everton", "Fulham"),
    ]
    table, remaining = P.season_table(fixtures, entry)
    assert table["ARS"]["points"] == 4 and table["CHE"]["points"] == 4 and table["FUL"]["points"] == 0 and table["EVE"]["points"] == 2
    assert table["CHE"]["gd"] == 3 and P._rank(table)[0] == "CHE", "level on points, goal difference decides"
    assert len(remaining) == 2
    for f in remaining:
        f["_home_abbr"], f["_away_abbr"] = entry(f["home"]["fd"])[0], entry(f["away"]["fd"])[0]
    strong = {"Arsenal": 2.2, "Chelsea": 1.6, "Everton": 1.0, "Fulham": 0.7}
    sim = P.simulate_season(table, remaining, lambda h, a: {"eh": strong[h], "ea": strong[a] * 0.8}, sims=400, seed=1)
    assert sim["simulations"] == 400 and sim["unpriced"] == 0
    teams = sim["teams"]
    assert sum(t["title"] for t in teams.values()) == pytest.approx(1.0, abs=1e-6)
    assert sum(t["relegation"] for t in teams.values()) == pytest.approx(3.0, abs=1e-6), "four clubs, bottom three go down"
    for abbr, t in teams.items():
        assert table[abbr]["points"] <= t["p10"] <= t["projPoints"] <= t["p90"] <= table[abbr]["points"] + 3
    assert teams["ARS"]["title"] + teams["CHE"]["title"] > teams["FUL"]["title"]
    # A club the model cannot price is played as 1-1, counted, never guessed.
    sim2 = P.simulate_season(table, remaining, lambda h, a: None, sims=50)
    assert sim2["unpriced"] == 2 and all(t["projPoints"] == table[a]["points"] + 1 for a, t in sim2["teams"].items())


# ---------- settlement keeps what the pages read ----------

def test_a_settled_night_keeps_graded_and_bets_and_the_graded_file_is_written(tmp_path: Path) -> None:
    S = _load("settle_results.py", "settle_pages")
    graded = {"401": {"home": 2, "away": 1, "finish": "FT", "pickResult": "win", "probs": [0.5, 0.3, 0.2]}}
    bets = [{"date": "2026-10-17", "group": "team", "result": "win", "staked": 0.5, "units": 0.45}]
    night = S.night_record({"games": [{}], "summary": {}, "graded": graded, "bets": bets})
    assert night["graded"] == graded and night["bets"] == bets
    hist = tmp_path / "history"
    S.write_graded(hist, date(2026, 10, 17), night)
    kept = json.loads((hist / S.GRADED_DIR / "2026-10-17.json").read_text(encoding="utf-8"))
    assert kept == {"401": {"home": 2, "away": 1, "finish": "FT", "pickResult": "win"}}, "the Game page reads the final and the grade, not the chances"
    S.write_graded(hist, date(2026, 10, 18), {"games": 0})
    assert not (hist / S.GRADED_DIR / "2026-10-18.json").exists(), "a night with no final writes nothing, so an old file is never emptied"


def test_graded_entry_and_bet_rows_carry_the_frozen_chances_and_the_cards_stake() -> None:
    S = _load("settle_results.py", "settle_rows")
    g = {"id": "401", "kickoff": "2026-10-17T14:00:00Z", "home": {"abbr": "ARS", "winProb": 0.55}, "away": {"abbr": "FUL", "winProb": 0.2},
         "drawProb": 0.25, "matchResult": {"home": -120, "draw": 260, "away": 330}, "total": {"overProb": 0.6}, "btts": {"yesProb": 0.5},
         "pick": {"kind": "bet", "market": "1x2", "label": "Arsenal to win", "side": "home", "line": None, "price": -120, "units": 0.5}}
    lines = {"401": {"ml_home": [{"t": "a", "v": -110}, {"t": "b", "v": -125}]}}
    entry = S.graded_entry(g, 2, 0, "FT", "win", lines)
    assert entry["probs"] == [0.55, 0.25, 0.2] and entry["mlHome"] == [-110, -125]
    assert sum(entry["market"]) == pytest.approx(1.0, abs=0.001) and entry["market"][0] > entry["market"][1] > entry["market"][2]
    assert entry["pick"]["result"] == "win" and entry["overProb"] == 0.6 and entry["bttsProb"] == 0.5
    results_games = [{"id": "401", "home": {"abbr": "ARS"}, "away": {"abbr": "FUL"},
                      "pick": {"kind": "bet", "market": "1x2", "label": "Arsenal to win", "side": "home", "price": -120, "units": 0.5, "result": "win"}},
                     {"id": "402", "home": {"abbr": "CHE"}, "away": {"abbr": "EVE"},
                      "pick": {"kind": "lean", "market": "1x2", "label": "Chelsea to win", "side": "home", "price": -150, "result": "win"}},
                     {"id": "403", "home": {"abbr": "LIV"}, "away": {"abbr": "WOL"},
                      "pick": {"kind": "bet", "market": "1x2", "label": "Liverpool to win", "side": "home", "price": -200, "result": "loss"}}]
    playing = {gid: ({"kickoff": "2026-10-17T14:00:00Z"}, None) for gid in ("401", "402", "403")}
    rows = S.bet_rows(date(2026, 10, 17), results_games, playing, [])
    assert [r["gameId"] for r in rows] == ["401", "403"], "a lean is not a bet"
    assert rows[0]["units"] == pytest.approx(0.4167, abs=0.0001) and rows[0]["team"] == "ARS" and "stakeAssumed" not in rows[0]
    assert rows[1]["staked"] == 1.0 and rows[1]["stakeAssumed"] is True and rows[1]["units"] == -1.0


# ---------- the match context the card prices ----------

def _matches(n_rounds: int = 12) -> pd.DataFrame:
    """A small league where Alpha wins big at home and Delta has just stopped scoring."""
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


def test_the_context_is_a_multiplier_on_expected_goals_and_nothing_else() -> None:
    matches = _matches()
    ctx = mc.build_match_context(matches)
    alpha, delta = ctx.team("Alpha"), ctx.team("Delta")
    assert alpha.home_edge > 1.0 >= delta.home_edge or alpha.home_edge > delta.home_edge
    assert mc.HOME_EDGE_CLAMP[0] <= alpha.home_edge <= mc.HOME_EDGE_CLAMP[1]
    assert delta.attack_form < 1.0, "Delta stopped scoring in its last three"
    assert mc.FORM_CLAMP[0] <= delta.attack_form <= mc.FORM_CLAMP[1]
    assert alpha.attack_available == 1.0 and alpha.missing == (), "no list: nobody is missing"
    assert ctx.availability_note.startswith("No availability list")
    moved = ctx.adjust("Alpha", "Delta", 1.5, 1.0)
    factors = ctx.factors("Alpha", "Delta")
    assert moved.home_xg == pytest.approx(1.5 * factors["home_edge"][0] * factors["form"][0] * factors["availability"][0])
    assert moved.away_xg == pytest.approx(1.0 * factors["home_edge"][1] * factors["form"][1] * factors["availability"][1])
    off = mc.build_match_context(matches, parts=())
    assert off.adjust("Alpha", "Delta", 1.5, 1.0).home_xg == 1.5 and off.factors("Alpha", "Delta") == {}


def test_who_is_missing_comes_off_the_attack_weighted_by_involvement_and_is_floored() -> None:
    squad = pd.DataFrame([
        {"team": "Alpha", "player": "Star", "position": "FWD", "status": "i", "chance_next_round": 0, "minutes": 900, "total_points": 60, "expected_goal_involvements": 8.0},
        {"team": "Alpha", "player": "Mid", "position": "MID", "status": "a", "chance_next_round": None, "minutes": 900, "total_points": 40, "expected_goal_involvements": 2.0},
        {"team": "Alpha", "player": "Wall", "position": "DEF", "status": "d", "chance_next_round": 50, "minutes": 800, "total_points": 30, "expected_goal_involvements": 0.1},
        {"team": "Alpha", "player": "Keeper", "position": "GKP", "status": "a", "chance_next_round": None, "minutes": 900, "total_points": 30, "expected_goal_involvements": 0.0},
        {"team": "Alpha", "player": "Benchwarmer", "position": "FWD", "status": "i", "chance_next_round": 0, "minutes": 40, "total_points": 2, "expected_goal_involvements": 0.3},
        {"team": "Beta", "player": "Fit", "position": "FWD", "status": "a", "chance_next_round": None, "minutes": 900, "total_points": 50, "expected_goal_involvements": 5.0},
    ])
    out = mc.availability_factors(squad)
    attack, conceded, missing = out["Alpha"]
    assert missing == ("Star", "Wall"), "a regular who is out or doubtful; the benchwarmer is not a regular"
    assert attack == pytest.approx(max(mc.AVAILABILITY_FLOOR, 1.0 - mc.AVAILABILITY_WEIGHT * 8.0 / 10.0))
    assert conceded == pytest.approx(1.0 + mc.AVAILABILITY_WEIGHT * (800 * 0.5) / (800 + 900))
    assert out["Beta"] == (1.0, 1.0, ())
    ctx = mc.build_match_context(_matches(), squad, availability_source="test list")
    assert ctx.team("Alpha").missing == ("Star", "Wall") and ctx.availability_source == "test list" and ctx.availability_note == ""


def test_the_layers_end_at_the_cards_number_and_the_card_carries_the_context() -> None:
    matches = _matches()
    model = PoissonGoalsModel().fit(matches)
    ctx = mc.build_match_context(matches)
    xh, xa = model.expected_goals("Alpha", "Delta")
    layers = ctx.layers("Alpha", "Delta", xh, xa, lambda h, a: model.probabilities_from_xg("Alpha", "Delta", h, a))
    assert [row["key"] for row in layers] == list(mc.LAYER_KEYS)
    assert layers[0]["delta"] is None and all(isinstance(row["delta"], float) for row in layers[1:])
    plain = model.match_probabilities("Alpha", "Delta")
    assert layers[0]["homeWin"] == pytest.approx(plain["home_win"], abs=1e-4), "the first layer is the ratings alone"
    fixtures = pd.DataFrame([{"home_team": "Alpha", "away_team": "Delta"}])
    carded = model.project_fixtures(fixtures, context=ctx).iloc[0]
    assert layers[-1]["homeWin"] == pytest.approx(carded["home_win"], abs=1e-4), "the last layer is the card's own number"
    assert carded["home_context"] == pytest.approx(ctx.adjust("Alpha", "Delta", xh, xa).home_factor, abs=1e-4)
    assert carded["home_context"] != 1.0 or carded["away_context"] != 1.0
    unmoved = model.project_fixtures(fixtures).iloc[0]
    assert unmoved["home_win"] == pytest.approx(plain["home_win"]) and "home_context" not in unmoved.index
    # Every market on the fixture moves off one score matrix, truncated at the
    # model's goal ceiling exactly as the plain fit's is: the three sides carry
    # the same mass moved or not, and nothing is renormalised away.
    moved_mass = carded["home_win"] + carded["draw"] + carded["away_win"]
    plain_mass = plain["home_win"] + plain["draw"] + plain["away_win"]
    assert 0.98 < moved_mass <= 1.0 and moved_mass == pytest.approx(plain_mass, abs=0.01)
