"""Checking whether the corners model's probabilities mean what they say.

Football-Data ships no historical corner prices, so profitability cannot be
backtested the way the goals markets are. Calibration can be, and it is the
precondition: if the model says 55% and it happens 40% of the time, there is no
point asking whether there is an edge.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.reports.count_model_calibration import (
    MIN_MATCHES_TO_JUDGE,
    CalibrationRow,
    render_report,
    summarize_calibration,
    walk_forward_predictions,
    worst_gap,
)


def _matches(n: int = 600, corners: int = 5) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "date": pd.Timestamp("2021-08-01") + pd.Timedelta(days=i),
                "season": "2122" if i < n // 2 else "2223",
                "home_team": f"T{i % 20}",
                "away_team": f"T{(i + 1) % 20}",
                "HC": corners,
                "AC": corners,
            }
        )
    return pd.DataFrame(rows)


class TestWalkForward:
    def test_predictions_are_produced(self) -> None:
        predictions = walk_forward_predictions(
            _matches(), event="corners", line=9.5, minimum_history=100
        )
        assert not predictions.empty
        assert {"predicted_over", "went_over", "actual_total"} <= set(
            predictions.columns
        )

    def test_no_prediction_is_made_without_enough_history(self) -> None:
        predictions = walk_forward_predictions(
            _matches(n=50), event="corners", line=9.5, minimum_history=200
        )
        assert predictions.empty

    def test_the_actual_total_is_both_teams_added(self) -> None:
        predictions = walk_forward_predictions(
            _matches(corners=6), event="corners", line=9.5, minimum_history=100
        )
        assert predictions["actual_total"].iloc[0] == 12.0

    def test_the_outcome_is_judged_against_the_line(self) -> None:
        predictions = walk_forward_predictions(
            _matches(corners=6), event="corners", line=9.5, minimum_history=100
        )
        assert predictions["went_over"].all()

    def test_a_low_scoring_league_does_not_go_over(self) -> None:
        predictions = walk_forward_predictions(
            _matches(corners=2), event="corners", line=9.5, minimum_history=100
        )
        assert not predictions["went_over"].any()


class TestSummary:
    def _rows(self) -> list[CalibrationRow]:
        predictions = pd.DataFrame(
            {
                "predicted_over": [0.5] * 40 + [0.8] * 40,
                "went_over": [True] * 20 + [False] * 20 + [True] * 32 + [False] * 8,
            }
        )
        return summarize_calibration(predictions)

    def test_bands_are_summarised(self) -> None:
        summary = self._rows()
        assert {row.bucket for row in summary} == {"45-55%", "70% or higher"}

    def test_the_observed_rate_is_measured(self) -> None:
        summary = {row.bucket: row for row in self._rows()}
        assert summary["45-55%"].observed == pytest.approx(0.5)
        assert summary["70% or higher"].observed == pytest.approx(0.8)

    def test_a_gap_is_predicted_minus_observed(self) -> None:
        summary = {row.bucket: row for row in self._rows()}
        assert summary["45-55%"].gap == pytest.approx(0.0, abs=1e-6)

    def test_a_thin_band_is_reported_but_not_judged(self) -> None:
        predictions = pd.DataFrame(
            {"predicted_over": [0.5] * 5, "went_over": [True] * 5}
        )
        summary = summarize_calibration(predictions)

        assert summary[0].matches == 5
        assert summary[0].judged is False

    def test_a_thin_band_does_not_set_the_worst_gap(self) -> None:
        """Five matches disagreeing is noise, not evidence."""
        predictions = pd.DataFrame(
            {
                "predicted_over": [0.5] * MIN_MATCHES_TO_JUDGE + [0.8] * 3,
                "went_over": [True] * (MIN_MATCHES_TO_JUDGE // 2)
                + [False] * (MIN_MATCHES_TO_JUDGE // 2)
                + [False] * 3,
            }
        )
        summary = summarize_calibration(predictions)

        assert worst_gap(summary) < 0.1

    def test_no_predictions_summarise_to_nothing(self) -> None:
        assert summarize_calibration(pd.DataFrame()) == []

    def test_no_judged_band_yields_no_gap(self) -> None:
        assert worst_gap([]) == 0.0


class TestReport:
    def test_it_states_the_method(self) -> None:
        text = render_report([], event="corners", line=9.5)

        assert "walk-forward" in text
        assert "how well the model remembers" in text

    def test_it_says_calibration_is_not_profitability(self) -> None:
        """The distinction someone will otherwise assume away."""
        text = render_report([], event="corners", line=9.5)

        assert "A calibrated model is not a profitable one" in text

    def test_thin_bands_are_marked(self) -> None:
        rows = [CalibrationRow("45-55%", 5, 0.5, 0.9)]
        text = render_report(rows, event="corners", line=9.5)

        assert "*" in text
        assert "reported, not judged" in text


class TestThreeWayCalibration:
    """Being right about "how many" does not make a model right about "which side".

    A total and a three-way are different questions off the same fit, so the
    three-way needs its own measurement rather than inheriting the totals
    result.
    """

    def test_predictions_are_produced(self) -> None:
        from epl_betting_lab.reports.count_model_calibration import (
            walk_forward_three_way,
        )

        predictions = walk_forward_three_way(
            _matches(), event="corners", minimum_history=100
        )

        assert not predictions.empty
        assert {"predicted_over", "went_over"} <= set(predictions.columns)

    def test_the_outcome_is_whether_home_won_the_count(self) -> None:
        from epl_betting_lab.reports.count_model_calibration import (
            walk_forward_three_way,
        )

        frame = _matches()
        frame["HC"] = 9
        frame["AC"] = 2
        predictions = walk_forward_three_way(
            frame, event="corners", minimum_history=100
        )

        assert predictions["went_over"].all()

    def test_equal_counts_are_not_a_home_win(self) -> None:
        """A drawn corner count is its own outcome, not a home win."""
        from epl_betting_lab.reports.count_model_calibration import (
            walk_forward_three_way,
        )

        predictions = walk_forward_three_way(
            _matches(corners=5), event="corners", minimum_history=100
        )

        assert not predictions["went_over"].any()

    def test_too_little_history_yields_nothing(self) -> None:
        from epl_betting_lab.reports.count_model_calibration import (
            walk_forward_three_way,
        )

        predictions = walk_forward_three_way(
            _matches(n=50), event="corners", minimum_history=200
        )

        assert predictions.empty
