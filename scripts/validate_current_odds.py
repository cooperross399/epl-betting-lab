#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.dashboard_actions import run_current_odds_validation


def main() -> None:
    paths = run_current_odds_validation()
    print((OUTPUTS_DIR / "current_odds_validation.md").read_text(encoding="utf-8"))
    print(f"\nSaved CSV to {paths['csv']}")
    print(f"Saved Markdown to {paths['markdown']}")


if __name__ == "__main__":
    main()
