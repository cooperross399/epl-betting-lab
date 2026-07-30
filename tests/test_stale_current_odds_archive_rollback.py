from __future__ import annotations

import json
import re

import pandas as pd
import pytest

import epl_betting_lab.reports.stale_current_odds_archive_rollback as rollback_module
from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256
from epl_betting_lab.reports.stale_current_odds_archive_rollback import (
    AUDIT_COLUMNS,
    AUDIT_CHECKSUM_COLUMNS,
    AUDIT_CONFIRMATION_COLUMNS,
    process_stale_current_odds_archive_rollback,
)


TIMESTAMP = "2026-07-21_140000"


def _odds_row(
    date: str,
    home_team: str,
    away_team: str,
    *,
    odds: str = "-110",
    notes: str = "",
) -> dict[str, str]:
    return {
        "date": date,
        "home_team": home_team,
        "away_team": away_team,
        "market": "1x2",
        "selection": "home",
        "american_odds": odds,
        "closing_american_odds": "",
        "book": "ExampleBook",
        "notes": notes,
    }


def _write_current_and_backup(current_path, backup_path) -> None:
    pd.DataFrame(
        [
            _odds_row("2026-08-01", "Liverpool", "Everton", notes="unchanged"),
            _odds_row("2026-08-02", "Fulham", "Brentford", odds="+105", notes="new row"),
        ]
    ).to_csv(current_path, index=False)
    pd.DataFrame(
        [
            _odds_row("2026-07-20", "Arsenal", "Chelsea", odds="-120", notes="restore"),
            _odds_row("2026-08-01", "Liverpool", "Everton", notes="unchanged"),
        ]
    ).to_csv(backup_path, index=False)


def _write_archive_checksum_audit(output_dir, backup_path, checksum=None) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    recorded_checksum = checksum or source_file_sha256(backup_path)
    pd.DataFrame([
        {
            "archive_id": "selected-backup-creator",
            "applied_at": "2026-07-21T13:00:00-04:00",
            "status": "applied",
            "backup_path": str(backup_path),
            "backup_checksum_sha256": recorded_checksum,
        }
    ]).to_csv(output_dir / "stale_current_odds_archive_audit.csv", index=False)
    return recorded_checksum


def _preview_confirmation(current_path, backup_path, output_dir) -> dict[str, object]:
    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
    )
    assert paths["status"] == "preview_ready"
    assert re.fullmatch(r"[0-9a-f]{64}", str(paths["confirm_id"]))
    return paths


def test_preview_lists_restored_and_replaced_rows_without_editing_files(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "2026-07-21_current_odds_pre_stale_archive.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    current_before = current_path.read_bytes()
    backup_before = backup_path.read_bytes()

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
    )

    assert paths["status"] == "preview_ready"
    preview = pd.read_csv(paths["csv"], dtype=str, keep_default_na=False)
    assert preview["rollback_action"].tolist() == [
        "Restore from backup",
        "Remove or replace current",
    ]
    assert preview["home_team"].tolist() == ["Arsenal", "Fulham"]
    assert preview["checksum_status"].eq("Not available").all()
    assert preview["checksum_gate_result"].eq("Allowed with warning").all()
    assert preview["current_checksum_sha256"].eq(source_file_sha256(backup_path)).all()
    assert preview["confirm_id"].eq(paths["confirm_id"]).all()
    assert preview["confirm_id_status"].eq("Preview ready").all()
    assert preview["confirmation_gate_result"].eq("Preview ready").all()
    assert preview["preview_current_checksum_sha256"].eq(
        source_file_sha256(current_path)
    ).all()
    assert preview["preview_backup_checksum_sha256"].eq(
        source_file_sha256(backup_path)
    ).all()
    assert preview["apply_current_checksum_sha256"].eq("").all()
    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert metadata["confirm_id"] == paths["confirm_id"]
    assert metadata["preview_current_checksum_sha256"] == source_file_sha256(current_path)
    assert metadata["preview_backup_checksum_sha256"] == source_file_sha256(backup_path)
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Current row count: 2" in markdown
    assert "Backup row count: 2" in markdown
    assert "Rows restored from backup: 1" in markdown
    assert "Current rows removed or replaced: 1" in markdown
    assert "apply replaces current_odds.csv" in markdown
    assert "Default mode is preview only" in markdown
    assert "Checksum status: Not available" in markdown
    assert "Gate result: Allowed with warning" in markdown
    assert f"Confirmation ID: `{paths['confirm_id']}`" in markdown
    assert f"--confirm-id {paths['confirm_id']}" in markdown
    assert f"--backup-path {backup_path}" in markdown
    assert current_path.read_bytes() == current_before
    assert backup_path.read_bytes() == backup_before
    assert not (tmp_path / "backups").exists()
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()


