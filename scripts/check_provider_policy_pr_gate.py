#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_policy_pr_gate import (
    FAILED_VERDICT,
    NOT_APPLICABLE_VERDICT,
    PASSED_VERDICT,
    save_provider_policy_pr_gate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed when a provider-policy PR lacks verified evidence or "
            "does not conform to its reviewed preview. This command is read-only "
            "except for its report outputs."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    parser.add_argument(
        "--base-ref",
        help=(
            "Optional PR base commit/ref. CI should pass the pull request base SHA; "
            "local runs default to origin/main or main."
        ),
    )
    parser.add_argument(
        "--head-ref",
        help=(
            "Optional PR head commit/ref. CI should pass the pull request head SHA; "
            "defaults to HEAD when --base-ref is supplied."
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

    result = save_provider_policy_pr_gate(
        provider.provider_key,
        base_ref=args.base_ref,
        head_ref=args.head_ref,
    )
    summary = result["summary"]
    detection = summary["change_detection"]
    print("EPL Betting Lab - Provider Policy PR Gate")
    print(f"Provider: {summary['provider_name']} ({summary['provider_key']})")
    print(f"Policy changed: {'yes' if summary['policy_changed'] else 'no'}")
    print(f"Detection: {detection['source']}")
    print(f"Verdict: {summary['verdict']}")
    if summary["blockers"]:
        print("Blocking issues:")
        for blocker in summary["blockers"]:
            print(f"- {blocker}")
    print(f"JSON: {result['json']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(
        "Read-only gate complete. No policy, evidence, staging, provider, cron, "
        "model, pick, bet, odds, import, or ledger file was changed."
    )
    if summary["verdict"] in {PASSED_VERDICT, NOT_APPLICABLE_VERDICT}:
        return 0
    return 1 if summary["verdict"] == FAILED_VERDICT else 2


if __name__ == "__main__":
    raise SystemExit(main())
