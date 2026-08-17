#!/usr/bin/env python
"""EPL Model scheduled-task bridge.

Reads existing repository evidence and reports whether the model is ready and
whether EPL CARD may run. Generates no picks, runs no provider, edits no
protected file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.scheduled_task_bridge import save_epl_model_task


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
    print("EPL Betting Lab - EPL Model Task")
    print(
        "Read-only status bridge: no picks, no provider run, no protected file "
        "edits, no settlement, no cron."
    )
    result = save_epl_model_task(output_dir=args.output_dir)
    summary = result["summary"]

    print(f"Model readiness: {summary['model_readiness']}")
    print(f"Fixture freshness: {summary['fixture_freshness']}")
    print(f"Selected slate: {summary['selected_slate']['window']}")
    print(
        "Slate fixtures in/out of window: "
        f"{summary['selected_slate']['fixtures_in_window']} / "
        f"{summary['selected_slate']['fixtures_outside_window']}"
    )
    print(f"Included markets: {summary['included_markets'] or 'none'}")
    print(f"Excluded markets: {summary['excluded_markets'] or 'none'}")
    print(
        "Manual odds entry required: "
        f"{'Yes' if summary['manual_odds_entry_required'] else 'No'}"
    )
    print(
        "Legacy manual template completeness: "
        f"{summary['odds_status']['completeness_percentage']:.1%} "
        f"({summary['odds_status']['missing_odds_count']} missing) "
        "- not the active source in API-first mode"
    )
    print(f"Provider shadow verdict: {summary['provider_status']['verdict']}")
    print(
        "Handoff eligible: "
        f"{'Yes' if summary['provider_status']['handoff_eligible'] else 'No'}"
    )
    print(f"Mapping coverage: {summary['mapping_coverage']['status']}")
    print(
        "Markets - core: "
        f"{summary['market_coverage']['core_markets_status']}; BTTS: "
        f"{summary['market_coverage']['btts_status']}"
    )
    for blocker in summary["blockers"]:
        print(f"BLOCKED: {blocker}")
    print(f"EPL CARD ready: {'Yes' if summary['epl_card_ready'] else 'No'}")
    print(f"Next action: {summary['next_action']}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")

    return 0 if summary["epl_card_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
