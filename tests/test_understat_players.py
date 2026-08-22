"""Player match logs from Understat: modelled rates and settled results.

Props cannot be priced without per-player rates or measured without
per-player results, and Football-Data carries neither.
"""

from __future__ import annotations

import pytest

from epl_betting_lab.providers.understat_players import (
    ON_TARGET_RESULTS,
    LeagueMatch,
    UnderstatError,
    build_match_log_rows,
    fetch_league_matches,
    fetch_player_match_logs,
)


MATCH = LeagueMatch(
    match_id="29138",
    date="2026-05-19",
    home_team="Bournemouth",
    away_team="Manchester City",
    is_result=True,
)


def _roster(
    roster_id: str,
    player_id: str,
    player: str,
    *,
    time: str = "90",
    goals: str = "0",
    shots: str = "0",
    assists: str = "0",
    yellow: str = "0",
    red: str = "0",
    position: str = "FW",
) -> dict:
    return {
        roster_id: {
            "id": roster_id,
            "player_id": player_id,
            "player": player,
            "time": time,
            "goals": goals,
            "shots": shots,
            "assists": assists,
            "yellow_card": yellow,
            "red_card": red,
            "position": position,
        }
    }


def _shot(player_id: str, result: str, minute: str = "10") -> dict:
    return {"player_id": player_id, "result": result, "minute": minute}


def _match_data() -> dict:
    return {
        "rosters": {
            "h": _roster("1", "100", "Justin Kluivert", goals="1", shots="4"),
            "a": _roster("2", "8260", "Erling Haaland", goals="1", shots="2"),
        },
        "shots": {
            "h": [
                _shot("100", "Goal", "23"),
                _shot("100", "SavedShot"),
                _shot("100", "MissedShots"),
                _shot("100", "BlockedShot"),
            ],
            "a": [_shot("8260", "Goal", "67"), _shot("8260", "ShotOnPost")],
        },
    }


class TestMatchLogRows:
    def test_one_row_per_player_who_appeared(self) -> None:
        rows = build_match_log_rows(MATCH, _match_data(), season="2025")

        assert len(rows) == 2
        by_player = {r["player"]: r for r in rows}
        assert by_player["Justin Kluivert"]["team"] == "Bournemouth"
        assert by_player["Justin Kluivert"]["venue"] == "home"
        assert by_player["Erling Haaland"]["opponent"] == "Bournemouth"
        assert by_player["Erling Haaland"]["venue"] == "away"

    def test_shots_on_target_are_goals_plus_saved(self) -> None:
        """Blocked shots and the woodwork are not on target. This is the
        standard definition and close to — not identical to — the Opta counts
        books settle against; the module docstring carries that caveat."""
        rows = build_match_log_rows(MATCH, _match_data(), season="2025")
        by_player = {r["player"]: r for r in rows}

        assert by_player["Justin Kluivert"]["shots_on_target"] == 2
        assert by_player["Erling Haaland"]["shots_on_target"] == 1
        assert ON_TARGET_RESULTS == {"Goal", "SavedShot"}

    def test_the_first_goal_minute_is_the_earliest(self) -> None:
        data = _match_data()
        data["shots"]["h"].append(_shot("100", "Goal", "80"))
        rows = build_match_log_rows(MATCH, data, season="2025")
        by_player = {r["player"]: r for r in rows}

        assert by_player["Justin Kluivert"]["first_goal_minute"] == 23
        assert by_player["Erling Haaland"]["first_goal_minute"] == 67

    def test_a_player_without_a_goal_has_no_first_goal_minute(self) -> None:
        data = _match_data()
        data["shots"]["a"] = [_shot("8260", "MissedShots")]
        rows = build_match_log_rows(MATCH, data, season="2025")
        by_player = {r["player"]: r for r in rows}

        assert by_player["Erling Haaland"]["first_goal_minute"] == ""

    def test_an_unused_substitute_is_not_an_appearance(self) -> None:
        """A prop on a player who never entered is voided by the book, not
        lost; logging zero minutes as an appearance would poison the rates."""
        data = _match_data()
        data["rosters"]["h"].update(
            _roster("3", "555", "Unused Keeper", time="0")
        )
        rows = build_match_log_rows(MATCH, data, season="2025")

        assert all(r["player"] != "Unused Keeper" for r in rows)

    def test_missing_rosters_fail_closed(self) -> None:
        with pytest.raises(UnderstatError, match="rosters"):
            build_match_log_rows(MATCH, {"shots": {}}, season="2025")


