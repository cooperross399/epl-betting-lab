#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.odds_profile_rollback import (
    process_odds_profile_rollback,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly restore an odds profile registry backup."
    )
    parser.add_argument("--backup-path", required=True, help="Registry backup JSON to inspect or restore.")
    parser.add_argument(
        "--registry",
        default=str(MANUAL_DIR / "odds_import_profiles.json"),
        help="Current profile registry path.",
    )
    parser.add_argument("--apply", action="store_true", help="Restore the selected backup from Terminal.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = process_odds_profile_rollback(
        Path(args.backup_path),
        Path(args.registry),
        OUTPUTS_DIR,
        apply=args.apply,
    )
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Rollback preview JSON: {paths['json']}")
    print(f"Rollback preview report: {paths['markdown']}")
    if "pre_rollback_backup" in paths:
        print(f"Pre-rollback backup: {paths['pre_rollback_backup']}")
    if "audit_markdown" in paths:
        print(f"Rollback audit: {paths['audit_markdown']}")


if __name__ == "__main__":
    main()
