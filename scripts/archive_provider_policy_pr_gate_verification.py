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
)
from epl_betting_lab.reports.provider_policy_pr_gate_verification_archive import (
    NOT_READY_VERDICT,
    ProviderPolicyGateVerificationArchiveError,
    READY_VERDICT,
    save_provider_policy_pr_gate_verification_archive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Archive a Provider Policy PR Gate receipt verification with its "
            "exact report checksums and available pull-request/run metadata. "
            "This command never edits provider policy."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    parser.add_argument(
        "--verification-path",
        type=Path,
        help=(
            "Optional receipt-verification JSON path. Defaults to "
            "data/outputs/provider_policy_pr_gate_receipt_verification.json."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        provider = create_provider(args.provider)
        result = save_provider_policy_pr_gate_verification_archive(
            provider.provider_key,
            verification_path=args.verification_path,
        )
    except (UnknownProviderError, ProviderPolicyGateVerificationArchiveError) as exc:
        print(f"FAILED: {exc}")
        return 1

    summary = result["summary"]
    print("EPL Betting Lab - Provider Policy PR Gate Verification Archive")
    print(f"Provider: {summary['provider_name']} ({summary['provider_key']})")
    print(f"Verdict: {summary['verdict']}")
    print(f"Approval ready: {'yes' if summary['approval_ready'] else 'no'}")
    print(f"Gate receipt ID: {summary['gate_receipt_id'] or 'Missing'}")
    print(f"Archive receipt ID: {summary['archive_receipt_id']}")
    print(f"PR: {summary['pr_url'] or summary['pr_number'] or 'Local/not available'}")
    print(
        "GitHub run: "
        f"{summary['github_run_url'] or summary['github_run_id'] or 'Local/not available'}"
    )
    if summary["blockers"]:
        print("Blockers/notices:")
        for blocker in summary["blockers"]:
            print(f"- {blocker}")
    print(f"JSON: {result['json']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(f"Archive: {result['archive_directory']}")
    print(
        "Read-only archive complete. No provider policy, staging, provider, cron, "
        "model, odds, import, ledger, pick, or bet was changed."
    )
    if summary["verdict"] == NOT_READY_VERDICT:
        print(
            "This archive is retained for diagnostics only and is not evidence "
            "that the PR is ready for approval."
        )
    if summary["verdict"] == READY_VERDICT:
        return 0
    if summary["verification_verdict"] == NOT_APPLICABLE_VERDICT:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
