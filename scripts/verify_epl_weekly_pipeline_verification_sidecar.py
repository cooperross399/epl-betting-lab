#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar_verification import (
    save_epl_weekly_pipeline_verification_sidecar_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-hash an archived EPL weekly pipeline verification sidecar and "
            "its referenced sealed pipeline receipt. This command is read-only "
            "apart from separate verification report outputs."
        )
    )
    parser.add_argument(
        "--sidecar-path",
        type=Path,
        help=(
            "Archived sidecar folder or sidecar JSON. Defaults to the latest "
            "archived weekly verification sidecar."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Verification output directory. Defaults to data/outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = save_epl_weekly_pipeline_verification_sidecar_verification(
        sidecar_path=args.sidecar_path,
        output_dir=args.output_dir,
    )
    summary = result["summary"]
    print("EPL Weekly Pipeline Verification Sidecar Verification")
    print(f"Verdict: {result['verdict']}")
    print(f"Sidecar archive: {summary['sidecar_archive_path'] or 'Not available'}")
    print(
        "Sidecar receipt ID: "
        f"{summary['original_sidecar_receipt_id'] or 'Not available'} "
        "(recalculated: "
        f"{summary['recalculated_sidecar_receipt_id'] or 'Not available'})"
    )
    print(
        "Referenced pipeline archive: "
        f"{summary['referenced_pipeline_archive_path'] or 'Not available'}"
    )
    print(f"Mismatch/blocker count: {summary['mismatch_count']}")
    print(f"Markdown report: {result['markdown']}")
    print(f"JSON report: {result['json']}")
    print(f"CSV report: {result['csv']}")
    print("Nothing was applied and no archive or protected input was changed.")
    return 0 if result["verdict"] == "Weekly verification sidecar verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
