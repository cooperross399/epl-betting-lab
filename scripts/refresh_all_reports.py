#!/usr/bin/env python
"""Refresh every report in dependency order, in one step.

Re-derives the card input, card, routine bridges, card comparison, and browser
status page from evidence already on disk. It never contacts the provider, so
it spends no quota and cannot change what the evidence says: refreshing the
view and refetching the data are separate actions.

Generates no picks beyond what the gates already allow, places no bets, applies
no settlement, and writes no protected file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.refresh_all import refresh_all_reports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Defaults to data/outputs.")
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated step names to run instead of all of them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    only = [item.strip() for item in args.only.split(",") if item.strip()] or None

    print("EPL Betting Lab - Refresh All Reports")
    print(
        "Offline: re-derives reports from evidence already on disk. No provider "
        "contact, no quota, no bets, no settlement, no protected file writes."
    )

    summary = refresh_all_reports(output_dir=args.output_dir, only=only)

    for step in summary["steps"]:
        mark = {"ok": "OK  ", "failed": "FAIL", "skipped": "--  "}[step["status"]]
        print(f"{mark} {step['step']}: {step['description']}")
        if step["status"] == "failed":
            print(f"     {step['error']}")

    print(
        f"Done: {summary['ok_count']} ok, {summary['failed_count']} failed, "
        f"{summary['skipped_count']} skipped."
    )
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
