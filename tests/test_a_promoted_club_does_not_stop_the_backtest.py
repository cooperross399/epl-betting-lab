"""A club with no rating yet is skipped and counted, never priced or fatal.

The first Matchday Refresh after PR #406 (2026-11-01) ran "Measure calibration
on the picks" and it died on the bought 2025/26 season's opening round:
Sunderland, promoted that summer, had no fitted rating, `PoissonGoalsModel`
refused to price them (`UnratedTeam`, by design), and the derived-market
backtest let that end the whole measurement. One unrated club cost every
market's trust weight. The backtest now leaves that fixture out, says how
many it left out, and measures the rest. It does not invent a league-average
side for them: no evidence, no price.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from epl_betting_lab.reports.derived_market_backtest import (
    MIN_TRAINING_MATCHES,
    BacktestResult,
    _score_matrix_bets,
)

TEAMS = [f"Club {i:02d}" for i in range(20)]


def _history() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    day = pd.Timestamp("2024-08-01")
    while len(rows) < MIN_TRAINING_MATCHES + 40:
        for h in range(20):
            for a in range(20):
                if h == a or len(rows) >= MIN_TRAINING_MATCHES + 40:
                    continue
                hg, ag = int(rng.poisson(1.5)), int(rng.poisson(1.2))
                rows.append(
                    {
                        "date": day,
                        "home_team": TEAMS[h],
                        "away_team": TEAMS[a],
                        "home_goals": hg,
                        "away_goals": ag,
                        "home_xg": hg + 0.1,
                        "away_xg": ag + 0.1,
                    }
                )
                day += pd.Timedelta(hours=6)
    return pd.DataFrame(rows)


def _odds(date: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for home, away in [(TEAMS[0], TEAMS[1]), ("Sunderland", TEAMS[2])]:
        for selection, price in [("Yes", -110), ("No", -110)]:
            rows.append(
                {
                    "date": date,
                    "home_team": home,
                    "away_team": away,
                    "market": "btts",
                    "selection": selection,
                    "american": price,
                    "book": "fanduel",
                }
            )
    return pd.DataFrame(rows)


def test_an_unrated_club_is_skipped_and_counted_not_fatal():
    matches = _history()
    when = matches["date"].max() + pd.Timedelta(days=3)
    result = BacktestResult()

    rows = _score_matrix_bets(_odds(when), matches, result)

    assert all("Sunderland" not in (r["home_team"], r["away_team"]) for r in rows)
    assert any("no fitted rating" in note and "1 fixture(s)" in note for note in result.notes), result.notes


def test_the_rated_fixture_on_the_same_day_is_still_priced():
    """Skipping must be per fixture, not per day: the day is the unit the walk
    forward fits on, and dropping the whole day would lose every rated match
    a promoted club happened to share a date with."""
    matches = _history()
    when = matches["date"].max() + pd.Timedelta(days=3)
    result = BacktestResult()

    import epl_betting_lab.reports.derived_market_backtest as backtest

    seen: list[pd.DataFrame] = []
    original = backtest.evaluate_btts

    def spy(projections, frame, **kwargs):
        seen.append(frame)
        return original(projections, frame, **kwargs)

    backtest.evaluate_btts = spy
    try:
        _score_matrix_bets(_odds(when), matches, result)
    finally:
        backtest.evaluate_btts = original

    assert seen, "the rated fixture never reached the BTTS rule"
    priced = pd.concat(seen)
    assert set(priced["home_team"]) == {TEAMS[0]}
