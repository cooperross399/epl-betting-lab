#!/usr/bin/env python
"""Generate the automated EPL card from provider-derived odds.

Runs the existing best-bets pipeline against the provider-derived card input.
No model math is changed. Only eligible markets produce picks; excluded markets
are listed with their reason and are never presented as passes or no-value
calls. Never fabricates a price, edits a protected file, places a bet, applies
settlement, or uses force mode.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.automated_card import save_automated_card


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Defaults to data/outputs.")
    parser.add_argument(
        "--card-input-path",
        type=Path,
        help="Provider-derived odds CSV. Defaults to the staging card input.",
    )
    parser.add_argument("--matches-path", type=Path)
    parser.add_argument("--fixtures-path", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Automated EPL Card")
    print(
        "Eligible markets only. No fabricated odds, no manual entry, no "
        "protected file writes, no bets, no settlement, no force mode."
    )

    result = save_automated_card(
        output_dir=args.output_dir,
        card_input_path=args.card_input_path,
        matches_path=args.matches_path,
        fixtures_path=args.fixtures_path,
    )
    summary = result["summary"]

    print(f"Card generated: {'Yes' if summary['card_generated'] else 'No'}")
    print(f"Included markets: {summary['included_markets'] or 'none'}")
    print(f"Excluded markets: {summary['excluded_markets'] or 'none'}")
    print(f"Odds source: {summary['odds_source']}")
    if summary["card_generated"]:
        print(f"Best bets: {len(summary['best_bets'])}")
        print(f"Leans: {len(summary['leans'])}")
        print(f"Passes/avoids: {len(summary['passes_or_avoids'])}")
        print(f"Unit suggestions: {len(summary['unit_suggestions'])}")
    else:
        print("Best bets / leans / passes / units: none produced (blocked)")
    for blocker in summary["blockers"]:
        print(f"BLOCKED: {blocker}")
    print(f"Next action: {summary.get('next_action', '')}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")

    return 0 if summary["card_generated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
