"""The props card and the xG ratings keep working when Understat does not.

From 2026-11-02 Understat answered every data request with something other
than JSON. Two things stopped, and only one said so:

- the match card's ratings lost xG for every match played since, and the card
  said "goals alone";
- the props refresh died at its first step, so no prop price was bought and
  no props card was built for two weeks, and nothing on the card said that.

And one thing had never worked: the props model was fitted on Understat's
club spellings ("Manchester United") while the staged prices carry the
project's ("Man United"), so the five clubs Understat spells differently never
had a player priced.
"""

from __future__ import annotations

import csv
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.data import fetch_understat_xg as xg
from epl_betting_lab.providers import espn_player_logs as espn
from epl_betting_lab.providers.fpl_players import LOG_FIELDS as FPL_LOG_FIELDS, build_fpl_logs
from epl_betting_lab.providers.understat_players import UnderstatError
from epl_betting_lab.reports.player_props_card import READY_STATUS

from epl_betting_lab.reports.player_props_card import build_player_props_card


def _load(name: str, relative: str):
    path = Path(__file__).resolve().parents[1] / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The props card's own fixtures, read by path: the suite runs with
# PYTHONSAFEPATH, so `tests` is not importable as a package.
_card = _load("props_card_fixtures", "tests/test_player_props_card.py")
STAGING_FIELDS, _logs, _policy, _staging_row, _write_csv = (
    _card.STAGING_FIELDS, _card._logs, _card._policy, _card._staging_row, _card._write_csv,
)


RUN_AT = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# ESPN's match summary, in Understat's shape
# ---------------------------------------------------------------------------

def _player(pid, name, pos, *, starter=True, sub_in=False, sub_out=False, plays=(), **stats):
    base = {"appearances": 1.0 if (starter or sub_in) else 0.0, "totalShots": 0.0,
            "shotsOnTarget": 0.0, "totalGoals": 0.0, "goalAssists": 0.0,
            "yellowCards": 0.0, "redCards": 0.0}
    base.update({k: float(v) for k, v in stats.items()})
    return {
        "starter": starter, "subbedIn": sub_in, "subbedOut": sub_out,
        "athlete": {"id": pid, "displayName": name},
        "position": {"abbreviation": pos},
        "stats": [{"name": k, "value": v} for k, v in base.items()],
        "plays": list(plays),
    }


def _sub(minute):
    return {"clock": {"displayValue": minute}, "substitution": True}


SUMMARY = {
    "rosters": [
        {
            "homeAway": "home",
            "team": {"displayName": "Brighton & Hove Albion"},
            "roster": [
                _player("1", "Bart Verbruggen", "G"),
                _player("2", "Diego Gómez", "AM-R", sub_out=True, totalShots=3, shotsOnTarget=1,
                        totalGoals=1,
                        plays=[{"clock": {"displayValue": "15'"}, "scoringPlay": True, "didScore": True},
                               _sub("90'+3'")]),
                _player("3", "Lewis Dunk", "CD-L", yellowCards=1),
                _player("4", "Yankuba Minteh", "SUB", starter=False, sub_in=True, plays=[_sub("82'")]),
                _player("5", "Jason Steele", "SUB", starter=False),
                _player("6", "Malick Yalcouyé", "SUB", starter=False, sub_in=True, plays=[_sub("90'+3'")]),
            ],
        },
        {
            "homeAway": "away",
            "team": {"displayName": "Manchester United"},
            "roster": [
                _player("7", "Bryan Mbeumo", "F", totalShots=2, goalAssists=1),
                _player("8", "Casemiro", "DM", redCards=1,
                        plays=[{"clock": {"displayValue": "60'"}, "redCard": True}]),
            ],
        },
    ]
}

EVENT = espn.LeagueEvent(
    event_id="401879244", kickoff="2026-11-08T14:00Z", season=2026,
    home="Brighton & Hove Albion", away="Manchester United", completed=True,
)


def _rows():
    return {row["player"]: row for row in espn.understat_shaped_rows(SUMMARY, EVENT)}


