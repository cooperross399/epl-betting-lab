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
        help=(
            "Restore the selected backup after confirmation checks and a recovery backup. "
            "Normally requires --confirm-id from preview."
        ),
    )
    parser.add_argument(
        "--allow-checksum-mismatch",
        action="store_true",
        help=(
            "Terminal-only override for an inspected backup with a known checksum mismatch. "
            "Requires --apply."
        ),
    )
    parser.add_argument(
        "--confirm-id",
        default="",
        help="Confirmation ID copied from the reviewed rollback preview. Used only with --apply.",
    )
    parser.add_argument(
        "--allow-unconfirmed-rollback",
        action="store_true",
        help=(
            "Terminal-only override when apply cannot match a reviewed preview. "
            "Requires --apply and writes a prominent audit warning."
        ),
    )
    args = parser.parse_args()
    if args.allow_checksum_mismatch and not args.apply:
        parser.error("--allow-checksum-mismatch requires --apply after manual backup inspection")
    if args.confirm_id and not args.apply:
        parser.error("--confirm-id is used only with --apply")
    if args.allow_unconfirmed_rollback and not args.apply:
        parser.error("--allow-unconfirmed-rollback requires --apply")
    return args


def main() -> None:
    args = parse_args()
    paths = process_stale_current_odds_archive_rollback(
        Path(args.backup_path),
        Path(args.current_odds),
        OUTPUTS_DIR,
        apply=args.apply,
        allow_checksum_mismatch=args.allow_checksum_mismatch,
        confirm_id=args.confirm_id,
        allow_unconfirmed_rollback=args.allow_unconfirmed_rollback,
    )
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Rollback preview CSV: {paths['csv']}")
    print(f"Rollback preview report: {paths['markdown']}")
    print(f"Checksum status: {paths.get('checksum_status', 'Not available')}")
    print(f"Checksum gate: {paths.get('checksum_gate_result', 'Not checked')}")
    print(f"Checksum note: {paths.get('checksum_gate_note', '')}")
    print(f"Confirmation ID: {paths.get('confirm_id', 'Not available')}")
    print(f"Confirmation ID status: {paths.get('confirm_id_status', 'Not available')}")
    print(f"Confirmation gate: {paths.get('confirmation_gate_result', 'Not checked')}")
    print(f"Confirmation note: {paths.get('confirmation_gate_note', '')}")
    if paths.get("checksum_gate_result") == "Override used":
        print(
            "WARNING: The checksum mismatch override was used. "
            "The restored backup may have changed after creation."
        )
    if paths.get("confirmation_gate_result") == "Override used":
        print(
            "WARNING: The unconfirmed rollback override was used. "
            "Apply did not match a reviewed preview."
        )
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
