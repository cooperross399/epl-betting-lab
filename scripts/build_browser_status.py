#!/usr/bin/env python
"""Build the single-page browser status report.

Renders the EPL Model, EPL CARD, and EPL SETTLE reports into one self-contained
HTML file that opens with a double click. Reads existing reports only: it runs
no provider, generates no picks, places no bets, applies no settlement, and
writes no credential.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.browser_status import save_status_html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Report directory to read from and write to. Defaults to data/outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Browser Status Page")
    print(
        "Read-only: renders existing reports. No provider run, no picks, no "
        "bets, no settlement, no credential."
    )

    result = save_status_html(output_dir=args.output_dir)
    print(f"HTML: {result['html']}")
    print(f"Size: {result['bytes']} bytes (self-contained, opens offline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
