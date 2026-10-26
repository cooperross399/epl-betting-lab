"""The cup and European picks are graded, not only priced.

Every Beyond the Premier League selection has been recorded since the section
started (`archive/extra_cards/...`), and closing-line value has read them since
`beyond_clv`. Nothing ever asked whether one won. The card printed "N staked
selection(s) from that section are recorded and not yet scored — nothing
settles them" under every record, so the section's results taught nobody
anything.

ESPN's keyless scoreboards carry every Champions League, Europa League,
Conference League, EFL Cup and Nations League final with its score and its
corners. The selections settle against them by the same rules, through the
same `build_scoreboard`, as the Premier League card.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from epl_betting_lab.reports import beyond_record
from epl_betting_lab.reports.card_scoreboard import UncountedSection, render_scoreboard
from epl_betting_lab.reports.extra_competitions_card import (
    BEYOND_SECTION_NAME,
    uncounted_beyond,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _event(home: str, away: str, score: tuple[int, int], corners: tuple[int, int] = (6, 5),
           *, when: str = "2026-10-21T19:00Z", status: str = "STATUS_FULL_TIME",
           completed: bool = True) -> dict:
    def side(where: str, name: str, goals: int, won: int) -> dict:
        return {"homeAway": where, "score": str(goals), "team": {"displayName": name},
                "statistics": [{"name": "wonCorners", "displayValue": str(won)}]}

    return {
        "date": when,
        "status": {"type": {"completed": completed, "name": status}},
        "competitions": [{"competitors": [
            side("home", home, score[0], corners[0]), side("away", away, score[1], corners[1]),
        ]}],
    }


UCL = {"events": [
    _event("Paris Saint-Germain", "Internazionale", (2, 1)),
    _event("Arsenal", "Bayern Munich", (1, 1), when="2026-10-22T19:00Z"),
    _event("Liverpool", "Real Madrid", (1, 1), status="STATUS_FINAL_AET"),
    _event("Chelsea", "Barcelona", (0, 0), completed=False, when="2026-11-04T20:00Z"),
]}
EFLC = {"events": [
    _event("Barnet", "Newport County", (2, 2), status="STATUS_FINAL_PEN"),
]}


def _pick(home, away, market, selection, odds=110, competition="UCL", kickoff="2026-10-21T19:00:00+00:00"):
    return {"competition": competition, "home_team": home, "away_team": away, "market": market,
            "selection": selection, "american_odds": odds, "suggested_units": 0.1,
            "kickoff_time": kickoff}


def _record(*selections, generated="2026-10-20T08:00:00+00:00") -> dict:
    return {"generated_at": generated, "selections": list(selections)}


class TestReadingFinals:
    def test_names_corners_and_scores_come_through(self) -> None:
        finals = beyond_record.finals_from_scoreboard(UCL, "UCL")
        psg = finals[finals["home_team"] == "Paris SG"].iloc[0]
        assert psg["away_team"] == "Inter"
        assert (psg["home_goals"], psg["away_goals"], psg["HC"], psg["AC"]) == (2, 1, 6, 5)

    def test_a_tie_that_went_to_extra_time_is_not_a_ninety_minute_result(self) -> None:
        """Markets settle on ninety minutes; ESPN's score after extra time is not that."""
        finals = beyond_record.finals_from_scoreboard(UCL, "UCL")
        assert "Liverpool" not in set(finals["home_team"])
        assert ("Liverpool", "Real Madrid") in beyond_record.extra_time_fixtures(UCL, "UCL")

    def test_an_efl_cup_shootout_follows_ninety_minutes(self) -> None:
        """The EFL Cup goes straight to penalties, so the score is the ninety."""
        finals = beyond_record.finals_from_scoreboard(EFLC, "EFLC")
        assert len(finals) == 1 and finals.iloc[0]["home_goals"] == 2

    def test_an_unplayed_fixture_is_not_a_result(self) -> None:
        finals = beyond_record.finals_from_scoreboard(UCL, "UCL")
        assert "Chelsea" not in set(finals["home_team"])


