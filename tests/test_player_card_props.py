"""Cards, tackles and goalkeeper saves: priced, held by policy until approved.

Cooper, 2026-10-19: "dont forget about tackles/cards/goalie saves", then
"bovada has tackles under player props" and "find goalie saves figure it
out". Guessed keys found nothing; the provider's own event-markets listing
found all three: `player_to_receive_card` / `player_to_receive_red_card`
(Bovada, DraftKings), `player_tackles_alternate` (BetMGM, Caesars,
DraftKings), and `player_goalie_saves` / `player_goalie_saves_alternate`
(DraftKings, Fanatics).

Cards are rated from the Understat logs' yellow and red cards. Tackles and
saves are in no log this lab had; Fantasy Premier League publishes both per
match (Opta's numbers, keyless), so `providers/fpl_players` reads them and
the same per-player model fits them, with last season's totals as extra
evidence. Every ladder is one outcome: only its best rung is staked.

The model's warning about cards stands and is printed with them: bookings
cluster and the referee, the strongest driver, is not in the data. The
held-out correction was fitted on the four volume markets only, so card
probabilities are uncorrected rather than borrowed from markets they are not.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.models.player_props import CARD_STATS, PlayerPropsModel
from epl_betting_lab.providers.player_props_staging import (
    PROP_EVENT_MARKETS,
    extract_prop_rows,
)
from epl_betting_lab.reports.player_props_backtest import SETTLEMENT_COLUMNS
from epl_betting_lab.reports.player_props_card import (
    HELD_STATUS,
    READY_STATUS,
    UNCORRECTED_MARKETS,
    approved_prop_markets,
)

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The props-card fixtures, read from their own file rather than imported as a
# package (tests/ has no __init__.py).
_fixtures = _load("props_card_fixtures", ROOT / "tests" / "test_player_props_card.py")
STAGING_FIELDS = _fixtures.STAGING_FIELDS
RUN_AT = _fixtures.RUN_AT
_build = _fixtures._build
_logs = _fixtures._logs
_policy = _fixtures._policy
_staging_row = _fixtures._staging_row
_write_csv = _fixtures._write_csv
CARD_MARKETS = ("player_to_receive_card", "player_to_receive_red_card")


def _row(player, match, *, yellow=0, red=0, team="Newcastle", opponent="Everton"):
    return {
        "player": player, "team": team, "opponent": opponent, "venue": "home",
        "position": "MC", "minutes": 90, "date": f"2026-08-{match + 1:02d}",
        "match_id": f"m{match}", "shots": 1, "shots_on_target": 0, "goals": 0,
        "assists": 0, "yellow_cards": yellow, "red_cards": red,
    }


def _league() -> pd.DataFrame:
    rows = []
    for m in range(20):
        rows.append(_row("Hothead", m, yellow=1 if m % 2 == 0 else 0, red=1 if m == 3 else 0))
        rows.append(_row("Saint", m))
        for p in range(4):
            rows.append(_row(f"Other {p}", m, yellow=1 if m % 5 == p else 0,
                             team="Everton", opponent="Newcastle"))
    return pd.DataFrame(rows)


class TestModel:
    def test_card_stats_are_bookings_and_dismissals(self) -> None:
        assert CARD_STATS == ("booked", "sent_off")

    def test_a_player_booked_often_is_likelier_to_be_booked(self) -> None:
        model = PlayerPropsModel().fit(_league())
        hot = model.over_probability("Hothead", "booked", 0.5, opponent="Everton", venue="home")
        clean = model.over_probability("Saint", "booked", 0.5, opponent="Everton", venue="home")
        assert hot is not None and clean is not None
        assert hot > clean
        assert 0.0 < clean < hot < 1.0

    def test_a_second_yellow_is_one_booking_not_two(self) -> None:
        """Booked is a yes/no per match: two yellows and a red settle one Yes."""
        frame = _league()
        frame.loc[frame["player"] == "Hothead", "yellow_cards"] = 2
        model = PlayerPropsModel().fit(frame)
        lam = model.expected_count("Hothead", "booked", opponent="Everton", venue="home")
        assert lam is not None and lam <= 1.0 + 1e-9

    def test_sent_off_reads_red_cards(self) -> None:
        model = PlayerPropsModel().fit(_league())
        hot = model.over_probability("Hothead", "sent_off", 0.5, opponent="Everton", venue="home")
        clean = model.over_probability("Saint", "sent_off", 0.5, opponent="Everton", venue="home")
        assert hot > clean

    def test_logs_without_cards_still_fit_and_hold_no_card_opinion(self) -> None:
        frame = _league().drop(columns=["yellow_cards", "red_cards"])
        model = PlayerPropsModel().fit(frame)
        assert model.over_probability("Hothead", "shots", 0.5, opponent="Everton", venue="home")
        assert model.over_probability("Hothead", "booked", 0.5, opponent="Everton", venue="home") is None


class TestStagingAndSettlement:
    def test_both_card_markets_are_fetched_and_kept(self) -> None:
        for market in CARD_MARKETS:
            assert market in PROP_EVENT_MARKETS
        event = {
            "id": "e1", "commence_time": "2026-10-25T14:00:00Z",
            "home_team": "Newcastle United", "away_team": "Liverpool",
            "bookmakers": [{"title": "Bovada", "markets": [{
                "key": "player_to_receive_card",
                "outcomes": [{"name": "Yes", "description": "Bruno Guimaraes", "price": 260}],
            }]}],
        }
        (row,) = extract_prop_rows(event, fetched_at="now")
        assert (row["market"], row["player"], row["selection"]) == (
            "player_to_receive_card", "Bruno Guimaraes", "Yes",
        )

    def test_cards_settle_on_the_derived_columns(self) -> None:
        assert SETTLEMENT_COLUMNS["player_to_receive_card"] == "booked"
        assert SETTLEMENT_COLUMNS["player_to_receive_red_card"] == "sent_off"


def _booking_logs(tmp_path: Path) -> Path:
    path = _logs(tmp_path)
    frame = pd.read_csv(path, dtype=str)
    isak = frame["player"] == "Alexander Isak"
    frame.loc[isak, "yellow_cards"] = "1"
    frame.to_csv(path, index=False)
    return path


class TestCard:
    def test_an_approved_card_market_prices_the_yes_side_uncorrected(
        self, tmp_path: Path
    ) -> None:
        from epl_betting_lab.reports.player_props_card import build_player_props_card

        summary = build_player_props_card(
            props_staging_path=_write_csv(
                tmp_path / "props.csv", STAGING_FIELDS,
                [_staging_row(market="player_to_receive_card", selection="Yes", american_odds=250)],
            ),
            logs_path=_booking_logs(tmp_path),
            policy_path=_policy(tmp_path / "policy.json", ["player_to_receive_card"]),
            run_at=RUN_AT,
        )
        assert summary["status"] == READY_STATUS
        (pick,) = summary["picks"]
        assert pick["market"] == "player_to_receive_card"
        assert pick["selection"] == "Yes"
        assert pick["units"] == 0.1
        assert "player_to_receive_card" in UNCORRECTED_MARKETS
        # Booked in every one of twelve matches: no correction pulls it down.
        assert pick["model_probability"] > 0.6

    def test_held_card_prices_are_reported_beside_approved_props(
        self, tmp_path: Path
    ) -> None:
        """The staged-but-held list is what a card approval binds to, even
        while the four volume props are already approved."""
        summary = _build(
            tmp_path,
            markets=["player_shots_on_target"],
            staging_rows=[
                _staging_row(),
                _staging_row(market="player_to_receive_card", selection="Yes"),
            ],
        )
        assert summary["status"] == READY_STATUS
        assert summary["markets_with_staged_prices"] == [
            "player_shots_on_target", "player_to_receive_card",
        ]
        assert "player_to_receive_card" in summary["held_prop_markets"]
        assert {p["market"] for p in summary["picks"]} == {"player_shots_on_target"}

    def test_held_by_policy_still_names_staged_cards(self, tmp_path: Path) -> None:
        summary = _build(
            tmp_path, markets=["1x2"],
            staging_rows=[_staging_row(market="player_to_receive_red_card", selection="Yes")],
        )
        assert summary["status"] == HELD_STATUS
        assert summary["markets_with_staged_prices"] == ["player_to_receive_red_card"]


def _board():
    return _load("build_board_json_cards", ROOT / "web" / "build_board_json.py")


@pytest.mark.parametrize(
    ("market", "key"),
    [("player_to_receive_card", "booked"), ("player_to_receive_red_card", "sent_off")],
)
def test_card_picks_reach_the_board_as_over_half(market: str, key: str) -> None:
    board = _board()
    pick = {
        "home_team": "Newcastle", "away_team": "Liverpool", "market": market,
        "player": "Bruno Guimaraes", "team": "Newcastle", "selection": "Yes",
        "model_probability": 0.4, "edge": 0.1, "american_odds": 250.0,
        "book": "Bovada", "units": 0.1,
    }
    block = board.props_block({"status": "Props card ready", "picks": [pick]},
                              {("Newcastle", "Liverpool"): "g1"})
    (row,) = block["rows"]
    assert (row["market"], row["line"], row["side"]) == (key, 0.5, "over")


def test_the_page_names_the_card_markets() -> None:
    text = (ROOT / "web" / "lib" / "sports.js").read_text(encoding="utf-8")
    assert 'booked: { title: "Booked", one: "card", many: "cards" }' in text
    assert 'sent_off: { title: "Sent off", one: "red card", many: "red cards" }' in text


# ----- tackles and saves, from Fantasy Premier League -----

from epl_betting_lab.models.player_props import FPL_STATS  # noqa: E402
from epl_betting_lab.providers.fpl_players import (  # noqa: E402
    build_fpl_logs,
    build_fpl_prior,
)

NEW_MARKETS = (
    "player_to_receive_card",
    "player_to_receive_red_card",
    "player_tackles_alternate",
    "player_goalie_saves",
    "player_goalie_saves_alternate",
)


def _bootstrap() -> dict:
    return {
        "teams": [{"id": 1, "name": "Spurs"}, {"id": 2, "name": "Newcastle"}],
        "element_types": [
            {"id": 1, "singular_name_short": "GKP"},
            {"id": 2, "singular_name_short": "DEF"},
        ],
        "elements": [
            {"id": 10, "first_name": "Destiny", "second_name": "Udogie", "team": 1, "element_type": 2},
            {"id": 11, "first_name": "Guglielmo", "second_name": "Vicario", "team": 1, "element_type": 1},
            {"id": 20, "first_name": "Nick", "second_name": "Pope", "team": 2, "element_type": 1},
        ],
    }


def _history(fixture, *, home, opponent, tackles=0, saves=0, minutes=90, yellow=0):
    return {
        "fixture": fixture, "opponent_team": opponent, "was_home": home,
        "kickoff_time": f"2026-09-{fixture:02d}T14:00:00Z", "minutes": minutes,
        "tackles": tackles, "saves": saves, "yellow_cards": yellow, "red_cards": 0,
    }


def _summaries() -> dict:
    return {
        10: {"history": [_history(m, home=m % 2 == 0, opponent=2, tackles=4) for m in range(1, 9)],
             "history_past": [{"season_name": "2025/26", "minutes": 2700, "tackles": 90, "saves": 0}]},
        11: {"history": [_history(m, home=m % 2 == 0, opponent=2, saves=3) for m in range(1, 9)],
             "history_past": []},
        20: {"history": [_history(m, home=m % 2 == 1, opponent=1, saves=4) for m in range(1, 9)]
                        + [_history(9, home=True, opponent=1, minutes=0)],
             "history_past": [{"season_name": "2024/25", "minutes": 3000, "saves": 100}]},
    }


class TestFantasyPremierLeague:
    def test_logs_carry_tackles_and_saves_per_appearance(self) -> None:
        logs = build_fpl_logs(_bootstrap(), _summaries())
        udogie = logs[logs["player"] == "Destiny Udogie"]
        assert len(udogie) == 8
        row = udogie.iloc[0]
        assert row["team"] == "Tottenham" and row["opponent"] == "Newcastle"
        assert row["position"] == "DEF" and int(row["tackles"]) == 4
        assert set(FPL_STATS) <= set(logs.columns)
        # An unused substitute is not an appearance.
        assert len(logs[logs["player"] == "Nick Pope"]) == 8

    def test_the_prior_is_last_season_only(self) -> None:
        prior = build_fpl_prior(_bootstrap(), _summaries(), season="2025/26")
        assert list(prior["player"]) == ["Destiny Udogie"]
        assert float(prior.iloc[0]["tackles"]) == 90.0

    def test_a_keeper_is_priced_on_saves_and_a_defender_on_tackles(self) -> None:
        logs = build_fpl_logs(_bootstrap(), _summaries())
        model = PlayerPropsModel(stats=FPL_STATS).fit(logs)
        pope = model.over_probability("Nick Pope", "saves", 2.5, opponent="Tottenham", venue="home")
        udogie = model.over_probability("Destiny Udogie", "tackles", 1.5, opponent="Newcastle", venue="away")
        assert pope is not None and pope > 0.4
        assert udogie is not None and udogie > 0.4

    def test_last_season_moves_a_short_record(self) -> None:
        logs = build_fpl_logs(_bootstrap(), _summaries())
        prior = build_fpl_prior(_bootstrap(), _summaries(), season="2025/26")
        plain = PlayerPropsModel(stats=FPL_STATS).fit(logs)
        informed = PlayerPropsModel(stats=FPL_STATS).fit(logs, prior=prior)
        # Four tackles a match now, three a match last season: the prior
        # pulls the rate toward three, never past it.
        a = plain.players["Destiny Udogie"].per90["tackles"]
        b = informed.players["Destiny Udogie"].per90["tackles"]
        assert b != a


def _fpl_logs_file(tmp_path: Path) -> Path:
    path = tmp_path / "fpl_logs.csv"
    build_fpl_logs(_bootstrap(), _summaries()).to_csv(path, index=False)
    return path


class TestTacklesAndSavesOnTheCard:
    def _card(self, tmp_path, rows, markets):
        from epl_betting_lab.reports.player_props_card import build_player_props_card

        return build_player_props_card(
            props_staging_path=_write_csv(tmp_path / "props.csv", STAGING_FIELDS, rows),
            logs_path=_logs(tmp_path),
            fpl_logs_path=_fpl_logs_file(tmp_path),
            policy_path=_policy(tmp_path / "policy.json", markets),
            run_at=RUN_AT,
        )

    def test_a_tackles_ladder_stakes_one_rung_under_the_books_spelling(
        self, tmp_path: Path
    ) -> None:
        rows = [
            _staging_row(home_team="Tottenham", away_team="Newcastle",
                         market="player_tackles_alternate", player="Iyenoma Destiny Udogie",
                         selection=f"Over@{line}", american_odds=odds, book="DraftKings")
            for line, odds in ((0.5, 150), (1.5, 200), (2.5, 300))
        ]
        summary = self._card(tmp_path, rows, ["player_tackles_alternate"])
        assert summary["status"] == READY_STATUS
        (pick,) = summary["picks"]
        assert pick["player"] == "Iyenoma Destiny Udogie"
        assert pick["team"] == "Tottenham"
        assert pick["market"] == "player_tackles_alternate"

    def test_both_saves_markets_are_one_outcome(self, tmp_path: Path) -> None:
        rows = [
            _staging_row(home_team="Tottenham", away_team="Newcastle",
                         market="player_goalie_saves", player="Nick Pope",
                         selection="Over@2.5", american_odds=200, book="DraftKings"),
            _staging_row(home_team="Tottenham", away_team="Newcastle",
                         market="player_goalie_saves_alternate", player="Nick Pope",
                         selection="Over@1.5", american_odds=150, book="Fanatics"),
        ]
        summary = self._card(tmp_path, rows, ["player_goalie_saves", "player_goalie_saves_alternate"])
        assert len(summary["picks"]) == 1
        assert summary["picks"][0]["team"] == "Newcastle"

    def test_without_fpl_logs_tackles_get_no_opinion(self, tmp_path: Path) -> None:
        from epl_betting_lab.reports.player_props_card import build_player_props_card

        summary = build_player_props_card(
            props_staging_path=_write_csv(tmp_path / "props.csv", STAGING_FIELDS, [
                _staging_row(home_team="Tottenham", away_team="Newcastle",
                             market="player_tackles_alternate", player="Destiny Udogie",
                             selection="Over@0.5", american_odds=300)]),
            logs_path=_logs(tmp_path),
            fpl_logs_path=tmp_path / "absent.csv",
            policy_path=_policy(tmp_path / "policy.json", ["player_tackles_alternate"]),
            run_at=RUN_AT,
        )
        assert summary["picks"] == []


def test_every_new_market_is_fetched_settled_and_held() -> None:
    for market in NEW_MARKETS:
        assert market in PROP_EVENT_MARKETS
        assert market in SETTLEMENT_COLUMNS
    assert SETTLEMENT_COLUMNS["player_tackles_alternate"] == "tackles"
    assert SETTLEMENT_COLUMNS["player_goalie_saves"] == "saves"
    assert SETTLEMENT_COLUMNS["player_goalie_saves_alternate"] == "saves"
    approved = approved_prop_markets()
    assert not set(NEW_MARKETS) & set(approved)


@pytest.mark.parametrize(
    ("market", "key"),
    [("player_tackles_alternate", "tackles"), ("player_goalie_saves", "goalie_saves"),
     ("player_goalie_saves_alternate", "goalie_saves")],
)
def test_tackles_and_saves_reach_the_board(market: str, key: str) -> None:
    board = _board()
    pick = {
        "home_team": "Newcastle", "away_team": "Liverpool", "market": market,
        "player": "Nick Pope", "team": "Newcastle", "selection": "Over@2.5",
        "model_probability": 0.5, "edge": 0.1, "american_odds": 150.0,
        "book": "DraftKings", "units": 0.1,
    }
    block = board.props_block({"status": "Props card ready", "picks": [pick]},
                              {("Newcastle", "Liverpool"): "g1"})
    (row,) = block["rows"]
    assert (row["market"], row["line"]) == (key, 2.5)


def test_the_page_names_tackles() -> None:
    text = (ROOT / "web" / "lib" / "sports.js").read_text(encoding="utf-8")
    assert 'tackles: { title: "Tackles", one: "tackle", many: "tackles" }' in text


def test_the_fpl_logs_are_fetched_only_for_tackles_or_saves() -> None:
    from epl_betting_lab.reports.player_props_card import needs_fpl_logs

    assert not needs_fpl_logs(["player_shots", "player_to_receive_card"])
    assert needs_fpl_logs(["player_shots", "player_goalie_saves"])
    assert needs_fpl_logs(["player_tackles_alternate"])


def test_a_prop_is_never_priced_at_a_book_that_cannot_be_bet(tmp_path: Path) -> None:
    """ReBet and Courtside carry these markets and are not on
    `books.BETTABLE_BOOKS`. The props card took the best price across every
    staged book, so a ReBet price could have been the one on the card."""
    rows = [
        _staging_row(american_odds=400, book="ReBet"),
        _staging_row(american_odds=150, book="FanDuel"),
    ]
    summary = _build(tmp_path, markets=["player_shots_on_target"], staging_rows=rows)
    (pick,) = summary["picks"]
    assert pick["book"] == "FanDuel"


def test_only_unbettable_prices_make_no_pick(tmp_path: Path) -> None:
    rows = [_staging_row(american_odds=400, book="Courtside")]
    summary = _build(tmp_path, markets=["player_shots_on_target"], staging_rows=rows)
    assert summary["picks"] == []
