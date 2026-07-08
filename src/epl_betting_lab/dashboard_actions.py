from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, MIN_EDGE, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_current_odds, load_matches, load_upcoming_fixtures
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.reports.bet_ledger import load_bet_ledger, save_bet_ledger_reports
from epl_betting_lab.reports.bet_ledger_health import save_bet_ledger_health_check
from epl_betting_lab.reports.bet_settlement import build_settlement_preview, save_settlement_preview
from epl_betting_lab.reports.thursday_best_bets import (
    build_thursday_best_bets,
    missing_current_odds_message,
    save_thursday_best_bets,
)
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.totals import evaluate_total_25


def require_existing_ledger(ledger_path: Path | None = None) -> pd.DataFrame:
    path = ledger_path or MANUAL_DIR / "bet_ledger.csv"
    if not path.exists():
        raise FileNotFoundError(
            "Missing data/manual/bet_ledger.csv. Run `python scripts/run_bet_ledger.py` once from Terminal to create it."
        )
    return load_bet_ledger(path)


def require_existing_current_odds(current_odds_path: Path | None = None) -> Path:
    path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    if not path.exists():
        raise FileNotFoundError(missing_current_odds_message(path))
    return path


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


def run_thursday_best_bets_report(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    odds_path = require_existing_current_odds(current_odds_path)
    matches = load_matches()
    fixtures = load_upcoming_fixtures()
    odds = load_current_odds(odds_path)

    model = PoissonGoalsModel().fit(matches, last_n_matches_per_team=38)
    projections = model.project_fixtures(fixtures)
    candidates = pd.concat([
        evaluate_1x2_value(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
        evaluate_total_25(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE, matches=matches),
        evaluate_btts(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
    ], ignore_index=True)

    report = build_thursday_best_bets(candidates)
    return save_thursday_best_bets(report, output_dir or OUTPUTS_DIR)
