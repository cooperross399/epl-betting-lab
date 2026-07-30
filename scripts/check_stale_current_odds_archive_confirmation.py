#!/usr/bin/env python
from __future__ import annotations

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.stale_current_odds_archive_confirmation import (
    save_stale_current_odds_archive_confirmation_status,
)


def main() -> None:
    paths = save_stale_current_odds_archive_confirmation_status(
        MANUAL_DIR / "current_odds.csv",
        OUTPUTS_DIR,
    )
    print(f"Status: {paths['status']}")
    print(f"Message: {paths['message']}")
    print(f"Status CSV: {paths['csv']}")
    print(f"Status report: {paths['markdown']}")
    if paths["exact_apply_command"]:
        print(f"Reviewed Terminal apply command: {paths['exact_apply_command']}")
    print("Read-only: no odds, archive, import, ledger, profile, or model files were changed.")


if __name__ == "__main__":
    main()
