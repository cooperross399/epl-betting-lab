from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.bet_ledger import (
    enrich_bet_ledger,
    save_bet_ledger_reports,
    summarize_ledger_by,
    summarize_overall,
)


def _sample_ledger() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "bet_id": "2026-001",
            "date": "2026-08-21",
            "season": "2627",
            "match": "Arsenal vs Coventry",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "model_recommendation_status": "BETTABLE",
            "raw_model_prob": 0.62,
            "calibrated_model_prob": 0.58,
            "raw_edge": 0.08,
            "calibrated_edge": 0.04,
            "american_odds": -110,
            "closing_american_odds": -130,
            "stake_units": 1.0,
            "stake_dollars": 25,
            "result": "win",
            "profit_units": pd.NA,
            "profit_dollars": pd.NA,
            "clv_probability_points": pd.NA,
            "book": "DraftKings",
            "notes": "",
        },
        {
            "bet_id": "2026-002",
            "date": "2026-08-22",
            "season": "2627",
            "match": "Chelsea vs Fulham",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "under",
            "model_recommendation_status": "LEAN",
            "american_odds": 120,
            "closing_american_odds": pd.NA,
            "stake_units": 0.5,
            "result": "pending",
            "book": "FanDuel",
        },
        {
            "bet_id": "2026-003",
            "date": "2026-08-23",
            "season": "2627",
            "match": "Spurs vs Wolves",
            "home_team": "Spurs",
            "away_team": "Wolves",
            "market": "btts",
            "selection": "yes",
            "model_recommendation_status": "BETTABLE",
            "american_odds": -105,
            "stake_units": 1.0,
            "result": "push",
            "book": "BetMGM",
        },
    ])


def test_enrich_bet_ledger_calculates_profit_and_clv() -> None:
    ledger = enrich_bet_ledger(_sample_ledger())
    win = ledger[ledger["result"] == "win"].iloc[0]

    assert round(win["profit_units"], 3) == 0.909
    assert round(win["profit_dollars"], 2) == 22.73
    assert win["clv_probability_points"] > 0
    assert bool(win["has_closing_odds"]) is True


def test_pending_bets_do_not_count_toward_profit() -> None:
    overall = summarize_overall(_sample_ledger())

    assert overall["tracked_bets"] == 3
    assert overall["settled_bets"] == 2
    assert overall["pending_bets"] == 1
    assert overall["wins"] == 1
    assert overall["pushes"] == 1
    assert overall["profit_units"] == 0.909


def test_push_counts_as_zero_profit() -> None:
    ledger = enrich_bet_ledger(_sample_ledger())
    push = ledger[ledger["result"] == "push"].iloc[0]

    assert push["profit_units"] == 0.0


def test_summarize_ledger_by_market() -> None:
    by_market = summarize_ledger_by(_sample_ledger(), ["market"])
    totals = by_market[by_market["market"] == "total_2_5"].iloc[0]

    assert totals["tracked_bets"] == 1
    assert totals["settled_bets"] == 0
    assert totals["pending_bets"] == 1
    assert totals["profit_units"] == 0.0


def test_save_bet_ledger_reports(tmp_path) -> None:
    paths = save_bet_ledger_reports(_sample_ledger(), tmp_path)

    assert paths["market"].name == "bet_ledger_by_market.csv"
    assert paths["selection"].name == "bet_ledger_by_selection.csv"
    assert paths["team"].name == "bet_ledger_by_team.csv"
    assert paths["markdown"].name == "bet_ledger_summary.md"
    assert paths["market"].exists()
    assert "Bet Ledger Summary" in paths["markdown"].read_text(encoding="utf-8")
