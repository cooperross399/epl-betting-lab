#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.odds_export_profile_diagnostic import (
    diagnose_odds_export_profiles,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare a sportsbook/odds-site CSV export against every configured mapping profile."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source export CSV path, such as data/manual/sportsbook_export.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = diagnose_odds_export_profiles(
        Path(args.source),
        MANUAL_DIR / "odds_import_profiles.json",
        OUTPUTS_DIR,
    )
    print(f"Diagnostic status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Diagnostic CSV: {paths['csv']}")
    print(f"Diagnostic report: {paths['markdown']}")


if __name__ == "__main__":
    main()
