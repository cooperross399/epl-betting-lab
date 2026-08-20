"""Does the corners model's stated probability match what actually happened?

Football-Data ships no historical corner prices, so profitability cannot be
backtested the way the goals markets are. What can be checked is the thing that
decides whether a model is worth pricing with at all: when it says 55%, does it
happen about 55% of the time?

The method is deliberately plain. Walk the seasons forward, fit only on matches
already played, predict the next match, and compare the predicted probability
against the result. Fitting on the whole dataset and then scoring it would
report how well the model remembers, not how well it predicts.

A calibrated model is not a profitable one. This says the numbers mean what
they claim, which is the precondition for asking whether there is an edge — not
a substitute for it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from epl_betting_lab.models.poisson_counts import PoissonCountModel


#: Probability bands to report. Wide enough that each holds enough matches for
#: the observed rate to mean something.
BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.3, "under 30%"),
    (0.3, 0.45, "30-45%"),
    (0.45, 0.55, "45-55%"),
    (0.55, 0.7, "55-70%"),
    (0.7, 1.01, "70% or higher"),
)

#: A bucket with fewer than this many matches is reported but not judged.
MIN_MATCHES_TO_JUDGE = 30


def _bucket(probability: float) -> str:
    for low, high, label in BUCKETS:
        if low <= probability < high:
            return label
    return BUCKETS[-1][2]


@dataclass
class CalibrationRow:
    bucket: str
    matches: int
    predicted: float
    observed: float

    @property
    def gap(self) -> float:
        return self.observed - self.predicted

    @property
    def judged(self) -> bool:
        return self.matches >= MIN_MATCHES_TO_JUDGE


def walk_forward_predictions(
    matches: pd.DataFrame,
    *,
    event: str,
    line: float,
    minimum_history: int = 200,
) -> pd.DataFrame:
    """Predicted P(total > line) beside what happened, one row per match.

    Each prediction is made from matches strictly before it. Refitting for
    every match would be honest and far too slow, so the model is refitted each
    time the season changes and used for the matches that follow — the same
    compromise the goals backtest makes.
    """
    home_column, away_column = PoissonCountModel.for_event(event).home_column, (
        PoissonCountModel.for_event(event).away_column
    )
    frame = matches.dropna(subset=[home_column, away_column]).copy()
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["actual_total"] = (
        pd.to_numeric(frame[home_column], errors="coerce")
        + pd.to_numeric(frame[away_column], errors="coerce")
    )
    frame = frame.dropna(subset=["actual_total"])

    rows: list[dict[str, object]] = []
    model: PoissonCountModel | None = None
    fitted_through = -1
    for index, match in frame.iterrows():
        if index < minimum_history:
            continue
        # Refit when the season turns, on everything played before this match.
        if model is None or match["season"] != fitted_through:
            history = frame.iloc[:index]
            if len(history) < minimum_history:
                continue
            model = PoissonCountModel.for_event(event).fit(history)
            fitted_through = match["season"]
        predicted = model.total_over_probability(
            match["home_team"], match["away_team"], line
        )
        rows.append(
            {
                "date": match["date"],
                "home_team": match["home_team"],
                "away_team": match["away_team"],
                "predicted_over": round(float(predicted), 4),
                "actual_total": float(match["actual_total"]),
                "went_over": bool(match["actual_total"] > line),
            }
        )
    return pd.DataFrame(rows)


def walk_forward_three_way(
    matches: pd.DataFrame,
    *,
    event: str,
    minimum_history: int = 200,
) -> pd.DataFrame:
    """Predicted P(home wins the count) beside what happened, per match.

    The same walk-forward discipline as the totals check, applied to the
    three-way. It is a different question from a total — a model can be well
    calibrated on "how many" and poorly calibrated on "which side" — so it
    needs measuring rather than assuming.
    """
    probe = PoissonCountModel.for_event(event)
    home_column, away_column = probe.home_column, probe.away_column
    frame = matches.dropna(subset=[home_column, away_column]).copy()
    frame = frame.sort_values("date").reset_index(drop=True)
    frame[home_column] = pd.to_numeric(frame[home_column], errors="coerce")
    frame[away_column] = pd.to_numeric(frame[away_column], errors="coerce")
    frame = frame.dropna(subset=[home_column, away_column])

    rows: list[dict[str, object]] = []
    model: PoissonCountModel | None = None
    fitted_through = None
    for index, match in frame.iterrows():
        if index < minimum_history:
            continue
        if model is None or match["season"] != fitted_through:
            history = frame.iloc[:index]
            if len(history) < minimum_history:
                continue
            model = PoissonCountModel.for_event(event).fit(history)
            fitted_through = match["season"]
        outcomes = model.match_probabilities(
            match["home_team"], match["away_team"]
        )
        rows.append(
            {
                "date": match["date"],
                "predicted_over": outcomes["home"],
                "went_over": bool(match[home_column] > match[away_column]),
            }
        )
    return pd.DataFrame(rows)


def summarize_calibration(predictions: pd.DataFrame) -> list[CalibrationRow]:
    """Predicted versus observed rate, by probability band."""
    if predictions.empty:
        return []
    frame = predictions.copy()
    frame["bucket"] = frame["predicted_over"].apply(_bucket)
    summary: list[CalibrationRow] = []
    for _, _, label in BUCKETS:
        group = frame[frame["bucket"] == label]
        if group.empty:
            continue
        summary.append(
            CalibrationRow(
                bucket=label,
                matches=int(len(group)),
                predicted=round(float(group["predicted_over"].mean()), 4),
                observed=round(float(group["went_over"].mean()), 4),
            )
        )
    return summary


def worst_gap(summary: Sequence[CalibrationRow]) -> float:
    """Largest predicted-versus-observed gap among bands big enough to judge."""
    judged = [row for row in summary if row.judged]
    if not judged:
        return 0.0
    return max(abs(row.gap) for row in judged)


def render_report(
    summary: Sequence[CalibrationRow], *, event: str, line: float
) -> str:
    lines = [
        f"# {event.title()} model calibration — over {line}",
        "",
        "Predictions are walk-forward: each one is made from matches played "
        "before it. Fitting on everything and then scoring it would report how "
        "well the model remembers, not how well it predicts.",
        "",
        "A calibrated model is not a profitable one. This says the numbers mean "
        "what they claim, which is what has to be true before asking whether "
        "there is an edge.",
        "",
        "| Predicted band | Matches | Mean predicted | Observed | Gap |",
        "|:---------------|--------:|---------------:|---------:|----:|",
    ]
    for row in summary:
        marker = "" if row.judged else " *"
        lines.append(
            f"| {row.bucket}{marker} | {row.matches} | {row.predicted:.1%} "
            f"| {row.observed:.1%} | {row.gap:+.1%} |"
        )
    lines += [
        "",
        f"\\* fewer than {MIN_MATCHES_TO_JUDGE} matches: reported, not judged.",
        "",
        f"Worst gap among judged bands: **{worst_gap(summary):.1%}**",
        "",
    ]
    return "\n".join(lines)
