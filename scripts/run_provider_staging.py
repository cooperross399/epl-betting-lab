#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import STAGING_DIR
from epl_betting_lab.providers.base import (
    ProviderRunRequest,
    SOURCE_FIXTURES_FILENAME,
    SOURCE_ODDS_FILENAME,
    UnknownProviderError,
)
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare provider odds and fixtures in data/staging. Dry-run is the "
            "default; this command never validates, promotes, or places bets."
        )
    )
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Provider adapter to use: {', '.join(available_provider_names())}.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="live",
        action="store_false",
        help="Preview configuration without provider network or staging writes (default).",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Explicitly fetch/copy provider data and write staging evidence.",
    )
    parser.set_defaults(live=False)
    parser.add_argument(
        "--overwrite-staging",
        action="store_true",
        help="Intentionally replace the complete existing staging bundle.",
    )
    parser.add_argument(
        "--generated-by",
        default="scripts/run_provider_staging.py",
        help="Non-secret person or process name stored in provenance.",
    )
    parser.add_argument(
        "--notes",
        default="Provider staging adapter run.",
        help="Optional non-secret provenance note.",
    )

    manual = parser.add_argument_group("manual provider options")
    manual.add_argument(
        "--odds-source",
        type=Path,
        default=STAGING_DIR / SOURCE_ODDS_FILENAME,
        help="Prepared real-odds source CSV inside data/staging.",
    )
    manual.add_argument(
        "--fixtures-source",
        type=Path,
        default=STAGING_DIR / SOURCE_FIXTURES_FILENAME,
        help="Prepared fixture source CSV inside data/staging.",
    )
    manual.add_argument(
        "--provider-name",
        default="manual_reviewed",
        help="Manual provider name checked later by staging provider policy.",
    )

    odds_api = parser.add_argument_group("odds_api provider options")
    odds_api.add_argument(
        "--sport-key",
        default="soccer_epl",
        help="Provider sport key. Defaults to soccer_epl.",
    )
    odds_api.add_argument(
        "--regions",
        default="us",
        help="Provider bookmaker region. Defaults to us.",
    )
    odds_api.add_argument(
        "--bookmakers",
        default="",
        help="Optional comma-separated bookmaker keys. Never include credentials.",
    )
    return parser.parse_args()


def _provider_from_args(args: argparse.Namespace):
    key = args.provider.strip().lower().replace("-", "_")
    if key == "manual":
        return create_provider(
            key,
            odds_source_path=args.odds_source,
            fixtures_source_path=args.fixtures_source,
            provider_name=args.provider_name,
        )
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

    result = provider.run(
        ProviderRunRequest(
            dry_run=not args.live,
            overwrite_staging=args.overwrite_staging,
            generated_by=args.generated_by,
            notes=args.notes,
        )
    )
    summary = result["summary"]
    print("EPL Betting Lab - Provider Staging")
    print(f"Provider: {summary['provider_name']} ({summary['provider_type']})")
    print(f"Mode: {summary.get('mode', 'Dry run' if not args.live else 'Live')}")
    print(f"Status: {summary['status']}")
    print(f"Provider report: {result['report_markdown']}")
    print(f"Provider JSON: {result['report_json']}")
    for warning in summary.get("warnings", []):
        print(f"WARNING: {warning}")
    for blocker in summary.get("blockers", []):
        print(f"BLOCKED: {blocker}")
    print(f"Next: {summary['next_step']}")
    print(
        "Safety: no secrets were printed; no production/manual files were edited; "
        "no bets were placed."
    )
    if summary["status"] in {"Completed", "Dry run ready"}:
        return 0
    return 1 if summary["status"] == "Failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
