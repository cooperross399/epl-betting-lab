#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.epl_weekly_pipeline_receipt_verification import (
    save_epl_weekly_pipeline_receipt_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an archived EPL weekly pipeline receipt and its report checksums. "
            "This command is read-only apart from verification report outputs."
        )
    )
    parser.add_argument(
        "--archive-path",
        type=Path,
        help="Archived run folder or archive receipt JSON. Defaults to the latest run.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Verification output directory. Defaults to data/outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = save_epl_weekly_pipeline_receipt_verification(
        archive_path=args.archive_path,
        output_dir=args.output_dir,
    )
    summary = result["summary"]
    print("EPL Weekly Pipeline Receipt Verification")
    print(f"Verdict: {result['verdict']}")
    print(f"Archive: {summary['archive_path'] or 'Not available'}")
    print(
        "Receipt ID: "
        f"{summary['original_receipt_id'] or 'Not available'} "
        f"(recalculated: {summary['recalculated_receipt_id'] or 'Not available'})"
    )
    print(f"Mismatch/blocker count: {summary['mismatch_count']}")
    print(f"Markdown report: {result['markdown']}")
    print(f"JSON report: {result['json']}")
    print(f"CSV report: {result['csv']}")
    print("Nothing was applied and no protected manual files were changed.")
    return 0 if result["verdict"] == "Weekly pipeline receipt verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
