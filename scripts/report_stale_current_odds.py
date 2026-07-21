#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.stale_current_odds import save_stale_current_odds_report


def main() -> None:
    paths = save_stale_current_odds_report(
        MANUAL_DIR / "current_odds.csv",
        OUTPUTS_DIR,
    )
    print("Created the read-only stale current odds report.")
    print(f"CSV: {paths['csv']}")
    print(f"Report: {paths['markdown']}")
    print("No odds were edited. Review stale rows before removing, archiving, or replacing anything manually.")


if __name__ == "__main__":
    main()
