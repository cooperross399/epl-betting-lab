from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.dashboard_actions import (
    require_existing_ledger,
    require_existing_current_odds,
    run_bet_ledger_report,
    run_current_odds_validation,
    run_ledger_health_check,
    run_settlement_preview,
)
from epl_betting_lab.reports.bet_ledger import LEDGER_COLUMNS


def _ledger(path) -> None:
    pd.DataFrame([
        {
            "bet_id": "bet-1",
            "date": "2026-08-21",
            "season": "2627",
            "match": "Arsenal vs Coventry",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": -120,
            "stake_units": 1.0,
            "result": "pending",
        }
    ], columns=LEDGER_COLUMNS).to_csv(path, index=False)


def _matches(path) -> None:
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "season": "2627",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "home_goals": 2,
            "away_goals": 0,
        }
    ]).to_csv(path, index=False)


def test_require_existing_ledger_does_not_create_missing_file(tmp_path) -> None:
    ledger_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        require_existing_ledger(ledger_path)

    assert not ledger_path.exists()


def test_require_existing_current_odds_shows_manual_copy_command(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"

    with pytest.raises(FileNotFoundError) as exc:
        require_existing_current_odds(odds_path)

    assert "cp data/manual/current_odds_template.csv data/manual/current_odds.csv" in str(exc.value)
    assert not odds_path.exists()


def test_run_current_odds_validation_writes_report_without_creating_odds_file(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"

    paths = run_current_odds_validation(odds_path, output_dir)

    assert paths["csv"].name == "current_odds_validation.csv"
    assert paths["markdown"].name == "current_odds_validation.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert not odds_path.exists()


def test_dashboard_report_actions_write_outputs_without_editing_ledger(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    matches_path = tmp_path / "matches.csv"
    output_dir = tmp_path / "outputs"
    _ledger(ledger_path)
    _matches(matches_path)
    original = ledger_path.read_text(encoding="utf-8")

    ledger_paths = run_bet_ledger_report(ledger_path, output_dir)
    health_paths = run_ledger_health_check(ledger_path, output_dir)
    settlement_paths = run_settlement_preview(ledger_path, matches_path, output_dir)

    assert ledger_paths["markdown"].name == "bet_ledger_summary.md"
    assert health_paths["markdown"].name == "bet_ledger_health_check.md"
    assert settlement_paths["markdown"].name == "bet_settlement_preview.md"
    assert ledger_path.read_text(encoding="utf-8") == original
