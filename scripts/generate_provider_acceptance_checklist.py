#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_acceptance_checklist import (
    DEFAULT_MINIMUM_LIVE_RUNS,
    DEFAULT_REVIEW_WINDOW,
    save_provider_acceptance_checklist,
)


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a read-only provider acceptance checklist from archived "
            "shadow runs."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    parser.add_argument(
        "--minimum-runs",
        type=_positive_integer,
        default=DEFAULT_MINIMUM_LIVE_RUNS,
        help=f"Required completed live runs (default: {DEFAULT_MINIMUM_LIVE_RUNS}).",
    )
    parser.add_argument(
        "--review-window",
        type=_positive_integer,
        default=DEFAULT_REVIEW_WINDOW,
        help=f"Latest live runs to review (default: {DEFAULT_REVIEW_WINDOW}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        provider = create_provider(args.provider)
    except UnknownProviderError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    if args.review_window < args.minimum_runs:
        print("BLOCKED: --review-window must be at least --minimum-runs.")
        return 2

    result = save_provider_acceptance_checklist(
        provider.provider_key,
        minimum_live_runs=args.minimum_runs,
        review_window=args.review_window,
    )
    summary = result["summary"]
    print("EPL Betting Lab - Provider Acceptance Checklist")
    print(f"Provider: {summary['provider_name']} ({summary['provider_key']})")
    print(f"Verdict: {summary['verdict']}")
    print(
        "Completed live runs: "
        f"{summary['completed_live_run_count']} / {summary['minimum_live_runs']} required"
    )
    print(f"Provider currently allowed: {summary['provider_currently_allowed']}")
    print(f"Next: {summary['next_step']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(f"JSON: {result['json']}")
    print(
        "Safety: this report cannot run a provider, edit policy, allowlist a "
        "provider, promote staging, enable cron, or place bets."
    )
    return 0 if summary["verdict"] == "Ready for human allowlist review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
