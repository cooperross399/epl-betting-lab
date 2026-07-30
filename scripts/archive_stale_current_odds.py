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
        help=(
            "Archive stale rows after confirmation checks and a verified backup. "
            "Normally requires --confirm-id from preview."
        ),
    )
    parser.add_argument(
        "--confirm-id",
        default="",
        help="Confirmation ID copied from the reviewed archive preview. Used only with --apply.",
    )
    parser.add_argument(
        "--allow-unconfirmed-archive",
        action="store_true",
        help=(
            "Terminal-only override when apply cannot match a reviewed preview. "
            "Requires --apply and writes a prominent audit warning."
        ),
    )
    args = parser.parse_args()
    if args.confirm_id and not args.apply:
        parser.error("--confirm-id is used only with --apply")
    if args.allow_unconfirmed_archive and not args.apply:
        parser.error("--allow-unconfirmed-archive requires --apply")
    return args


def main() -> None:
    args = parse_args()
    paths = archive_stale_current_odds(
        MANUAL_DIR / "current_odds.csv",
        OUTPUTS_DIR,
        apply=args.apply,
        confirm_id=args.confirm_id,
        allow_unconfirmed_archive=args.allow_unconfirmed_archive,
    )
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Preview CSV: {paths['csv']}")
    print(f"Preview report: {paths['markdown']}")
    print(f"Preview metadata: {paths['metadata']}")
    print(f"Confirmation ID: {paths.get('confirm_id', 'Not available')}")
    print(f"Confirmation ID status: {paths.get('confirm_id_status', 'Not available')}")
    print(f"Confirmation gate: {paths.get('confirmation_gate_result', 'Not checked')}")
    print(f"Confirmation note: {paths.get('confirmation_gate_note', '')}")
    if paths.get("confirmation_gate_result") == "Override used":
        print(
            "WARNING: The unconfirmed archive override was used. "
            "Apply did not match a reviewed preview."
        )
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
