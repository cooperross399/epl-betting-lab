#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.odds_export_profile_suggestion_validation import (
    validate_odds_export_profile_suggestion_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a draft odds export profile against its source CSV without applying it."
    )
    parser.add_argument(
        "--suggestion",
        default=str(OUTPUTS_DIR / "odds_export_profile_suggestion.json"),
        help="Draft suggestion JSON path.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Optional source CSV override. By default the stored source path is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = validate_odds_export_profile_suggestion_file(
        Path(args.suggestion),
        Path(args.source) if args.source else None,
        OUTPUTS_DIR,
    )
    print(f"Verdict: {paths['verdict']}")
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Validation CSV: {paths['csv']}")
    print(f"Validation report: {paths['markdown']}")


if __name__ == "__main__":
    main()
