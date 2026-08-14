#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_policy_pr_gate_receipt_verification import (
    NOT_APPLICABLE_VERDICT,
    VERIFIED_VERDICT,
    save_provider_policy_pr_gate_receipt_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-hash a Provider Policy PR Gate receipt against the exact Git, "
            "policy, changed-file, and evidence state it recorded. This command "
            "is read-only except for verification report outputs."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    parser.add_argument(
        "--gate-report-path",
        type=Path,
        help=(
            "Optional gate JSON path. Defaults to "
            "data/outputs/provider_policy_pr_gate.json."
        ),
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help=(
            "Write a read-only diagnostic even when exact Git context is "
            "unavailable. Diagnostic mode can never return an approval verdict."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        provider = create_provider(args.provider)
    except UnknownProviderError as exc:
        print(f"FAILED: {exc}")
        return 1

    result = save_provider_policy_pr_gate_receipt_verification(
        provider.provider_key,
        gate_report_path=args.gate_report_path,
        diagnostic_mode=args.diagnostic,
    )
    summary = result["summary"]
    print("EPL Betting Lab - Provider Policy PR Gate Receipt Verification")
    print(f"Provider: {summary['provider_name']} ({summary['provider_key']})")
    print(f"Verdict: {summary['verdict']}")
    print(f"Original receipt ID: {summary['original_gate_receipt_id'] or 'Missing'}")
    print(
        "Recalculated receipt ID: "
        f"{summary['recalculated_gate_receipt_id'] or 'Unavailable'}"
    )
    print(f"Base SHA: {summary['base_sha'] or 'Missing'}")
    print(f"Head SHA: {summary['head_sha'] or 'Missing'}")
    print(
        "Git context: "
        f"{summary.get('comparison_context_status') or 'Unavailable'}"
    )
    print(
        "Receipt binding: "
        f"{summary.get('receipt_binding_status') or 'Unverified'}"
    )
    if summary["mismatches"]:
        print("Mismatches/blockers:")
        for mismatch in summary["mismatches"]:
            print(f"- {mismatch}")
    print(f"JSON: {result['json']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(
        "Read-only verification complete. No provider policy, evidence, staging, "
        "provider, cron, model, odds, import, ledger, pick, or bet was changed."
    )
    if args.diagnostic:
        return 0
    if summary["verdict"] in {VERIFIED_VERDICT, NOT_APPLICABLE_VERDICT}:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
