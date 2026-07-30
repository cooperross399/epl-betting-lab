from __future__ import annotations

from datetime import date
import json
import re

import pandas as pd
import pytest

import epl_betting_lab.reports.stale_current_odds_archive as archive_module
from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256
from epl_betting_lab.reports.stale_current_odds_archive import (
    AUDIT_COLUMNS,
    AUDIT_CHECKSUM_COLUMNS,
    AUDIT_CONFIRMATION_COLUMNS,
    PREVIEW_COLUMNS,
    archive_stale_current_odds,
    build_stale_current_odds_archive_preview,
)


TODAY = date(2026, 7, 21)
TIMESTAMP = "2026-07-21_110000"


def _write_mixed_odds(path) -> None:
    pd.DataFrame(
        [
            {
                "date": "2026-07-20",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "market": "1x2",
                "selection": "home",
                "american_odds": "-120",
                "closing_american_odds": "-125",
                "book": "ExampleBook",
                "notes": "archive this stale row",
                "custom_column": "stale-extra",
            },
            {
                "date": "2026-07-21",
                "home_team": "Liverpool",
                "away_team": "Everton",
                "market": "total_2_5",
                "selection": "over",
                "american_odds": "+105",
                "closing_american_odds": "",
                "book": "ExampleBook",
                "notes": "keep today",
                "custom_column": "today-extra",
            },
            {
                "date": "2026-08-01",
                "home_team": "Fulham",
                "away_team": "Brentford",
                "market": "btts",
                "selection": "yes",
                "american_odds": "-110",
                "closing_american_odds": "",
                "book": "ExampleBook",
                "notes": "keep future",
                "custom_column": "future-extra",
            },
            {
                "date": "not-a-date",
                "home_team": "Leeds",
                "away_team": "Burnley",
                "market": "1x2",
                "selection": "draw",
                "american_odds": "+220",
                "closing_american_odds": "",
                "book": "ExampleBook",
                "notes": "fix this date",
                "custom_column": "invalid-extra",
            },
            {
                "date": "",
                "home_team": "Sunderland",
                "away_team": "Bournemouth",
                "market": "total_2_5",
                "selection": "under",
                "american_odds": "+115",
                "closing_american_odds": "",
                "book": "ExampleBook",
                "notes": "fill this date",
                "custom_column": "blank-extra",
            },
        ]
    ).to_csv(path, index=False)


def _preview_confirmation(odds_path, output_dir, *, today=TODAY) -> dict[str, object]:
    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        today=today,
    )
    assert paths["status"] == "preview_ready"
    assert re.fullmatch(r"[0-9a-f]{64}", str(paths["confirm_id"]))
    return paths


