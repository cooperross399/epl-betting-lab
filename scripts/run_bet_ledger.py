#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.bet_ledger import (
    ensure_ledger_template,
    load_bet_ledger,
    save_bet_ledger_reports,
)


def main() -> None:
    template_path = MANUAL_DIR / "bet_ledger_template.csv"
    ledger_path = MANUAL_DIR / "bet_ledger.csv"
    ensure_ledger_template(template_path)
    ensure_ledger_template(ledger_path)

    ledger = load_bet_ledger(ledger_path)
    paths = save_bet_ledger_reports(ledger, OUTPUTS_DIR)

    print(f"Read bet ledger from {ledger_path}")
    print("Saved bet ledger reports:")
    for path in paths.values():
        print(f"- {path}")


if __name__ == "__main__":
    main()
