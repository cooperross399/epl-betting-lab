#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.odds_export_profile_suggestion import (
    suggest_odds_export_profile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a review-only draft mapping profile from sportsbook export columns."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source export CSV path, such as data/manual/sportsbook_export.csv.",
    )
    parser.add_argument(
        "--profile-name",
        default="",
        help="Name for the draft profile, such as example_book.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = suggest_odds_export_profile(
        Path(args.source),
        args.profile_name,
        OUTPUTS_DIR,
    )
    print(f"Suggestion status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Draft JSON: {paths['json']}")
    print(f"Draft report: {paths['markdown']}")


if __name__ == "__main__":
    main()
