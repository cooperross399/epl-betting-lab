#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.github_manual_run_verification import (
    save_github_manual_run_verification,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a manual Thursday GitHub run from its downloaded report outputs."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUTS_DIR,
        help="Directory containing the handoff and scheduled workflow summaries.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = save_github_manual_run_verification(args.output_dir)
    print("EPL Betting Lab - GitHub Manual Thursday Run Verification")
    print(f"Verdict: {paths['verdict']}")
    print(f"Next step: {paths['next_step']}")
    print(f"CSV: {paths['csv']}")
    print(f"Markdown: {paths['markdown']}")
    print("Read-only check complete. No odds, fixtures, ledger, or profile files changed.")
    return 0 if str(paths["verdict"]).startswith("Verified ") else 2


if __name__ == "__main__":
    raise SystemExit(main())
