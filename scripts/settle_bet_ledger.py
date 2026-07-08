#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, PROCESSED_DIR
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.bet_ledger import ensure_ledger_template, load_bet_ledger
from epl_betting_lab.reports.bet_settlement import (
    apply_settlements_to_ledger,
    build_settlement_preview,
    save_settlement_preview,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or apply settlements for pending manual bet ledger rows."
    )
    parser.add_argument(
        "--ledger",
        default=str(MANUAL_DIR / "bet_ledger.csv"),
        help="Path to the manual bet ledger. Default: data/manual/bet_ledger.csv",
    )
    parser.add_argument(
        "--matches",
        default=str(PROCESSED_DIR / "epl_historical_matches.csv"),
        help="Path to processed EPL match results. Default: data/processed/epl_historical_matches.csv",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply confident win/loss/push suggestions to the ledger. Without this flag, only preview files are written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ledger_path = Path(args.ledger)
    matches_path = Path(args.matches)
    ensure_ledger_template(MANUAL_DIR / "bet_ledger_template.csv")
    ensure_ledger_template(ledger_path)

    ledger = load_bet_ledger(ledger_path)
    matches = load_matches(matches_path)
    preview = build_settlement_preview(ledger, matches)
    paths = save_settlement_preview(preview, OUTPUTS_DIR)

    applied = 0
    if args.apply:
        updated, applied = apply_settlements_to_ledger(ledger, preview)
        updated.to_csv(ledger_path, index=False)

    print("Saved settlement preview:")
    for path in paths.values():
        print(f"- {path}")
    if args.apply:
        print(f"Applied settlements: {applied}")
        print(f"Updated ledger: {ledger_path}")
    else:
        print("Preview only. Run with --apply to update confident win/loss/push rows.")


if __name__ == "__main__":
    main()
