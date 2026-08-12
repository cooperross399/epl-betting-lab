#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt_verification import (
    save_provider_human_acceptance_receipt_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recalculate every checksum bound by a human provider acceptance "
            "receipt before an allowlist PR is considered."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    parser.add_argument(
        "--receipt-path",
        type=Path,
        help=(
            "Optional current or archived receipt JSON path. Defaults to the "
            "latest data/outputs receipt."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        provider = create_provider(args.provider)
    except UnknownProviderError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    result = save_provider_human_acceptance_receipt_verification(
        provider.provider_key,
        receipt_path=args.receipt_path,
    )
    summary = result["summary"]
    print("EPL Betting Lab - Provider Human Acceptance Receipt Verification")
    print(f"Provider: {summary['provider_name']} ({summary['provider_key']})")
    print(f"Receipt: {summary['receipt_path']}")
    print(f"Receipt ID: {summary['receipt_id'] or 'Not available'}")
    print(f"Reviewer: {summary['reviewer_name'] or 'Not available'}")
    print(f"Decision: {summary['decision'] or 'Not available'}")
    print(f"Verdict: {summary['verdict']}")
    print(f"Next: {summary['next_step']}")
    print(f"JSON: {result['json']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(
        "Read-only verification complete. No policy, staging, odds, ledger, model, "
        "provider, cron, pick, or bet action was performed."
    )
    return 0 if summary["verdict"] == "Verified for allowlist PR review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