def test_espn_rows_carry_every_column_the_props_model_reads():
    rows = espn.understat_shaped_rows(SUMMARY, EVENT)
    assert rows and all(set(row) == set(espn.UNDERSTAT_SHAPED_FIELDS) for row in rows)


def test_an_unused_substitute_is_not_an_appearance():
    assert "Jason Steele" not in _rows()


def test_minutes_come_from_the_substitution_and_red_card_clocks():
    rows = _rows()
    assert rows["Bart Verbruggen"]["minutes"] == 90
    assert rows["Diego Gómez"]["minutes"] == 90       # off in stoppage time
    assert rows["Yankuba Minteh"]["minutes"] == 8     # on at 82'
    assert rows["Malick Yalcouyé"]["minutes"] == 1    # on in stoppage time
    assert rows["Casemiro"]["minutes"] == 60          # sent off at 60'


def test_clubs_are_in_the_spelling_the_staged_prices_carry():
    rows = _rows()
    assert rows["Lewis Dunk"]["team"] == "Brighton"
    assert rows["Lewis Dunk"]["opponent"] == "Man United"
    assert rows["Bryan Mbeumo"]["team"] == "Man United"
    assert rows["Bryan Mbeumo"]["venue"] == "away"


def test_statistics_and_positions_map_onto_understats():
    rows = _rows()
    gomez = rows["Diego Gómez"]
    assert (gomez["goals"], gomez["shots"], gomez["shots_on_target"]) == (1, 3, 1)
    assert gomez["first_goal_minute"] == 15
    assert rows["Bryan Mbeumo"]["assists"] == 1
    assert rows["Lewis Dunk"]["yellow_cards"] == 1
    assert rows["Casemiro"]["red_cards"] == 1
    assert rows["Bart Verbruggen"]["position"] == "GK"
    assert rows["Lewis Dunk"]["position"].startswith("D")
    assert gomez["position"].startswith("M")
    assert rows["Bryan Mbeumo"]["position"] == "FW"
    assert rows["Yankuba Minteh"]["position"] == "Sub"
    assert gomez["match_id"] == "espn-401879244" and gomez["player_id"] == "espn-2"


# ---------------------------------------------------------------------------
# The props refresh does not die with Understat
# ---------------------------------------------------------------------------

def _load_refresh():
    return _load("run_props_card_refresh_under_test", "scripts/run_props_card_refresh.py")


