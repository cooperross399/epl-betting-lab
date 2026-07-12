from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.current_odds_import import (
    IMPORT_PREVIEW_COLUMNS,
    build_current_odds_import_preview,
    process_current_odds_import,
)


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Man United"},
    ])


def _matches() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2026-04-01", "home_team": "Man United", "away_team": "Arsenal"},
    ])


def _import_row(**overrides: str) -> dict[str, str]:
    row = {
        "date": "2026-08-21",
        "home_team": "Arsenal",
        "away_team": "Man United",
        "market": "1x2",
        "selection": "home",
        "american_odds": "+120",
        "book": "FanDuel",
        "closing_american_odds": "",
        "notes": "",
    }
    row.update(overrides)
    return row


def test_preview_normalizes_labels_and_identifies_existing_update() -> None:
    imported = pd.DataFrame([
        _import_row(
            date="08/21/2026",
            home_team="arsenal",
            away_team="Manchester United",
            market="Match Result",
            selection="H",
            american_odds="+125",
        )
    ])
    existing = pd.DataFrame([_import_row(american_odds="+120")])

    preview, summary = build_current_odds_import_preview(imported, existing, _fixtures(), _matches())

    row = preview.iloc[0]
    assert row["date"] == "2026-08-21"
    assert row["home_team"] == "Arsenal"
    assert row["away_team"] == "Man United"
    assert row["market"] == "1x2"
    assert row["selection"] == "home"
    assert row["import_status"] == "valid"
    assert row["import_action"] == "update_existing"
    assert summary["update_rows"] == 1


def test_preview_rejects_duplicate_unknown_and_invalid_rows() -> None:
    imported = pd.DataFrame([
        _import_row(),
        _import_row(home_team="ARSENAL", selection="Home win"),
        _import_row(home_team="Unknown FC"),
        _import_row(market="shots", selection="over"),
        _import_row(american_odds="not odds"),
        _import_row(selection="sideways"),
        _import_row(book=""),
    ])

    preview, summary = build_current_odds_import_preview(imported, pd.DataFrame(), _fixtures(), _matches())

    assert preview.iloc[0]["import_action"] == "skip_invalid"
    assert preview.iloc[1]["import_action"] == "skip_invalid"
    assert "duplicate import row" in preview.iloc[0]["issues"]
    assert "unknown home_team" in preview.iloc[2]["issues"]
    assert "invalid market" in preview.iloc[3]["issues"]
    assert "non-numeric american_odds" in preview.iloc[4]["issues"]
    assert "invalid selection" in preview.iloc[5]["issues"]
    assert "missing book" in preview.iloc[6]["issues"]
    assert summary["duplicate_rows"] == 3
    assert summary["invalid_rows"] == 7


def test_matching_key_includes_book() -> None:
    imported = pd.DataFrame([_import_row(book="DraftKings")])
    existing = pd.DataFrame([_import_row(book="FanDuel")])

    preview, summary = build_current_odds_import_preview(imported, existing, _fixtures(), _matches())

    assert preview.iloc[0]["import_action"] == "add_new"
    assert summary["add_rows"] == 1


def test_preview_writes_reports_without_editing_current_odds(tmp_path) -> None:
    import_path = tmp_path / "current_odds_import.csv"
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([_import_row(american_odds="+130")]).to_csv(import_path, index=False)
    pd.DataFrame([_import_row(american_odds="+120")]).to_csv(odds_path, index=False)
    original = odds_path.read_text(encoding="utf-8")

    paths = process_current_odds_import(
        import_path,
        odds_path,
        output_dir,
        fixtures=_fixtures(),
        matches=_matches(),
    )

    assert paths["csv"].name == "current_odds_import_preview.csv"
    assert paths["markdown"].name == "current_odds_import_report.md"
    assert odds_path.read_text(encoding="utf-8") == original
    preview = pd.read_csv(paths["csv"], dtype=str).fillna("")
    assert preview.iloc[0]["import_action"] == "update_existing"
    assert "preview / dry run" in paths["markdown"].read_text(encoding="utf-8")


def test_preview_warns_on_heavy_juice_and_totals_unders() -> None:
    imported = pd.DataFrame([
        _import_row(market="total 2.5", selection="under 2.5", american_odds="-170")
    ])

    preview, summary = build_current_odds_import_preview(imported, pd.DataFrame(), _fixtures(), _matches())

    row = preview.iloc[0]
    assert row["import_status"] == "valid"
    assert "heavy juice" in row["warnings"]
    assert "totals under requires extreme caution" in row["warnings"]
    assert summary["warning_rows"] == 1


