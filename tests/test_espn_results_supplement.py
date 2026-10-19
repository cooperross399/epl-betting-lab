"""Finished fixtures reach the model before Football-Data publishes them.

The ratings and the card's record both read one file,
`epl_historical_matches.csv`, and until 2026-10-19 only Football-Data wrote
it. Football-Data publishes a round some time after it is played: on Monday
2026-10-19 at 12:42 UTC it still held 60 of the season's matches while ESPN
had 69 finals, so the 17-18 October round taught the ratings nothing and the
record showed twelve played picks as "waiting on results data".

ESPN's public scoreboard carries the score, the corners and the shots for
every final. Those rows fill the gap, and Football-Data's own row replaces
each one as soon as it is published.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from epl_betting_lab.data import espn_results
from epl_betting_lab.reports.card_scoreboard import build_scoreboard


def _competitor(side: str, name: str, team_id: str, score: int, corners: int) -> dict:
    return {
        "homeAway": side,
        "score": str(score),
        "team": {"id": team_id, "displayName": name},
        "statistics": [
            {"name": "wonCorners", "displayValue": str(corners)},
            {"name": "totalShots", "displayValue": "12"},
            {"name": "shotsOnTarget", "displayValue": "5"},
            {"name": "foulsCommitted", "displayValue": "9"},
        ],
    }


def _event(
    event_id: str,
    kickoff: str,
    home: str,
    away: str,
    score: tuple[int, int],
    corners: tuple[int, int] = (5, 3),
    *,
    completed: bool = True,
    season: int = 2026,
) -> dict:
    return {
        "id": event_id,
        "date": kickoff,
        "season": {"year": season},
        "status": {
            "type": {
                "completed": completed,
                "name": "STATUS_FULL_TIME" if completed else "STATUS_SCHEDULED",
            }
        },
        "competitions": [
            {
                "competitors": [
                    _competitor("home", home, "1", score[0], corners[0]),
                    _competitor("away", away, "2", score[1], corners[1]),
                ]
            }
        ],
    }


def _football_data_row(home: str, away: str, when: str, hg: int, ag: int) -> dict:
    return {
        "season": "2627",
        "Div": "E0",
        "Date": pd.Timestamp(when).strftime("%d/%m/%Y"),
        "HomeTeam": home,
        "AwayTeam": away,
        "FTHG": hg,
        "FTAG": ag,
        "FTR": "H" if hg > ag else "A" if ag > hg else "D",
        "HC": 4,
        "AC": 4,
        "AvgCH": 2.1,
        "date": when,
        "home_team": home,
        "away_team": away,
        "home_goals": hg,
        "away_goals": ag,
        "result": "H" if hg > ag else "A" if ag > hg else "D",
    }


SCOREBOARD = {
    "events": [
        # Published by Football-Data already: its row must win.
        _event("1", "2026-10-11T14:00Z", "Arsenal", "Chelsea", (2, 1)),
        # The round Football-Data has not published yet.
        _event("2", "2026-10-18T13:00Z", "AFC Bournemouth", "Sunderland", (2, 0), (5, 3)),
        _event("3", "2026-10-18T15:30Z", "Nottingham Forest", "Arsenal", (0, 1), (2, 7)),
        # Not played yet.
        _event("4", "2026-10-19T19:00Z", "Everton", "Fulham", (0, 0), completed=False),
        # Last season's fixture in the same calendar year.
        _event("5", "2026-05-24T15:00Z", "Liverpool", "Brentford", (3, 0), season=2025),
    ]
}


class TestReadingFinals:
    def test_only_completed_fixtures_of_the_season_become_rows(self) -> None:
        rows = espn_results.finals_from_scoreboard(SCOREBOARD, season_year=2026)
        assert sorted(rows["home_team"]) == ["Arsenal", "Bournemouth", "Nott'm Forest"]

    def test_rows_carry_the_columns_the_model_and_the_record_read(self) -> None:
        rows = espn_results.finals_from_scoreboard(SCOREBOARD, season_year=2026)
        forest = rows[rows["home_team"] == "Nott'm Forest"].iloc[0]
        assert forest["away_team"] == "Arsenal"
        assert (forest["home_goals"], forest["away_goals"]) == (0, 1)
        assert (forest["FTHG"], forest["FTAG"], forest["FTR"]) == (0, 1, "A")
        assert (forest["HC"], forest["AC"]) == (2, 7)
        assert forest["Div"] == "E0"
        assert forest["season"] == "2627"
        assert forest["result_source"] == "espn"

    def test_the_date_is_the_uk_date_football_data_and_understat_use(self) -> None:
        """A 20:00 London kick-off is 19:00 UTC in October; one at 23:30 UTC
        would be the next UK day. The xG join is on the date."""
        late = {"events": [_event("9", "2026-10-18T23:30Z", "Leeds United", "Wolves", (1, 1))]}
        rows = espn_results.finals_from_scoreboard(late, season_year=2026)
        assert str(rows.iloc[0]["date"])[:10] == "2026-10-19"

    def test_card_counts_are_left_blank_rather_than_guessed(self) -> None:
        """Football-Data's HY/AY are what the card markets were measured on.
        ESPN's booking events are not the same count in every case (a second
        yellow), so the card markets wait for Football-Data."""
        rows = espn_results.finals_from_scoreboard(SCOREBOARD, season_year=2026)
        assert rows["HY"].isna().all() and rows["AY"].isna().all()

    def test_an_unmapped_club_is_reported_not_coerced(self) -> None:
        odd = {"events": [_event("8", "2026-10-18T13:00Z", "Atletico Nowhere", "Arsenal", (1, 0))]}
        rows = espn_results.finals_from_scoreboard(odd, season_year=2026)
        assert rows.empty


class TestFillingTheGap:
    def _dataset(self) -> pd.DataFrame:
        return pd.DataFrame(
            [_football_data_row("Arsenal", "Chelsea", "2026-10-11", 3, 3)]
        )

    def test_missing_finals_are_added_and_published_ones_are_not(self) -> None:
        finals = espn_results.finals_from_scoreboard(SCOREBOARD, season_year=2026)
        merged, added = espn_results.supplement(self._dataset(), finals)
        assert added == 2
        assert len(merged) == 3
        arsenal = merged[merged["home_team"] == "Arsenal"].iloc[0]
        # Football-Data's own row, untouched: its score and its closing price.
        assert (arsenal["home_goals"], arsenal["away_goals"]) == (3, 3)
        assert arsenal["AvgCH"] == 2.1

    def test_football_data_replaces_an_earlier_espn_row(self) -> None:
        """A file restored from a previous run already holds ESPN rows. Once
        Football-Data publishes the fixture, its row is the only one left."""
        finals = espn_results.finals_from_scoreboard(SCOREBOARD, season_year=2026)
        first, _ = espn_results.supplement(self._dataset(), finals)
        published = pd.concat(
            [
                first,
                pd.DataFrame(
                    [_football_data_row("Bournemouth", "Sunderland", "2026-10-18", 2, 0)]
                ),
            ],
            ignore_index=True,
        )
        merged, added = espn_results.supplement(published, finals)
        bournemouth = merged[merged["home_team"] == "Bournemouth"]
        assert len(bournemouth) == 1
        assert bournemouth.iloc[0]["result_source"] != "espn"
        assert added == 1  # Forest v Arsenal only

    def test_running_twice_adds_nothing_twice(self) -> None:
        finals = espn_results.finals_from_scoreboard(SCOREBOARD, season_year=2026)
        once, _ = espn_results.supplement(self._dataset(), finals)
        twice, _ = espn_results.supplement(once, finals)
        assert len(twice) == len(once) == 3

    def test_no_finals_leaves_the_dataset_exactly_as_it_was(self) -> None:
        dataset = self._dataset()
        merged, added = espn_results.supplement(dataset, espn_results.empty_finals())
        assert added == 0
        pd.testing.assert_frame_equal(
            merged.reset_index(drop=True)[dataset.columns], dataset
        )


class TestTheRecordSettlesFromIt:
    def test_a_played_pick_settles_before_football_data_publishes(self) -> None:
        """The symptom of 2026-10-19: played, and still waiting on results."""
        card = {
            "card_generated": True,
            "generated_at": "2026-10-17T08:00:00+00:00",
            "best_bets": [
                {
                    "home_team": "Nott'm Forest",
                    "away_team": "Arsenal",
                    "market": "corners_total_9_5",
                    "selection": "under",
                    "american_odds": -110,
                    "suggested_units": 0.1,
                    "kickoff_time": "2026-10-18T15:30:00Z",
                }
            ],
        }
        now = datetime(2026, 10, 19, 12, 42, tzinfo=timezone.utc)
        before = build_scoreboard([card], _round_trip(TestFillingTheGap()._dataset()), now=now)
        assert before.awaiting_results == 1

        finals = espn_results.finals_from_scoreboard(SCOREBOARD, season_year=2026)
        merged, _ = espn_results.supplement(TestFillingTheGap()._dataset(), finals)
        after = build_scoreboard([card], _round_trip(merged), now=now)
        assert after.awaiting_results == 0
        (entry,) = [s for s in after.scored if s.home_team == "Nott'm Forest"]
        assert entry.won is True  # 2 + 7 = 9 corners, under 9.5


def _round_trip(frame: pd.DataFrame) -> pd.DataFrame:
    """As the record reads it: written to CSV and loaded back."""
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"])
    return out


class TestTheScriptIsSoft:
    def test_an_espn_failure_leaves_the_file_untouched(self, tmp_path, monkeypatch) -> None:
        path = tmp_path / "epl_historical_matches.csv"
        TestFillingTheGap()._dataset().to_csv(path, index=False)
        before = path.read_bytes()

        def broken(url: str):
            raise espn_results.EspnResultsError("ESPN is down")

        status = espn_results.supplement_file(path, season_code="2627", request=broken)
        assert status.added == 0 and status.error
        assert path.read_bytes() == before

    def test_a_missing_dataset_is_not_invented(self, tmp_path) -> None:
        path = tmp_path / "epl_historical_matches.csv"
        status = espn_results.supplement_file(
            path, season_code="2627", request=lambda url: SCOREBOARD
        )
        assert status.error and not path.exists()

    def test_the_file_gains_the_round(self, tmp_path) -> None:
        path = tmp_path / "epl_historical_matches.csv"
        TestFillingTheGap()._dataset().to_csv(path, index=False)
        asked: list[str] = []

        def request(url: str):
            asked.append(url)
            return SCOREBOARD

        status = espn_results.supplement_file(path, season_code="2627", request=request)
        assert status.added == 2 and not status.error
        written = pd.read_csv(path)
        assert len(written) == 3
        # One scoreboard per calendar year the season spans; no key, no quota.
        assert all("site.api.espn.com" in url for url in asked)
        assert any("dates=2026" in url for url in asked)
        assert any("dates=2027" in url for url in asked)


@pytest.mark.parametrize(
    "code,year", [("2627", 2026), ("2526", 2025), ("2122", 2021)]
)
def test_season_code_to_espn_year(code: str, year: int) -> None:
    assert espn_results.espn_season_year(code) == year


def test_an_empty_answer_keeps_earlier_rows_but_never_beside_football_data() -> None:
    dataset = TestFillingTheGap()._dataset()
    finals = espn_results.finals_from_scoreboard(SCOREBOARD, season_year=2026)
    first, _ = espn_results.supplement(dataset, finals)
    published = pd.concat(
        [first, pd.DataFrame([_football_data_row("Bournemouth", "Sunderland", "2026-10-18", 2, 0)])],
        ignore_index=True,
    )
    merged, added = espn_results.supplement(published, espn_results.empty_finals())
    assert added == 1
    assert len(merged[merged["home_team"] == "Bournemouth"]) == 1
    assert len(merged[merged["home_team"] == "Nott'm Forest"]) == 1
