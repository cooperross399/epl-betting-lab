#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import STAGING_DIR
from epl_betting_lab.providers.manual_staging_provider import (
    SOURCE_FIXTURES_FILENAME,
    SOURCE_ODDS_FILENAME,
    run_manual_staging_provider,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy prepared manual provider CSVs into staging and write provenance. "
            "This does not validate or promote the data."
        )
    )
    parser.add_argument(
        "--odds-source",
        type=Path,
        default=STAGING_DIR / SOURCE_ODDS_FILENAME,
        help="Prepared real-odds CSV inside data/staging.",
    )
    parser.add_argument(
        "--fixtures-source",
        type=Path,
        default=STAGING_DIR / SOURCE_FIXTURES_FILENAME,
        help="Prepared upcoming-fixtures CSV inside data/staging.",
    )
    parser.add_argument(
        "--provider-name",
        default="manual_reviewed",
        help="Provider name that must later pass staging_provider_policy.json.",
    )
    parser.add_argument(
        "--generated-by",
        default="scripts/run_manual_staging_provider.py",
        help="Person or controlled process preparing this staging bundle.",
    )
    parser.add_argument(
        "--notes",
        default="Controlled manual staging provider run.",
        help="Optional provenance note. Do not include credentials.",
    )
    parser.add_argument(
        "--overwrite-staging",
        action="store_true",
        help="Intentionally replace all existing staging outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_manual_staging_provider(
        odds_source_path=args.odds_source,
        fixtures_source_path=args.fixtures_source,
        provider_name=args.provider_name,
        generated_by=args.generated_by,
        notes=args.notes,
        overwrite_staging=args.overwrite_staging,
    )
    summary = result["summary"]
    print("EPL Betting Lab - Manual Staging Provider")
    print(f"Status: {summary['status']}")
    print(
        f"Provider: {summary['provider_name']} ({summary['provider_type']})"
    )
    print(f"Provider report: {result['report_markdown']}")
    print(f"Provider JSON: {result['report_json']}")
    if summary["status"] == "Completed":
        print(f"Staging odds: {result['staging_odds']}")
        print(f"Staging fixtures: {result['staging_fixtures']}")
        print(f"Provenance: {result['provenance']}")
        print("Next: python scripts/validate_staging_inputs.py")
    else:
        print(f"Next: {summary['next_step']}")
        for blocker in summary["blockers"]:
            print(f"BLOCKED: {blocker}")
    print("No production/manual files were edited. No odds were fabricated.")
    return 0 if summary["status"] == "Completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
