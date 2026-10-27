"""Every staked player prop is posted on the public site and tracked there,
the way the NHL site does it.

Cooper, 2026-10-27: "We want all the player props posted and tracked on the
website as well just like the NHL". What this pins, end to end:

(a) `web/build_board_json.props_block` turns the props card's picks, across
    every approved market, into one board row per pick on its own fixture,
    with a note per market that restates the card's measurement (never an
    edge), a note saying how many props the card priced and how many are
    listed, and the players the card withheld as unlikely to play.
(b) Every EPL page (Game, Record, Tracker, Season, Methods) links the board's
    Props tab, as the NHL pages do.
(c) A settled night with graded props lands in results.json (`props.summary`,
    `props.season`), in the tracker rows (group "props", with the player and
    the prop type) and on board.json's `record.props`, which the shared board
    shows as "Props best bets · season".
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PAGES = ("Game.dc.html", "Record.dc.html", "Tracker.dc.html", "Season.dc.html", "Methods.dc.html")


def _load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, WEB / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------- (a) the board ----------

def _pick(**over):
    pick = {
        "date": "2026-10-25", "kickoff_time": "2026-10-25T14:00:00Z",
        "home_team": "Newcastle", "away_team": "Liverpool",
        "market": "player_shots", "player": "Alexander Isak", "team": "Newcastle",
        "selection": "Over@2.5", "model_probability": 0.6, "implied_probability": 0.45,
        "edge": 0.15, "american_odds": 120.0, "book": "FanDuel", "units": 0.1,
    }
    pick.update(over)
    return pick


GAMES = {("Newcastle", "Liverpool"): "g1", ("Arsenal", "Chelsea"): "g2"}

PICKS = [
    _pick(),
    _pick(market="player_shots_on_target", player="Mohamed Salah", team="Liverpool", selection="Over@1.5"),
    _pick(market="player_goal_scorer_anytime", player="Bukayo Saka", team="Arsenal", home_team="Arsenal",
          away_team="Chelsea", selection="Yes", american_odds=210.0),
    _pick(market="player_to_receive_card", player="Moises Caicedo", team="Chelsea", home_team="Arsenal",
          away_team="Chelsea", selection="Yes", american_odds=180.0),
    _pick(market="player_tackles_alternate", player="Bruno Guimaraes", team="Newcastle", selection="Over@2.5"),
    _pick(market="player_goalie_saves_alternate", player="Alisson", team="Liverpool", selection="Over@3.5"),
]

CARD = {
    "status": "Props card ready",
    "note": "The standing measurement demonstrates no edge in these markets.",
    "picks": PICKS,
    "priced": 9,
    "below_bar": 3,
    "withheld_unavailable": [
        {"player": "Cole Palmer", "team": "Chelsea", "status": "i", "chance": "25",
         "chance_next_round": "25", "news": "Groin injury - Expected back 05 Nov"},
        {"player": "Anthony Gordon", "team": "Newcastle", "status": "s", "chance": "0",
         "chance_next_round": "0", "news": "Suspended until 02 Nov"},
        # Withheld on status alone: the list states no chance for him.
        {"player": "Sandro Tonali", "team": "Newcastle", "status": "u", "chance": "",
         "chance_next_round": "", "news": "Unavailable - loan"},
    ],
}


def test_every_pick_across_the_markets_is_a_row_on_its_game_with_a_note_per_market() -> None:
    board = _load("build_board_json.py", "bbj_props_everywhere")
    block = board.props_block(CARD, GAMES)

    assert block["status"] == "ok"
    rows = {(r["player"], r["market"]): r for r in block["rows"]}
    assert set(rows) == {
        ("Alexander Isak", "shots"), ("Mohamed Salah", "shots_on_target"), ("Bukayo Saka", "goals"),
        ("Moises Caicedo", "booked"), ("Bruno Guimaraes", "tackles"), ("Alisson", "goalie_saves"),
    }
    assert rows[("Bukayo Saka", "goals")]["gameId"] == "g2" and rows[("Alisson", "goalie_saves")]["gameId"] == "g1"
    assert rows[("Bukayo Saka", "goals")]["line"] == 0.5 and rows[("Moises Caicedo", "booked")]["side"] == "over"
    for row in block["rows"]:
        assert row["kind"] == "bet" and row["units"] == 0.1, "rows are the card's staked best bets only"
        assert {"gameId", "player", "team", "opp", "market", "side", "line", "price", "book",
                "modelProb", "fairPrice", "edgePct", "kind", "units"} <= set(row)
    # One line per market the board can carry, each the card's own measurement, never an edge.
    assert set(block["marketNotes"]) == set(board.PROP_MARKET_KEYS.values())
    for market in rows.values():
        assert block["marketNotes"][market["market"]].endswith(("no demonstrated edge.", "stays ungraded."))
    for text in block["marketNotes"].values():
        assert "no demonstrated edge" in text
    # The saves line states the grader's own rule (a keeper the summary does
    # not name is ungraded, never void), not a book's.
    saves = block["marketNotes"]["goalie_saves"]
    assert "in the squad who does not come on is void" in saves and "does not name stays ungraded" in saves


def test_only_the_markets_the_committed_backtest_measured_are_called_measured() -> None:
    """The public note may not claim a measurement the lab never made: the
    held-out backtest priced shots on target and the anytime goal only."""
    board = _load("build_board_json.py", "bbj_props_measured")
    backtest = json.loads((ROOT / "data" / "outputs" / "player_props_backtest.json").read_text(encoding="utf-8"))
    measured = {board.PROP_MARKET_KEYS[m] for m in backtest["per_market"]}
    assert measured == {"shots_on_target", "goals"}
    assert {m for m, text in board.PROP_MARKET_NOTES.items() if text.startswith("Measured")} == measured
    for market in set(board.PROP_MARKET_KEYS.values()) - measured:
        assert board.PROP_MARKET_NOTES[market].startswith("Never measured against real prices")


def test_the_note_carries_the_cards_counts_and_the_players_it_withheld() -> None:
    board = _load("build_board_json.py", "bbj_props_note")
    block = board.props_block(CARD, GAMES)
    note = block["note"]
    assert note.startswith(CARD["note"])
    assert "priced 9 props" in note and "6 are listed" in note
    assert "Cole Palmer (Chelsea, 25%)" in note and "Anthony Gordon (Newcastle, 0%)" in note
    assert "Sandro Tonali (Newcastle, unavailable)" in note, "a status-only withhold gives the status, not a chance"
    assert "unlikely to play" in note and "injury list" not in note
    # The threshold is not a promise, and no site is named on a page.
    assert "8%" not in note and "0.08" not in note
    for word in ("fantasy", "fpl", "understat", "opta"):
        assert word not in json.dumps(block).lower()


def test_a_card_without_the_counts_still_lists_its_picks() -> None:
    """A props card written before `priced` existed carries no count line."""
    board = _load("build_board_json.py", "bbj_props_old_card")
    block = board.props_block({"status": "Props card ready", "note": "no edge", "picks": PICKS[:1]}, GAMES)
    assert len(block["rows"]) == 1 and block["note"] == "no edge"
    assert block["marketNotes"]["shots"]


def test_a_ready_card_with_no_row_says_why_and_calls_nothing_a_best_bet() -> None:
    """The shared page shows this note as the tab's empty state, so it is the
    one state in which the note is read. The usual week: opinions on
    everything, nothing clearing the bar."""
    board = _load("build_board_json.py", "bbj_props_no_rows")
    base = {"status": "Props card ready", "note": "no edge", "priced": 143}
    nothing_cleared = board.props_block({**base, "picks": []}, GAMES)["note"]
    assert "The card priced 143 props; no pick cleared the bar, so none is listed." in nothing_cleared
    pulled = board.props_block({**base, "picks": PICKS[:2]}, GAMES, withdrawn=[
        {"player": p["player"], "home_team": p["home_team"], "away_team": p["away_team"],
         "market": p["market"], "selection": p["selection"], "state": "bench"} for p in PICKS[:2]])["note"]
    assert "every pick was withdrawn at the lineup check, so none is listed." in pulled
    assert "Withdrawn at the lineup check, not starting: Alexander Isak (bench), Mohamed Salah (bench)." in pulled
    off_board = board.props_block({**base, "picks": PICKS[:2]}, {("Arsenal", "Chelsea"): "g2"})["note"]
    assert "its 2 picks are on fixtures this board does not carry, so none is listed." in off_board
    for note in (nothing_cleared, pulled, off_board):
        assert "0 are listed" not in note and "each a best bet" not in note


def test_a_held_card_lists_nothing_and_still_says_why() -> None:
    board = _load("build_board_json.py", "bbj_props_held")
    block = board.props_block({"status": "Held by policy", "note": "held", "picks": PICKS, "priced": 9,
                               "withheld_unavailable": CARD["withheld_unavailable"]}, GAMES)
    assert block["status"] == "abstain" and block["rows"] == [] and block["note"] == "held"


# ---------- (a2) the card's own counts ----------

LOG_FIELDS = ["season", "date", "match_id", "team", "opponent", "venue", "player", "player_id",
              "position", "minutes", "goals", "assists", "shots", "shots_on_target",
              "yellow_cards", "red_cards", "first_goal_minute"]
STAGING_FIELDS = ["date", "commence_time", "home_team", "away_team", "market", "player",
                  "selection", "american_odds", "book", "notes"]


def _csv(path: Path, fields: list[str], rows: list[dict]) -> Path:
    import csv
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row.get(f, "") for f in fields})
    return path


def test_the_card_counts_an_outcome_once_however_many_books_spell_the_player(tmp_path: Path) -> None:
    """`priced` is outcomes with a model opinion on the model's own player;
    two books' spellings of one player are one outcome and, when both clear
    the bar, one stake (the better edge), so `below_bar` is never negative."""
    from datetime import datetime, timezone
    from epl_betting_lab.reports.player_props_card import build_player_props_card

    logs = []
    for m in range(12):
        for name in ("Alexander Isak", "Anthony Gordon"):
            logs.append({"season": "2026", "date": f"2026-08-{m + 1:02d}", "match_id": f"m{m}",
                         "team": "Newcastle", "opponent": "Everton", "venue": "home", "player": name,
                         "player_id": name, "position": "FW", "minutes": 90, "goals": 1, "assists": 0,
                         "shots": 4, "shots_on_target": 3, "yellow_cards": 0, "red_cards": 0})
        for q in range(6):
            logs.append({"season": "2026", "date": f"2026-08-{m + 1:02d}", "match_id": f"m{m}",
                         "team": "Everton", "opponent": "Newcastle", "venue": "away", "player": f"Squad {q}",
                         "player_id": f"sq{q}", "position": "MC", "minutes": 90, "shots": 1, "shots_on_target": 1})
    fixture = {"date": "2026-08-23", "commence_time": "2026-08-23T15:00:00Z", "home_team": "Newcastle",
               "away_team": "Liverpool", "market": "player_shots_on_target", "selection": "Over@0.5"}
    staging = [
        {**fixture, "player": "Alexander Isak", "american_odds": 150, "book": "FanDuel"},
        {**fixture, "player": "Isak", "american_odds": 160, "book": "DraftKings"},
        {**fixture, "player": "Anthony Gordon", "american_odds": 150, "book": "FanDuel"},
    ]
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"provider_allowlist_entries": {"the_odds_api": {
        "allowlist_status": "allowed", "reviewer_name": "cooperross399",
        "evidence_receipt_id": "odds_api-20260821T114655-0400-20ffa5677988",
        "required_markets": ["player_shots_on_target"]}}}))
    summary = build_player_props_card(
        props_staging_path=_csv(tmp_path / "props.csv", STAGING_FIELDS, staging),
        logs_path=_csv(tmp_path / "logs.csv", LOG_FIELDS, logs),
        policy_path=policy, run_at=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
    )
    assert summary["status"] == "Props card ready"
    assert summary["priced"] == 2, "Isak once, Gordon once"
    picks = {p["player"]: p for p in summary["picks"]}
    assert set(picks) == {"Isak", "Anthony Gordon"}, "the better price of the two spellings keeps the stake"
    assert picks["Isak"]["model_player"] == "Alexander Isak" and picks["Isak"]["book"] == "DraftKings"
    assert summary["below_bar"] == 0 and summary["priced"] - len(summary["picks"]) == 0


# ---------- (b) the pages ----------

@pytest.mark.parametrize("page", PAGES)
def test_each_epl_page_links_the_props_tab(page: str) -> None:
    text = (WEB / page).read_text(encoding="utf-8")
    assert '["Props", "Board.dc.html#props"]' in text, page
    assert text.index('"Board.dc.html"]') < text.index('"Board.dc.html#props"') < text.index('"Results.dc.html"]'), \
        f"{page}: the Props tab sits between This week and Results, as on the NHL pages"


# ---------- (c) the record ----------

DAY = date(2026, 10, 18)
GID = "401879268"


def _prop(player, market, side, line, price=110, units=0.1, team="NFO", opp="ARS"):
    return {"gameId": GID, "player": player, "team": team, "opp": opp, "market": market,
            "side": side, "line": line, "price": price, "book": "DraftKings", "kind": "bet", "units": units}


def _board(rows):
    return {
        "season": "2026-27", "generatedAt": "2026-10-17T09:00:00Z", "windowLabel": "2026-10-17 through 2026-10-19",
        "teams": {"NFO": {"name": "Nott'm Forest"}, "ARS": {"name": "Arsenal"}},
        "games": [{"id": GID, "kickoff": "2026-10-18T15:30Z",
                   "home": {"abbr": "NFO", "winProb": 0.3}, "away": {"abbr": "ARS", "winProb": 0.45},
                   "drawProb": 0.25, "total": {"overProb": 0.5}, "pick": None}],
        "props": {"status": "ok", "note": "", "marketNotes": {}, "rows": rows},
    }


def _player(pid, name, appeared=1, **stats):
    base = {"appearances": float(appeared), "totalShots": 0.0, "shotsOnTarget": 0.0, "totalGoals": 0.0,
            "goalAssists": 0.0, "yellowCards": 0.0, "redCards": 0.0, "saves": 0.0}
    base.update({k: float(v) for k, v in stats.items()})
    return {"athlete": {"id": pid, "displayName": name}, "stats": [{"name": k, "value": v} for k, v in base.items()]}


SUMMARY = {
    "rosters": [
        {"homeAway": "home", "roster": [_player("1", "Chris Wood", totalShots=4, shotsOnTarget=1),
                                        _player("2", "Matz Sels", saves=5)]},
        {"homeAway": "away", "roster": [_player("10", "Bukayo Saka", totalShots=3, shotsOnTarget=2, goalAssists=1)]},
    ]
}


@pytest.fixture
def settle(monkeypatch):
    module = _load("settle_results.py", "settle_props_everywhere")
    monkeypatch.setattr(module, "finals", lambda sport, day: {GID: {"home": 0, "away": 1, "finish": "REG"}})
    monkeypatch.setattr(module, "match_summary", lambda sport, gid: SUMMARY)
    return module


def test_a_settled_night_reaches_results_the_tracker_and_the_boards_record(settle, tmp_path: Path) -> None:
    rows = [
        _prop("Chris Wood", "shots", "over", 2.5, price=150),                       # 4 -> win, +0.15
        _prop("Chris Wood", "shots_on_target", "over", 1.5, price=-120),            # 1 -> loss, -0.1
        _prop("Matz Sels", "goalie_saves", "over", 3.5),                            # 5 -> win, +0.11
        _prop("Bukayo Saka", "assists", "over", 0.5, team="ARS", opp="NFO"),        # 1 -> win, +0.11
    ]
    boards = [_board(rows)]
    latest, waiting = settle.settle_day("epl", DAY, boards)
    assert waiting is False

    # results.json: every graded prop and the day's tally.
    props = latest["props"]
    assert {(r["player"], r["market"], r["result"]) for r in props["rows"]} == {
        ("Chris Wood", "shots", "win"), ("Chris Wood", "shots_on_target", "loss"),
        ("Matz Sels", "goalie_saves", "win"), ("Bukayo Saka", "assists", "win"),
    }
    assert props["summary"]["w"] == 3 and props["summary"]["l"] == 1 and props["summary"]["p"] == 0
    assert props["summary"]["units"] == pytest.approx(0.15 - 0.1 + 0.11 + 0.11, abs=0.001)

    # The tracker's rows: group "props", the player and the prop type on each.
    tracked = [b for b in latest["bets"] if b["group"] == "props"]
    assert {(b["player"], b["propType"], b["result"]) for b in tracked} == {
        ("Chris Wood", "shots", "win"), ("Chris Wood", "shots_on_target", "loss"),
        ("Matz Sels", "goalie_saves", "win"), ("Bukayo Saka", "assists", "win"),
    }
    assert all(b["staked"] == 0.1 and b["market"] == b["propType"] for b in tracked)
    pages = _load("build_site_pages.py", "bsp_props_everywhere")
    hist = tmp_path / "history"
    (hist / "settled").mkdir(parents=True)
    (hist / "settled" / f"{DAY.isoformat()}.json").write_text(
        json.dumps({"resultsDate": DAY.isoformat(), **settle.night_record(latest)}), encoding="utf-8")
    tracker = pages.tracker(hist, "2026-10-20T09:00:00Z")
    assert [g["key"] for g in tracker["byGroup"]] == ["props"]
    assert {g["label"] for g in tracker["byPlayer"]} == {"Chris Wood (NFO)", "Matz Sels (NFO)", "Bukayo Saka (ARS)"}
    assert {g["key"] for g in tracker["byPropType"]} == {"shots:over", "shots_on_target:over", "goalie_saves:over", "assists:over"}

    # The season, onto results.json and the board's record strip.
    season = settle.season_record("epl", DAY, tmp_path, boards, latest, waiting)
    assert season["props"] == {"w": 3, "l": 1, "p": 0, "units": pytest.approx(0.27, abs=0.001), "nights": 1}
    data = tmp_path / "data"
    data.mkdir()
    (data / "board.json").write_text(json.dumps({"record": {"settled": 3}}), encoding="utf-8")
    settle.write_season(data, latest, season)
    assert latest["props"]["season"] == season["props"]
    board = json.loads((data / "board.json").read_text(encoding="utf-8"))
    assert board["record"]["props"] == {"w": 3, "l": 1, "p": 0, "units": pytest.approx(0.27, abs=0.001), "nights": 1}
    assert board["record"]["settled"] == 3, "the keys the record already carried are kept"


def test_a_night_without_props_writes_no_props_record(settle, tmp_path: Path) -> None:
    board = _board([])
    board.pop("props")
    latest, waiting = settle.settle_day("epl", DAY, [board])
    season = settle.season_record("epl", DAY, tmp_path, [board], latest, waiting)
    assert "props" not in season
    data = tmp_path / "data"
    data.mkdir()
    (data / "board.json").write_text(json.dumps({"record": {}}), encoding="utf-8")
    settle.write_season(data, latest, season)
    assert "props" not in json.loads((data / "board.json").read_text(encoding="utf-8"))["record"], \
        "a props tally nobody made is never published as 0-0"