def test_apply_backs_up_current_restores_selected_backup_and_writes_audit(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "2026-07-21_current_odds_pre_stale_archive.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    recorded_checksum = _write_archive_checksum_audit(output_dir, backup_path)
    current_before = current_path.read_bytes()
    selected_backup_before = backup_path.read_bytes()
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        timestamp=TIMESTAMP,
        rollback_id="stale-rollback-test",
        applied_at="2026-07-21T14:00:00-04:00",
    )

    assert paths["status"] == "applied"
    assert current_path.read_bytes() == selected_backup_before
    assert backup_path.read_bytes() == selected_backup_before
    assert paths["pre_rollback_backup"].read_bytes() == current_before
    assert paths["pre_rollback_backup"].name == (
        f"{TIMESTAMP}_current_odds_pre_stale_archive_rollback.csv"
    )
    audit = pd.read_csv(paths["audit_csv"], dtype=str, keep_default_na=False)
    assert audit.columns.tolist() == AUDIT_COLUMNS
    assert audit.iloc[-1]["rollback_id"] == "stale-rollback-test"
    assert audit.iloc[-1]["current_rows_before"] == "2"
    assert audit.iloc[-1]["backup_rows"] == "2"
    assert audit.iloc[-1]["rows_restored"] == "1"
    assert audit.iloc[-1]["rows_removed_or_replaced"] == "1"
    assert audit.iloc[-1]["rows_after"] == "2"
    assert audit.iloc[-1]["backup_checksum_sha256"] == source_file_sha256(backup_path)
    assert audit.iloc[-1]["recovery_backup_checksum_sha256"] == source_file_sha256(
        paths["pre_rollback_backup"]
    )
    assert audit.iloc[-1]["checksum_status"] == "Verified"
    assert audit.iloc[-1]["recorded_checksum_sha256"] == recorded_checksum
    assert audit.iloc[-1]["current_checksum_sha256"] == source_file_sha256(backup_path)
    assert audit.iloc[-1]["checksum_gate_result"] == "Allowed"
    assert audit.iloc[-1]["confirm_id"] == preview_paths["confirm_id"]
    assert audit.iloc[-1]["confirm_id_status"] == "Matched"
    assert audit.iloc[-1]["preview_current_checksum_sha256"] == source_file_sha256(
        paths["pre_rollback_backup"]
    )
    assert audit.iloc[-1]["apply_current_checksum_sha256"] == source_file_sha256(
        paths["pre_rollback_backup"]
    )
    assert audit.iloc[-1]["preview_backup_checksum_sha256"] == source_file_sha256(
        backup_path
    )
    assert audit.iloc[-1]["apply_backup_checksum_sha256"] == source_file_sha256(
        backup_path
    )
    assert audit.iloc[-1]["confirmation_gate_result"] == "Allowed"
    assert "Latest Rollback" in paths["audit_markdown"].read_text(encoding="utf-8")
    assert "Recovery backup SHA-256" in paths["audit_markdown"].read_text(encoding="utf-8")
    apply_markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Applied: yes" in apply_markdown
    assert "explicitly applied from Terminal" in apply_markdown
    assert "Gate result: Allowed" in apply_markdown
    assert "Confirmation ID status: Matched" in apply_markdown


def test_apply_upgrades_legacy_rollback_audit_with_blank_checksum_fields(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "2026-07-21_current_odds_pre_stale_archive.csv"
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _write_current_and_backup(current_path, backup_path)
    optional_columns = [*AUDIT_CHECKSUM_COLUMNS, *AUDIT_CONFIRMATION_COLUMNS]
    legacy_columns = [column for column in AUDIT_COLUMNS if column not in optional_columns]
    legacy_row = {column: "" for column in legacy_columns}
    legacy_row["rollback_id"] = "legacy-rollback"
    pd.DataFrame([legacy_row], columns=legacy_columns).to_csv(
        output_dir / "stale_current_odds_archive_rollback_audit.csv",
        index=False,
    )
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        timestamp="2026-07-21_140001",
    )

    audit = pd.read_csv(paths["audit_csv"], dtype=str, keep_default_na=False)
    assert audit.columns.tolist() == AUDIT_COLUMNS
    assert audit.iloc[0]["rollback_id"] == "legacy-rollback"
    assert audit.iloc[0]["backup_checksum_sha256"] == ""
    assert audit.iloc[0]["recovery_backup_checksum_sha256"] == ""
    assert audit.iloc[0]["confirm_id"] == ""
    assert audit.iloc[0]["confirmation_gate_result"] == ""
    assert audit.iloc[-1]["backup_checksum_sha256"] == source_file_sha256(backup_path)
    assert audit.iloc[-1]["checksum_status"] == "Not available"
    assert audit.iloc[-1]["checksum_gate_result"] == "Allowed with warning"
    assert "no audit checksum was available" in paths["message"]


