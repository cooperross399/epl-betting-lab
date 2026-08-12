#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_allowlist_evidence_bundle_verification import (
    VERIFIED_VERDICT,
    save_provider_allowlist_evidence_bundle_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-hash a provider allowlist evidence bundle before PR approval. "
            "This command never edits provider policy or evidence files."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    parser.add_argument(
        "--bundle-path",
        type=Path,
        help=(
            "Optional repository-local bundle JSON path. By default, the latest "
            "archived bundle for the provider is verified."
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

    result = save_provider_allowlist_evidence_bundle_verification(
        provider.provider_key,
        bundle_path=args.bundle_path,
    )
    summary = result["summary"]
    print("EPL Betting Lab - Provider Allowlist Evidence Bundle Verification")
    print(f"Provider: {summary['provider_name']} ({summary['provider_key']})")
    print(f"Bundle: {summary['bundle_path']}")
    print(f"Verdict: {summary['verdict']}")
    if summary["blockers"]:
        print("Blockers or mismatches:")
        for blocker in summary["blockers"]:
            print(f"- {blocker}")
    print(f"JSON: {result['json']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(
        "Read-only verification complete. No policy, receipt, staging, provider, "
        "cron, model, pick, bet, odds, import, or ledger file was changed."
    )
    return 0 if summary["verdict"] == VERIFIED_VERDICT else 2


if __name__ == "__main__":
    raise SystemExit(main())
