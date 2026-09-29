"""The live record divided by a denominator with the pushes taken out.

`derived_market_backtest` learned this and wrote it down: dropping pushes
removed 33 of 115 draw-no-bet selections and reported +7.1% for a rule that
returned +5.1%. CLAUDE.md carries the rule as "**A push is a bet.**"

`card_scoreboard` — the sibling that produces the record printed on the card
and in the email — kept doing it. A push was counted into `void` and left
with `won=None`, so `settled` excluded it and it reached neither
`staked_units` nor `profit_units`. The published ROI was profit over a
denominator that omitted every returned stake.

The two unsettleable branches beside it are NOT bets and stay out: a market
with no rule never resolves, and a missing corner count is a gap in the data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.reports.card_scoreboard import (
    ScoredSelection,
    Scoreboard,
    build_scoreboard,
    render_scoreboard,
)


def _card(picks: list[dict]) -> dict:
    return {
        "card_generated": True,
        "generated_at": "2026-09-20T09:00:00+00:00",
        "best_bets": picks,
        "leans": [],
    }


def _pick(market: str, selection: str, home: str, away: str) -> dict:
    return {
        "date": "2026-09-20",
        "home_team": home,
        "away_team": away,
        "market": market,
        "selection": selection,
        "american_odds": 100,
        "suggested_units": 1.0,
        "kickoff_time": "2026-09-20T14:00:00+00:00",
    }


def _results(rows: list[tuple[str, str, int, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-09-20"),
                "home_team": h,
                "away_team": a,
                "home_goals": hg,
                "away_goals": ag,
            }
            for h, a, hg, ag in rows
        ]
    )


class TestAPushCountsInTheDenominator:
    def _board(self) -> Scoreboard:
        """One winner and one draw-no-bet push, both staked a unit."""
        card = _card(
            [
                _pick("1x2", "home", "Arsenal", "Chelsea"),
                _pick("draw_no_bet", "home", "Spurs", "Everton"),
            ]
        )
        return build_scoreboard(
            [card],
            _results([("Arsenal", "Chelsea", 2, 1), ("Spurs", "Everton", 1, 1)]),
        )

    def test_the_push_is_settled_and_staked(self) -> None:
        board = self._board()

        assert board.void == 1, "the fixture did not produce a push"
        assert len(board.settled) == 2, (
            "the push is not in the settled sample, so the denominator "
            "omits a stake that was really down"
        )
        assert board.staked_units == pytest.approx(2.0)

    def test_the_roi_is_over_the_larger_denominator(self) -> None:
        """The whole point: the number the card prints."""
        board = self._board()

        # One winner at +100 returns +1.00u; the push returns 0.00u.
        assert board.profit_units == pytest.approx(1.0)
        assert board.roi == pytest.approx(0.5)

    def test_the_control_dropping_the_push_would_report_double(self) -> None:
        """Shows the inflation rather than describing it.

        With the push out of the denominator the same two selections read
        +100% instead of +50% — the shape that turned +5.1% into +7.1% in
        the backtest.
        """
        board = self._board()
        without = [s for s in board.settled if not s.pushed]

        assert sum(s.stake_units for s in without) == pytest.approx(1.0)
        assert board.profit_units / sum(s.stake_units for s in without) == (
            pytest.approx(1.0)
        )

    def test_an_unsettleable_row_stays_out(self) -> None:
        """A market with no rule never resolves; it is not a bet that pushed."""
        card = _card([_pick("corners_1x2", "home", "Arsenal", "Chelsea")])
        board = build_scoreboard([card], _results([("Arsenal", "Chelsea", 2, 1)]))

        assert board.unsettleable == 1
        assert board.settled == []
        assert board.staked_units == 0

    def test_the_record_says_the_push_was_counted(self) -> None:
        rendered = "\n".join(render_scoreboard(self._board()))

        assert "returned the stake" in rendered
        assert "a push is a bet" in rendered


def test_a_pushed_selection_reports_itself_settled() -> None:
    """The dataclass property, directly."""
    push = ScoredSelection(
        fixture_date="2026-09-20",
        home_team="Spurs",
        away_team="Everton",
        market="draw_no_bet",
        selection="home",
        american_odds=100,
        stake_units=1.0,
        first_seen="2026-09-19",
        pushed=True,
    )

    assert push.settled
    assert push.won is None
    assert push.profit_units == 0.0
