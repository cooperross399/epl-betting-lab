from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.bet_settlement import (
    apply_settlements_to_ledger,
    build_settlement_preview,
    save_settlement_preview,
    settle_market,
)


def _ledger() -> pd.DataFrame:
    return pd.DataFrame([
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
        },
        {
            "bet_id": "bet-2",
            "date": "2026-08-22",
            "season": "2627",
            "match": "Chelsea vs Fulham",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "under",
            "american_odds": 110,
            "stake_units": 0.5,
            "result": "pending",
        },
        {
            "bet_id": "bet-3",
            "date": "2026-08-23",
            "season": "2627",
            "match": "Spurs vs Wolves",
            "home_team": "Spurs",
            "away_team": "Wolves",
            "market": "btts",
            "selection": "no",
            "american_odds": -105,
            "stake_units": 1.0,
            "result": "pending",
        },
        {
            "bet_id": "bet-4",
            "date": "2026-08-24",
            "season": "2627",
            "match": "Liverpool vs Everton",
            "home_team": "Liverpool",
            "away_team": "Everton",
            "market": "1x2",
            "selection": "draw",
            "american_odds": 300,
            "stake_units": 1.0,
            "result": "pending",
        },
    ])


def _matches() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": "2026-08-21",
            "season": "2627",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "home_goals": 2,
            "away_goals": 0,
        },
        {
            "date": "2026-08-22",
            "season": "2627",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "home_goals": 1,
            "away_goals": 1,
        },
        {
            "date": "2026-08-23",
            "season": "2627",
            "home_team": "Spurs",
            "away_team": "Wolves",
            "home_goals": 2,
            "away_goals": 1,
        },
    ])


def test_settle_market_supports_current_markets() -> None:
    assert settle_market("1x2", "home", 2, 0)[0] == "win"
    assert settle_market("1x2", "draw", 2, 2)[0] == "win"
    assert settle_market("total_2_5", "over", 2, 1)[0] == "win"
    assert settle_market("total_2_5", "under", 1, 1)[0] == "win"
    assert settle_market("btts", "yes", 1, 1)[0] == "win"
    assert settle_market("btts", "no", 1, 0)[0] == "win"


def test_build_settlement_preview_suggests_results_and_unmatched() -> None:
    preview = build_settlement_preview(_ledger(), _matches())
    suggestions = dict(zip(preview["bet_id"], preview["suggested_result"], strict=False))

    assert suggestions["bet-1"] == "win"
    assert suggestions["bet-2"] == "win"
    assert suggestions["bet-3"] == "loss"
    assert suggestions["bet-4"] == "unmatched"
    assert preview.loc[preview["bet_id"] == "bet-1", "final_score"].iloc[0] == "2-0"


def test_apply_settlements_updates_only_confident_pending_rows() -> None:
    preview = build_settlement_preview(_ledger(), _matches())
    updated, applied = apply_settlements_to_ledger(_ledger(), preview)
    results = dict(zip(updated["bet_id"], updated["result"], strict=False))

    assert applied == 3
    assert results["bet-1"] == "win"
    assert results["bet-2"] == "win"
    assert results["bet-3"] == "loss"
    assert results["bet-4"] == "pending"
    assert float(updated.loc[updated["bet_id"] == "bet-2", "profit_units"].iloc[0]) == 0.55


def test_apply_settlements_does_not_overwrite_settled_rows() -> None:
    ledger = _ledger()
    ledger.loc[ledger["bet_id"] == "bet-1", "result"] = "loss"
    preview = build_settlement_preview(ledger, _matches())
    updated, applied = apply_settlements_to_ledger(ledger, preview)

    assert applied == 2
    assert updated.loc[updated["bet_id"] == "bet-1", "result"].iloc[0] == "loss"


def test_save_settlement_preview(tmp_path) -> None:
    preview = build_settlement_preview(_ledger(), _matches())
    paths = save_settlement_preview(preview, tmp_path)

    assert paths["csv"].name == "bet_settlement_preview.csv"
    assert paths["markdown"].name == "bet_settlement_preview.md"
    assert paths["csv"].exists()
    assert "Settlement Preview" in paths["markdown"].read_text(encoding="utf-8")
