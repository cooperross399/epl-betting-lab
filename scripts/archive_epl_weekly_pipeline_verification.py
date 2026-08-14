#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar import (
    SIDECAR_ARCHIVED_VERDICT,
    archive_latest_epl_weekly_pipeline_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Archive the latest automatic EPL weekly pipeline receipt verification "
            "as a checksum-bound sidecar. This command only writes report copies."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report output directory. Defaults to data/outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = archive_latest_epl_weekly_pipeline_verification(args.output_dir)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Verification sidecar not created: {exc}")
        return 2

    summary = result["summary"]
    print("EPL Weekly Pipeline Verification Sidecar")
    print(f"Verdict: {result['verdict']}")
    print(f"Pipeline receipt ID: {summary['pipeline_receipt_id'] or 'Missing'}")
    print(f"Sidecar receipt ID: {summary['sidecar_receipt_id']}")
    print(f"Sidecar archive: {result['archive_dir']}")
    print(f"Markdown report: {result['markdown']}")
    print("The sealed pipeline archive and protected input files were not changed.")
    return 0 if result["verdict"] == SIDECAR_ARCHIVED_VERDICT else 2


if __name__ == "__main__":
    raise SystemExit(main())
