#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.odds_profile_verification import (
    verify_installed_odds_profile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify an installed odds export profile against a source CSV in memory."
    )
    parser.add_argument("--profile", required=True, help="Installed profile name.")
    parser.add_argument(
        "--source",
        required=True,
        help="Source export CSV path, such as data/manual/sportsbook_export.csv.",
    )
    parser.add_argument(
        "--registry",
        default=str(MANUAL_DIR / "odds_import_profiles.json"),
        help="Profile registry JSON path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = verify_installed_odds_profile(
        args.profile,
        Path(args.source),
        Path(args.registry),
        OUTPUTS_DIR,
    )
    print(f"Verdict: {paths['verdict']}")
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Verification CSV: {paths['csv']}")
    print(f"Verification report: {paths['markdown']}")


if __name__ == "__main__":
    main()
