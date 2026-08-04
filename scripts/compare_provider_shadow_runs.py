#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_shadow_history import (
    save_provider_shadow_run_comparison,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare the latest two archived shadow runs for one provider."
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

    result = save_provider_shadow_run_comparison(provider.provider_key)
    summary = result["summary"]
    print("EPL Betting Lab - Provider Shadow Run Comparison")
    print(f"Provider: {summary['provider_name']} ({summary['provider_key']})")
    print(f"Archived runs found: {summary['archive_count']}")
    print(f"Verdict: {summary['verdict']}")
    print(f"Reason: {summary['verdict_reason']}")
    print(f"Next: {summary['next_step']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(f"JSON: {result['json']}")
    print(
        "Safety: comparison is report-only; it cannot edit policy, promote staging, "
        "enable cron, generate trusted picks, or place bets."
    )
    return 1 if summary["verdict"] == "Failed/untrusted" else 0


if __name__ == "__main__":
    raise SystemExit(main())
