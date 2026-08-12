#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_allowlist_pr_conformance import (
    CONFORMS_VERDICT,
    save_provider_allowlist_pr_conformance,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether a provider allowlist policy change exactly matches an "
            "existing reviewed preview. This command never edits policy."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    parser.add_argument(
        "--preview-path",
        type=Path,
        help=(
            "Optional allowlist PR preview JSON path. Defaults to "
            "data/outputs/provider_allowlist_pr_preview.json."
        ),
    )
    parser.add_argument(
        "--policy-path",
        type=Path,
        help=(
            "Optional provider policy JSON path. Defaults to "
            "data/manual/staging_provider_policy.json."
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

    result = save_provider_allowlist_pr_conformance(
        provider.provider_key,
        preview_path=args.preview_path,
        policy_path=args.policy_path,
    )
    summary = result["summary"]
    print("EPL Betting Lab - Provider Allowlist PR Conformance Check")
    print(f"Provider: {summary['provider_name']} ({summary['provider_type']})")
    print(f"Verdict: {summary['verdict']}")
    if summary["blockers"]:
        print("Issues:")
        for blocker in summary["blockers"]:
            print(f"- {blocker}")
    print(f"JSON: {result['json']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(
        "Read-only check complete. No policy, receipt, staging, provider, cron, "
        "model, pick, bet, odds, import, or ledger file was changed."
    )
    return 0 if summary["verdict"] == CONFORMS_VERDICT else 2


if __name__ == "__main__":
    raise SystemExit(main())
