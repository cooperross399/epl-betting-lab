#!/usr/bin/env python
"""Measure the markets that carry the card against prices really offered.

Reads the historical prices bought from the provider, keeps only the ones a
bettable book quoted, and runs the card's own rule over them walk-forward.
Writes a report and the scored bets. Buys nothing and places nothing.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.derived_market_backtest import (
    build_backtest,
    render,
    summarize,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--odds", default=str(PROCESSED_DIR / "historical_market_odds.csv")
    )
    parser.add_argument("--output", default=str(OUTPUTS_DIR / "derived_market_backtest.md"))
    args = parser.parse_args()

    odds_path = Path(args.odds)
    if not odds_path.is_file():
        print(f"BLOCKED: no historical prices at {odds_path}.")
        print("Run the Harvest Historical BTTS workflow first.")
        return 2

    result = build_backtest(pd.read_csv(odds_path), load_matches())
    summary = summarize(result)
    report = render(result, summary)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    if not result.scored.empty:
        result.scored.to_csv(output_path.with_suffix(".csv"), index=False)
    print(report)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
