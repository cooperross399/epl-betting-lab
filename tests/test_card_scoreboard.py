"""Scoring the cards that were actually issued.

`bet_ledger.csv` has a header and no rows. Settlement is preview-only. Nothing
has ever recorded how a recommendation turned out, so every claim about whether
this works rests on a backtest of seasons already in the file — in-sample by
definition.

This scores the cards rather than what anyone bet: no manual entry, and it is
the honest measure of the model anyway.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.reports.card_scoreboard import (
    build_scoreboard,
    first_recommendations,
    render_scoreboard,
    settle,
)


def _pick(**over) -> dict:
    row = {
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "market": "1x2",
        "selection": "home",
        "american_odds": 150.0,
        "suggested_units": 0.25,
    }
    row.update(over)
    return row


def _card(generated: str, picks: list[dict], generated_ok: bool = True) -> dict:
    return {
        "card_generated": generated_ok,
        "generated_at": generated,
        "best_bets": picks,
        "leans": [],
    }


def _results(rows: list[tuple[str, str, str, int, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": pd.Timestamp(d), "home_team": h, "away_team": a,
             "home_goals": hg, "away_goals": ag}
            for d, h, a, hg, ag in rows
        ]
    )


class TestSettlement:
    @pytest.mark.parametrize(
        "market,selection,hg,ag,expected",
        [
            ("1x2", "home", 2, 1, True),
            ("1x2", "draw", 1, 1, True),
            ("1x2", "away", 2, 1, False),
            ("btts", "yes", 1, 1, True),
            ("btts", "no", 3, 0, True),
            ("total_2_5", "over", 2, 1, True),
            ("total_2_5", "under", 1, 1, True),
            ("double_chance", "home_or_draw", 1, 1, True),
            ("double_chance", "draw_or_away", 2, 1, False),
            ("double_chance", "home_or_away", 1, 1, False),
            ("draw_no_bet", "home", 2, 1, True),
            ("draw_no_bet", "away", 2, 1, False),
        ],
    )
    def test_markets_settle_correctly(self, market, selection, hg, ag, expected) -> None:
        assert settle(market, selection, hg, ag) is expected

    def test_a_draw_voids_draw_no_bet(self) -> None:
        """Stake returned. Neither a win nor a loss."""
        assert settle("draw_no_bet", "home", 1, 1) is None

    def test_an_unknown_market_is_not_guessed(self) -> None:
        assert settle("corners_1x2", "home", 2, 1) is None


class TestWhichPriceIsScored:
    def test_the_first_card_to_name_a_selection_wins(self) -> None:
        """Taking the latest would score a price nobody could act on first."""
        cards = [
            _card("2026-08-20T13:00:00+00:00", [_pick(american_odds=150.0)]),
            _card("2026-08-21T13:00:00+00:00", [_pick(american_odds=180.0)]),
        ]
        picks = first_recommendations(cards)

        assert len(picks) == 1
        assert picks[0]["american_odds"] == 150.0

    def test_a_lean_is_not_a_recommendation(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00", [_pick(suggested_units=0.0)])]

        assert first_recommendations(cards) == []

    def test_a_blocked_card_contributes_nothing(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00", [_pick()], generated_ok=False)]

        assert first_recommendations(cards) == []


class TestTheResultMustFollowTheCard:
    """The same fixture pairing recurs every season.

    Matching on team names alone scored a card for 21 August 2026 against
    Newcastle versus Liverpool from 25 August 2025, and returned a confident
    nought for five — the kind of wrong number that looks like a finding.
    """

    def test_an_earlier_season_does_not_settle_a_later_card(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00", [_pick()])]
        results = _results([("2025-08-25", "Arsenal", "Chelsea", 0, 3)])

        board = build_scoreboard(cards, results)

        assert board.pending == 1
        assert board.settled == []

    def test_a_result_after_the_card_settles_it(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00", [_pick()])]
        results = _results([("2026-08-22", "Arsenal", "Chelsea", 2, 1)])

        board = build_scoreboard(cards, results)

        assert len(board.settled) == 1
        assert board.settled[0].won is True

    def test_the_first_result_after_the_card_is_the_one_meant(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00", [_pick()])]
        results = _results([
            ("2027-01-10", "Arsenal", "Chelsea", 0, 1),
            ("2026-08-22", "Arsenal", "Chelsea", 2, 1),
        ])

        board = build_scoreboard(cards, results)

        assert board.settled[0].fixture_date == "2026-08-22"


class TestProfit:
    def test_a_winning_plus_price_pays_the_odds(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00",
                       [_pick(american_odds=150.0, suggested_units=0.25)])]
        board = build_scoreboard(cards, _results([("2026-08-22","Arsenal","Chelsea",2,1)]))

        assert board.profit_units == pytest.approx(0.375)

    def test_a_winning_minus_price_pays_less_than_the_stake(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00",
                       [_pick(american_odds=-200.0, suggested_units=0.5)])]
        board = build_scoreboard(cards, _results([("2026-08-22","Arsenal","Chelsea",2,1)]))

        assert board.profit_units == pytest.approx(0.25)

    def test_a_loss_costs_the_stake(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00", [_pick(suggested_units=0.25)])]
        board = build_scoreboard(cards, _results([("2026-08-22","Arsenal","Chelsea",0,1)]))

        assert board.profit_units == pytest.approx(-0.25)

    def test_roi_is_measured_on_turnover(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00",
                       [_pick(american_odds=100.0, suggested_units=0.5)])]
        board = build_scoreboard(cards, _results([("2026-08-22","Arsenal","Chelsea",2,1)]))

        assert board.roi == pytest.approx(1.0)

    def test_nothing_settled_has_no_roi(self) -> None:
        board = build_scoreboard([], pd.DataFrame())

        assert board.roi is None


class TestReport:
    def test_pending_only_says_so_rather_than_showing_zero(self) -> None:
        cards = [_card("2026-08-20T13:00:00+00:00", [_pick()])]
        board = build_scoreboard(cards, pd.DataFrame())
        text = " ".join(render_scoreboard(board))

        assert "Nothing settled yet" in text
        assert "1 selection(s) are waiting" in text

    def test_it_says_how_long_this_will_take_to_mean_anything(self) -> None:
        """A running total invites over-reading. It should say so itself."""
        cards = [_card("2026-08-20T13:00:00+00:00", [_pick()])]
        board = build_scoreboard(cards, _results([("2026-08-22","Arsenal","Chelsea",2,1)]))
        text = " ".join(render_scoreboard(board))

        assert "out-of-sample" in text
        assert "1,500 settled bets" in text

    def test_an_empty_board_renders_nothing(self) -> None:
        assert render_scoreboard(build_scoreboard([], pd.DataFrame())) == []
