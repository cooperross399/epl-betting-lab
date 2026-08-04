#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import (
    OUTPUTS_DIR,
    STAGING_DIR,
    STAGING_PROVENANCE_PATH,
    STAGING_PROVIDER_POLICY_PATH,
)
from epl_betting_lab.reports.staging_input_validation import (
    FIXTURES_STAGING_FILENAME,
    ODDS_STAGING_FILENAME,
    save_staging_input_validation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate provider odds and fixture staging CSVs without copying or "
            "promoting them."
        )
    )
    parser.add_argument(
        "--odds-path",
        type=Path,
        default=STAGING_DIR / ODDS_STAGING_FILENAME,
        help="Odds staging CSV inside data/staging.",
    )
    parser.add_argument(
        "--fixtures-path",
        type=Path,
        default=STAGING_DIR / FIXTURES_STAGING_FILENAME,
        help="Fixtures staging CSV inside data/staging.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUTS_DIR,
        help="Directory for the read-only validation reports.",
    )
    parser.add_argument(
        "--provenance-path",
        type=Path,
        default=STAGING_PROVENANCE_PATH,
        help="Provider/source provenance JSON inside data/staging.",
    )
    parser.add_argument(
        "--provider-policy-path",
        type=Path,
        default=STAGING_PROVIDER_POLICY_PATH,
        help="Allowed provider, receipt age, timezone, and Thursday cutoff policy.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = save_staging_input_validation(
        args.odds_path,
        args.fixtures_path,
        output_dir=args.output_dir,
        provenance_path=args.provenance_path,
        provider_policy_path=args.provider_policy_path,
    )
    print("EPL Betting Lab - Staging Input Validation")
    print(f"Verdict: {result['verdict']}")
    print(
        "Provider: "
        f"{result['provider_name'] or 'unknown'} ({result['provider_type']})"
    )
    print(f"Provider policy: {result['provider_policy_status']}")
    print(f"Provider provenance: {result['provenance_status']}")
    print(
        "Source checksums (odds / fixtures): "
        f"{result['source_odds_checksum_status']} / "
        f"{result['source_fixtures_checksum_status']}"
    )
    print(
        "Staging checksums (odds / fixtures): "
        f"{result['staging_odds_checksum_status']} / "
        f"{result['staging_fixtures_checksum_status']}"
    )
    print(
        "Source-to-staging pairs (odds / fixtures): "
        f"{result['odds_checksum_pair_status']} / "
        f"{result['fixtures_checksum_pair_status']}"
    )
    print(f"Receipt age policy: {result['receipt_age_status']}")
    print(f"Thursday cutoff policy: {result['cutoff_policy_status']}")
    print(
        "Eligible for handoff: "
        f"{'yes' if result['handoff_eligible'] else 'no'}"
    )
    print(f"Next step: {result['next_step']}")
    print(f"CSV: {result['csv']}")
    print(f"Markdown: {result['markdown']}")
    print(f"JSON: {result['json']}")
    print("Read-only validation complete. No staging or manual files were changed.")
    return 0 if result["verdict"] == "Ready for handoff" else 2


if __name__ == "__main__":
    raise SystemExit(main())
