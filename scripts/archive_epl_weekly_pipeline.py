#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    archive_latest_epl_weekly_pipeline,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Archive the latest EPL weekly pipeline reports with a deterministic, "
            "checksum-bound receipt. This command only writes report copies."
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
        result = archive_latest_epl_weekly_pipeline(args.output_dir)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Archive not created: {exc}")
        return 2

    comparison = result["comparison"]
    print("EPL weekly pipeline receipt archived safely.")
    print(f"Receipt ID: {result['receipt_id']}")
    print(f"Archive folder: {result['archive_dir']}")
    print(f"Comparison verdict: {comparison['verdict']}")
    print("Only report outputs were copied. No manual files or bets were changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
