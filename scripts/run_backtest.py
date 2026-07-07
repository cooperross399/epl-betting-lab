#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.backtest.walk_forward import run_walk_forward_backtest, summarize_backtest
from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.backtest_bias import save_backtest_bias_reports


def main() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    matches = load_matches()
    bets = run_walk_forward_backtest(matches)
    summary = summarize_backtest(bets)

    bets_path = OUTPUTS_DIR / "backtest_bets.csv"
    summary_path = OUTPUTS_DIR / "backtest_summary.csv"
    bets.to_csv(bets_path, index=False)
    summary.to_csv(summary_path, index=False)
    report_paths = save_backtest_bias_reports(bets, OUTPUTS_DIR)

    print("Backtest summary:")
    print(summary.to_string(index=False) if not summary.empty else "No bets found.")
    print(f"\nSaved bets to {bets_path}")
    print(f"Saved summary to {summary_path}")
    print("Saved bias reports:")
    for path in report_paths.values():
        print(f"- {path}")


if __name__ == "__main__":
    main()
