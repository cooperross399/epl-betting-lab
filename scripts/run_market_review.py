#!/usr/bin/env python
"""Where the card loses money, and whether two declared fixes would have helped.

Reads the card archive, the bought historical prices and Football-Data's
history. Buys nothing, places nothing and changes nothing the card reads.
Writes data/outputs/market_review.md. See reports/market_review.py.
"""
from __future__ import annotations

import argparse
import traceback
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from epl_betting_lab.reports import market_review as review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odds", default=str(PROCESSED_DIR / "historical_market_odds.csv"))
    parser.add_argument("--output", default=str(OUTPUTS_DIR / "market_review.md"))
    args = parser.parse_args()
    notes: list[str] = []
    live = pd.DataFrame()
    derived = one_x_two = None
    lean: list[pd.DataFrame] = []
    side: list[tuple[str, pd.DataFrame | None]] = []
    scored = None
    weights = None

    try:
        from epl_betting_lab.data.loaders import load_matches
        from epl_betting_lab.reports.card_scoreboard import build_scoreboard, load_archived_cards

        archived = load_archived_cards(OUTPUTS_DIR / "archive" / "automated_cards")
        board = build_scoreboard(archived, load_matches())
        live = review.live_frame(board.scored)
        notes.append(f"Live: {len(live)} settled picks from {len(archived)} archived cards.")
    except Exception:  # noqa: BLE001 - each part is reported, never fatal
        notes.append("Live record failed: " + traceback.format_exc(limit=2).replace("\n", " "))

    try:
        from epl_betting_lab.data.loaders import load_matches_with_xg
        from epl_betting_lab.reports.derived_market_backtest import build_backtest

        odds_path = Path(args.odds)
        if odds_path.is_file():
            result = build_backtest(pd.read_csv(odds_path), load_matches_with_xg())
            scored = result.scored
            derived = review.derived_rules(result.scored)
            lean.append(
                review.model_minus_market(
                    review.with_market_probability(
                        result.scored[result.scored["market"].isin(["draw_no_bet", "double_chance", "btts"])]
                    ),
                    "calibrated_model_prob",
                )
            )
        else:
            notes.append(f"No bought prices at {odds_path}; that part was not run.")
    except Exception:  # noqa: BLE001
        notes.append("Bought-price part failed: " + traceback.format_exc(limit=2).replace("\n", " "))

    try:
        from epl_betting_lab.data.loaders import load_matches_with_xg
        from epl_betting_lab.models.poisson_goals import RatingConfig
        from epl_betting_lab.reports.out_of_sample import walk_forward_probabilities

        probs = walk_forward_probabilities(load_matches_with_xg(), RatingConfig.legacy())
        one_x_two = review.one_x_two_rules(probs)
        lean.append(review.model_minus_market(review.one_x_two_frame(probs), "calibrated_model_prob"))
        side_table, weights = review.side_fix_1x2(probs)
        notes.append("Side weights (home, draw, away), fitted on the rule seasons: " + ", ".join(f"{w:.4f}" for w in weights))
        side.append(("Side fix, 1X2: card rule on re-weighted probabilities (log loss row: model / re-weighted / market)", side_table))
    except Exception:  # noqa: BLE001
        notes.append("1X2 part failed: " + traceback.format_exc(limit=2).replace("\n", " "))

    try:
        if scored is not None and weights is not None:
            side.append(("Side fix on the bought 2025/26 draw-no-bet and double-chance prices", review.side_fix_derived(scored, weights)))
    except Exception:  # noqa: BLE001
        notes.append("Side fix on bought prices failed: " + traceback.format_exc(limit=3).replace("\n", " "))

    report = review.render(live, derived, one_x_two, lean, notes, side)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
