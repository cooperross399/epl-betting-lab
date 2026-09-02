"""Do the corner markets' stated probabilities match what happens?

Nothing measured this, and corners are the majority of the card: 23 of the
first 42 best bets, against 4 for BTTS. Their entire validation was a set of
synthetic unit tests plus six real-data checks that are `@needs_dataset`-skipped
and therefore never run in CI — and those check that the *fit* lands near league
averages, which is a different question from whether a stated 60% happens 60%
of the time.

No corner rule can ever be profit-backtested. No source retains historical
corner prices, so unlike 1X2 and the 2.5 line there is no held-out-season test
available at any price. Calibration against outcomes is the only measurement
these markets admit, and Football-Data ships the counts (`HC`/`AC`) on every
row, so it costs nothing but time.

The same warning as `btts_calibration` applies, and applies harder here because
there is no profit backtest to overrule a calibration result:
`docs/why_better_calibration_lost_money.md` records a change that improved
calibration everywhere and cost 140 units. Good calibration is a precondition.
It cannot license a stake, and a bad number here is a reason to stake less
rather than a licence to fit the model until the number moves.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from epl_betting_lab.strategies.count_markets import (
    COUNT_MARKETS,
    UNAVAILABLE_MARKETS,
    fit_count_models,
    probabilities_for,
)

#: Bands to report a market in. Matched to the BTTS report so the two read alike.
BANDS: tuple[tuple[float, float], ...] = ((0.0, 0.30), (0.30, 0.45), (0.45, 0.55), (0.55, 0.70), (0.70, 1.01))
MIN_BAND_MATCHES = 20
START_AFTER_MATCHES = 380
#: Refitting the count models for every match is far slower than the goals
#: model. Every Nth match keeps the walk-forward honest — each prediction still
#: uses only its own past — at a fraction of the cost.
DEFAULT_STRIDE = 5

#: What actually happened, per market, from the corner counts on the row.
def _outcome(market: str, home_corners: float, away_corners: float) -> dict[str, float]:
    _, line, kind = COUNT_MARKETS[market]
    if kind == "1x2":
        return {
            "home": float(home_corners > away_corners),
            "draw": float(home_corners == away_corners),
            "away": float(away_corners > home_corners),
        }
    total = home_corners + away_corners
    return {"over": float(total > line), "under": float(total < line)}


def walk_forward_counts(
    matches: pd.DataFrame,
    markets: tuple[str, ...] | None = None,
    *,
    start_after_matches: int = START_AFTER_MATCHES,
    stride: int = DEFAULT_STRIDE,
) -> pd.DataFrame:
    """Predicted probability and outcome per (match, market, selection)."""
    chosen = tuple(
        m for m in (markets or tuple(COUNT_MARKETS)) if m not in UNAVAILABLE_MARKETS
    )
    df = (
        matches.dropna(subset=["home_goals", "away_goals", "date", "HC", "AC"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    rows = []
    for i in range(start_after_matches, len(df), max(1, stride)):
        game = df.iloc[i]
        models = fit_count_models(df.iloc[:i])
        for market in chosen:
            event, _, _ = COUNT_MARKETS[market]
            model = models.get(event)
            if model is None:
                continue
            try:
                predicted = probabilities_for(market, model, game.home_team, game.away_team)
            except (KeyError, ValueError):
                continue
            happened = _outcome(market, float(game.HC), float(game.AC))
            for selection, probability in predicted.items():
                if selection not in happened:
                    continue
                rows.append({
                    "market": market,
                    "selection": selection,
                    "predicted": float(probability),
                    "observed": happened[selection],
                })
    return pd.DataFrame(rows)


def calibration_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-market bands, plus the threshold-free scores on an ALL row."""
    if frame.empty:
        return pd.DataFrame(columns=["market", "band", "matches", "predicted", "observed", "gap_points"])
    rows = []
    for market, group in frame.groupby("market"):
        predicted = group["predicted"].to_numpy(dtype=float)
        observed = group["observed"].to_numpy(dtype=float)
        for low, high in BANDS:
            chosen = (predicted >= low) & (predicted < high)
            if chosen.sum() < MIN_BAND_MATCHES:
                continue
            rows.append({
                "market": market,
                "band": f"{int(low * 100)}-{int(high * 100)}%",
                "matches": int(chosen.sum()),
                "predicted": round(float(predicted[chosen].mean()) * 100, 1),
                "observed": round(float(observed[chosen].mean()) * 100, 1),
                "gap_points": round(float(observed[chosen].mean() - predicted[chosen].mean()) * 100, 1),
            })
        safe = np.clip(predicted, 1e-9, 1 - 1e-9)
        rows.append({
            "market": market,
            "band": "ALL",
            "matches": int(len(predicted)),
            "predicted": round(float(predicted.mean()) * 100, 1),
            "observed": round(float(observed.mean()) * 100, 1),
            "gap_points": round(float(observed.mean() - predicted.mean()) * 100, 1),
            "brier": round(float(((predicted - observed) ** 2).mean()), 4),
            "logloss": round(float(-(observed * np.log(safe) + (1 - observed) * np.log(1 - safe)).mean()), 4),
        })
    return pd.DataFrame(rows)


def render_markdown(table: pd.DataFrame) -> str:
    return "\n".join([
        "# Corner market calibration",
        "",
        "Walk-forward: each prediction made by a model fitted only on the matches",
        "before it, judged against the corner counts Football-Data ships on the",
        "same rows. No prices are involved here — but they DO exist, contrary to",
        "what this report used to say. The provider sells historical corner",
        "prices, and `data/outputs/derived_market_backtest.md` now measures the",
        "corner rule against money at books that can be bet. Calibration is the",
        "precondition; that report is the test.",
        "",
        "Corners are the majority of the live card. Before this report their whole",
        "validation was synthetic unit tests plus six real-data checks skipped in",
        "CI, and those check the fit against league averages rather than whether a",
        "stated probability happens that often.",
        "",
        "`gap_points` is observed minus predicted. A bad number here is a reason to",
        "stake less, never a licence to fit the model until it moves:",
        "docs/why_better_calibration_lost_money.md records a change that improved",
        "calibration everywhere and cost 140 units.",
        "",
        table.to_markdown(index=False) if not table.empty else "_No data._",
        "",
    ])


def save_count_calibration_reports(table: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "count_calibration.csv"
    md_path = output_dir / "count_calibration.md"
    table.to_csv(csv_path, index=False)
    md_path.write_text(render_markdown(table), encoding="utf-8")
    return {"csv": csv_path, "markdown": md_path}
