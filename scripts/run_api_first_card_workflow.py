#!/usr/bin/env python
"""API-first card workflow: provider staging -> eligibility -> card input.

Removes the manual odds-entry step. Reads existing provider staging evidence,
decides per-market eligibility, and writes a provider-derived card input outside
`data/manual/`.

This command never fetches live odds itself (run the shadow verifier for that),
never writes a protected manual file, never fabricates a missing price, and
never places a bet or applies settlement.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.market_eligibility import DEFAULT_DISABLED_MARKETS
from epl_betting_lab.reports.automated_card_input import save_automated_card_input


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staging-odds-path",
        type=Path,
        help="Provider staging odds CSV. Defaults to data/staging/current_odds_staging.csv.",
    )
    parser.add_argument(
        "--staging-fixtures-path",
        type=Path,
        help="Provider staging fixtures CSV. Defaults to data/staging/upcoming_fixtures_staging.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    parser.add_argument(
        "--card-input-path",
        type=Path,
        help=(
            "Where to write the derived card input. Defaults to "
            "data/staging/automated_card_current_odds.csv. Paths under "
            "data/manual/ are refused."
        ),
    )
    parser.add_argument(
        "--disabled-markets",
        default=",".join(DEFAULT_DISABLED_MARKETS),
        help=(
            "Comma-separated markets excluded from automated picks. "
            f"Defaults to {','.join(DEFAULT_DISABLED_MARKETS)}."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    disabled = tuple(
        item.strip().casefold()
        for item in str(args.disabled_markets).split(",")
        if item.strip()
    )

    print("EPL Betting Lab - API-First Card Workflow")
    print(
        "Provider-derived odds only: no manual entry, no fabricated prices, no "
        "protected file writes, no bets, no settlement, no cron."
    )

    result = save_automated_card_input(
        staging_odds_path=args.staging_odds_path,
        staging_fixtures_path=args.staging_fixtures_path,
        output_dir=args.output_dir,
        card_input_path=args.card_input_path,
        disabled_markets=disabled,
    )
    summary = result["summary"]
    eligibility = summary["eligibility"]

    print(f"Status: {summary['status']}")
    print(f"Selected window: {summary['window_label']}")
    print(f"Fixtures in window: {summary['fixtures_in_window']}")
    print(f"Included markets: {summary['included_markets'] or 'none'}")
    print(f"Excluded markets: {summary['excluded_markets'] or 'none'}")
    for market in eligibility["markets"]:
        print(
            f"  - {market['market']}: {market['status']} "
            f"({market['fixtures_covered']}/{market['fixtures_expected']} fixtures, "
            f"{market['row_count']} rows)"
        )
    print(f"Card input rows: {summary['row_count']}")
    print(f"Card input path: {summary['card_input_path']}")
    print(
        "Manual odds entry required: "
        f"{'Yes' if summary['manual_entry_required'] else 'No'}"
    )
    for warning in eligibility["warnings"]:
        print(f"WARNING: {warning}")
    for blocker in summary["blockers"]:
        print(f"BLOCKED: {blocker}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")

    if summary["blockers"]:
        return 2
    return 0 if summary["card_input_written"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
