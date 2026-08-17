#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.fixture_slate_check import run_fixture_slate_check


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check data/manual/upcoming_fixtures.csv for problems before odds entry: "
            "duplicate fixtures, double-booked teams, unknown team spellings, past or "
            "malformed dates, partial matchweeks, and drift between the slate and the "
            "odds file. Read-only: it never edits fixtures or odds, never fabricates "
            "prices, and never places bets."
        )
    )
    parser.add_argument(
        "--fixtures-path",
        type=Path,
        help="Fixture slate CSV. Defaults to data/manual/upcoming_fixtures.csv.",
    )
    parser.add_argument(
        "--matches-path",
        type=Path,
        help="Historical matches CSV. Defaults to data/processed/epl_historical_matches.csv.",
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Fixture Slate Confirmation Check")
    print("Read-only: nothing is edited and no odds are fabricated.")
    result = run_fixture_slate_check(
        args.fixtures_path,
        matches_path=args.matches_path,
        current_odds_path=args.current_odds_path,
        output_dir=args.output_dir,
    )
    summary = result["summary"]
    print("")
    print(f"Status: {result['status']}")
    print(f"Fixtures checked: {summary['fixture_count']}")
    print(
        f"Issues: {summary['error_count']} error(s), {summary['warning_count']} "
        f"warning(s), {summary['info_count']} informational note(s)."
    )
    issues = result["issues"]
    if not issues.empty:
        for _, row in issues[issues["severity"] == "error"].iterrows():
            print(f"  [error] {row['detail']}")
        for _, row in issues[issues["severity"] == "warning"].iterrows():
            print(f"  [warning] {row['detail']}")
    print(f"Markdown report: {result['paths']['markdown']}")
    print(f"CSV report: {result['paths']['csv']}")
    print(f"JSON report: {result['paths']['json']}")
    print(
        "A ready verdict still requires manually confirming the slate against the "
        "official EPL schedule before entering odds."
    )
    if result["status"] in {"Needs slate fixes", "Missing fixtures"}:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
