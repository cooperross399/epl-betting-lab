#!/usr/bin/env python
"""Measure BTTS calibration under each candidate ratings configuration.

Writes data/outputs/btts_calibration_by_ratings.{csv,md}. Needs no prices:
BTTS has none to backtest against, which is the whole reason this exists.
"""
from __future__ import annotations

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches_with_xg
from epl_betting_lab.models.poisson_goals import BTTS_RATINGS, CARD_RATINGS
from epl_betting_lab.reports.btts_calibration import (
    RatingsUnderTest,
    compare_ratings,
    save_btts_calibration_reports,
)

CANDIDATES = [
    RatingsUnderTest("legacy (goals ratio, last 38)", CARD_RATINGS, last_n_matches_per_team=38),
    RatingsUnderTest("btts ratings (adjusted, 365d, xG blend)", BTTS_RATINGS),
]


def main() -> None:
    table = compare_ratings(load_matches_with_xg(), CANDIDATES)
    paths = save_btts_calibration_reports(table, OUTPUTS_DIR)
    print(table.to_string(index=False))
    for key, path in paths.items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()
