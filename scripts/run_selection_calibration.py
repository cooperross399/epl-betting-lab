#!/usr/bin/env python
"""Measure calibration on the picks and write each market's trust weight.

Reads the bought historical prices (the private odds-history branch, restored
by the workflow), runs the derived-market backtest walk-forward, and compares
every priced row with the rows the card rule picked. Adds the props
backtest's picks when that file is present. Writes
`selection_calibration.json` (read by the card) and `.md`. Buys nothing.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR
from epl_betting_lab.reports.selection_calibration import (
    DEFAULT_JSON,
    DEFAULT_MARKDOWN,
    measure,
    render,
    write,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odds", default=str(PROCESSED_DIR / "historical_market_odds.csv"))
    parser.add_argument("--props", default=str(OUTPUTS_DIR / "player_props_backtest.csv"))
    parser.add_argument("--json", default=str(DEFAULT_JSON))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    odds_path = Path(args.odds)
    if not odds_path.is_file():
        print(f"no bought prices at {odds_path}; nothing measured, the card is not moved.")
        return 0

    from epl_betting_lab.data.loaders import load_matches_with_xg
    from epl_betting_lab.reports.derived_market_backtest import build_backtest

    result = build_backtest(pd.read_csv(odds_path), load_matches_with_xg())
    markets: dict[str, dict[str, object]] = {}
    if not result.bets.empty:
        markets.update(measure(result.scored, result.bets, source="derived backtest"))

    props_path = Path(args.props)
    if props_path.is_file():
        props = pd.read_csv(props_path)
        if not props.empty and "market" in props.columns:
            markets.update(measure(None, props, source="props backtest"))

    if not markets:
        print("nothing settled to measure; the card is not moved.")
        return 0
    write(markets, Path(args.json), Path(args.markdown))
    print(render(markets, "now"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