def test_preview_classifies_archive_keep_and_manual_review_rows(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    _write_mixed_odds(odds_path)

    preview, summary = build_stale_current_odds_archive_preview(odds_path, today=TODAY)

    assert preview.columns.tolist() == PREVIEW_COLUMNS
    assert preview["archive_action"].tolist() == [
        "Archive and remove",
        "Keep",
        "Keep",
        "Keep for manual review",
        "Keep for manual review",
    ]
    assert summary["status"] == "preview_ready"
    assert summary["stale_rows"] == 1
    assert summary["current_rows"] == 2
    assert summary["invalid_date_rows"] == 1
    assert summary["blank_date_rows"] == 1
    assert summary["rows_kept"] == 4


def test_preview_writes_reports_without_changing_or_archiving_odds(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()

    paths = archive_stale_current_odds(odds_path, output_dir, today=TODAY)

    assert paths["status"] == "preview_ready"
    assert paths["csv"].name == "stale_current_odds_archive_preview.csv"
    assert paths["markdown"].name == "stale_current_odds_archive_preview.md"
    assert paths["metadata"].name == "stale_current_odds_archive_preview.json"
    assert re.fullmatch(r"[0-9a-f]{64}", str(paths["confirm_id"]))
    assert odds_path.read_bytes() == before
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Preview only: no input files were changed" in markdown
    assert "Rows To Archive And Remove" in markdown
    assert f"Confirmation ID: `{paths['confirm_id']}`" in markdown
    assert f"--confirm-id {paths['confirm_id']}" in markdown
    preview = pd.read_csv(paths["csv"], dtype=str, keep_default_na=False)
    assert preview["confirm_id"].eq(paths["confirm_id"]).all()
    assert preview["preview_current_checksum_sha256"].eq(source_file_sha256(odds_path)).all()
    assert preview["preview_stale_row_count"].eq("1").all()
    assert preview["preview_keep_row_count"].eq("2").all()
    assert preview["preview_manual_review_row_count"].eq("2").all()
    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert metadata["confirm_id"] == paths["confirm_id"]
    assert metadata["preview_current_checksum_sha256"] == source_file_sha256(odds_path)
    assert metadata["preview_stale_row_count"] == 1
    assert metadata["preview_keep_row_count"] == 2
    assert metadata["preview_manual_review_row_count"] == 2


def test_apply_backs_up_archives_and_keeps_current_and_date_fix_rows(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    before_frame = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    preview_paths = _preview_confirmation(odds_path, output_dir)

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        today=TODAY,
        timestamp=TIMESTAMP,
        archive_id="stale-archive-test",
        applied_at="2026-07-21T11:00:00-04:00",
    )

    assert paths["status"] == "applied"
    assert paths["backup"].read_bytes() == before
    archived = pd.read_csv(paths["stale_archive"], dtype=str, keep_default_na=False)
    current = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    assert archived.columns.tolist() == before_frame.columns.tolist()
    assert archived["custom_column"].tolist() == ["stale-extra"]
    assert current["custom_column"].tolist() == [
        "today-extra",
        "future-extra",
        "invalid-extra",
        "blank-extra",
    ]
    assert current["date"].tolist() == ["2026-07-21", "2026-08-01", "not-a-date", ""]
    audit = pd.read_csv(paths["audit_csv"], dtype=str, keep_default_na=False)
    assert audit.columns.tolist() == AUDIT_COLUMNS
    assert audit.iloc[-1]["archive_id"] == "stale-archive-test"
    assert audit.iloc[-1]["stale_rows_archived"] == "1"
    assert audit.iloc[-1]["current_rows_kept"] == "2"
    assert audit.iloc[-1]["date_fix_rows_kept"] == "2"
    assert audit.iloc[-1]["rows_after"] == "4"
    assert audit.iloc[-1]["backup_checksum_sha256"] == source_file_sha256(paths["backup"])
    assert audit.iloc[-1]["archive_file_checksum_sha256"] == source_file_sha256(
        paths["stale_archive"]
    )
    assert audit.iloc[-1]["confirm_id"] == preview_paths["confirm_id"]
    assert audit.iloc[-1]["confirm_id_status"] == "Matched"
    assert audit.iloc[-1]["preview_current_checksum_sha256"] == source_file_sha256(
        paths["backup"]
    )
    assert audit.iloc[-1]["apply_current_checksum_sha256"] == source_file_sha256(
        paths["backup"]
    )
    assert audit.iloc[-1]["preview_stale_row_count"] == "1"
    assert audit.iloc[-1]["apply_stale_row_count"] == "1"
    assert audit.iloc[-1]["preview_keep_row_count"] == "2"
    assert audit.iloc[-1]["apply_keep_row_count"] == "2"
    assert audit.iloc[-1]["preview_manual_review_row_count"] == "2"
    assert audit.iloc[-1]["apply_manual_review_row_count"] == "2"
    assert audit.iloc[-1]["confirmation_gate_result"] == "Allowed"
    assert "Archive apply completed" in paths["markdown"].read_text(encoding="utf-8")
    assert "Latest Apply" in paths["audit_markdown"].read_text(encoding="utf-8")
    assert "Backup SHA-256" in paths["audit_markdown"].read_text(encoding="utf-8")


def test_apply_upgrades_legacy_audit_with_blank_old_checksum_fields(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _write_mixed_odds(odds_path)
    optional_columns = [*AUDIT_CHECKSUM_COLUMNS, *AUDIT_CONFIRMATION_COLUMNS]
    legacy_columns = [column for column in AUDIT_COLUMNS if column not in optional_columns]
    legacy_row = {column: "" for column in legacy_columns}
    legacy_row["archive_id"] = "legacy-archive"
    pd.DataFrame([legacy_row], columns=legacy_columns).to_csv(
        output_dir / "stale_current_odds_archive_audit.csv",
        index=False,
    )
    preview_paths = _preview_confirmation(odds_path, output_dir)

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        today=TODAY,
        timestamp="2026-07-21_110001",
    )

    audit = pd.read_csv(paths["audit_csv"], dtype=str, keep_default_na=False)
    assert audit.columns.tolist() == AUDIT_COLUMNS
    assert audit.iloc[0]["archive_id"] == "legacy-archive"
    assert audit.iloc[0]["backup_checksum_sha256"] == ""
    assert audit.iloc[0]["archive_file_checksum_sha256"] == ""
    assert audit.iloc[0]["confirm_id"] == ""
    assert audit.iloc[0]["confirmation_gate_result"] == ""
    assert audit.iloc[-1]["backup_checksum_sha256"] == source_file_sha256(paths["backup"])


def test_apply_with_no_stale_rows_is_a_read_only_no_op(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame(
        [
            {"date": "2026-07-21", "home_team": "Arsenal", "away_team": "Chelsea"},
            {"date": "not-a-date", "home_team": "Leeds", "away_team": "Burnley"},
        ]
    ).to_csv(odds_path, index=False)
    before = odds_path.read_bytes()

    paths = archive_stale_current_odds(odds_path, output_dir, apply=True, today=TODAY)

    assert paths["status"] == "no_stale_rows"
    assert odds_path.read_bytes() == before
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()
    assert "Date Rows Kept For Manual Fixing" in paths["markdown"].read_text(encoding="utf-8")


def test_apply_all_stale_rows_leaves_a_header_only_current_odds_file(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame(
        [
            {"date": "2026-07-01", "home_team": "Arsenal", "away_team": "Chelsea"},
            {"date": "2026-07-02", "home_team": "Leeds", "away_team": "Burnley"},
        ]
    ).to_csv(odds_path, index=False)
    preview_paths = _preview_confirmation(odds_path, output_dir)

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        today=TODAY,
        timestamp=TIMESTAMP,
    )

    current = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    archived = pd.read_csv(paths["stale_archive"], dtype=str, keep_default_na=False)
    assert current.empty
    assert current.columns.tolist() == ["date", "home_team", "away_team"]
    assert len(archived) == 2


@pytest.mark.parametrize(
    ("setup", "expected_status"),
    [
        ("missing", "missing_file"),
        ("empty", "empty_file"),
        ("missing_date", "missing_date_column"),
        ("unreadable", "unreadable_file"),
    ],
)
def test_apply_refuses_invalid_source_files(tmp_path, setup, expected_status) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    if setup == "empty":
        odds_path.write_text("", encoding="utf-8")
    elif setup == "missing_date":
        pd.DataFrame([{"home_team": "Arsenal", "away_team": "Chelsea"}]).to_csv(
            odds_path,
            index=False,
        )
    elif setup == "unreadable":
        odds_path.write_bytes(b"\xff\xfe\x00\x00")
    before = odds_path.read_bytes() if odds_path.exists() else None

    paths = archive_stale_current_odds(odds_path, output_dir, apply=True, today=TODAY)

    assert paths["status"] == expected_status
    assert (odds_path.read_bytes() if odds_path.exists() else None) == before
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()
    assert "no input files were changed" in paths["markdown"].read_text(encoding="utf-8").lower()


def test_apply_refuses_backup_or_archive_collision(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    preview_paths = _preview_confirmation(odds_path, output_dir)
    backup_dir = odds_path.parent / "backups"
    backup_dir.mkdir()
    collision = backup_dir / f"{TIMESTAMP}_current_odds_pre_stale_archive.csv"
    collision.write_text("existing backup", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        archive_stale_current_odds(
            odds_path,
            output_dir,
            apply=True,
            confirm_id=str(preview_paths["confirm_id"]),
            today=TODAY,
            timestamp=TIMESTAMP,
        )

    assert odds_path.read_bytes() == before
    assert collision.read_text(encoding="utf-8") == "existing backup"
    assert not (odds_path.parent / "archive" / "current_odds_stale").exists()


def test_apply_refuses_to_overwrite_unreadable_existing_audit(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    preview_paths = _preview_confirmation(odds_path, output_dir)
    audit_path = output_dir / "stale_current_odds_archive_audit.csv"
    audit_path.write_text("wrong,column\n", encoding="utf-8")

    with pytest.raises(ValueError, match="audit"):
        archive_stale_current_odds(
            odds_path,
            output_dir,
            apply=True,
            confirm_id=str(preview_paths["confirm_id"]),
            today=TODAY,
            timestamp=TIMESTAMP,
        )

    assert odds_path.read_bytes() == before
    assert audit_path.read_text(encoding="utf-8") == "wrong,column\n"
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()


def test_current_odds_stays_unchanged_if_atomic_rewrite_fails(tmp_path, monkeypatch) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    preview_paths = _preview_confirmation(odds_path, output_dir)
    real_write = archive_module._write_csv_atomic

    def fail_current_write(frame, path, *, overwrite=True):
        if path == odds_path:
            raise OSError("simulated current odds write failure")
        return real_write(frame, path, overwrite=overwrite)

    monkeypatch.setattr(archive_module, "_write_csv_atomic", fail_current_write)

    with pytest.raises(OSError, match="simulated"):
        archive_stale_current_odds(
            odds_path,
            output_dir,
            apply=True,
            confirm_id=str(preview_paths["confirm_id"]),
            today=TODAY,
            timestamp=TIMESTAMP,
        )

    assert odds_path.read_bytes() == before
    backup_path = odds_path.parent / "backups" / f"{TIMESTAMP}_current_odds_pre_stale_archive.csv"
    stale_path = (
        odds_path.parent
        / "archive"
        / "current_odds_stale"
        / f"{TIMESTAMP}_current_odds_stale.csv"
    )
    assert backup_path.exists()
    assert stale_path.exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()


@pytest.mark.parametrize(
    ("confirm_id", "expected_status"),
    [
        (None, "Missing"),
        ("not-a-confirmation-id", "Invalid"),
        ("0" * 64, "Invalid"),
    ],
)
def test_apply_blocks_missing_or_invalid_confirmation_before_mutation(
    tmp_path,
    confirm_id,
    expected_status,
) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    _preview_confirmation(odds_path, output_dir)

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        confirm_id=confirm_id,
        today=TODAY,
        timestamp=TIMESTAMP,
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == expected_status
    assert paths["confirmation_gate_result"] == "Blocked"
    assert odds_path.read_bytes() == before
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()


def test_apply_blocks_when_current_odds_changed_after_preview(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    preview_paths = _preview_confirmation(odds_path, output_dir)
    preview_checksum = source_file_sha256(odds_path)
    frame = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    frame.loc[0, "american_odds"] = "-115"
    frame.to_csv(odds_path, index=False)
    changed = odds_path.read_bytes()

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        today=TODAY,
        timestamp=TIMESTAMP,
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == "Current odds changed"
    assert paths["preview_current_checksum_sha256"] == preview_checksum
    assert paths["apply_current_checksum_sha256"] == source_file_sha256(odds_path)
    assert paths["preview_current_checksum_sha256"] != paths["apply_current_checksum_sha256"]
    assert odds_path.read_bytes() == changed
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()


def test_apply_blocks_when_date_based_row_counts_changed_after_preview(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    preview_paths = _preview_confirmation(odds_path, output_dir)
    before = odds_path.read_bytes()

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        today=date(2026, 7, 22),
        timestamp=TIMESTAMP,
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == "Row counts changed"
    assert paths["preview_stale_row_count"] == "1"
    assert paths["apply_stale_row_count"] == "2"
    assert odds_path.read_bytes() == before
    assert not (odds_path.parent / "backups").exists()


def test_apply_blocks_when_preview_belongs_to_a_different_current_odds_path(
    tmp_path,
) -> None:
    reviewed_path = tmp_path / "reviewed" / "current_odds.csv"
    apply_path = tmp_path / "apply" / "current_odds.csv"
    reviewed_path.parent.mkdir()
    apply_path.parent.mkdir()
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(reviewed_path)
    apply_path.write_bytes(reviewed_path.read_bytes())
    preview_paths = _preview_confirmation(reviewed_path, output_dir)
    before = apply_path.read_bytes()

    paths = archive_stale_current_odds(
        apply_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        today=TODAY,
        timestamp=TIMESTAMP,
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == "Current path mismatch"
    assert apply_path.read_bytes() == before
    assert not (apply_path.parent / "backups").exists()


def test_apply_blocks_malformed_confirmation_metadata_before_mutation(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    preview_paths = _preview_confirmation(odds_path, output_dir)
    before = odds_path.read_bytes()
    preview_paths["metadata"].write_text("{not-json", encoding="utf-8")

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        today=TODAY,
        timestamp=TIMESTAMP,
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == "Invalid preview"
    assert "malformed" in paths["confirmation_gate_note"].lower()
    assert odds_path.read_bytes() == before
    assert not (odds_path.parent / "backups").exists()


def test_apply_unconfirmed_override_is_terminal_only_and_audited(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        allow_unconfirmed_archive=True,
        today=TODAY,
        timestamp=TIMESTAMP,
    )

    assert paths["status"] == "applied"
    assert paths["confirm_id_status"] == "Override used"
    assert paths["confirmation_gate_result"] == "Override used"
    assert "did not match a reviewed preview" in paths["confirmation_gate_note"]
    audit = pd.read_csv(paths["audit_csv"], dtype=str, keep_default_na=False)
    latest = audit.iloc[-1]
    assert latest["confirmation_gate_result"] == "Override used"
    assert latest["preview_current_checksum_sha256"] == ""
    assert latest["apply_current_checksum_sha256"] == source_file_sha256(paths["backup"])
    assert latest["apply_stale_row_count"] == "1"
    assert latest["apply_keep_row_count"] == "2"
    assert latest["apply_manual_review_row_count"] == "2"
    assert "WARNING" in paths["audit_markdown"].read_text(encoding="utf-8")
