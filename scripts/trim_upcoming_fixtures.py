#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.fixture_slate_trim import (
    apply_fixture_slate_trim,
    build_fixture_slate_trim_preview,
    save_fixture_slate_trim_preview,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or apply keeping only the imminent matchweek group in "
            "data/manual/upcoming_fixtures.csv. Later matchweek fixtures are moved "
            "to a dated deferred-fixtures archive, never deleted. Preview is the "
            "default and edits nothing. Apply is Terminal-only and requires the "
            "confirmation ID from a fresh preview. This tool never edits odds, "
            "fabricates prices, or places bets."
        )
    )
    parser.add_argument(
        "--fixtures-path",
        type=Path,
        help="Fixture slate CSV. Defaults to data/manual/upcoming_fixtures.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the previewed trim. Requires --confirm-id from the preview.",
    )
    parser.add_argument(
        "--confirm-id",
        default="",
        help="Confirmation ID printed by the preview.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Fixture Slate Trim")
    if args.apply:
        result = apply_fixture_slate_trim(
            args.fixtures_path,
            confirm_id=args.confirm_id,
            output_dir=args.output_dir,
        )
        print(f"Status: {result['status']}")
        print(result["message"])
        if result["status"] == "Trim applied":
            print(f"Backup: {result['backup_path']}")
            print(f"Deferred fixtures archive: {result['deferred_archive_path']}")
            print(
                "Next: rerun `python scripts/run_week1_launch_readiness.py` and "
                "review its odds-template guidance so the odds file matches the "
                "trimmed slate."
            )
            return 0
        return 2

    preview = build_fixture_slate_trim_preview(args.fixtures_path)
    paths = save_fixture_slate_trim_preview(preview, args.output_dir)
    print("Preview only: nothing was edited.")
    print(f"Status: {preview['status']}")
    print(preview["message"])
    print(
        f"Keep: {preview['kept_count']} | Defer: {preview['deferred_count']} | "
        f"Needs attention: {preview['attention_count']}"
    )
    if preview["confirm_id"]:
        print("")
        print("To apply this exact trim from Terminal:")
        print("python scripts/trim_upcoming_fixtures.py \\")
        print("  --apply \\")
        print(f"  --confirm-id {preview['confirm_id']}")
    print(f"Markdown preview: {paths['markdown']}")
    print(f"CSV preview: {paths['csv']}")
    if preview["status"] in {"Missing fixtures", "Needs fixture refresh"}:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
