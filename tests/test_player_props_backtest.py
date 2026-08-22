"""The props measurement: walk-forward, book-style voids, loud about gaps."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from epl_betting_lab.reports.player_props_backtest import (
    build_player_props_backtest,
    save_player_props_backtest,
    _implied_probability,
    _player_key,
    _team_key,
)


ODDS_FIELDS = [
    "sampled_at",
    "commence_time",
    "home_team",
    "away_team",
    "market",
    "player",
    "selection",
    "american",
]

LOG_FIELDS = [
    "season",
    "date",
    "match_id",
    "team",
    "opponent",
    "venue",
    "player",
    "player_id",
    "position",
    "minutes",
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "yellow_cards",
    "red_cards",
    "first_goal_minute",
]


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return path


def _log_row(
    player: str,
    date: str,
    match_id: str,
    *,
    team: str = "Arsenal",
    opponent: str = "Chelsea",
    venue: str = "home",
    minutes: int = 90,
    shots_on_target: int = 3,
    goals: int = 0,
) -> dict:
    return {
        "season": "2025",
        "date": date,
        "match_id": match_id,
        "team": team,
        "opponent": opponent,
        "venue": venue,
        "player": player,
        "player_id": _player_key(player).replace(" ", ""),
        "position": "FW",
        "minutes": minutes,
        "goals": goals,
        "assists": 0,
        "shots": shots_on_target + 1,
        "shots_on_target": shots_on_target,
        "yellow_cards": 0,
        "red_cards": 0,
        "first_goal_minute": "",
    }


def _training_logs() -> list[dict]:
    """Enough history in January for the model to hold opinions in May.

    A star with 3 SOT every match, and a chorus line of teammates and
    opponents so baselines and factors exist.
    """
    rows = []
    for m in range(10):
        date = f"2026-01-{m + 1:02d}"
        rows.append(_log_row("Star Striker", date, f"t{m}", shots_on_target=3))
        for p in range(8):
            rows.append(
                _log_row(
                    f"Squad Player {p}",
                    date,
                    f"t{m}",
                    shots_on_target=1,
                    team="Arsenal" if p % 2 == 0 else "Chelsea",
                    opponent="Chelsea" if p % 2 == 0 else "Arsenal",
                    venue="home" if p % 2 == 0 else "away",
                )
            )
    for m in range(460):
        date = f"2026-0{m % 3 + 1}-{m % 28 + 1:02d}"
        rows.append(
            _log_row(
                f"Filler {m}",
                date,
                f"f{m}",
                team="Everton",
                opponent="Fulham",
                shots_on_target=1,
            )
        )
    return rows


def _odds_row(
    *,
    date: str = "2026-05-09",
    home: str = "Arsenal",
    away: str = "Chelsea",
    market: str = "player_shots_on_target",
    player: str = "Star Striker",
    selection: str = "Over@0.5",
    american: float = 150,
) -> dict:
    return {
        "sampled_at": f"{date}T11:00:00Z",
        "commence_time": f"{date}T14:00:00Z",
        "home_team": home,
        "away_team": away,
        "market": market,
        "player": player,
        "selection": selection,
        "american": american,
    }


def _build(tmp_path: Path, odds: list[dict], logs: list[dict], **kwargs):
    odds_path = _write_csv(tmp_path / "odds.csv", ODDS_FIELDS, odds)
    logs_path = _write_csv(tmp_path / "logs.csv", LOG_FIELDS, logs)
    return build_player_props_backtest(
        odds_path=odds_path, logs_path=logs_path, **kwargs
    )


class TestSettlement:
    def test_a_cleared_edge_that_hit_is_a_win(self, tmp_path: Path) -> None:
        logs = _training_logs()
        logs.append(
            _log_row("Star Striker", "2026-05-09", "m1", shots_on_target=2)
        )
        summary = _build(tmp_path, [_odds_row()], logs)

        assert len(summary["bets"]) == 1
        bet = summary["bets"][0]
        assert bet["outcome"] == "won"
        assert bet["profit"] == pytest.approx(1.5)

    def test_a_cleared_edge_that_missed_is_a_loss(self, tmp_path: Path) -> None:
        logs = _training_logs()
        logs.append(
            _log_row("Star Striker", "2026-05-09", "m1", shots_on_target=0)
        )
        summary = _build(tmp_path, [_odds_row()], logs)

        bet = summary["bets"][0]
        assert bet["outcome"] == "lost"
        assert bet["profit"] == -1.0

    def test_a_player_who_never_entered_voids(self, tmp_path: Path) -> None:
        """Books return the stake on a DNP; a measurement that counted it as
        a loss would punish the model for squad rotation."""
        logs = _training_logs()  # no May 9 appearance for the star
        summary = _build(tmp_path, [_odds_row()], logs)

        bet = summary["bets"][0]
        assert bet["outcome"] == "void"
        assert bet["profit"] == 0.0
        market = summary["per_market"]["player_shots_on_target"]
        assert market["voids"] == 1
        assert market["settled"] == 0

    def test_below_the_edge_threshold_no_bet_is_counted(
        self, tmp_path: Path
    ) -> None:
        logs = _training_logs()
        logs.append(
            _log_row("Star Striker", "2026-05-09", "m1", shots_on_target=2)
        )
        # At -2000 the implied probability is ~95%; no model clears that.
        summary = _build(
            tmp_path, [_odds_row(american=-2000)], logs
        )

        assert summary["bets"] == []
        assert summary["priced_outcomes"] == 1


class TestWalkForward:
    def test_without_enough_prior_history_nothing_is_priced(
        self, tmp_path: Path
    ) -> None:
        """The model never reads a result it is being scored on — and a
        fixture earlier than the history is not scored at all."""
        logs = _training_logs()
        early = _odds_row(date="2026-01-02")
        summary = _build(tmp_path, [early], logs)

        assert summary["priced_outcomes"] == 0
        assert summary["bets"] == []


class TestLoudGaps:
    def test_an_unmapped_team_is_reported_not_guessed(
        self, tmp_path: Path
    ) -> None:
        summary = _build(
            tmp_path,
            [_odds_row(home="Real Madrid")],
            _training_logs(),
        )

        assert summary["bets"] == []
        assert any("Real Madrid" in item for item in summary["unmatched_teams"])

    def test_an_unknown_player_is_reported_not_guessed(
        self, tmp_path: Path
    ) -> None:
        summary = _build(
            tmp_path,
            [_odds_row(player="Nobody Atall")],
            _training_logs(),
        )

        assert summary["bets"] == []
        assert "Nobody Atall" in summary["unmatched_players"]

    def test_a_playerless_odds_file_is_refused(self, tmp_path: Path) -> None:
        odds_path = _write_csv(
            tmp_path / "odds.csv",
            [f for f in ODDS_FIELDS if f != "player"],
            [],
        )
        logs_path = _write_csv(tmp_path / "logs.csv", LOG_FIELDS, [])

        with pytest.raises(KeyError, match="player"):
            build_player_props_backtest(odds_path=odds_path, logs_path=logs_path)

    def test_missing_files_are_refused(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_player_props_backtest(
                odds_path=tmp_path / "absent.csv",
                logs_path=tmp_path / "also_absent.csv",
            )


class TestIdentity:
    def test_player_keys_survive_accents_and_hyphens(self) -> None:
        assert _player_key("Benjamin Šeško") == _player_key("Benjamin Sesko")
        assert _player_key("Heung-Min Son") == _player_key("Heung Min Son")

    def test_player_keys_survive_letters_accents_cannot_explain(self) -> None:
        """ø, æ and friends are whole letters, not base-plus-accent; NFKD
        leaves them alone and \"Nørgaard\" never met \"Norgaard\"."""
        assert _player_key("Christian Nørgaard") == _player_key(
            "Christian Norgaard"
        )
        assert _player_key("Łukasz Fabiański") == _player_key(
            "Lukasz Fabianski"
        )

    def test_a_books_longer_name_resolves_to_the_squad_player(
        self, tmp_path: Path
    ) -> None:
        """Books append surnames Understat omits, or quote the surname
        alone; either direction of containment resolves when exactly one
        squad player fits."""
        logs = _training_logs()
        logs.append(
            _log_row("Star Striker", "2026-05-09", "m1", shots_on_target=2)
        )
        summary = _build(
            tmp_path,
            [_odds_row(player="Star Striker Noom Quomah")],
            logs,
        )

        assert len(summary["bets"]) == 1
        assert summary["unmatched_players"] == []

    def test_an_ambiguous_short_name_stays_unmatched(
        self, tmp_path: Path
    ) -> None:
        logs = _training_logs()
        logs.append(_log_row("Thiago Silva", "2026-01-11", "amb1"))
        logs.append(_log_row("Bernardo Silva", "2026-01-11", "amb2"))
        summary = _build(tmp_path, [_odds_row(player="Silva")], logs)

        assert summary["bets"] == []
        assert "Silva" in summary["unmatched_players"]

    def test_both_spellings_of_a_team_share_a_key(self) -> None:
        assert _team_key("Wolverhampton Wanderers") == _team_key("Wolves")
        assert _team_key("Nott'm Forest") == _team_key("Nottingham Forest")
        assert _team_key("Sporting Lisbon") == ""

    def test_implied_probability_matches_the_price(self) -> None:
        assert _implied_probability(100) == pytest.approx(0.5)
        assert _implied_probability(300) == pytest.approx(0.25)
        assert _implied_probability(-150) == pytest.approx(0.6)


