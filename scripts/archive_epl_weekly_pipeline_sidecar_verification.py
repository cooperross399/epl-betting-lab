#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.epl_weekly_pipeline_sidecar_verification_archive import (
    SIDECAR_VERIFICATION_ARCHIVED_VERDICT,
    archive_latest_epl_weekly_pipeline_sidecar_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Archive the latest EPL weekly pipeline sidecar-verification reports "
            "as a separate checksum-bound receipt. This command only copies and "
            "writes reports; sealed archives are not modified."
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
        result = archive_latest_epl_weekly_pipeline_sidecar_verification(
            args.output_dir
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Sidecar verification was not archived: {exc}")
        return 2

    summary = result["summary"]
    print("EPL Weekly Pipeline Sidecar Verification Archive")
    print(f"Verdict: {result['verdict']}")
    print(
        "Archive receipt ID: "
        f"{summary['sidecar_verification_archive_receipt_id']}"
    )
    print(f"Sealed sidecar checked: {summary['sidecar_archive_path'] or 'Missing'}")
    print(f"Archive folder: {result['archive_dir']}")
    print(f"Markdown report: {result['markdown']}")
    print("The sealed pipeline and verification sidecar archives were not changed.")
    return 0 if result["verdict"] == SIDECAR_VERIFICATION_ARCHIVED_VERDICT else 2


if __name__ == "__main__":
    raise SystemExit(main())
