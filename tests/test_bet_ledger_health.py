from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.bet_ledger_health import (
    build_bet_ledger_health_check,
    save_bet_ledger_health_check,
)


def _problem_ledger() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "bet_id": "dup-1",
            "match": "Arsenal vs Coventry",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": -120,
            "stake_units": 1.0,
            "result": "win",
            "profit_units": pd.NA,
            "notes": "",
        },
        {
            "bet_id": "dup-1",
            "match": "Chelsea vs Fulham",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "sideways",
            "american_odds": pd.NA,
            "stake_units": pd.NA,
            "result": "pending",
            "notes": "draft from weekly card",
        },
        {
            "bet_id": "bad-result",
            "match": "Spurs vs Wolves",
            "home_team": "Spurs",
            "away_team": pd.NA,
            "market": "shots",
            "selection": "over",
            "american_odds": 110,
            "stake_units": pd.NA,
            "result": "graded",
            "notes": "",
        },
        {
            "bet_id": "blank-result",
            "match": "Liverpool vs Everton",
            "home_team": "Liverpool",
            "away_team": "Everton",
            "market": "btts",
            "selection": "yes",
            "american_odds": 100,
            "stake_units": 0.5,
            "result": "",
            "notes": "",
        },
    ])


def test_build_bet_ledger_health_check_flags_common_issues() -> None:
    issues = build_bet_ledger_health_check(_problem_ledger())
    issue_names = set(issues["issue"])

    assert "duplicate_bet_id" in issue_names
    assert "missing_american_odds" in issue_names
    assert "missing_pending_stake_units" in issue_names
    assert "invalid_result" in issue_names
    assert "missing_result" in issue_names
    assert "settled_profit_blank" in issue_names
    assert "missing_closing_american_odds" in issue_names
    assert "invalid_market" in issue_names
    assert "invalid_selection" in issue_names
    assert "missing_team" in issue_names
    assert "draft_recommendation_not_confirmed" in issue_names


def test_missing_closing_odds_are_optional_info() -> None:
    issues = build_bet_ledger_health_check(_problem_ledger())
    closing = issues[issues["issue"] == "missing_closing_american_odds"]

    assert not closing.empty
    assert set(closing["severity"]) == {"info"}


def test_clean_ledger_has_no_issues() -> None:
    ledger = pd.DataFrame([
        {
            "bet_id": "ok-1",
            "match": "Arsenal vs Coventry",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": -120,
            "closing_american_odds": -130,
            "stake_units": 1.0,
            "result": "pending",
            "notes": "confirmed placed",
        }
    ])

    assert build_bet_ledger_health_check(ledger).empty


def test_save_bet_ledger_health_check(tmp_path) -> None:
    paths = save_bet_ledger_health_check(_problem_ledger(), tmp_path)

    assert paths["csv"].name == "bet_ledger_health_check.csv"
    assert paths["markdown"].name == "bet_ledger_health_check.md"
    assert paths["csv"].exists()
    assert "Ledger Health Check" in paths["markdown"].read_text(encoding="utf-8")