class TestCalibration:
    def test_every_settled_outcome_calibrates_bet_or_not(
        self, tmp_path: Path
    ) -> None:
        """Forty bets prove nothing; the probability-outcome pairs are where
        the sample has power, so even a no-edge outcome is counted."""
        logs = _training_logs()
        logs.append(
            _log_row("Star Striker", "2026-05-09", "m1", shots_on_target=2)
        )
        # -2000 offers no edge, so no bet — but the outcome still settles.
        summary = _build(tmp_path, [_odds_row(american=-2000)], logs)

        assert summary["bets"] == []
        assert summary["settled_calibration_samples"] == 1
        buckets = summary["calibration"]["all"]
        assert sum(b["n"] for b in buckets) == 1
        assert summary["calibration"]["player_shots_on_target"]

    def test_a_void_never_calibrates(self, tmp_path: Path) -> None:
        summary = _build(tmp_path, [_odds_row()], _training_logs())

        assert summary["settled_calibration_samples"] == 0


class TestReports:
    def test_the_saved_report_names_every_caveat(self, tmp_path: Path) -> None:
        logs = _training_logs()
        logs.append(
            _log_row("Star Striker", "2026-05-09", "m1", shots_on_target=2)
        )
        odds_path = _write_csv(tmp_path / "odds.csv", ODDS_FIELDS, [_odds_row()])
        logs_path = _write_csv(tmp_path / "logs.csv", LOG_FIELDS, logs)

        result = save_player_props_backtest(
            output_dir=tmp_path / "out",
            odds_path=odds_path,
            logs_path=logs_path,
        )
        markdown = Path(result["markdown"]).read_text(encoding="utf-8")

        assert "one-sided" in markdown
        assert "Understat definition" in markdown
        assert "calibration-grade" in markdown
        assert Path(result["json"]).is_file()
        assert Path(result["csv"]).is_file()