def test_apply_blocks_checksum_mismatch_without_changing_current_odds(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "2026-07-21_current_odds_pre_stale_archive.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    recorded_checksum = _write_archive_checksum_audit(output_dir, backup_path)
    changed_backup = pd.read_csv(backup_path, dtype=str, keep_default_na=False)
    changed_backup.loc[0, "notes"] = "manually changed after archive"
    changed_backup.to_csv(backup_path, index=False)
    current_before = current_path.read_bytes()
    backup_before = backup_path.read_bytes()
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        timestamp="2026-07-21_140002",
    )

    assert paths["status"] == "checksum_mismatch_blocked"
    assert paths["checksum_status"] == "Mismatch"
    assert paths["checksum_gate_result"] == "Blocked"
    assert paths["recorded_checksum_sha256"] == recorded_checksum
    assert paths["current_checksum_sha256"] == source_file_sha256(backup_path)
    assert current_path.read_bytes() == current_before
    assert backup_path.read_bytes() == backup_before
    assert not (tmp_path / "backups").exists()
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()
    preview = pd.read_csv(paths["csv"], dtype=str, keep_default_na=False)
    assert preview["checksum_status"].eq("Mismatch").all()
    assert preview["checksum_gate_result"].eq("Blocked").all()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Rollback was not applied" in markdown
    assert "--allow-checksum-mismatch" in markdown


def test_apply_allows_checksum_mismatch_only_with_explicit_override(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "2026-07-21_current_odds_pre_stale_archive.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    recorded_checksum = _write_archive_checksum_audit(output_dir, backup_path)
    changed_backup = pd.read_csv(backup_path, dtype=str, keep_default_na=False)
    changed_backup.loc[0, "notes"] = "manually inspected changed backup"
    changed_backup.to_csv(backup_path, index=False)
    backup_before = backup_path.read_bytes()
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        allow_checksum_mismatch=True,
        confirm_id=str(preview_paths["confirm_id"]),
        timestamp="2026-07-21_140003",
        rollback_id="checksum-override-test",
    )

    assert paths["status"] == "applied"
    assert paths["checksum_status"] == "Mismatch"
    assert paths["checksum_gate_result"] == "Override used"
    assert "may have changed after creation" in paths["message"]
    assert current_path.read_bytes() == backup_before
    audit = pd.read_csv(paths["audit_csv"], dtype=str, keep_default_na=False)
    latest = audit.iloc[-1]
    assert latest["rollback_id"] == "checksum-override-test"
    assert latest["checksum_status"] == "Mismatch"
    assert latest["recorded_checksum_sha256"] == recorded_checksum
    assert latest["current_checksum_sha256"] == source_file_sha256(backup_path)
    assert latest["checksum_gate_result"] == "Override used"
    assert latest["confirmation_gate_result"] == "Allowed"
    assert "explicit Terminal-only" in latest["checksum_gate_note"]
    audit_markdown = paths["audit_markdown"].read_text(encoding="utf-8")
    assert "explicit checksum mismatch override" in audit_markdown


@pytest.mark.parametrize("provided_confirm_id", [None, "0" * 64, "not-a-confirmation-id"])
def test_apply_blocks_missing_or_invalid_confirmation_id(
    tmp_path,
    provided_confirm_id,
) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "selected_backup.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    current_before = current_path.read_bytes()
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        confirm_id=provided_confirm_id,
        timestamp="2026-07-21_140004",
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirmation_gate_result"] == "Blocked"
    assert paths["confirm_id_status"] == ("Missing" if provided_confirm_id is None else "Invalid")
    assert paths["confirm_id"] == preview_paths["confirm_id"]
    assert current_path.read_bytes() == current_before
    assert not (tmp_path / "backups").exists()
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "did not match the reviewed preview" in markdown