def test_the_player_logs_are_rebuilt_from_espn_when_understat_fails(tmp_path, monkeypatch):
    refresh = _load_refresh()
    monkeypatch.setattr(refresh, "PROCESSED_DIR", tmp_path)

    def understat_down(*args, **kwargs):
        raise UnderstatError("Understat returned non-JSON for https://understat.com/getLeagueData/EPL/2026.")

    result = espn.FetchResult(rows=espn.understat_shaped_rows(SUMMARY, EVENT), fetched=1)
    monkeypatch.setattr(refresh, "fetch_player_match_logs", understat_down)
    monkeypatch.setattr(refresh, "fetch_understat_shaped_logs", lambda season: result)

    note = refresh._refresh_player_logs()

    assert "ESPN" in note
    with (tmp_path / refresh.LOGS_FILENAME).open(encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert {row["player"] for row in written} >= {"Diego Gómez", "Bryan Mbeumo"}


def test_with_both_sources_down_the_refresh_carries_on(tmp_path, monkeypatch):
    refresh = _load_refresh()
    monkeypatch.setattr(refresh, "PROCESSED_DIR", tmp_path)

    def understat_down(*args, **kwargs):
        raise UnderstatError("down")

    def espn_down(season):
        raise espn.EspnError("down")

    monkeypatch.setattr(refresh, "fetch_player_match_logs", understat_down)
    monkeypatch.setattr(refresh, "fetch_understat_shaped_logs", espn_down)

    note = refresh._refresh_player_logs()
    assert note.startswith("WARNING")


# ---------------------------------------------------------------------------
# A club Understat spells differently is still priced
# ---------------------------------------------------------------------------

def test_a_player_logged_under_understats_club_spelling_is_priced(tmp_path):
    logs = pd.read_csv(_logs(tmp_path), dtype=str)
    logs = logs.replace({"Newcastle": "Newcastle United"})
    logs.to_csv(tmp_path / "logs.csv", index=False)
    summary = build_player_props_card(
        props_staging_path=_write_csv(tmp_path / "props.csv", STAGING_FIELDS, [_staging_row()]),
        logs_path=tmp_path / "logs.csv",
        policy_path=_policy(tmp_path / "policy.json", ["player_shots_on_target"]),
        run_at=RUN_AT,
    )
    assert summary["status"] == READY_STATUS
    assert [pick["player"] for pick in summary["picks"]] == ["Alexander Isak"]
    assert summary["picks"][0]["team"] == "Newcastle"


# ---------------------------------------------------------------------------
# Team xG from Fantasy Premier League where Understat has none
# ---------------------------------------------------------------------------

BOOTSTRAP = {
    "teams": [{"id": 1, "name": "Arsenal"}, {"id": 2, "name": "Man Utd"}],
    "element_types": [{"id": 4, "singular_name_short": "FWD"}],
    "elements": [
        {"id": 10, "first_name": "A", "second_name": "One", "team": 1, "element_type": 4},
        {"id": 11, "first_name": "A", "second_name": "Two", "team": 1, "element_type": 4},
        {"id": 20, "first_name": "B", "second_name": "One", "team": 2, "element_type": 4},
    ],
}


def _history(fixture, kickoff, opponent, home, xg_value, minutes=90):
    return {"fixture": fixture, "kickoff_time": kickoff, "opponent_team": opponent,
            "was_home": home, "minutes": minutes, "expected_goals": str(xg_value)}


SUMMARIES = {
    10: {"history": [_history(1, "2026-11-08T16:30:00Z", 2, True, 1.2),
                     _history(2, "2026-11-01T15:00:00Z", 2, False, 0.4)]},
    11: {"history": [_history(1, "2026-11-08T16:30:00Z", 2, True, 0.5),
                     _history(2, "2026-11-01T15:00:00Z", 2, False, 0.0, minutes=0)]},
    20: {"history": [_history(1, "2026-11-08T16:30:00Z", 1, False, 0.7),
                     _history(2, "2026-11-01T15:00:00Z", 1, True, 1.9)]},
}


def test_the_fpl_logs_carry_each_appearances_expected_goals():
    logs = build_fpl_logs(BOOTSTRAP, SUMMARIES)
    assert "expected_goals" in FPL_LOG_FIELDS
    assert pytest.approx(sorted(logs["expected_goals"].astype(float))) == [0.4, 0.5, 0.7, 1.2, 1.9]


def test_fpl_logs_sum_to_one_row_per_match():
    table = xg.team_xg_from_fpl_logs(build_fpl_logs(BOOTSTRAP, SUMMARIES))
    by_home = {row.home_team: row for row in table.itertuples()}
    assert set(by_home) == {"Arsenal", "Man United"}
    assert by_home["Arsenal"].home_xg == pytest.approx(1.7)
    assert by_home["Arsenal"].away_xg == pytest.approx(0.7)
    assert by_home["Arsenal"].date == pd.Timestamp("2026-11-08")
    assert by_home["Man United"].home_xg == pytest.approx(1.9)


def _fpl_file(tmp_path: Path) -> Path:
    path = tmp_path / "fpl_match_logs.csv"
    build_fpl_logs(BOOTSTRAP, SUMMARIES).to_csv(path, index=False)
    return path


def test_a_failed_understat_fetch_keeps_what_it_had_and_fills_the_rest_from_fpl(tmp_path, monkeypatch):
    # One shared match stands in for the twenty the scale needs in a season.
    monkeypatch.setattr(xg, "MIN_OVERLAP_FOR_SCALE", 1)
    processed = tmp_path / "processed"
    processed.mkdir()
    # What an earlier run kept: the 1 November match only.
    pd.DataFrame([{"date": "2026-11-01", "home_team": "Man United", "away_team": "Arsenal",
                   "home_xg": 2.1, "away_xg": 0.5}]).to_csv(processed / xg.XG_FILENAME, index=False)

    def down(url):
        raise UnderstatError("Understat returned non-JSON.")

    table, note = xg.fetch_and_fill_team_xg(
        ["2026"], raw_dir=tmp_path / "raw", processed_dir=processed,
        requester=down, fpl_logs_path=_fpl_file(tmp_path),
    )
    kept = table[table.home_team == "Man United"].iloc[0]
    assert (kept.home_xg, kept.away_xg) == (2.1, 0.5)          # Understat's own row stands
    filled = table[table.home_team == "Arsenal"].iloc[0]
    # Scaled to Understat's level on the match both sources hold: 2.6 / 2.3.
    scale = (2.1 + 0.5) / (1.9 + 0.4)
    assert filled.home_xg == pytest.approx(1.7 * scale)
    assert filled.away_xg == pytest.approx(0.7 * scale)
    assert "Fantasy Premier League" in note and "1 match" in note
    on_disk = pd.read_csv(processed / xg.XG_FILENAME)
    assert len(on_disk) == 2


def test_with_no_xg_source_at_all_the_fetch_still_fails(tmp_path):
    def down(url):
        raise UnderstatError("down")

    with pytest.raises(UnderstatError):
        xg.fetch_and_fill_team_xg(
            ["2026"], raw_dir=tmp_path / "raw", processed_dir=tmp_path / "processed",
            requester=down, fpl_logs_path=tmp_path / "missing.csv",
        )


def test_too_few_shared_matches_leave_the_fpl_figures_unscaled(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame([{"date": "2026-11-01", "home_team": "Man United", "away_team": "Arsenal",
                   "home_xg": 2.1, "away_xg": 0.5}]).to_csv(processed / xg.XG_FILENAME, index=False)

    def down(url):
        raise UnderstatError("down")

    table, note = xg.fetch_and_fill_team_xg(
        ["2026"], raw_dir=tmp_path / "raw", processed_dir=processed,
        requester=down, fpl_logs_path=_fpl_file(tmp_path),
    )
    filled = table[table.home_team == "Arsenal"].iloc[0]
    assert filled.home_xg == pytest.approx(1.7)
    assert "scaled by 1.000" in note


def test_a_second_run_with_nothing_new_to_fill_is_not_a_failure(tmp_path):
    """2026-11-17/18: the first run after PR #422 filled every FPL match and
    the table rode to the next run in matchday-state. During the
    international break no match was added, so the fill found nothing
    missing and raised, and every later run said the ratings were on goals
    alone while every played match had xG on file."""
    processed = tmp_path / "processed"
    processed.mkdir()
    fpl = _fpl_file(tmp_path)

    def down(url):
        raise UnderstatError("Understat returned non-JSON.")

    held = pd.DataFrame([
        {"date": "2026-11-01", "home_team": "Man United", "away_team": "Arsenal",
         "home_xg": 2.1, "away_xg": 0.5},
        {"date": "2026-11-08", "home_team": "Arsenal", "away_team": "Man United",
         "home_xg": 1.7, "away_xg": 0.7},
    ])
    held.to_csv(processed / xg.XG_FILENAME, index=False)

    table, note = xg.fetch_and_fill_team_xg(
        ["2026"], raw_dir=tmp_path / "raw", processed_dir=processed,
        requester=down, fpl_logs_path=fpl,
    )
    assert len(table) == 2
    assert "already on file" in note and "Fantasy Premier League" in note
    assert len(pd.read_csv(processed / xg.XG_FILENAME)) == 2


def test_a_held_table_without_fpl_to_check_it_against_still_fails(tmp_path):
    """Nothing missing only means something when FPL could say what was
    played: with FPL down too, a held table may be weeks behind."""
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame([{"date": "2026-11-01", "home_team": "Man United", "away_team": "Arsenal",
                   "home_xg": 2.1, "away_xg": 0.5}]).to_csv(processed / xg.XG_FILENAME, index=False)

    def down(url):
        raise UnderstatError("down")

    with pytest.raises(UnderstatError):
        xg.fetch_and_fill_team_xg(
            ["2026"], raw_dir=tmp_path / "raw", processed_dir=processed,
            requester=down, fpl_logs_path=tmp_path / "missing.csv",
        )
