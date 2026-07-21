#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.stale_current_odds_backup_picker import (
    save_stale_current_odds_backup_list,
)


def main() -> None:
    paths = save_stale_current_odds_backup_list(
        MANUAL_DIR / "backups",
        OUTPUTS_DIR,
    )
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Backup list CSV: {paths['csv']}")
    print(f"Backup list report: {paths['markdown']}")
    print("Read-only: no odds, import, ledger, profile, or model files were changed.")


if __name__ == "__main__":
    main()
