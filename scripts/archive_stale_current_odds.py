#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.stale_current_odds_archive import archive_stale_current_odds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview stale current-odds archiving, or apply it explicitly with backups."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Archive stale rows and rewrite current_odds.csv after creating a backup.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = archive_stale_current_odds(
        MANUAL_DIR / "current_odds.csv",
        OUTPUTS_DIR,
        apply=args.apply,
    )
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Preview CSV: {paths['csv']}")
    print(f"Preview report: {paths['markdown']}")
    if "backup" in paths:
        print(f"Backup: {paths['backup']}")
    if "stale_archive" in paths:
        print(f"Stale rows archive: {paths['stale_archive']}")
    if "audit_markdown" in paths:
        print(f"Apply audit: {paths['audit_markdown']}")
    if not args.apply:
        print(
            "Preview only. No input files were changed. "
            "Use --apply from Terminal only after reviewing the preview."
        )
    elif paths["status"] != "applied":
        print("No files were changed because the preview was not ready to apply.")


if __name__ == "__main__":
    main()
