#!/usr/bin/env python
from epl_betting_lab.reports.thursday_best_bets_comparison import save_thursday_best_bets_comparison


def main() -> None:
    paths = save_thursday_best_bets_comparison()
    print(paths["markdown"].read_text(encoding="utf-8"))
    print(f"\nSaved CSV to {paths['csv']}")
    print(f"Saved Markdown to {paths['markdown']}")


if __name__ == "__main__":
    main()
