#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.epl_weekly_pipeline import run_epl_weekly_pipeline


def _print_progress(step: str, status: str, message: str) -> None:
    print(f"[{status}] {step}: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the safe, report-only EPL weekly operations pipeline. This command "
            "never uses force mode or applies changes to manual data files."
        )
    )
    parser.add_argument(
        "--current-odds-path",
        type=Path,
        help="Current odds CSV. Defaults to data/manual/current_odds.csv.",
    )
    parser.add_argument(
        "--fixtures-path",
        type=Path,
        help="Upcoming fixtures CSV. Defaults to data/manual/upcoming_fixtures.csv.",
    )
    parser.add_argument(
        "--matches-path",
        type=Path,
        help="Historical matches CSV. Defaults to data/processed/epl_historical_matches.csv.",
    )
    parser.add_argument(
        "--ledger-path",
        type=Path,
        help="Bet ledger CSV. Defaults to data/manual/bet_ledger.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Weekly Operations Pipeline")
    print(
        "Safe mode: reports only. No force mode, imports, settlements, stale-odds "
        "archive/rollback, provider runs, policy changes, cron, or bets."
    )
    result = run_epl_weekly_pipeline(
        current_odds_path=args.current_odds_path,
        fixtures_path=args.fixtures_path,
        matches_path=args.matches_path,
        ledger_path=args.ledger_path,
        output_dir=args.output_dir,
        progress=_print_progress,
    )
    summary = result["summary"]
    print("")
    print(f"Final status: {result['status']}")
    print(f"Recommended next human action: {summary['recommended_next_action']}")
    print(
        "Card counts: "
        f"{summary['card_counts']['best_bets']} best bet(s), "
        f"{summary['card_counts']['leans']} lean(s), "
        f"{summary['card_counts']['passes']} pass/avoid row(s)."
    )
    print(f"Markdown summary: {result['markdown']}")
    print(f"JSON summary: {result['json']}")
    print(f"CSV step log: {result['csv']}")
    print(f"Pipeline receipt ID: {summary['pipeline_receipt_id']}")
    print(f"Archive folder: {summary['pipeline_archive_path']}")
    print(
        "Archive verification: "
        f"{summary['receipt_verification_verdict']} "
        f"({summary['receipt_verification_mismatch_count']} mismatch(es))"
    )
    print(
        "Verified receipt IDs: "
        f"{summary['receipt_verification_original_id'] or 'Not available'} / "
        f"{summary['receipt_verification_recalculated_id'] or 'Not available'}"
    )
    print(f"Comparison verdict: {summary['pipeline_comparison_verdict']}")
    print("No bets were placed and no protected manual files were edited.")

    if result["status"] == "Failed":
        return 1
    if result["status"] in {
        "Needs odds",
        "Needs odds fixes",
        "Needs data refresh",
        "Blocked",
    }:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
