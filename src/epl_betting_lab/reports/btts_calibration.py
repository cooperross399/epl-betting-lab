"""Does the stated BTTS probability match how often both teams score?

BTTS cannot be profit-backtested. Football-Data ships historical prices for 1X2
and the 2.5 line and none at all for both-teams-to-score, and the bought
provider history covers props and corner totals only. Calibration against
outcomes is the one measurement this market admits, because it needs no prices.

That makes this module unusually easy to misuse, and
`docs/why_better_calibration_lost_money.md` is the record of exactly that: a
change that improved BTTS calibration from 9.2 points to 3.9 by shrinking
toward a league-average prior, and cost about 140 units, because shrinking
toward a prior that disagrees with sharp prices manufactures edges — 546 bets
became 851.

So calibration alone must never authorise a change here. What it can do is
show that a change made for an independent reason did not damage this market,
and — as it happens — repaired a bias that had been recorded as unfixable. The
distinction that matters is HOW the numbers improved: a shrinkage improves
calibration by saying less, and would leave the threshold-free scores flat or
worse. Better ratings improve calibration by being more right, and carry Brier
and log loss with them. Both are reported below for that reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig

#: Predicted-probability bands, matching docs/why_better_calibration_lost_money.md
#: so the numbers there and here can be read against each other.
BANDS: tuple[tuple[float, float], ...] = ((0.0, 0.30), (0.30, 0.45), (0.45, 0.55), (0.55, 0.70), (0.70, 1.01))
MIN_BAND_MATCHES = 20
START_AFTER_MATCHES = 380


@dataclass(frozen=True)
class RatingsUnderTest:
    name: str
    config: RatingConfig | None
    last_n_matches_per_team: int | None = None


def walk_forward_btts(
    matches: pd.DataFrame,
    ratings: RatingsUnderTest,
    *,
    start_after_matches: int = START_AFTER_MATCHES,
) -> pd.DataFrame:
    """Predicted p(BTTS) and the outcome, each match fitted only on its past."""
    df = (
        matches.dropna(subset=["home_goals", "away_goals", "date"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    rows = []
    for i in range(start_after_matches, len(df)):
        game = df.iloc[i]
        model = PoissonGoalsModel().fit(
            df.iloc[:i],
            last_n_matches_per_team=ratings.last_n_matches_per_team,
            config=ratings.config,
        )
        probs = model.match_probabilities(game.home_team, game.away_team)
        rows.append({
            "date": game.date,
            "predicted": float(probs["btts_yes"]),
            "observed": 1.0 if (game.home_goals > 0 and game.away_goals > 0) else 0.0,
        })
    return pd.DataFrame(rows)


def calibration_table(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    """Per-band predicted vs observed, plus the threshold-free scores.

    The band rows are the calibration claim. The ALL row carries Brier and log
    loss, which is what separates "more right" from "says less".
    """
    predicted = frame["predicted"].to_numpy(dtype=float)
    observed = frame["observed"].to_numpy(dtype=float)
    rows = []
    for low, high in BANDS:
        chosen = (predicted >= low) & (predicted < high)
        if chosen.sum() < MIN_BAND_MATCHES:
            continue
        rows.append({
            "ratings": name,
            "band": f"{int(low * 100)}-{int(high * 100)}%",
            "matches": int(chosen.sum()),
            "predicted": round(float(predicted[chosen].mean()) * 100, 1),
            "observed": round(float(observed[chosen].mean()) * 100, 1),
            "gap_points": round(float(observed[chosen].mean() - predicted[chosen].mean()) * 100, 1),
        })
    safe = np.clip(predicted, 1e-9, 1 - 1e-9)
    rows.append({
        "ratings": name,
        "band": "ALL",
        "matches": int(len(predicted)),
        "predicted": round(float(predicted.mean()) * 100, 1),
        "observed": round(float(observed.mean()) * 100, 1),
        "gap_points": round(float(observed.mean() - predicted.mean()) * 100, 1),
        "brier": round(float(((predicted - observed) ** 2).mean()), 4),
        "logloss": round(float(-(observed * np.log(safe) + (1 - observed) * np.log(1 - safe)).mean()), 4),
    })
    return pd.DataFrame(rows)


def compare_ratings(matches: pd.DataFrame, candidates: list[RatingsUnderTest]) -> pd.DataFrame:
    return pd.concat(
        [calibration_table(walk_forward_btts(matches, r), r.name) for r in candidates],
        ignore_index=True,
    )


def render_markdown(table: pd.DataFrame) -> str:
    lines = [
        "# BTTS calibration by ratings",
        "",
        "Walk-forward: every match predicted by a model fitted only on the matches",
        "before it. No prices are involved, so this is the one measurement BTTS",
        "admits — and, on its own, one that must never authorise a change here.",
        "See docs/why_better_calibration_lost_money.md.",
        "",
        "`gap_points` is observed minus predicted: positive means the model",
        "under-states how often both teams score, which manufactures false edges",
        "on the `no` side.",
        "",
        table.to_markdown(index=False),
        "",
    ]
    return "\n".join(lines)


def save_btts_calibration_reports(table: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "btts_calibration_by_ratings.csv"
    md_path = output_dir / "btts_calibration_by_ratings.md"
    table.to_csv(csv_path, index=False)
    md_path.write_text(render_markdown(table), encoding="utf-8")
    return {"csv": csv_path, "markdown": md_path}
