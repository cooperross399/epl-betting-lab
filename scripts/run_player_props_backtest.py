#!/usr/bin/env python
"""Measure player props against the prices that were actually for sale.

Walk-forward: the model is fitted only on appearances dated before each
priced fixture. Flat stakes, book-style voiding, per-market ROI and the
caveats that bound what the numbers can claim. Read-only — no picks, no
card, no ledger, no policy edits, no bets.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.player_props_backtest import (
    DEFAULT_EDGE_THRESHOLD,
    save_player_props_backtest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--edge-threshold",
        type=float,
        default=DEFAULT_EDGE_THRESHOLD,
        help=(
            "Minimum modelled edge to count a bet. Defaults higher than the "
            "card's match-level bar on purpose: the model prices the morning "
            "and books reprice on the team sheet."
        ),
    )
    parser.add_argument(
        "--calibration-split",
        help=(
            "ISO date. Outcomes before it fit the calibration correction; "
            "everything reported — bets, ROI, tables — is on-or-after it "
            "only. Never fit and measure on the same window."
        ),
    )
    parser.add_argument("--odds-path", type=Path)
    parser.add_argument("--logs-path", type=Path)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = save_player_props_backtest(
            output_dir=args.output_dir,
            odds_path=args.odds_path,
            logs_path=args.logs_path,
            edge_threshold=args.edge_threshold,
            calibration_split=args.calibration_split,
        )
    except (FileNotFoundError, KeyError) as exc:
        print(f"BLOCKED: {exc}")
        return 2
    summary = result["summary"]

    print("EPL Betting Lab - Player Props Backtest")
    print(
        "Walk-forward, flat stakes, book-style voids. No picks, no card, no "
        "ledger, no policy, no bets."
    )
    print(f"Priced outcomes with a model opinion: {summary['priced_outcomes']}")
    print(f"No model opinion: {summary['no_model_opinion']}")
    print(f"Edge threshold: {summary['edge_threshold']:.0%}")
    correction = summary.get("calibration_correction")
    if correction:
        print(
            f"Calibration split: {summary['calibration_split']} — everything "
            "below is the held-out window only."
        )
        print(
            f"Correction: sigmoid({correction['intercept']} + "
            f"{correction['slope']} x logit(p)) from "
            f"{correction['fitted_on']} pre-split outcomes."
        )
    for market, stats in summary["per_market"].items():
        roi = stats["roi"]
        print(
            f"  {market}: {stats['bets']} bet(s), {stats['voids']} void(s), "
            f"{stats['wins']} win(s), "
            f"{stats['flat_profit_units']} unit(s)"
            + (f", ROI {roi:.1%}" if roi is not None else "")
        )
    if summary["unmatched_teams"]:
        print(f"Unmatched fixtures: {len(summary['unmatched_teams'])}")
    if summary["unmatched_players"]:
        print(f"Unmatched players: {len(summary['unmatched_players'])}")
    for caveat in summary["caveats"]:
        print(f"CAVEAT: {caveat}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
