from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.ledger_prefill import (
    merge_draft_rows,
    prefill_ledger_from_weekly_card,
    stable_bet_id,
    weekly_card_to_ledger_rows,
)


def _weekly_card() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": "2026-08-21",
            "season": "2627",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "status": "BETTABLE",
            "raw_model_prob": 0.72,
            "calibrated_model_prob": 0.64,
            "raw_edge": 0.09,
            "calibrated_edge": 0.05,
            "american_odds": -150,
            "closing_american_odds": -170,
            "suggested_units": 0.5,
            "suggested_wager_$": 12.5,
            "book": "DraftKings",
        },
        {
            "date": "2026-08-22",
            "season": "2627",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "under",
            "status": "PASS",
            "model_prob": 0.55,
            "edge": 0.01,
            "american_odds": 105,
            "book": "FanDuel",
        },
        {
            "date": "2026-08-23",
            "season": "2627",
            "home_team": "Spurs",
            "away_team": "Wolves",
            "market": "btts",
            "selection": "yes",
            "status": "LEAN",
            "model_prob": 0.58,
            "edge": 0.025,
            "american_odds": 120,
        },
    ])


def test_weekly_card_to_ledger_rows_defaults_to_bettable_and_lean() -> None:
    drafts = weekly_card_to_ledger_rows(_weekly_card())

    assert len(drafts) == 2
    assert set(drafts["model_recommendation_status"]) == {"BETTABLE", "LEAN"}
    assert set(drafts["result"]) == {"pending"}
    assert drafts["closing_american_odds"].isna().all()
    assert drafts.iloc[0]["book"] == "DraftKings"
    assert drafts.iloc[0]["stake_units"] == 0.5


def test_weekly_card_to_ledger_rows_can_include_pass() -> None:
    drafts = weekly_card_to_ledger_rows(_weekly_card(), allowed_statuses=["BETTABLE", "LEAN", "PASS"])

    assert len(drafts) == 3
    assert "PASS" in set(drafts["model_recommendation_status"])


def test_stable_bet_id_is_repeatable() -> None:
    row = _weekly_card().iloc[0]

    assert stable_bet_id(row) == stable_bet_id(row)


def test_merge_draft_rows_skips_duplicates() -> None:
    drafts = weekly_card_to_ledger_rows(_weekly_card())
    existing = drafts.head(1).copy()
    merged, stats = merge_draft_rows(existing, drafts)

    assert len(merged) == 2
    assert stats["added_rows"] == 1
    assert stats["skipped_duplicates"] == 1
    assert stats["overwritten_rows"] == 0


def test_merge_draft_rows_overwrites_when_explicit() -> None:
    drafts = weekly_card_to_ledger_rows(_weekly_card())
    existing = drafts.head(1).copy()
    existing.loc[existing.index[0], "notes"] = "manual note"
    merged, stats = merge_draft_rows(existing, drafts, overwrite_existing=True)

    assert len(merged) == 2
    assert stats["overwritten_rows"] == 1
    assert "manual note" not in set(merged["notes"])


def test_prefill_ledger_from_weekly_card_writes_once_without_duplicates(tmp_path) -> None:
    weekly_path = tmp_path / "weekly_card.csv"
    ledger_path = tmp_path / "bet_ledger.csv"
    _weekly_card().to_csv(weekly_path, index=False)

    first = prefill_ledger_from_weekly_card(weekly_path, ledger_path)
    second = prefill_ledger_from_weekly_card(weekly_path, ledger_path)
    ledger = pd.read_csv(ledger_path)

    assert first["added_rows"] == 2
    assert second["added_rows"] == 0
    assert second["skipped_duplicates"] == 2
    assert len(ledger) == 2
