#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_upcoming_fixtures
from epl_betting_lab.reports.current_odds_completeness import save_current_odds_completeness


def main() -> None:
    try:
        fixtures = load_upcoming_fixtures()
    except FileNotFoundError:
        fixtures = None
    paths = save_current_odds_completeness(MANUAL_DIR / "current_odds.csv", OUTPUTS_DIR, fixtures=fixtures)
    print("Checked current odds entry completeness.")
    print(f"CSV: {paths['csv']}")
    print(f"Report: {paths['markdown']}")
    print("No odds were edited. Fill in missing odds manually before generating Thursday best bets.")


if __name__ == "__main__":
    main()
