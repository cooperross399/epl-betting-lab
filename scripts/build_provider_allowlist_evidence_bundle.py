#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_allowlist_evidence_bundle import (
    save_provider_allowlist_evidence_bundle,
)


READY_VERDICT = "Evidence bundle ready for PR review"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a checksum-bound, read-only evidence bundle for provider "
            "allowlist PR review. This command never edits provider policy."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        provider = create_provider(args.provider)
    except UnknownProviderError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    result = save_provider_allowlist_evidence_bundle(provider.provider_key)
    summary = result["summary"]
    print("EPL Betting Lab - Provider Allowlist PR Evidence Bundle")
    print(f"Provider: {summary['provider_name']} ({summary['provider_key']})")
    print(f"Verdict: {summary['verdict']}")
    print(f"Bundle ID: {summary['bundle_id']}")
    print(f"Bundle SHA-256: {summary['bundle_checksum_sha256']}")
    print(f"JSON: {result['json']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(f"Archived bundle: {result['archive_directory']}")
    print(
        "Read-only evidence build complete. No policy, receipt, staging, provider, "
        "cron, model, pick, bet, odds, import, or ledger file was changed."
    )
    return 0 if summary["verdict"] == READY_VERDICT else 2


if __name__ == "__main__":
    raise SystemExit(main())
