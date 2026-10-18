"""The EPL Due List: the rule, the drought, who is left off, and where it is shown."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab import due_list as d
from epl_betting_lab.providers import espn_player_logs as espn
from epl_betting_lab.reports.card_notification import build_notification

ROOT = Path(__file__).resolve().parents[1]


def _row(season, date, event, team, pid, *, goals=0, appeared=1, player=None):
    return {
        "season": season, "date": date, "event_id": event, "team": team, "opponent": "X",
        "player_id": pid, "player": player or f"P{pid}", "appeared": appeared, "goals": goals,
    }


def _season(season, pid, team, goal_flags, *, player=None):
    """One league appearance a week from a fixed start: August for this season, then onward."""
    start = pd.Timestamp(f"{season}-08-01") if season == 2026 else pd.Timestamp(f"{season}-08-10")
    return [
        _row(season, (start + pd.Timedelta(days=7 * i)).strftime("%Y-%m-%d"), f"e{season}-{i}", team, pid,
             goals=g, player=player)
        for i, g in enumerate(goal_flags)
    ]


class TestTheRule:
    def test_bands_and_bars(self) -> None:
        assert d.tier_bar(27) == 4 and d.band_label(27) == "20+"
        assert d.tier_bar(17) == 6 and d.band_label(17) == "15-19"
        assert d.tier_bar(10) == 8 and d.band_label(14) == "10-14"
        assert d.tier_bar(9) is None and d.band_label(9) is None
        assert d.tier_bar(float("nan")) is None

    def test_the_rule_sentence_is_built_from_the_constants(self) -> None:
        sentence = d.rule_sentence()
        assert "10+ Premier League goals" in sentence
        assert "20+ goals -> 4" in sentence and "10-14 goals -> 8" in sentence

    def test_one_in(self) -> None:
        assert d.one_in(0.5, 4) == 16
        assert d.one_in(1.0, 3) is None and d.one_in(0.3, 0) is None


class TestTheDrought:
    def test_only_appearances_count_and_it_carries_across_seasons(self) -> None:
        rows = _season(2025, "1", "Arsenal", [1] + [0] * 11)
        # On the bench, never came on: not a game without a goal.
        rows.append(_row(2026, "2026-08-20", "bench", "Arsenal", "1", appeared=0))
        rows += _season(2026, "1", "Arsenal", [0, 0])
        frame = d.prepare_logs(pd.DataFrame(rows))
        last = frame[frame["event_id"] == "e2026-1"].iloc[0]
        assert last["drought"] == 12  # 11 at the end of last season, 1 this season
        assert "bench" not in set(frame["event_id"])

    def test_last_season_record(self) -> None:
        rows = _season(2025, "1", "Arsenal", [2, 0, 1, 0]) + _season(2026, "1", "Arsenal", [0])
        frame = d.prepare_logs(pd.DataFrame(rows))
        now = frame[frame["season"] == 2026].iloc[0]
        assert now["prior_goals"] == 3 and now["prior_apps"] == 4 and now["prior_rate"] == 0.5

    def test_a_missing_goal_count_is_not_a_blank(self) -> None:
        rows = _season(2025, "1", "Arsenal", [1, 0, 0])
        rows[1]["goals"] = None
        frame = d.prepare_logs(pd.DataFrame(rows))
        assert len(frame) == 2


def _qualifier_logs():
    """Player 1: 12 goals last season, 8 straight blanks now. Player 2: 9 goals (below)."""
    rows = _season(2025, "1", "Arsenal", [0] * 26 + [1] * 12, player="Due Striker")
    rows += _season(2025, "2", "Chelsea", [0] * 29 + [1] * 9, player="Near Miss")
    rows += _season(2026, "1", "Arsenal", [0] * 8, player="Due Striker")
    rows += _season(2026, "2", "Chelsea", [0] * 8, player="Near Miss")
    return rows


FIXTURES = [
    {"event_id": "next1", "home": "Arsenal", "away": "Everton", "kickoff": "2026-10-03T14:00Z"},
    {"event_id": "next2", "home": "Chelsea", "away": "Fulham", "kickoff": "2026-10-03T16:30Z"},
]


class TestTheList:
    def test_a_qualifier_at_his_bar_is_listed_and_one_below_the_floor_is_not(self) -> None:
        rows = d.build_due_list(pd.DataFrame(_qualifier_logs()), FIXTURES, season=2026, before="2026-10-03")
        assert [r.player for r in rows] == ["Due Striker"]
        row = rows[0]
        assert (row.team, row.opponent, row.event_id) == ("Arsenal", "Everton", "next1")
        assert (row.prior_goals, row.bar, row.drought, row.band) == (12, 8, 8, "10-14")
        assert row.price is None

    def test_one_short_of_the_bar_is_not_listed(self) -> None:
        logs = [r for r in _qualifier_logs() if r["event_id"] != "e2026-7"]
        assert d.build_due_list(pd.DataFrame(logs), FIXTURES, season=2026, before="2026-10-03") == []

    def test_a_club_not_in_the_round_lists_nobody(self) -> None:
        assert d.build_due_list(pd.DataFrame(_qualifier_logs()), FIXTURES[1:], season=2026, before="2026-10-03") == []

    def test_a_player_with_no_squad_this_season_has_left_and_is_not_listed(self) -> None:
        logs = [r for r in _qualifier_logs() if not (r["player_id"] == "1" and r["season"] == 2026)]
        assert d.build_due_list(pd.DataFrame(logs), FIXTURES, season=2026, before="2026-10-03") == []

    def test_the_club_listed_is_his_latest(self) -> None:
        logs = _qualifier_logs()
        for r in logs:
            if r["player_id"] == "1" and r["season"] == 2026:
                r["team"] = "Everton"
        rows = d.build_due_list(pd.DataFrame(logs), FIXTURES, season=2026, before="2026-10-03")
        assert rows[0].team == "Everton" and rows[0].opponent == "Arsenal"

    def test_missing_from_the_last_squad_is_flagged_and_from_two_is_removed(self) -> None:
        logs = _qualifier_logs()
        # Arsenal played two more league matches without him in either squad.
        for i, day in enumerate(("2026-09-20", "2026-09-27")):
            logs.append(_row(2026, day, f"ars{i}", "Arsenal", "99", player="Team Mate"))
        removed: list = []
        rows = d.build_due_list(pd.DataFrame(logs), FIXTURES, season=2026, before="2026-10-03", removed_out=removed)
        assert rows == []
        assert removed[0][0].player == "Due Striker"
        assert "last 2 league matches" in removed[0][1]

        logs = [r for r in logs if r["event_id"] != "ars0"]
        rows = d.build_due_list(pd.DataFrame(logs), FIXTURES, season=2026, before="2026-10-03")
        assert "last league match" in rows[0].status

    def test_nothing_on_or_after_the_round_leaks_into_the_drought(self) -> None:
        logs = _qualifier_logs() + [_row(2026, "2026-10-03", "next1", "Arsenal", "1", goals=1)]
        rows = d.build_due_list(pd.DataFrame(logs), FIXTURES, season=2026, before="2026-10-03")
        assert rows[0].drought == 8

    def test_a_staged_price_is_carried_and_never_invented(self) -> None:
        rows = d.build_due_list(
            pd.DataFrame(_qualifier_logs()), FIXTURES, season=2026, before="2026-10-03",
            prices={"1": (240.0, "FanDuel")},
        )
        assert (rows[0].price, rows[0].book) == (240.0, "FanDuel")


class TestTheSection:
    def test_it_says_it_is_not_a_selection_and_reads_the_measurement(self) -> None:
        rows = d.build_due_list(pd.DataFrame(_qualifier_logs()), FIXTURES, season=2026, before="2026-10-03")
        headline = {"hit_rate": {"window": "2022/23 to 2025/26", "listed_n": 388, "listed_rate": 0.18,
                                 "others_n": 2286, "others_rate": 0.286, "diff": -0.106,
                                 "diff_low": -0.148, "diff_high": -0.063}}
        text = d.render_section(rows, headline=headline)
        assert "no units" in text and "nothing here is a selection" in text
        assert "scoring less often, not more" in text
        assert "| Due Striker | Arsenal | Everton |" in text
        assert "not posted" in text

    def test_without_a_backtest_it_claims_nothing(self) -> None:
        assert "nothing is said" in d.headline_sentence(None)

    def test_the_committed_backtest_is_readable(self) -> None:
        headline = d.load_headline(ROOT / "data" / "outputs")
        assert headline is not None
        assert headline["hit_rate"]["listed_n"] > 0
        assert headline["priced"] is None

    def test_the_card_carries_the_list(self, tmp_path: Path) -> None:
        (tmp_path / d.DUE_LIST_MD).write_text("### Due List · anytime goalscorers\n\nrow\n", encoding="utf-8")
        body = build_notification(output_dir=tmp_path, now=datetime(2026, 10, 3, 9, tzinfo=timezone.utc))["body"]
        assert "### Due List · anytime goalscorers" in body


def _summary():
    def player(pid, name, *, starter, apps, goals, own=0):
        stats = [{"name": "appearances", "value": float(apps)}, {"name": "totalGoals", "value": float(goals)},
                 {"name": "ownGoals", "value": float(own)}]
        return {"starter": starter, "athlete": {"id": pid, "displayName": name},
                "position": {"abbreviation": "F"}, "stats": stats}

    return {"rosters": [
        {"homeAway": "home", "team": {"displayName": "Arsenal"},
         "roster": [player("1", "A Striker", starter=True, apps=1, goals=2),
                    player("2", "A Sub", starter=False, apps=0, goals=0)]},
        {"homeAway": "away", "team": {"displayName": "Everton"},
         "roster": [player("3", "E Defender", starter=True, apps=1, goals=0, own=1)]},
    ]}


class TestEspn:
    EVENT = espn.LeagueEvent("100", "2026-09-01T14:00Z", 2026, "Arsenal", "Everton", True)

    def test_squad_rows(self) -> None:
        rows = espn.match_rows(_summary(), self.EVENT)
        by = {r["player_id"]: r for r in rows}
        assert by["1"]["goals"] == 2 and by["1"]["team"] == "Arsenal" and by["1"]["opponent"] == "Everton"
        assert by["2"]["appeared"] == 0
        assert by["3"]["goals"] == 0 and by["3"]["own_goals"] == 1
        assert set(rows[0]) == set(espn.LOG_FIELDS)

    def test_a_summary_without_both_squads_is_no_rows(self) -> None:
        assert espn.match_rows({"rosters": []}, self.EVENT) == []

    def test_a_season_is_two_calendar_years_filtered(self) -> None:
        def ev(eid, season, done=True):
            return {"id": eid, "date": "2026-01-01T15:00Z", "season": {"year": season},
                    "status": {"type": {"completed": done}},
                    "competitions": [{"competitors": [
                        {"homeAway": "home", "team": {"displayName": "Arsenal"}},
                        {"homeAway": "away", "team": {"displayName": "Everton"}}]}]}

        calls = []

        def request(url):
            calls.append(url)
            if "scoreboard" in url:
                return {"events": [ev("a", 2025), ev("b", 2024), ev("c", 2025, done=False)]}
            if url.endswith("event=a"):
                return _summary()
            raise AssertionError(url)

        result = espn.fetch_logs([2025], request=request, workers=1)
        assert {e.event_id for e in result.events} == {"a", "c"}
        assert result.fetched == 1 and not result.failed
        assert any("dates=2025" in c for c in calls) and any("dates=2026" in c for c in calls)

    def test_an_unreadable_summary_is_named_not_filled(self) -> None:
        def request(url):
            if "scoreboard" in url:
                return {"events": [{"id": "a", "date": "2026-01-01T15:00Z", "season": {"year": 2025},
                                    "status": {"type": {"completed": True}}, "competitions": [{}]}]}
            raise espn.EspnError("down")

        result = espn.fetch_logs([2025], request=request, workers=1)
        assert result.failed == ["a"] and result.rows == []


def _board():
    spec = importlib.util.spec_from_file_location("build_board_json_due", ROOT / "web" / "build_board_json.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_board_attaches_rows_to_their_fixture_in_the_shared_page_shape(tmp_path: Path) -> None:
    board = _board()
    rows = d.build_due_list(pd.DataFrame(_qualifier_logs()), FIXTURES, season=2026, before="2026-10-03")
    payload = d.payload(rows, removed=[], season=2026, before="2026-10-03",
                        generated_at="2026-10-02T09:00:00+00:00", headline=None)
    path = tmp_path / board.DUE_LIST_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    due = board.load_due_list(tmp_path)
    assert board.due_rows_for(due, "next2") == []
    (entry,) = board.due_rows_for(due, "next1")
    assert entry["market"] == "goals" and entry["line"] == 0.5 and entry["rule"] == "tier"
    assert entry["team"] == "ARS" and entry["drought"] == 8 and entry["tierBar"] == 8
    assert entry["price"] is None and "cellRecord" not in entry
    assert board.load_due_list(tmp_path / "nowhere") is None


def test_the_matchday_run_builds_the_list_and_uploads_it_for_the_board() -> None:
    text = (ROOT / ".github" / "workflows" / "matchday-refresh.yml").read_text(encoding="utf-8")
    assert "python scripts/build_due_list.py" in text
    assert f"data/outputs/{d.DUE_LIST_JSON}" in text
