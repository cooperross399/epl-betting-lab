#!/usr/bin/env python
"""EPL CARD scheduled-task bridge.

Reports whether the card is allowed to run. While any gate is unmet the card
withholds every selection rather than inventing one.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.scheduled_task_bridge import save_epl_card_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - EPL Card Task")
    print(
        "Read-only status bridge: picks are withheld unless every gate passes. "
        "No provider run, no protected file edits, no bets."
    )
    result = save_epl_card_task(output_dir=args.output_dir)
    summary = result["summary"]

    print(f"Card status: {summary['card_status']}")
    print(f"Picks suppressed: {'Yes' if summary['picks_suppressed'] else 'No'}")
    if summary["card_ready"]:
        print(f"Best bets: {len(summary['best_bets'])}")
        print(f"Leans: {len(summary['leans'])}")
        print(f"Passes/avoids: {len(summary['passes_or_avoids'])}")
        print(f"Unit suggestions: {len(summary['unit_suggestions'])}")
    else:
        print("Best bets: withheld (card not ready)")
        print("Leans: withheld (card not ready)")
        print("Passes/avoids: withheld (card not ready)")
        print("Unit suggestions: withheld (card not ready)")
    print(f"Included markets: {summary['included_markets'] or 'none'}")
    print(f"Excluded markets: {summary['excluded_markets'] or 'none'}")
    print(
        "Manual odds entry required: "
        f"{'Yes' if summary['manual_odds_entry_required'] else 'No'}"
    )
    print(f"Odds source: {summary['odds_source']}")
    print(
        "Odds completeness (active source): "
        f"{summary['odds_completeness']['completion_percentage']:.1%} "
        f"({summary['odds_completeness']['missing_odds_count']} missing)"
    )
    print(f"Provider source: {summary['provider_source']['source_used']}")
    for warning in summary["validation_warnings"]:
        print(f"WARNING: {warning}")
    for blocker in summary["blockers"]:
        print(f"BLOCKED: {blocker}")
    print(f"Next action: {summary['next_action']}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")

    return 0 if summary["card_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
