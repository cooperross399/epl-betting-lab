#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.bet_ledger import ensure_ledger_template, load_bet_ledger
from epl_betting_lab.reports.bet_ledger_health import save_bet_ledger_health_check


def main() -> None:
    ledger_path = MANUAL_DIR / "bet_ledger.csv"
    ensure_ledger_template(MANUAL_DIR / "bet_ledger_template.csv")
    ensure_ledger_template(ledger_path)

    ledger = load_bet_ledger(ledger_path)
    paths = save_bet_ledger_health_check(ledger, OUTPUTS_DIR)

    print(f"Checked bet ledger at {ledger_path}")
    print("Saved ledger health check:")
    for path in paths.values():
        print(f"- {path}")


if __name__ == "__main__":
    main()
