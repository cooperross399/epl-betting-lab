from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.tier_performance import (
    load_tier_performance_source,
    save_tier_performance_reports,
    summarize_tier_performance,
)


def _write_ledger(path: Path) -> None:
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
            "model_recommendation_status": "BETTABLE",
            "confidence_tier": "A",
            "american_odds": -110,
            "closing_american_odds": -130,
            "suggested_units": 0.5,
            "stake_units": 1.0,
            "result": "win",
            "book": "DraftKings",
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
            "model_recommendation_status": "LEAN",
            "confidence_tier": "C",
            "american_odds": 120,
            "suggested_units": 0.1,
            "stake_units": 0.25,
            "result": "pending",
            "book": "FanDuel",
        },
    ]).to_csv(path, index=False)


def _write_archive(output_dir: Path) -> None:
    archive_dir = output_dir / "archive" / "thursday_best_bets" / "2026-08-21"
    archive_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {
            "section": "Best bets",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "status": "BETTABLE",
            "confidence_tier": "A",
            "american_odds": -110,
            "suggested_units": 0.5,
        },
        {
            "section": "Leans",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "under",
            "status": "LEAN",
            "confidence_tier": "C",
            "american_odds": 120,
            "suggested_units": 0.1,
        },
        {
            "section": "Passes / notable avoids",
            "home_team": "Spurs",
            "away_team": "Wolves",
            "market": "btts",
            "selection": "yes",
            "status": "PASS - no edge",
            "confidence_tier": "Pass/Avoid",
            "american_odds": -105,
            "suggested_units": 0.0,
        },
    ]).to_csv(archive_dir / "120000_thursday_best_bets.csv", index=False)


def test_tier_source_combines_settled_ledger_and_archived_tracking_rows(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    _write_ledger(ledger_path)
    _write_archive(tmp_path)

    source, notes = load_tier_performance_source(ledger_path, tmp_path)

    assert notes == []
    assert set(source["source_type"]) == {"actual_bet", "recommendation_tracking_only"}
    assert int(source["is_actual_bet"].sum()) == 2
    assert int(source["is_tracking_only"].sum()) == 3
    assert "A" in set(source["confidence_tier"])
    assert "Pass/Avoid" in set(source["confidence_tier"])


def test_tier_summary_counts_profit_and_tracking_separately(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    _write_ledger(ledger_path)
    _write_archive(tmp_path)
    source, _ = load_tier_performance_source(ledger_path, tmp_path)

    summary = summarize_tier_performance(source, ["confidence_tier", "recommendation_status"])
    a_row = summary[(summary["confidence_tier"] == "A") & (summary["recommendation_status"] == "BETTABLE")].iloc[0]
    c_row = summary[(summary["confidence_tier"] == "C") & (summary["recommendation_status"] == "LEAN")].iloc[0]

    assert a_row["actual_bets"] == 1
    assert a_row["settled_bets"] == 1
    assert a_row["wins"] == 1
    assert a_row["tracking_only_recommendations"] == 1
    assert a_row["units_won_lost"] > 0
    assert a_row["bets_with_clv"] == 1
    assert c_row["pending_bets"] == 1
    assert c_row["tracking_only_recommendations"] == 1
    assert c_row["units_won_lost"] == 0


def test_save_tier_performance_reports_writes_all_outputs(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    _write_ledger(ledger_path)
    _write_archive(tmp_path)

    paths = save_tier_performance_reports(ledger_path, tmp_path)

    assert paths["summary"].name == "tier_performance_summary.csv"
    assert paths["market"].name == "tier_performance_by_market.csv"
    assert paths["team"].name == "tier_performance_by_team.csv"
    assert paths["odds_range"].name == "tier_performance_by_odds_range.csv"
    assert paths["clv"].name == "tier_performance_by_clv.csv"
    assert paths["markdown"].name == "tier_performance_report.md"
    assert "Tier Performance Report" in paths["markdown"].read_text(encoding="utf-8")
    assert "C-tier should remain watchlist-only" in paths["markdown"].read_text(encoding="utf-8")


def test_tier_performance_handles_missing_inputs(tmp_path) -> None:
    paths = save_tier_performance_reports(tmp_path / "missing_ledger.csv", tmp_path)

    summary = pd.read_csv(paths["summary"])
    markdown = paths["markdown"].read_text(encoding="utf-8")

    assert summary.empty
    assert "Missing bet ledger" in markdown
    assert "No archived Thursday best-bets reports" in markdown
