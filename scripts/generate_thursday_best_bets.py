#!/usr/bin/env python
import sys

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.dashboard_actions import run_thursday_best_bets_report


def main() -> None:
    paths = run_thursday_best_bets_report()

    print((OUTPUTS_DIR / "thursday_best_bets.md").read_text(encoding="utf-8"))
    print(f"\nSaved CSV to {paths['csv']}")
    print(f"Saved Markdown to {paths['markdown']}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
