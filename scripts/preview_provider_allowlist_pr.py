#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    READY_STATUS,
    save_provider_allowlist_pr_preview,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preview an exact provider allowlist policy PR without editing policy "
            "or allowing the provider."
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
            "Optional receipt verification JSON path. Defaults to the latest "
            "data/outputs verification report."
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

    result = save_provider_allowlist_pr_preview(
        provider.provider_key,
        verification_path=args.verification_path,
    )
    summary = result["summary"]
    print("EPL Betting Lab - Provider Allowlist PR Readiness Preview")
    print(f"Provider: {summary['provider_name']} ({summary['provider_type']})")
    print(f"Status: {summary['status']}")
    if summary["blockers"]:
        print("Blockers:")
        for blocker in summary["blockers"]:
            print(f"- {blocker}")
    if summary["recommended_pr_title"]:
        print(f"Recommended PR title: {summary['recommended_pr_title']}")
    print(f"JSON: {result['json']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(
        "Preview complete. No policy, staging, provider, cron, model, pick, bet, "
        "receipt, odds, import, or ledger file was changed."
    )
    return 0 if summary["status"] == READY_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
