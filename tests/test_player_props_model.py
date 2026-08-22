"""Per-player Poisson rates: shrunk, minutes-aware, and silent off-evidence."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from epl_betting_lab.models.player_props import (
    PROP_STATS,
    PlayerPropsModel,
    _position_group,
)


def _appearance(
    player: str,
    *,
    match_id: str,
    team: str = "Arsenal",
    opponent: str = "Chelsea",
    venue: str = "home",
    position: str = "FW",
    minutes: int = 90,
    shots: int = 0,
    shots_on_target: int = 0,
    goals: int = 0,
    assists: int = 0,
    date: str = "2026-01-01",
) -> dict:
    return {
        "player": player,
        "team": team,
        "opponent": opponent,
        "venue": venue,
        "position": position,
        "minutes": minutes,
        "shots": shots,
        "shots_on_target": shots_on_target,
        "goals": goals,
        "assists": assists,
        "date": date,
        "match_id": match_id,
    }


def _logs(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _league(rows_per_player: int = 12, shots: int = 2) -> list[dict]:
    """A flat league of forwards, so baselines are known exactly."""
    rows = []
    for p in range(8):
        for m in range(rows_per_player):
            rows.append(
                _appearance(
                    f"Baseline {p}",
                    match_id=f"m{p}-{m}",
                    team=f"Team {p}",
                    opponent=f"Opp {p}",
                    venue="home" if m % 2 == 0 else "away",
                    shots=shots,
                    shots_on_target=1,
                    goals=0,
                    assists=0,
                    date=f"2026-01-{m + 1:02d}",
                )
            )
    return rows


class TestFit:
    def test_missing_columns_fail_closed(self) -> None:
        with pytest.raises(KeyError, match="missing columns"):
            PlayerPropsModel().fit(pd.DataFrame({"player": ["A"]}))

    def test_a_short_record_stays_near_the_baseline(self) -> None:
        """One hot match must not make a player a 6-shot machine."""
        rows = _league()
        rows.append(
            _appearance("Hot Streak", match_id="hot1", shots=6, minutes=90)
        )
        model = PlayerPropsModel().fit(_logs(rows))

        rate = model.players["Hot Streak"].per90["shots"]
        baseline = model.baselines["F"]["shots"]
        # 90 minutes of evidence keeps 90/(90+900) = ~9% of the deviation.
        assert baseline < rate < baseline + 0.15 * (6.0 - baseline)

    def test_a_long_record_keeps_most_of_its_deviation(self) -> None:
        rows = _league()
        for m in range(30):
            rows.append(
                _appearance(
                    "Proven Volume",
                    match_id=f"pv{m}",
                    shots=5,
                    date=f"2026-02-{m % 28 + 1:02d}",
                )
            )
        model = PlayerPropsModel().fit(_logs(rows))

        rate = model.players["Proven Volume"].per90["shots"]
        baseline = model.baselines["F"]["shots"]
        # 2700 minutes keeps 75% of the deviation.
        assert rate > baseline + 0.7 * (5.0 - baseline)

    def test_substitute_appearances_group_by_the_named_position(self) -> None:
        rows = _league()
        rows.append(_appearance("Mixed", match_id="x1", position="FW"))
        rows.append(_appearance("Mixed", match_id="x2", position="Sub"))
        rows.append(_appearance("Mixed", match_id="x3", position="FW"))
        model = PlayerPropsModel().fit(_logs(rows))

        assert model.players["Mixed"].group == "F"

    def test_position_groups_read_the_first_letters(self) -> None:
        assert _position_group("FW") == "F"
        assert _position_group("MC") == "M"
        assert _position_group("DR") == "D"
        assert _position_group("GK") == "GK"
        assert _position_group("Sub") == ""


class TestPricing:
    def test_below_minimum_minutes_there_is_no_opinion(self) -> None:
        """League baseline is the honest rate for an unknown player, but a
        prop priced purely on "average forward" is not a modelled opinion —
        the model stays silent rather than staking it."""
        rows = _league()
        rows.append(_appearance("Two Games", match_id="t1", shots=3))
        rows.append(
            _appearance("Two Games", match_id="t2", shots=3, date="2026-01-02")
        )
        model = PlayerPropsModel().fit(_logs(rows))

        assert (
            model.expected_count(
                "Two Games", "shots", opponent="Chelsea", venue="home"
            )
            is None
        )
        assert (
            model.over_probability(
                "Unknown Player", "shots", 1.5, opponent="Chelsea", venue="home"
            )
            is None
        )

    def test_the_over_probability_is_the_poisson_tail(self) -> None:
        rows = _league()
        model = PlayerPropsModel().fit(_logs(rows))
        player = "Baseline 0"
        lam = model.expected_count(
            player, "shots", opponent="Nowhere FC", venue="home"
        )
        expected = 1.0 - math.exp(-lam) * (1.0 + lam)

        probability = model.over_probability(
            player, "shots", 1.5, opponent="Nowhere FC", venue="home"
        )

        assert probability == pytest.approx(expected, abs=1e-9)

    def test_anytime_scorer_is_over_half_a_goal(self) -> None:
        rows = _league()
        for m in range(12):
            rows.append(
                _appearance(
                    "Finisher",
                    match_id=f"f{m}",
                    goals=1,
                    shots=3,
                    date=f"2026-03-{m + 1:02d}",
                )
            )
        model = PlayerPropsModel().fit(_logs(rows))

        anytime = model.anytime_scorer_probability(
            "Finisher", opponent="Nowhere FC", venue="home"
        )
        over_half = model.over_probability(
            "Finisher", "goals", 0.5, opponent="Nowhere FC", venue="home"
        )

        assert anytime == over_half
        assert 0.0 < anytime < 1.0

    def test_a_leaky_opponent_raises_the_expectation(self) -> None:
        rows = _league()
        # One team concedes double the league's shots, every match.
        for m in range(20):
            rows.append(
                _appearance(
                    f"Visitor {m}",
                    match_id=f"leak{m}",
                    team="Various",
                    opponent="Sieve United",
                    shots=4,
                    date=f"2026-04-{m % 28 + 1:02d}",
                )
            )
        model = PlayerPropsModel().fit(_logs(rows))
        player = "Baseline 0"

        versus_sieve = model.expected_count(
            player, "shots", opponent="Sieve United", venue="home"
        )
        versus_unknown = model.expected_count(
            player, "shots", opponent="Nowhere FC", venue="home"
        )

        assert versus_sieve > versus_unknown

    def test_an_unknown_stat_is_refused(self) -> None:
        model = PlayerPropsModel().fit(_logs(_league()))

        with pytest.raises(KeyError, match="Unknown prop stat"):
            model.expected_count(
                "Baseline 0", "nutmegs", opponent="Chelsea", venue="home"
            )

    def test_every_priced_stat_is_a_log_column(self) -> None:
        from epl_betting_lab.providers.understat_players import LOG_FIELDS

        for stat in PROP_STATS:
            assert stat in LOG_FIELDS
