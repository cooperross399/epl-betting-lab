#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.odds_export_conversion import convert_odds_export


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a sportsbook/odds-site CSV export into the safe current odds import format."
    )
    parser.add_argument("--profile", required=True, help="Mapping profile name, such as generic.")
    parser.add_argument(
        "--source",
        default=str(MANUAL_DIR / "sportsbook_export.csv"),
        help="Source export CSV path. Defaults to data/manual/sportsbook_export.csv.",
    )
    parser.add_argument(
        "--overwrite-import",
        action="store_true",
        help="Intentionally replace data/manual/current_odds_import.csv.",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Write conversion reports only; do not create current_odds_import.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = convert_odds_export(
        args.profile,
        Path(args.source),
        MANUAL_DIR / "odds_import_profiles.json",
        MANUAL_DIR / "current_odds_import.csv",
        OUTPUTS_DIR,
        overwrite_import=args.overwrite_import,
        write_import=not args.preview_only,
    )
    print(f"Conversion status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Preview CSV: {paths['csv']}")
    print(f"Report: {paths['markdown']}")
    if "import" in paths:
        print(f"Standard import file: {paths['import']}")
        print("Next: run `python scripts/import_current_odds.py` for the existing safety checks.")
    elif paths["status"] == "blocked_existing_import":
        print("Existing current_odds_import.csv was preserved. Use --overwrite-import only intentionally.")


if __name__ == "__main__":
    main()
