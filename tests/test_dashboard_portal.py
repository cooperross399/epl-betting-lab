from __future__ import annotations

import pandas as pd

from epl_betting_lab.dashboard_portal import (
    ODDS_IMPORT_STEPS,
    PORTAL_SECTIONS,
    SECTION_DESCRIPTIONS,
    build_ledger_portal_summary,
)


def test_portal_sections_are_beginner_friendly_and_complete() -> None:
    assert PORTAL_SECTIONS == (
        "Home / Command Center",
        "Thursday Card",
        "Odds Import",
        "Performance Reports",
        "Bet Ledger",
        "Archives & Comparisons",
        "Tools / Diagnostics",
    )
    assert set(SECTION_DESCRIPTIONS) == set(PORTAL_SECTIONS)


def test_odds_import_steps_preserve_the_safe_workflow_order() -> None:
    assert [step.number for step in ODDS_IMPORT_STEPS] == list(range(1, 10))
    assert [step.label for step in ODDS_IMPORT_STEPS] == [
        "Diagnose export",
        "Suggest profile",
        "Validate suggested profile",
        "Preview profile install",
        "Verify installed profile",
        "Rollback preview",
        "Convert export",
        "Preview current odds import",
        "View import audits",
    ]


def test_ledger_portal_summary_handles_missing_ledger(tmp_path) -> None:
    summary = build_ledger_portal_summary(tmp_path / "bet_ledger.csv")

    assert summary.status == "Missing"
    assert summary.profit_units is None
    assert summary.pending_bets is None


def test_ledger_portal_summary_reports_units_roi_and_pending(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    pd.DataFrame([
        {
            "bet_id": "bet-1",
            "american_odds": 100,
            "stake_units": 0.5,
            "result": "win",
        },
        {
            "bet_id": "bet-2",
            "american_odds": -110,
            "stake_units": 0.25,
            "result": "pending",
        },
    ]).to_csv(ledger_path, index=False)

    summary = build_ledger_portal_summary(ledger_path)

    assert summary.status == "Ready"
    assert summary.record == "1-0-0"
    assert summary.profit_units == 0.5
    assert summary.roi == 1.0
    assert summary.pending_bets == 1


def test_ledger_portal_summary_handles_invalid_results(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    pd.DataFrame([{"bet_id": "bad", "result": "maybe"}]).to_csv(ledger_path, index=False)

    summary = build_ledger_portal_summary(ledger_path)

    assert summary.status == "Needs review"
    assert summary.record == "Unavailable"
    assert "Unsupported result" in summary.message
