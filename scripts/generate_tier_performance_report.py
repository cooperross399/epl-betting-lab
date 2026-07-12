#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.tier_performance import save_tier_performance_reports


def main() -> None:
    paths = save_tier_performance_reports(MANUAL_DIR / "bet_ledger.csv", OUTPUTS_DIR)
    print(paths["markdown"].read_text(encoding="utf-8"))
    print("\nSaved tier performance reports:")
    for path in paths.values():
        print(f"- {path}")


if __name__ == "__main__":
    main()
