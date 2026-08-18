#!/usr/bin/env python
"""Render the current state as a GitHub Actions job summary.

Writes markdown suitable for $GITHUB_STEP_SUMMARY so the card is readable on
the run page with no download and no terminal. Reads existing reports only:
no provider contact, no picks generated, no bets, no settlement.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from epl_betting_lab.reports.run_summary import save_run_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Defaults to data/outputs.")
    parser.add_argument(
        "--append-to-step-summary",
        action="store_true",
        help="Also append to $GITHUB_STEP_SUMMARY when running in Actions.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = save_run_summary(output_dir=args.output_dir)
    print(result["text"])

    if args.append_to_step_summary:
        target = os.environ.get("GITHUB_STEP_SUMMARY", "")
        if target:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(result["text"] + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
