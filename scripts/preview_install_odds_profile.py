#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.odds_profile_install import process_odds_profile_install


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly install a validated draft odds export profile."
    )
    parser.add_argument(
        "--suggestion",
        default=str(OUTPUTS_DIR / "odds_export_profile_suggestion.json"),
        help="Draft suggestion JSON path.",
    )
    parser.add_argument(
        "--registry",
        default=str(MANUAL_DIR / "odds_import_profiles.json"),
        help="Profile registry JSON path.",
    )
    parser.add_argument("--apply", action="store_true", help="Install from Terminal after safety checks.")
    parser.add_argument(
        "--allow-needs-edits",
        action="store_true",
        help="Explicitly accept a Needs edits verdict or unresolved review fields.",
    )
    parser.add_argument(
        "--allow-missing-validation",
        action="store_true",
        help="Explicitly accept that no ready validation verdict is available.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Explicitly replace an existing profile with the same name.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = process_odds_profile_install(
        Path(args.suggestion),
        OUTPUTS_DIR / "odds_export_profile_suggestion_validation.md",
        OUTPUTS_DIR / "odds_export_profile_suggestion_validation.csv",
        Path(args.registry),
        OUTPUTS_DIR,
        apply=args.apply,
        allow_needs_edits=args.allow_needs_edits,
        allow_missing_validation=args.allow_missing_validation,
        replace_existing=args.replace_existing,
    )
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Preview JSON: {paths['json']}")
    print(f"Preview report: {paths['markdown']}")
    if "backup" in paths:
        print(f"Backup: {paths['backup']}")
    if "audit_markdown" in paths:
        print(f"Install audit: {paths['audit_markdown']}")


if __name__ == "__main__":
    main()
