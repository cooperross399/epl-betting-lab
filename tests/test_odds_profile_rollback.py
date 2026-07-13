from __future__ import annotations

import json

import pandas as pd
import pytest

from epl_betting_lab.reports.odds_profile_rollback import (
    process_odds_profile_rollback,
)


def _write_registry(path, profiles: dict[str, object]) -> str:
    text = json.dumps({"profiles": profiles}, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def test_rollback_preview_shows_profile_differences_without_editing_registry(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    backup_path = tmp_path / "selected_backup.json"
    output_dir = tmp_path / "outputs"
    original = _write_registry(
        registry_path,
        {"keep": {"version": 2}, "remove_me": {"version": 1}},
    )
    _write_registry(
        backup_path,
        {"keep": {"version": 1}, "restore_me": {"version": 1}},
    )

    paths = process_odds_profile_rollback(
        backup_path,
        registry_path,
        output_dir,
    )

    assert paths["status"] == "preview_ready"
    preview = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert preview["current_profile_count"] == 2
    assert preview["backup_profile_count"] == 2
    assert preview["profiles_added_by_rollback"] == ["restore_me"]
    assert preview["profiles_removed_by_rollback"] == ["remove_me"]
    assert preview["profiles_changed_by_rollback"] == ["keep"]
    assert "replaces odds_import_profiles.json" in preview["warning"]
    assert registry_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "backups").exists()


def test_rollback_apply_backs_up_current_registry_restores_selected_backup_and_audits(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    backup_path = tmp_path / "selected_backup.json"
    output_dir = tmp_path / "outputs"
    current_text = _write_registry(registry_path, {"current": {"version": 2}})
    backup_text = _write_registry(backup_path, {"restored": {"version": 1}})

    paths = process_odds_profile_rollback(
        backup_path,
        registry_path,
        output_dir,
        apply=True,
        timestamp="20260712_130000",
        rollback_id="rollback-1",
        applied_at="2026-07-12T13:00:00-04:00",
    )

    assert paths["status"] == "applied"
    assert registry_path.read_text(encoding="utf-8") == backup_text
    assert paths["pre_rollback_backup"].read_text(encoding="utf-8") == current_text
    audit = pd.read_csv(paths["audit_csv"], dtype=str).fillna("")
    assert audit.loc[0, "rollback_id"] == "rollback-1"
    assert audit.loc[0, "profiles_added_by_rollback"] == "restored"
    assert audit.loc[0, "profiles_removed_by_rollback"] == "current"
    assert "Odds Profile Rollback Audit" in paths["audit_markdown"].read_text(encoding="utf-8")


def test_equivalent_backup_reports_no_changes_and_does_not_apply(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    backup_path = tmp_path / "selected_backup.json"
    output_dir = tmp_path / "outputs"
    original = _write_registry(registry_path, {"same": {"version": 1}})
    backup_path.write_text('{"profiles":{"same":{"version":1}}}\n', encoding="utf-8")

    paths = process_odds_profile_rollback(
        backup_path,
        registry_path,
        output_dir,
        apply=True,
    )

    assert paths["status"] == "no_changes"
    assert "already equivalent" in paths["message"]
    assert registry_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "backups").exists()
    assert not (output_dir / "odds_profile_rollback_audit.csv").exists()


def test_rollback_has_beginner_friendly_path_and_file_errors(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    backup_path = tmp_path / "selected_backup.json"
    output_dir = tmp_path / "outputs"

    missing_registry = process_odds_profile_rollback(
        backup_path,
        registry_path,
        output_dir,
    )
    assert missing_registry["status"] == "missing_registry"

    _write_registry(registry_path, {"current": {}})
    invalid_path = process_odds_profile_rollback(
        backup_path,
        registry_path,
        output_dir,
    )
    assert invalid_path["status"] == "invalid_backup_path"

    backup_path.write_text("{bad-json", encoding="utf-8")
    unreadable = process_odds_profile_rollback(
        backup_path,
        registry_path,
        output_dir,
    )
    assert unreadable["status"] == "unreadable_backup"

    same_path = process_odds_profile_rollback(
        registry_path,
        registry_path,
        output_dir,
    )
    assert same_path["status"] == "invalid_backup_path"
    assert same_path["json"].exists()
    assert same_path["markdown"].exists()


def test_unreadable_rollback_audit_blocks_before_registry_replacement(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    backup_path = tmp_path / "selected_backup.json"
    output_dir = tmp_path / "outputs"
    original = _write_registry(registry_path, {"current": {"version": 2}})
    _write_registry(backup_path, {"restored": {"version": 1}})
    output_dir.mkdir()
    (output_dir / "odds_profile_rollback_audit.csv").write_text(
        "wrong,columns\n1,2\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        process_odds_profile_rollback(
            backup_path,
            registry_path,
            output_dir,
            apply=True,
        )

    assert registry_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "backups").exists()
