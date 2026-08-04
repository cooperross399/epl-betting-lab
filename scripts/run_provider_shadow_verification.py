#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.providers.base import UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)
from epl_betting_lab.reports.provider_shadow_verification import (
    save_provider_shadow_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a controlled provider shadow verification. Dry-run is the "
            "default and makes no network request."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Registered provider: {', '.join(available_provider_names())}.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="live",
        action="store_false",
        help="Check provider configuration without network/staging writes (default).",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Explicitly fetch staging evidence, then run read-only validation.",
    )
    parser.set_defaults(live=False)
    parser.add_argument(
        "--overwrite-staging",
        action="store_true",
        help="Intentionally replace the complete existing staging bundle.",
    )
    parser.add_argument("--sport-key", default="soccer_epl")
    parser.add_argument("--regions", default="us")
    parser.add_argument(
        "--bookmakers",
        default="",
        help="Optional comma-separated provider bookmaker keys; never a credential.",
    )
    return parser.parse_args()


def _provider_from_args(args: argparse.Namespace):
    key = args.provider.strip().lower().replace("-", "_")
    if key == "odds_api":
        return create_provider(
            key,
            sport_key=args.sport_key,
            regions=args.regions,
            bookmakers=args.bookmakers,
        )
    return create_provider(key)


def main() -> int:
    args = parse_args()
    try:
        provider = _provider_from_args(args)
    except UnknownProviderError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    result = save_provider_shadow_verification(
        args.provider,
        dry_run=not args.live,
        overwrite_staging=args.overwrite_staging,
        provider=provider,
    )
    summary = result["summary"]
    print("EPL Betting Lab - Provider Shadow Verification")
    print(f"Provider: {summary['provider_name']} ({summary['provider_type']})")
    print(f"Mode: {summary['mode']}")
    print(f"Verdict: {summary['verdict']}")
    print(f"Reason: {summary['verdict_reason']}")
    print(f"Staging validation: {summary['staging_validation']['verdict']}")
    print(
        "Market rows (1X2 / totals / BTTS): "
        f"{summary['market_coverage']['market_counts']['1x2']} / "
        f"{summary['market_coverage']['market_counts']['total_2_5']} / "
        f"{summary['market_coverage']['market_counts']['btts']}"
    )
    print(f"Provider allowed by policy: {summary['provider_policy']['provider_allowed']}")
    print(f"Next: {summary['next_step']}")
    print(f"Markdown: {result['markdown']}")
    print(f"CSV: {result['csv']}")
    print(f"JSON: {result['json']}")
    print(
        "Safety: no trusted picks, policy edits, staging promotion, cron, bets, "
        "or secret output."
    )
    if not args.live:
        return 0
    if summary["verdict"] == "Shadow ready for review":
        return 0
    return 1 if summary["verdict"] == "Failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
