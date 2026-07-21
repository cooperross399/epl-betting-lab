#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.stale_current_odds_archive_rollback import (
    process_stale_current_odds_archive_rollback,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly restore a pre-archive current-odds backup."
    )
    parser.add_argument(
        "--backup-path",
        required=True,
        help="Selected pre-archive current_odds CSV backup to inspect or restore.",
    )
    parser.add_argument(
        "--current-odds",
        default=str(MANUAL_DIR / "current_odds.csv"),
        help="Current odds file that rollback would replace.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Restore the selected backup after creating a backup of the current file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = process_stale_current_odds_archive_rollback(
        Path(args.backup_path),
        Path(args.current_odds),
        OUTPUTS_DIR,
        apply=args.apply,
    )
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Rollback preview CSV: {paths['csv']}")
    print(f"Rollback preview report: {paths['markdown']}")
    if "pre_rollback_backup" in paths:
        print(f"Pre-rollback backup: {paths['pre_rollback_backup']}")
    if "audit_markdown" in paths:
        print(f"Rollback audit: {paths['audit_markdown']}")
    if not args.apply:
        print(
            "Preview only. No input files were changed. "
            "Add --apply from Terminal only after reviewing the preview."
        )
    elif paths["status"] != "applied":
        print("No files were changed because the rollback preview was not ready to apply.")


if __name__ == "__main__":
    main()
