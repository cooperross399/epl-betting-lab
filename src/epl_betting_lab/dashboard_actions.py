from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.bet_ledger import load_bet_ledger, save_bet_ledger_reports
from epl_betting_lab.reports.bet_ledger_health import save_bet_ledger_health_check
from epl_betting_lab.reports.bet_settlement import build_settlement_preview, save_settlement_preview


def require_existing_ledger(ledger_path: Path | None = None) -> pd.DataFrame:
    path = ledger_path or MANUAL_DIR / "bet_ledger.csv"
    if not path.exists():
        raise FileNotFoundError(
            "Missing data/manual/bet_ledger.csv. Run `python scripts/run_bet_ledger.py` once from Terminal to create it."
        )
    return load_bet_ledger(path)


def run_bet_ledger_report(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_bet_ledger_reports(require_existing_ledger(ledger_path), output_dir or OUTPUTS_DIR)


def run_ledger_health_check(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_bet_ledger_health_check(require_existing_ledger(ledger_path), output_dir or OUTPUTS_DIR)


def run_settlement_preview(
    ledger_path: Path | None = None,
    matches_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    ledger = require_existing_ledger(ledger_path)
    matches = load_matches(matches_path)
    preview = build_settlement_preview(ledger, matches)
    return save_settlement_preview(preview, output_dir or OUTPUTS_DIR)