class TestLeagueMatches:
    def test_it_returns_every_match_with_identity(self) -> None:
        payload = {
            "dates": [
                {
                    "id": "28778",
                    "datetime": "2025-08-15 19:00:00",
                    "isResult": True,
                    "h": {"title": "Liverpool"},
                    "a": {"title": "Bournemouth"},
                },
                {
                    "id": "29000",
                    "datetime": "2026-05-24 15:00:00",
                    "isResult": False,
                    "h": {"title": "Fulham"},
                    "a": {"title": "Everton"},
                },
            ]
        }
        matches = fetch_league_matches("2025", requester=lambda url: payload)

        assert [m.match_id for m in matches] == ["28778", "29000"]
        assert matches[0].date == "2025-08-15"
        assert matches[0].home_team == "Liverpool"
        assert matches[1].is_result is False

    def test_a_missing_match_list_fails_closed(self) -> None:
        with pytest.raises(UnderstatError, match="no match list"):
            fetch_league_matches("2025", requester=lambda url: {"teams": {}})


class TestFetchRun:
    def _requester(self, calls: list[str]):
        def request(url: str):
            calls.append(url)
            if "getLeagueData" in url:
                return {
                    "dates": [
                        {
                            "id": "29138",
                            "datetime": "2026-05-19 15:00:00",
                            "isResult": True,
                            "h": {"title": "Bournemouth"},
                            "a": {"title": "Manchester City"},
                        },
                        {
                            "id": "29999",
                            "datetime": "2026-05-24 15:00:00",
                            "isResult": False,
                            "h": {"title": "Fulham"},
                            "a": {"title": "Everton"},
                        },
                    ]
                }
            return _match_data()

        return request

    def test_only_played_matches_are_fetched(self) -> None:
        calls: list[str] = []
        result = fetch_player_match_logs(
            ["2025"],
            requester=self._requester(calls),
            sleep_seconds=0,
        )

        assert result.matches_fetched == 1
        assert result.not_played_yet == 1
        assert len(result.rows) == 2
        assert not any("29999" in url for url in calls)

    def test_a_held_match_is_never_refetched(self) -> None:
        calls: list[str] = []
        result = fetch_player_match_logs(
            ["2025"],
            requester=self._requester(calls),
            already_fetched=["29138"],
            sleep_seconds=0,
        )

        assert result.matches_fetched == 0
        assert result.already_had == 1
        assert result.rows == []

    def test_requests_are_spaced_out(self) -> None:
        sleeps: list[float] = []
        fetch_player_match_logs(
            ["2025"],
            requester=self._requester([]),
            sleep_seconds=1.5,
            sleeper=sleeps.append,
        )

        assert sleeps == [1.5]

    def test_a_bad_match_is_reported_and_skipped(self) -> None:
        def request(url: str):
            if "getLeagueData" in url:
                return {
                    "dates": [
                        {
                            "id": "1",
                            "datetime": "2026-05-19 15:00:00",
                            "isResult": True,
                            "h": {"title": "A"},
                            "a": {"title": "B"},
                        }
                    ]
                }
            return {"nothing": True}

        result = fetch_player_match_logs(
            ["2025"], requester=request, sleep_seconds=0
        )

        assert result.matches_fetched == 0
        assert len(result.errors) == 1