class TestGrading:
    def _board(self, *picks):
        record = _record(*picks)
        return beyond_record.build_beyond_record(
            [record], {"UCL": [UCL], "EFLC": [EFLC]}, now=NOW
        )

    def test_picks_settle_by_the_card_rules(self) -> None:
        result = self._board(
            _pick("Paris SG", "Inter", "draw_no_bet", "home", 150),
            _pick("Paris SG", "Inter", "corners_total_10_5", "over", -110),
            _pick("Arsenal", "Bayern Munich", "draw_no_bet", "away", 120,
                  kickoff="2026-10-22T19:00:00+00:00"),
        )
        total = result.total
        assert len(total.settled) == 3
        assert sum(1 for s in total.settled if s.won) == 2  # DNB win, 11 corners over 10.5
        assert sum(1 for s in total.settled if s.pushed) == 1  # draw: stake back
        assert total.profit_units == pytest.approx(0.15 + 0.1 * 100 / 110)

    def test_each_competition_keeps_its_own_record(self) -> None:
        result = self._board(
            _pick("Paris SG", "Inter", "draw_no_bet", "home"),
            _pick("Barnet", "Newport County", "btts", "yes", competition="EFLC"),
        )
        assert set(result.by_competition) == {"UCL", "EFLC"}
        assert len(result.by_competition["EFLC"].settled) == 1

    def test_extra_time_is_counted_as_unsettleable_not_waiting(self) -> None:
        result = self._board(_pick("Liverpool", "Real Madrid", "total_2_5", "under"))
        assert result.total.awaiting_results == 0
        assert result.total.unsettleable == 1

    def test_a_pick_not_yet_played_is_pending(self) -> None:
        result = self._board(_pick("Chelsea", "Barcelona", "btts", "no",
                                   kickoff="2026-11-04T20:00:00+00:00"))
        assert result.total.pending == 1 and not result.total.settled

    def test_the_first_record_to_name_a_pick_is_the_one_graded(self) -> None:
        early = _record(_pick("Paris SG", "Inter", "draw_no_bet", "home", 150))
        late = _record(_pick("Paris SG", "Inter", "draw_no_bet", "home", -300),
                       generated="2026-10-21T08:00:00+00:00")
        result = beyond_record.build_beyond_record([early, late], {"UCL": [UCL]}, now=NOW)
        (settled,) = result.total.settled
        assert settled.american_odds == 150


class TestTheReport:
    def test_it_is_written_and_summarised(self, tmp_path) -> None:
        records = [_record(_pick("Paris SG", "Inter", "draw_no_bet", "home", 150))]
        payloads = {"UCL": [UCL]}
        beyond_record.save_beyond_record(
            records, tmp_path, fetch=lambda competition, years: payloads.get(competition, []), now=NOW
        )
        text = (tmp_path / beyond_record.REPORT_FILENAME).read_text()
        assert "UEFA Champions League" in text and "+0.15" in text
        summary = json.loads((tmp_path / beyond_record.SUMMARY_FILENAME).read_text())
        assert summary["settled"] == 1 and summary["won"] == 1
        assert summary["profit_units"] == pytest.approx(0.15)

    def test_espn_failing_writes_a_report_that_says_so(self, tmp_path) -> None:
        def broken(competition, years):
            raise beyond_record.BeyondResultsError("ESPN is down")

        records = [_record(_pick("Paris SG", "Inter", "draw_no_bet", "home"))]
        beyond_record.save_beyond_record(records, tmp_path, fetch=broken, now=NOW)
        text = (tmp_path / beyond_record.REPORT_FILENAME).read_text()
        assert "ESPN is down" in text
        assert not (tmp_path / beyond_record.SUMMARY_FILENAME).exists()


class TestTheCardSaysWhereTheRecordIs:
    def test_a_graded_section_prints_its_own_numbers(self, tmp_path) -> None:
        (tmp_path / "extra_competitions_card.json").write_text(json.dumps(
            {"selections": [{"suggested_units": 0.1}, {"suggested_units": 0.1}]}))
        (tmp_path / beyond_record.SUMMARY_FILENAME).write_text(json.dumps(
            {"settled": 7, "won": 4, "pushed": 1, "profit_units": 0.23}))
        section = uncounted_beyond(tmp_path)
        assert section.staked == 2 and section.settled == 7
        rendered = "\n".join(render_scoreboard(_settled_board(), uncounted=[section]))
        assert BEYOND_SECTION_NAME in rendered
        assert "7 settled" in rendered and "+0.23 units" in rendered
        assert "nothing settles them" not in rendered

    def test_an_ungraded_section_no_longer_claims_nothing_can_settle_it(self) -> None:
        rendered = "\n".join(render_scoreboard(
            _settled_board(), uncounted=[UncountedSection(BEYOND_SECTION_NAME, 5)]))
        assert "5 staked selection(s)" in rendered
        assert "nothing settles them" not in rendered


def _settled_board():
    from epl_betting_lab.reports.card_scoreboard import Scoreboard, ScoredSelection

    return Scoreboard(scored=[ScoredSelection(
        fixture_date="2026-09-20", home_team="Arsenal", away_team="Chelsea", market="1x2",
        selection="home", american_odds=-110, stake_units=1.0, first_seen="2026-09-19",
        won=True, profit_units=0.91)])
