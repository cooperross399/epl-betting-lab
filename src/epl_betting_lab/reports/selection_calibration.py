"""Calibration on the bets the card picks, not just on every row it prices.

Both sister labs found the same thing: a model can look calibrated over every
selection it prices and still be badly overconfident on the ones it picks.
CBB: 0.4 points under-confident over 526,728 rows, 10.4 points OVER-confident
over the 174,136 it selected, every bin over-predicted. NHL: 9-12 points. A
model is selected into its bets by its own disagreement with the price, so its
bets are the tail of its own error distribution — the winner's curse.

This lab had only ever checked the whole population (`count_calibration.md`
reads -0.0 points on corners). This report reads both, per market, from the
derived-market backtest's scored candidates and the bets the card rule took,
and from the props backtest's picks.

It also writes a TRUST WEIGHT per market (the CBB lab's `models/trust.py`):
the share of the model's disagreement with the price that the picked bets
actually earned, ``w = (hit rate - implied) / (predicted - implied)``, clipped
to [0, 1]. The card pulls each pick toward the price by it:
``p' = implied + w (p - implied)``, so its edge becomes ``w x edge``. A market
with fewer than `MIN_PICKS_FOR_TRUST` settled picks gets no weight and is not
moved: too few to say anything, either way. A weight is a measurement read
off one season of bought prices; it is not evidence of an edge, and a weight
of 1 is not one either.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR

#: Below this many settled (non-push) picks a market's weight is not set.
MIN_PICKS_FOR_TRUST = 30

DEFAULT_JSON = OUTPUTS_DIR / "selection_calibration.json"
DEFAULT_MARKDOWN = OUTPUTS_DIR / "selection_calibration.md"


def implied_probability(american: float) -> float:
    american = float(american)
    if american > 0:
        return 100.0 / (american + 100.0)
    return -american / (-american + 100.0)


def _probability(frame: pd.DataFrame) -> pd.Series:
    for column in ("calibrated_model_prob", "model_probability", "model_prob"):
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce")
    raise KeyError("no model probability column")


def _won(frame: pd.DataFrame) -> pd.Series:
    if "won" in frame.columns:
        return frame["won"].astype(bool)
    return frame["outcome"].astype(str).str.lower().eq("won")


def _settled(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop pushes and voids: calibration is about win against loss."""
    out = frame.copy()
    if "push" in out.columns:
        out = out[~out["push"].astype(bool)]
    if "outcome" in out.columns:
        out = out[out["outcome"].astype(str).str.lower().isin(["won", "lost"])]
    return out


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


@dataclass(frozen=True)
class Cell:
    n: int
    predicted: float
    observed: float
    implied: float
    low: float
    high: float

    @property
    def gap_points(self) -> float:
        """Predicted minus observed, in points. Positive = overconfident."""
        return round(100 * (self.predicted - self.observed), 1)


def cell(frame: pd.DataFrame) -> Cell | None:
    frame = _settled(frame)
    if frame.empty:
        return None
    probability = _probability(frame)
    won = _won(frame)
    implied = frame["american_odds" if "american_odds" in frame.columns else "american"].map(implied_probability)
    n = int(len(frame))
    hits = int(won.sum())
    low, high = wilson(hits, n)
    return Cell(
        n=n,
        predicted=float(probability.mean()),
        observed=hits / n,
        implied=float(implied.mean()),
        low=low,
        high=high,
    )


def trust_weight(picked: Cell | None) -> float | None:
    """The share of the model's disagreement the picks earned, in [0, 1]."""
    if picked is None or picked.n < MIN_PICKS_FOR_TRUST:
        return None
    disagreement = picked.predicted - picked.implied
    if disagreement <= 0:
        return None
    return round(min(1.0, max(0.0, (picked.observed - picked.implied) / disagreement)), 3)


def measure(
    scored: pd.DataFrame | None, picked: pd.DataFrame, *, source: str
) -> dict[str, dict[str, object]]:
    """Per market: every priced row, the picked rows, and the weight."""
    out: dict[str, dict[str, object]] = {}
    for market in sorted(picked["market"].astype(str).unique()):
        everything = None
        if scored is not None and not scored.empty:
            everything = cell(scored[scored["market"].astype(str) == market])
        chosen = cell(picked[picked["market"].astype(str) == market])
        if chosen is None:
            continue
        out[market] = {
            "source": source,
            "all": None if everything is None else everything.__dict__ | {"gap_points": everything.gap_points},
            "picked": chosen.__dict__ | {"gap_points": chosen.gap_points},
            "trust_weight": trust_weight(chosen),
        }
    return out


def render(markets: dict[str, dict[str, object]], generated_at: str) -> str:
    lines = [
        "# Calibration on the picks",
        "",
        f"Generated {generated_at}.",
        "",
        "Every priced row against the rows the card rule actually picked. A gap is "
        "predicted minus observed, in points: positive means the model said more "
        "than happened. The sister labs found the picks 9-12 points overconfident "
        "while the whole population looked calibrated (the winner's curse). "
        "Calibration can rule a model out, never in, and none of this is evidence "
        "of an edge.",
        "",
        "| market | source | all: n | all: gap | picked: n | predicted | observed (95%) | implied | picked: gap | trust weight |",
        "|:--|:--|--:|--:|--:|--:|:--|--:|--:|--:|",
    ]
    for market, entry in markets.items():
        everything = entry["all"]
        picked = entry["picked"]
        weight = entry["trust_weight"]
        lines.append(
            "| {m} | {s} | {an} | {ag} | {n} | {p:.1%} | {o:.1%} ({lo:.1%}-{hi:.1%}) | {i:.1%} | {g:+.1f} | {w} |".format(
                m=market,
                s=entry["source"],
                an="" if everything is None else everything["n"],
                ag="" if everything is None else f"{everything['gap_points']:+.1f}",
                n=picked["n"],
                p=picked["predicted"],
                o=picked["observed"],
                lo=picked["low"],
                hi=picked["high"],
                i=picked["implied"],
                g=picked["gap_points"],
                w="not set (under %d picks)" % MIN_PICKS_FOR_TRUST if weight is None and picked["n"] < MIN_PICKS_FOR_TRUST
                else ("not set" if weight is None else f"{weight:.2f}"),
            )
        )
    lines += [
        "",
        "The trust weight is the share of the model's disagreement with the price "
        "the picks earned. The card multiplies each pick's edge by it before the "
        "bar reads it; a pick that no longer clears the bar becomes an unstaked "
        "lean. Not set means the market is not moved.",
        "",
    ]
    return "\n".join(lines)


def write(
    markets: dict[str, dict[str, object]],
    json_path: Path = DEFAULT_JSON,
    markdown_path: Path = DEFAULT_MARKDOWN,
) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"generated_at": generated_at, "markets": markets}, indent=2, default=float),
        encoding="utf-8",
    )
    markdown_path.write_text(render(markets, generated_at), encoding="utf-8")


def load_trust_weights(path: Path | None = None) -> dict[str, float]:
    """Market -> weight, for markets that have one. Missing file: nothing moves."""
    path = path or DEFAULT_JSON
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    weights = {}
    for market, entry in (data.get("markets") or {}).items():
        weight = entry.get("trust_weight") if isinstance(entry, dict) else None
        if isinstance(weight, (int, float)) and 0 <= weight <= 1:
            weights[str(market)] = float(weight)
    return weights
