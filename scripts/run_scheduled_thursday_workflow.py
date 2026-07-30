#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.scheduled_thursday_workflow import (
    run_scheduled_thursday_workflow,
)


def _print_progress(step: str, status: str, message: str) -> None:
    print(f"[{status}] {step}: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the safe, report-only Thursday workflow."
    )
    parser.add_argument(
        "--github-runner-handoff",
        action="store_true",
        help=(
            "Require strict repository-path, checksum, freshness, validation, "
            "and completeness gates for GitHub runner inputs."
        ),
    )
    parser.add_argument(
        "--current-odds-path",
        type=Path,
        help="Prepared current odds CSV path. Defaults to data/manual/current_odds.csv.",
    )
    parser.add_argument(
        "--fixtures-path",
        type=Path,
        help=(
            "Prepared upcoming fixtures CSV path. Defaults to "
            "data/manual/upcoming_fixtures.csv."
        ),
    )
    parser.add_argument(
        "--expected-current-odds-sha256",
        default="",
        help="Optional SHA-256 entered at dispatch to confirm the selected odds file.",
    )
    parser.add_argument(
        "--expected-fixtures-sha256",
        default="",
        help="Optional SHA-256 entered at dispatch to confirm the selected fixture file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Scheduled Thursday Workflow")
    print(
        "Safe mode: report generation only. No odds, imports, ledger rows, profiles, "
        "settlements, or bets will be changed."
    )
    result = run_scheduled_thursday_workflow(
        current_odds_path=args.current_odds_path,
        fixtures_path=args.fixtures_path,
        require_github_runner_handoff=args.github_runner_handoff,
        expected_current_odds_sha256=args.expected_current_odds_sha256,
        expected_fixtures_sha256=args.expected_fixtures_sha256,
        progress=_print_progress,
    )
    status = str(result["status"])
    summary = result["summary"]
    print("")
    print(f"Workflow status: {status}")
    input_handoff = summary.get("input_handoff")
    if isinstance(input_handoff, dict):
        print(f"Input handoff status: {input_handoff['status']}")
        print(f"Current odds input: {input_handoff['current_odds_path']}")
        print(f"Upcoming fixtures input: {input_handoff['fixtures_path']}")
        print(
            "Card generation allowed by input handoff: "
            f"{'yes' if input_handoff['card_generation_allowed'] else 'no'}"
        )
    print(f"Recommended next action: {summary['recommended_next_action']}")
    print(f"Markdown summary: {result['markdown']}")
    print(f"JSON summary: {result['json']}")
    print("No bets were placed and no protected manual files were edited.")
    if status == "Failed":
        return 1
    if status == "Blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
