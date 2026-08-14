#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    compare_latest_epl_weekly_pipeline_runs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the latest two archived EPL weekly pipeline receipts. "
            "This command is read-only apart from generated comparison reports."
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
    result = compare_latest_epl_weekly_pipeline_runs(args.output_dir)
    print(f"Weekly pipeline comparison: {result['verdict']}")
    print(f"Markdown report: {result['markdown']}")
    print(f"JSON report: {result['json']}")
    print(f"CSV report: {result['csv']}")
    print("No manual files were edited and no bets were placed.")
    return 1 if result["verdict"] == "Failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
