from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.current_odds_maintenance import (
    build_current_odds_maintenance_preview,
    maintain_current_odds,
)


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"},
    ])


def _existing_row() -> dict[str, str]:
    return {
        "date": "2026-08-21",
        "home_team": "Arsenal",
        "away_team": "Coventry",
        "market": "1x2",
        "selection": "home",
        "american_odds": "-150",
        "closing_american_odds": "-145",
        "book": "FanDuel",
        "notes": "already entered",
        "custom_column": "keep me",
    }


def test_preview_adds_only_missing_rows_and_preserves_existing_inputs() -> None:
    existing = pd.DataFrame([_existing_row()])

    preview, expected = build_current_odds_maintenance_preview(_fixtures(), existing, book="FanDuel")

    assert len(expected) == 7
    assert len(preview) == 6
    assert preview["maintenance_action"].eq("add_missing_row").all()
    assert not ((preview["market"] == "1x2") & (preview["selection"] == "home")).any()
    assert existing.iloc[0]["american_odds"] == "-150"
    assert existing.iloc[0]["closing_american_odds"] == "-145"
    assert existing.iloc[0]["notes"] == "already entered"


def test_apply_appends_missing_rows_and_writes_backup_without_erasing_prices(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([_existing_row()]).to_csv(odds_path, index=False)

    paths = maintain_current_odds(
        _fixtures(),
        odds_path,
        output_dir,
        apply=True,
        book="FanDuel",
        timestamp="20260708_120000",
    )

    assert paths["backup"] == tmp_path / "backups" / "current_odds_20260708_120000.csv"
    assert paths["backup"].exists()
    backup = pd.read_csv(paths["backup"], dtype=str).fillna("")
    assert len(backup) == 1
    assert backup.iloc[0]["american_odds"] == "-150"

    updated = pd.read_csv(odds_path, dtype=str).fillna("")
    assert len(updated) == 7
    original = updated[(updated["market"] == "1x2") & (updated["selection"] == "home")].iloc[0]
    assert original["american_odds"] == "-150"
    assert original["closing_american_odds"] == "-145"
    assert original["book"] == "FanDuel"
    assert original["notes"] == "already entered"
    assert original["custom_column"] == "keep me"
    assert (output_dir / "current_odds_maintenance_preview.csv").exists()
    assert (output_dir / "current_odds_maintenance_report.md").exists()


def test_dry_run_writes_preview_reports_without_editing_current_odds(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([_existing_row()]).to_csv(odds_path, index=False)
    original = odds_path.read_text(encoding="utf-8")

    paths = maintain_current_odds(_fixtures(), odds_path, output_dir, apply=False, book="FanDuel")

    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert "backup" not in paths
    assert odds_path.read_text(encoding="utf-8") == original
    report = paths["markdown"].read_text(encoding="utf-8")
    assert "dry run" in report
    assert "--apply" in report


def test_book_prefill_applies_to_new_rows_when_no_existing_file(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"

    paths = maintain_current_odds(_fixtures(), odds_path, output_dir, apply=True, book="DraftKings")

    updated = pd.read_csv(paths["current_odds"], dtype=str).fillna("")
    assert len(updated) == 7
    assert updated["book"].eq("DraftKings").all()
    assert not (tmp_path / "backups").exists()
