#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.claude_thursday_handoff import run_claude_thursday_handoff


def _print_progress(step: str, status: str, message: str) -> None:
    print(f"[{status}] {step}: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create the read-only Claude Thursday EPL packet. By default this runs the "
            "safe weekly pipeline first. It never fabricates odds, places bets, uses "
            "force mode, applies settlement, runs live providers, edits protected "
            "manual files, or enables cron."
        )
    )
    parser.add_argument(
        "--read-latest",
        action="store_true",
        help=(
            "Build the packet from the existing data/outputs/epl_weekly_pipeline.json "
            "summary instead of rerunning the weekly pipeline."
        ),
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
    print("EPL Betting Lab - Claude Thursday Handoff")
    print(
        "Safe mode: reports only. No fabricated odds, force mode, imports, "
        "settlements, provider runs, policy changes, cron, or bets."
    )
    if args.read_latest:
        print("Mode: reading the latest weekly pipeline summary without rerunning it.")
    else:
        print("Mode: running the safe weekly pipeline first.")

    result = run_claude_thursday_handoff(
        read_latest=args.read_latest,
        current_odds_path=args.current_odds_path,
        fixtures_path=args.fixtures_path,
        matches_path=args.matches_path,
        ledger_path=args.ledger_path,
        output_dir=args.output_dir,
        progress=None if args.read_latest else _print_progress,
    )
    packet = result["packet"]
    counts = packet["card_counts"]
    archive = packet["archive"]

    print("")
    print(f"Weekly pipeline status: {result['status']}")
    print(f"Card ready: {'Yes' if result['card_ready'] else 'No'}")
    if not result["card_ready"]:
        print("No card is ready. Blockers:")
        for blocker in packet["blockers"] or ["No blocker detail was recorded."]:
            print(f"  - {blocker}")
    print(
        "Card counts: "
        f"{counts['best_bets']} best bet(s), {counts['leans']} lean(s), "
        f"{counts['passes']} pass/avoid row(s)."
    )
    print(f"Archive receipt ID: {archive['receipt_id'] or 'Not available'}")
    print(f"Receipt verification: {archive['receipt_verification_verdict']}")
    print(f"Sidecar verification: {archive['sidecar_verification_verdict']}")
    print(f"Recommended next human action: {packet['recommended_next_action']}")
    print(f"JSON packet: {result['json']}")
    print(f"Markdown packet: {result['markdown']}")
    print(f"CSV packet: {result['csv']}")
    print("No bets were placed and no protected manual files were edited.")

    if result["status"] == "Failed":
        return 1
    if not result["card_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
