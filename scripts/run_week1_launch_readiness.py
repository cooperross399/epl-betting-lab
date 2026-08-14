#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.week1_launch_readiness import run_week1_launch_readiness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare and check Week 1 fixtures and real manual odds. A missing odds "
            "file receives a blank template; existing odds are preserved by default."
        )
    )
    parser.add_argument(
        "--fixtures-path",
        type=Path,
        help="Upcoming fixtures CSV. Defaults to data/manual/upcoming_fixtures.csv.",
    )
    parser.add_argument(
        "--current-odds-path",
        type=Path,
        help="Current odds CSV. Defaults to data/manual/current_odds.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    parser.add_argument(
        "--book",
        default="",
        help="Optional sportsbook name to prefill when a blank template is created.",
    )
    parser.add_argument(
        "--overwrite-template",
        action="store_true",
        help=(
            "Terminal-only: intentionally replace an existing current_odds.csv with a "
            "new blank template. Existing real prices will be removed."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Week 1 Launch Readiness")
    print(
        "Safe setup: blank templates only. No invented odds, bets, providers, settlement, "
        "allowlisting, cron, or model changes."
    )
    result = run_week1_launch_readiness(
        fixtures_path=args.fixtures_path,
        current_odds_path=args.current_odds_path,
        output_dir=args.output_dir,
        overwrite_template=args.overwrite_template,
        book=args.book,
    )
    summary = result["summary"]
    print(f"Final readiness status: {result['status']}")
    print(f"Fixture status: {summary['fixture_status']}")
    print(f"Odds file status: {summary['odds_file_status']}")
    print(f"Odds completeness: {float(summary['odds_completeness_percentage']):.1%}")
    print(f"Missing odds rows: {summary['missing_odds_count']}")
    print(f"Invalid odds issues: {summary['invalid_odds_issue_count']}")
    print(f"Stale/past odds rows: {summary['stale_odds_row_count']}")
    print(f"Next action: {summary['next_human_action']}")
    print(f"Markdown report: {result['markdown']}")
    print(f"JSON report: {result['json']}")
    print(f"CSV report: {result['csv']}")

    if result["status"] == "Failed":
        return 1
    if result["status"] != "Ready for weekly pipeline":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
