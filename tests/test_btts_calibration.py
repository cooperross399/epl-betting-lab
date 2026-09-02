"""BTTS is priced on the ratings that remove its measured bias.

BTTS has no historical prices at any source this project can reach, so no bet
rule on it can ever be profit-backtested. Calibration against outcomes is the
only measurement it admits — and docs/why_better_calibration_lost_money.md is
the record of that measurement authorising a change that cost 140 units. These
tests pin the distinction that makes this change different: the threshold-free
scores move with the calibration rather than against it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from epl_betting_lab.models.poisson_goals import BTTS_RATINGS, CARD_RATINGS, TOTALS_RATINGS
from epl_betting_lab.reports.btts_calibration import (
    BANDS,
    MIN_BAND_MATCHES,
    RatingsUnderTest,
    calibration_table,
    render_markdown,
)


def _frame(predicted, observed):
    return pd.DataFrame({"predicted": predicted, "observed": observed})


def test_btts_uses_the_opponent_adjusted_xg_ratings_not_the_legacy_ones():
    assert BTTS_RATINGS.opponent_adjusted and BTTS_RATINGS.goal_source == "blend"
    assert BTTS_RATINGS != CARD_RATINGS
    # Same configuration the 2.5 line uses, but named separately so either
    # market can move without dragging the other.
    assert BTTS_RATINGS == TOTALS_RATINGS


def test_the_gap_is_observed_minus_predicted_so_a_positive_gap_means_understating():
    """Direction matters: understating BTTS-yes manufactures false `no` edges."""
    table = calibration_table(_frame([0.5] * 40, [1.0] * 40), "under")
    assert table[table.band == "ALL"].gap_points.iloc[0] == 50.0
    table = calibration_table(_frame([0.5] * 40, [0.0] * 40), "over")
    assert table[table.band == "ALL"].gap_points.iloc[0] == -50.0


def test_the_all_row_carries_the_threshold_free_scores():
    """Brier and log loss are what separate 'more right' from 'says less'.

    A shrinkage improves calibration by making the model less committal and
    leaves these flat or worse. Better ratings carry them along. Without these
    columns the report could not tell the two apart, which is the whole reason
    the earlier fix looked good.
    """
    table = calibration_table(_frame([0.6] * 50, [1.0] * 50), "x")
    row = table[table.band == "ALL"].iloc[0]
    assert not np.isnan(row.brier) and not np.isnan(row.logloss)
    band_rows = table[table.band != "ALL"]
    assert band_rows.brier.isna().all()


def test_thin_bands_are_dropped_rather_than_reported():
    """A band with a handful of matches is noise wearing a percentage sign."""
    predicted = [0.35] * (MIN_BAND_MATCHES - 1) + [0.5] * 40
    table = calibration_table(_frame(predicted, [1.0] * len(predicted)), "x")
    assert "30-45%" not in set(table.band)
    assert "45-55%" in set(table.band)


def test_the_bands_match_the_document_they_will_be_read_against():
    assert (0.30, 0.45) in BANDS and (0.45, 0.55) in BANDS and (0.55, 0.70) in BANDS


def test_the_report_says_calibration_alone_cannot_authorise_a_change():
    text = render_markdown(calibration_table(_frame([0.5] * 40, [1.0] * 40), "x"))
    assert "must never authorise" in text
    assert "why_better_calibration_lost_money" in text


def test_ratings_under_test_carries_the_legacy_window():
    """The legacy configuration is only itself with its 38-match window."""
    legacy = RatingsUnderTest("legacy", CARD_RATINGS, last_n_matches_per_team=38)
    assert legacy.last_n_matches_per_team == 38
    assert RatingsUnderTest("new", BTTS_RATINGS).last_n_matches_per_team is None