def test_apply_backs_up_updates_appends_and_skips_invalid_rows(tmp_path) -> None:
    import_path = tmp_path / "current_odds_import.csv"
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    existing = _import_row(
        american_odds="+120",
        closing_american_odds="+115",
        notes="keep existing note",
    )
    existing["custom_column"] = "keep me"
    pd.DataFrame([existing]).to_csv(odds_path, index=False)
    pd.DataFrame([
        _import_row(american_odds="+130"),
        _import_row(market="Total 2.5", selection="Over 2.5", american_odds="-110"),
        _import_row(market="shots", selection="over", american_odds="+100"),
    ]).to_csv(import_path, index=False)

    paths = process_current_odds_import(
        import_path,
        odds_path,
        output_dir,
        apply=True,
        fixtures=_fixtures(),
        matches=_matches(),
        timestamp="20260712_120000",
    )

    assert paths["backup"] == tmp_path / "backups" / "current_odds_20260712_120000.csv"
    backup = pd.read_csv(paths["backup"], dtype=str).fillna("")
    assert len(backup) == 1
    updated = pd.read_csv(odds_path, dtype=str).fillna("")
    assert len(updated) == 2
    home = updated[updated["market"] == "1x2"].iloc[0]
    assert home["american_odds"] == "+130"
    assert home["closing_american_odds"] == "+115"
    assert home["notes"] == "keep existing note"
    assert home["custom_column"] == "keep me"
    total = updated[updated["market"] == "total_2_5"].iloc[0]
    assert total["selection"] == "over"
    assert total["american_odds"] == "-110"
    assert not updated["market"].eq("shots").any()


def test_apply_can_create_new_current_odds_without_fake_backup(tmp_path) -> None:
    import_path = tmp_path / "current_odds_import.csv"
    odds_path = tmp_path / "current_odds.csv"
    pd.DataFrame([_import_row()]).to_csv(import_path, index=False)

    paths = process_current_odds_import(
        import_path,
        odds_path,
        tmp_path / "outputs",
        apply=True,
        fixtures=_fixtures(),
        matches=_matches(),
    )

    assert odds_path.exists()
    assert "backup" not in paths
    assert pd.read_csv(odds_path).shape[0] == 1


def test_missing_empty_and_invalid_column_files_write_safe_reports(tmp_path) -> None:
    import_path = tmp_path / "current_odds_import.csv"
    output_dir = tmp_path / "outputs"
    missing_paths = process_current_odds_import(import_path, tmp_path / "current_odds.csv", output_dir)
    assert list(pd.read_csv(missing_paths["csv"]).columns) == IMPORT_PREVIEW_COLUMNS
    missing_report = missing_paths["markdown"].read_text(encoding="utf-8")
    assert "current_odds_import_template.csv" in missing_report

    pd.DataFrame(columns=["date", "home_team"]).to_csv(import_path, index=False)
    empty_paths = process_current_odds_import(import_path, tmp_path / "current_odds.csv", output_dir)
    assert "it has no odds rows" in empty_paths["markdown"].read_text(encoding="utf-8")

    pd.DataFrame([{"date": "2026-08-21", "home_team": "Arsenal"}]).to_csv(import_path, index=False)
    invalid_paths = process_current_odds_import(
        import_path,
        tmp_path / "current_odds.csv",
        output_dir,
        fixtures=_fixtures(),
        matches=_matches(),
    )
    preview = pd.read_csv(invalid_paths["csv"], dtype=str).fillna("")
    assert preview.iloc[0]["import_status"] == "invalid"
    assert "missing required columns" in preview.iloc[0]["issues"]
    assert not (tmp_path / "current_odds.csv").exists()

    import_path.write_text('date,home_team\n"2026-08-21,Arsenal\n', encoding="utf-8")
    unreadable_paths = process_current_odds_import(import_path, tmp_path / "current_odds.csv", output_dir)
    assert "could not be read" in unreadable_paths["markdown"].read_text(encoding="utf-8")


def test_template_contains_supported_columns_without_fabricated_odds() -> None:
    template_path = Path(__file__).resolve().parents[1] / "data" / "manual" / "current_odds_import_template.csv"
    template = pd.read_csv(template_path, dtype=str).fillna("")

    assert set(template.columns) == {
        "date",
        "home_team",
        "away_team",
        "market",
        "selection",
        "american_odds",
        "book",
        "closing_american_odds",
        "notes",
    }
    assert template["american_odds"].eq("").all()
    assert template["closing_american_odds"].eq("").all()
