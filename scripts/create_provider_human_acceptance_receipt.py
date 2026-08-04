#!/usr/bin/env python
from __future__ import annotations

import argparse
import shlex

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    SUPPORTED_DECISIONS,
    ProviderHumanAcceptanceReceiptError,
    process_provider_human_acceptance_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or intentionally write a human provider acceptance receipt "
            "bound to the latest reviewed evidence."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    parser.add_argument(
        "--reviewer-name",
        required=True,
        help="Name of the person reviewing the provider evidence.",
    )
    parser.add_argument(
        "--decision",
        required=True,
        choices=SUPPORTED_DECISIONS,
        help="Human review decision to document.",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional plain-English reviewer notes.",
    )
    parser.add_argument(
        "--write-receipt",
        action="store_true",
        help=(
            "Intentionally write current and archived receipt reports. Without "
            "this flag, the command only previews in Terminal."
        ),
    )
    parser.add_argument(
        "--allow-not-ready-approval",
        action="store_true",
        help=(
            "Terminal-only override for an approval decision when the checklist "
            "is not Ready for human allowlist review."
        ),
    )
    return parser.parse_args()


def _write_command(args: argparse.Namespace) -> str:
    parts = [
        "python",
        "scripts/create_provider_human_acceptance_receipt.py",
        "--provider",
        args.provider,
        "--reviewer-name",
        args.reviewer_name,
        "--decision",
        args.decision,
    ]
    if args.notes:
        parts.extend(("--notes", args.notes))
    if args.allow_not_ready_approval:
        parts.append("--allow-not-ready-approval")
    parts.append("--write-receipt")
    return " ".join(shlex.quote(part) for part in parts)


def main() -> int:
    args = parse_args()
    try:
        provider = create_provider(args.provider)
        result = process_provider_human_acceptance_receipt(
            provider.provider_key,
            args.reviewer_name,
            args.decision,
            notes=args.notes,
            allow_not_ready_approval=args.allow_not_ready_approval,
            write_receipt=args.write_receipt,
        )
    except (UnknownProviderError, ProviderHumanAcceptanceReceiptError) as exc:
        print(f"BLOCKED: {exc}")
        return 2

    receipt = result["receipt"]
    gate = receipt["approval_gate"]
    print("EPL Betting Lab - Provider Human Acceptance Receipt")
    print(f"Mode: {'WRITE RECEIPT' if result['written'] else 'PREVIEW ONLY'}")
    print(f"Provider: {receipt['provider_name']} ({receipt['provider_key']})")
    print(f"Reviewer: {receipt['reviewer_name']}")
    print(f"Decision: {receipt['decision']}")
    print(f"Checklist verdict: {receipt['checklist_verdict']}")
    print(f"Approval gate: {gate['status']} - {gate['note']}")
    print(f"Receipt ID: {receipt['receipt_id']}")
    print(
        "Evidence: "
        f"{len(receipt['evidence']['reviewed_shadow_archives'])} reviewed shadow "
        "archive(s) plus the checklist and available comparison/policy files."
    )
    for warning in receipt.get("warnings", []):
        print(f"WARNING: {warning}")

    if result["written"]:
        print(f"JSON: {result['json']}")
        print(f"Markdown: {result['markdown']}")
        print(f"CSV: {result['csv']}")
        print(f"Archived receipt: {result['archive_directory']}")
    else:
        print("No receipt or archive files were written.")
        print("After reviewing this preview, write the receipt with:")
        print(_write_command(args))
    print(
        "Safety: this receipt does not edit provider policy, allowlist a provider, "
        "promote staging, enable cron, generate picks, or place bets."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
