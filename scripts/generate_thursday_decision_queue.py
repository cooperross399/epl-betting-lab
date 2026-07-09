#!/usr/bin/env python
from epl_betting_lab.reports.thursday_decision_queue import save_thursday_decision_queue


def main() -> None:
    paths = save_thursday_decision_queue()
    print(paths["markdown"].read_text(encoding="utf-8"))
    print(f"\nSaved CSV to {paths['csv']}")
    print(f"Saved Markdown to {paths['markdown']}")


if __name__ == "__main__":
    main()
