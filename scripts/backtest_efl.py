#!/usr/bin/env python
"""Walk the ratings model forward through the EFL and write what it did.

Costs nothing to run: Football-Data ships its own bookmaker prices beside the
results, so this asks whether the model beats the market without touching the
paid provider.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import EFL_DIVISIONS, OUTPUTS_DIR
from epl_betting_lab.data.fetch_football_data import processed_path_for
from epl_betting_lab.reports import efl_backtest as backtest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--divisions", nargs="+", default=list(EFL_DIVISIONS))
    parser.add_argument("--out", type=Path, default=OUTPUTS_DIR / "efl_backtest.md")
    parser.add_argument("--bets-out", type=Path, default=None)
    args = parser.parse_args()

    frames: list[pd.DataFrame] = []
    for division in args.divisions:
        path = processed_path_for(division)
        if not path.is_file():
            print(f"{division}: no dataset at `{path}`. Build it with "
                  f"`scripts/fetch_data.py --divisions {division}` first.")
            return 2
        matches = pd.read_csv(path)
        for ratings in backtest.RATING_CONFIGS:
            result = backtest.run_division(matches, division, ratings=ratings)
            for note in result.notes:
                print(f"{division}/{ratings}: {note}")
            print(
                f"{division}/{ratings}: {result.matches_bet:,} of "
                f"{result.matches_seen:,} matches priced, "
                f"{len(result.bets):,} candidate selections"
            )
            frames.append(result.bets)

    bets = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(
        not f.empty for f in frames
    ) else pd.DataFrame()

    report = backtest.render(bets, backtest.summarize(bets))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote {args.out}")

    if args.bets_out is not None and not bets.empty:
        args.bets_out.parent.mkdir(parents=True, exist_ok=True)
        bets.assign(outcome=bets["outcome"].astype(str)).to_csv(args.bets_out, index=False)
        print(f"Wrote {args.bets_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
