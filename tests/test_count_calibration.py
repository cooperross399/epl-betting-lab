"""The corner markets are measured, because nothing else can measure them.

Corners are 23 of the first 42 best bets — the majority of the card — and no
source retains their historical prices, so no corner rule can ever be
profit-backtested. Their whole validation was synthetic unit tests plus six
real-data checks that are `@needs_dataset`-skipped and never run in CI, and
those check the fit against league averages rather than whether a stated
probability happens that often.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from epl_betting_lab.reports.count_calibration import (
    BANDS,
    MIN_BAND_MATCHES,
    _outcome,
    calibration_table,
    render_markdown,
    walk_forward_counts,
)
from epl_betting_lab.strategies.count_markets import UNAVAILABLE_MARKETS


def test_the_three_way_corner_outcome_reads_the_counts_not_the_goals():
    assert _outcome("corners_1x2", 7, 3) == {"home": 1.0, "draw": 0.0, "away": 0.0}
    assert _outcome("corners_1x2", 5, 5) == {"home": 0.0, "draw": 1.0, "away": 0.0}


def test_corner_totals_settle_on_the_combined_count_and_cannot_push():
    over = _outcome("corners_total_9_5", 6, 4)
    assert over == {"over": 1.0, "under": 0.0}
    under = _outcome("corners_total_10_5", 5, 5)
    assert under == {"over": 0.0, "under": 1.0}


def test_markets_no_book_offers_are_not_measured():
    """Cards are modelled and unavailable; measuring them would be noise."""
    frame = walk_forward_counts(_matches(), start_after_matches=40, stride=20)
    assert not frame.empty
    assert set(frame.market) & UNAVAILABLE_MARKETS == set()


def _matches(n=120, seed=3):
    rng = np.random.default_rng(seed)
    teams = ["A", "B", "C", "D"]
    rows = []
    for i in range(n):
        home, away = teams[i % 4], teams[(i + 1) % 4]
        rows.append({
            "date": pd.Timestamp("2024-08-01") + pd.Timedelta(days=i),
            "home_team": home, "away_team": away,
            "home_goals": rng.poisson(1.4), "away_goals": rng.poisson(1.1),
            "HC": rng.poisson(5.5), "AC": rng.poisson(4.5),
            "HY": rng.poisson(1.8), "AY": rng.poisson(2.0),
            "HR": 0, "AR": 0,
        })
    return pd.DataFrame(rows)


def test_a_walk_forward_prediction_only_ever_sees_its_own_past():
    """The whole measurement is worthless if a fit can see the match it scores."""
    frame = walk_forward_counts(_matches(), start_after_matches=40, stride=20)
    assert not frame.empty
    assert set(frame.columns) == {"market", "selection", "predicted", "observed"}
    assert frame.predicted.between(0, 1).all()
    assert frame.observed.isin([0.0, 1.0]).all()


def test_thin_bands_are_dropped_and_the_all_row_carries_the_scores():
    frame = pd.DataFrame({
        "market": ["corners_1x2"] * 40,
        "selection": ["home"] * 40,
        "predicted": [0.5] * 40,
        "observed": [1.0] * 20 + [0.0] * 20,
    })
    table = calibration_table(frame)
    row = table[table.band == "ALL"].iloc[0]
    assert not np.isnan(row.brier) and not np.isnan(row.logloss)
    assert row.gap_points == 0.0
    assert MIN_BAND_MATCHES == 20 and (0.45, 0.55) in BANDS


def test_the_report_refuses_to_let_calibration_authorise_a_stake():
    """No profit backtest exists here to overrule a good calibration number."""
    table = calibration_table(pd.DataFrame({
        "market": ["corners_1x2"] * 30, "selection": ["home"] * 30,
        "predicted": [0.4] * 30, "observed": [0.0] * 30,
    }))
    text = render_markdown(table)
    assert "reason to" in text and "stake less" in text
    assert "why_better_calibration_lost_money" in text
    assert "no prices are involved" in text.lower()


def test_an_empty_frame_produces_an_empty_table_not_a_crash():
    assert calibration_table(pd.DataFrame()).empty
