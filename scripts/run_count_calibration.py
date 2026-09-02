#!/usr/bin/env python
"""Measure the corner markets' calibration. Needs no prices; none exist."""
from __future__ import annotations

import argparse

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.count_calibration import (
    DEFAULT_STRIDE,
    calibration_table,
    save_count_calibration_reports,
    walk_forward_counts,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    args = parser.parse_args()
    table = calibration_table(walk_forward_counts(load_matches(), stride=args.stride))
    paths = save_count_calibration_reports(table, OUTPUTS_DIR)
    print(table.to_string(index=False))
    for key, path in paths.items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()
