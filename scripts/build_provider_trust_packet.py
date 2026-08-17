#!/usr/bin/env python
"""Build the consolidated provider trust / allowlist approval packet.

Read-only. It cannot edit `staging_provider_policy.json`, allowlist a provider,
generate picks, promote staging, enable cron, or place bets.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.provider_trust_packet import (
    PROVIDER_NAME,
    save_provider_trust_packet,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider-name",
        default=PROVIDER_NAME,
        help=f"Provider name checked against the policy allowlist. Default: {PROVIDER_NAME}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Provider Trust Packet")
    print(
        "Read-only: cannot edit policy, allowlist a provider, generate picks, "
        "promote staging, enable cron, or place bets."
    )
    result = save_provider_trust_packet(
        output_dir=args.output_dir, provider_name=args.provider_name
    )
    summary = result["summary"]
    acceptance = summary["acceptance"]
    markets = summary["market_eligibility_summary"]

    print(f"Provider: {summary['provider_name']}")
    print(
        "Currently allowlisted: "
        f"{'Yes' if summary['currently_allowlisted'] else 'No'}"
    )
    print(f"Acceptance verdict: {acceptance['verdict']}")
    print(
        "Completed live runs: "
        f"{acceptance['completed_live_runs']}/{acceptance['required_live_runs']} "
        f"({acceptance['runs_remaining']} remaining)"
    )
    print(f"Included markets: {markets['included_markets'] or 'none'}")
    print(f"Excluded markets: {markets['excluded_markets'] or 'none'}")
    print(
        "Manual odds entry required: "
        f"{'Yes' if markets['manual_entry_required'] else 'No'}"
    )
    print(
        "Ready for human approval: "
        f"{'Yes' if summary['ready_for_human_approval'] else 'No'}"
    )
    for item in summary["outstanding_requirements"]:
        print(f"OUTSTANDING: {item}")
    print(f"Exact approval needed: {summary['exact_approval_needed']}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")

    return 0 if summary["ready_for_human_approval"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