def test_apply_blocks_when_current_odds_changed_after_preview(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "selected_backup.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)
    changed = pd.read_csv(current_path, dtype=str, keep_default_na=False)
    changed.loc[0, "notes"] = "changed after review"
    changed.to_csv(current_path, index=False)
    current_after_change = current_path.read_bytes()

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        timestamp="2026-07-21_140005",
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == "Current odds changed"
    assert paths["confirmation_gate_result"] == "Blocked"
    assert paths["preview_current_checksum_sha256"] != paths["apply_current_checksum_sha256"]
    assert current_path.read_bytes() == current_after_change
    assert not (tmp_path / "backups").exists()


def test_apply_blocks_when_selected_backup_changed_after_preview(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "selected_backup.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)
    changed = pd.read_csv(backup_path, dtype=str, keep_default_na=False)
    changed.loc[0, "notes"] = "changed after review"
    changed.to_csv(backup_path, index=False)
    current_before = current_path.read_bytes()

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        timestamp="2026-07-21_140006",
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == "Backup changed"
    assert paths["confirmation_gate_result"] == "Blocked"
    assert paths["preview_backup_checksum_sha256"] != paths["apply_backup_checksum_sha256"]
    assert current_path.read_bytes() == current_before
    assert not (tmp_path / "backups").exists()


def test_apply_blocks_when_backup_path_differs_from_preview(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    reviewed_backup = tmp_path / "reviewed_backup.csv"
    other_backup = tmp_path / "other_backup.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, reviewed_backup)
    pd.read_csv(reviewed_backup, dtype=str, keep_default_na=False).to_csv(
        other_backup,
        index=False,
    )
    preview_paths = _preview_confirmation(current_path, reviewed_backup, output_dir)
    current_before = current_path.read_bytes()

    paths = process_stale_current_odds_archive_rollback(
        other_backup,
        current_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        timestamp="2026-07-21_140007",
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == "Backup path mismatch"
    assert current_path.read_bytes() == current_before
    assert not (tmp_path / "backups").exists()


def test_apply_override_allows_unconfirmed_rollback_and_records_warning(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "selected_backup.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    backup_before = backup_path.read_bytes()

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        allow_unconfirmed_rollback=True,
        timestamp="2026-07-21_140008",
        rollback_id="unconfirmed-override-test",
    )

    assert paths["status"] == "applied"
    assert paths["confirmation_gate_result"] == "Override used"
    assert paths["confirm_id_status"] == "Override used"
    assert current_path.read_bytes() == backup_before
    audit = pd.read_csv(paths["audit_csv"], dtype=str, keep_default_na=False)
    latest = audit.iloc[-1]
    assert latest["confirmation_gate_result"] == "Override used"
    assert latest["confirm_id_status"] == "Override used"
    assert latest["preview_current_checksum_sha256"] == ""
    assert latest["apply_current_checksum_sha256"] != ""
    assert "did not match a reviewed preview" in latest["confirmation_gate_note"]
    assert "unconfirmed rollback override" in paths["audit_markdown"].read_text(
        encoding="utf-8"
    )


def test_apply_blocks_malformed_preview_metadata(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "selected_backup.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)
    preview_paths["metadata"].write_text("{bad json", encoding="utf-8")
    current_before = current_path.read_bytes()

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
        confirm_id=str(preview_paths["confirm_id"]),
        timestamp="2026-07-21_140009",
    )

    assert paths["status"] == "confirmation_blocked"
    assert paths["confirm_id_status"] == "Invalid preview"
    assert "malformed" in paths["confirmation_gate_note"]
    assert current_path.read_bytes() == current_before
    assert not (tmp_path / "backups").exists()


def test_matching_backup_is_a_read_only_no_op_even_with_apply(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "matching_backup.csv"
    output_dir = tmp_path / "outputs"
    frame = pd.DataFrame([_odds_row("2026-08-01", "Arsenal", "Chelsea")])
    frame.to_csv(current_path, index=False)
    frame.to_csv(backup_path, index=False)
    before = current_path.read_bytes()

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
    )

    assert paths["status"] == "no_changes"
    assert current_path.read_bytes() == before
    assert not (tmp_path / "backups").exists()
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()


@pytest.mark.parametrize(
    ("setup", "expected_status"),
    [
        ("missing_backup", "missing_backup_path"),
        ("non_csv", "invalid_backup_path"),
        ("same_file", "backup_equals_current"),
        ("empty_backup", "empty_backup"),
        ("header_only_backup", "empty_backup"),
        ("malformed_backup", "malformed_backup"),
        ("unreadable_backup", "unreadable_backup"),
        ("missing_date", "malformed_backup"),
    ],
)
def test_invalid_backups_are_reported_and_never_applied(tmp_path, setup, expected_status) -> None:
    current_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([_odds_row("2026-08-01", "Arsenal", "Chelsea")]).to_csv(
        current_path,
        index=False,
    )
    backup_path = tmp_path / "selected_backup.csv"
    if setup == "non_csv":
        backup_path = tmp_path / "selected_backup.txt"
        backup_path.write_text("date\n2026-07-20\n", encoding="utf-8")
    elif setup == "same_file":
        backup_path = current_path
    elif setup == "empty_backup":
        backup_path.write_text("", encoding="utf-8")
    elif setup == "header_only_backup":
        backup_path.write_text("date,home_team,away_team\n", encoding="utf-8")
    elif setup == "malformed_backup":
        backup_path.write_text('date,home_team\n"2026-07-20,Arsenal\n', encoding="utf-8")
    elif setup == "unreadable_backup":
        backup_path.write_bytes(b"\xff\xfe\x00\x00")
    elif setup == "missing_date":
        pd.DataFrame([{"home_team": "Arsenal", "away_team": "Chelsea"}]).to_csv(
            backup_path,
            index=False,
        )
    before = current_path.read_bytes()

    paths = process_stale_current_odds_archive_rollback(
        backup_path,
        current_path,
        output_dir,
        apply=True,
    )

    assert paths["status"] == expected_status
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert paths["checksum_status"] == "Not available"
    assert paths["checksum_gate_result"] == "Not checked"
    assert current_path.read_bytes() == before
    assert not (tmp_path / "backups").exists()
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()


def test_missing_current_odds_and_missing_backup_argument_have_friendly_previews(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    backup_path = tmp_path / "backup.csv"
    pd.DataFrame([_odds_row("2026-07-20", "Arsenal", "Chelsea")]).to_csv(
        backup_path,
        index=False,
    )

    missing_current = process_stale_current_odds_archive_rollback(
        backup_path,
        tmp_path / "current_odds.csv",
        output_dir,
        apply=True,
    )
    missing_backup = process_stale_current_odds_archive_rollback(
        None,
        tmp_path / "current_odds.csv",
        output_dir,
        apply=True,
    )

    assert missing_current["status"] == "missing_current_odds"
    assert missing_backup["status"] == "missing_backup_path"
    assert "Choose a pre-archive CSV backup" in missing_backup["message"]


def test_unreadable_existing_audit_blocks_before_current_odds_replacement(tmp_path) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "selected_backup.csv"
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _write_current_and_backup(current_path, backup_path)
    before = current_path.read_bytes()
    (output_dir / "stale_current_odds_archive_rollback_audit.csv").write_text(
        "wrong,columns\n1,2\n",
        encoding="utf-8",
    )
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)

    with pytest.raises(ValueError, match="audit"):
        process_stale_current_odds_archive_rollback(
            backup_path,
            current_path,
            output_dir,
            apply=True,
            confirm_id=str(preview_paths["confirm_id"]),
            timestamp=TIMESTAMP,
        )

    assert current_path.read_bytes() == before
    assert not (tmp_path / "backups").exists()


def test_failed_restore_recovers_current_odds_from_pre_rollback_backup(tmp_path, monkeypatch) -> None:
    current_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "selected_backup.csv"
    output_dir = tmp_path / "outputs"
    _write_current_and_backup(current_path, backup_path)
    before = current_path.read_bytes()
    preview_paths = _preview_confirmation(current_path, backup_path, output_dir)
    real_replace = rollback_module._replace_from_backup_atomic
    calls = 0

    def corrupt_first_restore(source, destination):
        nonlocal calls
        calls += 1
        if calls == 1:
            destination.write_text("corrupt restore", encoding="utf-8")
            return
        real_replace(source, destination)

    monkeypatch.setattr(rollback_module, "_replace_from_backup_atomic", corrupt_first_restore)

    with pytest.raises(OSError, match="pre-rollback backup was restored"):
        process_stale_current_odds_archive_rollback(
            backup_path,
            current_path,
            output_dir,
            apply=True,
            confirm_id=str(preview_paths["confirm_id"]),
            timestamp=TIMESTAMP,
        )

    assert current_path.read_bytes() == before
    assert (
        tmp_path
        / "backups"
        / f"{TIMESTAMP}_current_odds_pre_stale_archive_rollback.csv"
    ).exists()
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()
