from __future__ import annotations

import json

import pandas as pd
import pytest

from epl_betting_lab.reports.odds_export_profile_suggestion_validation import (
    VERDICT_INVALID,
    VERDICT_NEEDS_EDITS,
    VERDICT_READY,
)
from epl_betting_lab.reports.odds_profile_install import (
    process_odds_profile_install,
)


PROFILE = {
    "description": "Reviewed example profile",
    "column_map": {
        "game_date": "date",
        "home": "home_team",
        "away": "away_team",
        "bet_type": "market",
        "pick": "selection",
        "odds": "american_odds",
        "sportsbook": "book",
    },
}


def _suggestion(path, profile_name: str = "example_book", *, review_needed: bool = False) -> None:
    payload = {
        "profile_name": profile_name,
        "suggested_profile": PROFILE,
        "missing_required_fields": ["book"] if review_needed else [],
        "field_suggestions": [],
        "review_needed": (
            [
                {
                    "standard_field": "book",
                    "required": True,
                    "suggested_source_column": "REVIEW_NEEDED",
                    "review_needed": True,
                }
            ]
            if review_needed
            else []
        ),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _registry(path, profiles: dict[str, object] | None = None) -> str:
    payload = {"profiles": profiles or {"generic": {"description": "keep", "column_map": PROFILE["column_map"]}}}
    text = json.dumps(payload, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def _validation(markdown_path, csv_path, verdict: str, statuses: list[str] | None = None) -> None:
    markdown_path.write_text(f"# Validation\n\n## Verdict: {verdict}\n", encoding="utf-8")
    pd.DataFrame({"validation_status": statuses or ["valid"]}).to_csv(csv_path, index=False)


def _paths(tmp_path):
    suggestion_path = tmp_path / "suggestion.json"
    validation_markdown = tmp_path / "validation.md"
    validation_csv = tmp_path / "validation.csv"
    registry_path = tmp_path / "odds_import_profiles.json"
    output_dir = tmp_path / "outputs"
    return suggestion_path, validation_markdown, validation_csv, registry_path, output_dir


def test_preview_shows_exact_registry_change_without_editing_registry(tmp_path) -> None:
    suggestion, validation_md, validation_csv, registry, outputs = _paths(tmp_path)
    _suggestion(suggestion)
    original = _registry(registry)
    _validation(validation_md, validation_csv, VERDICT_READY)

    paths = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
    )

    assert paths["status"] == "preview_ready"
    preview = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert preview["profile_name"] == "example_book"
    assert preview["profile_exists"] is False
    assert preview["current_registry_profile_count"] == 1
    assert preview["new_registry_profile_count"] == 2
    assert preview["validation_verdict"] == VERDICT_READY
    assert preview["exact_json_block"] == {"example_book": PROFILE}
    assert registry.read_text(encoding="utf-8") == original
    assert not (tmp_path / "backups").exists()


def test_ready_apply_creates_backup_installs_profile_and_writes_audit(tmp_path) -> None:
    suggestion, validation_md, validation_csv, registry, outputs = _paths(tmp_path)
    _suggestion(suggestion)
    original = _registry(registry)
    _validation(validation_md, validation_csv, VERDICT_READY)

    paths = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
        apply=True,
        timestamp="20260712_120000",
        install_id="install-1",
        applied_at="2026-07-12T12:00:00-04:00",
    )

    assert paths["status"] == "applied"
    installed = json.loads(registry.read_text(encoding="utf-8"))
    assert installed["profiles"]["example_book"] == PROFILE
    assert paths["backup"].read_text(encoding="utf-8") == original
    audit = pd.read_csv(paths["audit_csv"], dtype=str).fillna("")
    assert audit.loc[0, "install_id"] == "install-1"
    assert audit.loc[0, "install_action"] == "add_new"
    assert audit.loc[0, "profile_count_before"] == "1"
    assert audit.loc[0, "profile_count_after"] == "2"
    assert "Odds Profile Install Audit" in paths["audit_markdown"].read_text(encoding="utf-8")


def test_duplicate_profile_requires_explicit_replace_flag(tmp_path) -> None:
    suggestion, validation_md, validation_csv, registry, outputs = _paths(tmp_path)
    _suggestion(suggestion)
    old_profile = {"description": "old", "column_map": PROFILE["column_map"]}
    original = _registry(registry, {"example_book": old_profile})
    _validation(validation_md, validation_csv, VERDICT_READY)

    blocked = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
        apply=True,
    )
    assert blocked["status"] == "apply_blocked"
    assert "--replace-existing" in blocked["markdown"].read_text(encoding="utf-8")
    assert registry.read_text(encoding="utf-8") == original

    applied = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
        apply=True,
        replace_existing=True,
        timestamp="20260712_120001",
        install_id="install-replace",
        applied_at="2026-07-12T12:00:01-04:00",
    )
    assert applied["status"] == "applied"
    installed = json.loads(registry.read_text(encoding="utf-8"))
    assert installed["profiles"]["example_book"] == PROFILE
    audit = pd.read_csv(applied["audit_csv"], dtype=str).fillna("")
    assert audit.loc[0, "install_action"] == "replace_existing"
    assert audit.loc[0, "profile_count_before"] == "1"
    assert audit.loc[0, "profile_count_after"] == "1"


def test_invalid_verdict_can_never_be_overridden(tmp_path) -> None:
    suggestion, validation_md, validation_csv, registry, outputs = _paths(tmp_path)
    _suggestion(suggestion)
    original = _registry(registry)
    _validation(validation_md, validation_csv, VERDICT_INVALID, ["invalid"])

    paths = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
        apply=True,
        allow_needs_edits=True,
        allow_missing_validation=True,
    )

    assert paths["status"] == "apply_blocked"
    assert "can never be installed" in paths["markdown"].read_text(encoding="utf-8")
    assert registry.read_text(encoding="utf-8") == original


def test_needs_edits_requires_additional_explicit_flag(tmp_path) -> None:
    suggestion, validation_md, validation_csv, registry, outputs = _paths(tmp_path)
    _suggestion(suggestion, review_needed=True)
    original = _registry(registry)
    _validation(validation_md, validation_csv, VERDICT_NEEDS_EDITS, ["invalid"])

    blocked = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
        apply=True,
    )
    assert blocked["status"] == "apply_blocked"
    assert registry.read_text(encoding="utf-8") == original

    applied = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
        apply=True,
        allow_needs_edits=True,
        timestamp="20260712_120002",
        install_id="install-needs-edits",
        applied_at="2026-07-12T12:00:02-04:00",
    )
    assert applied["status"] == "applied"
    assert applied["backup"].exists()


def test_missing_validation_warns_and_requires_explicit_override(tmp_path) -> None:
    suggestion, validation_md, validation_csv, registry, outputs = _paths(tmp_path)
    _suggestion(suggestion)
    original = _registry(registry)

    preview = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
    )
    assert preview["status"] == "preview_ready"
    assert "Validation report is missing" in preview["markdown"].read_text(encoding="utf-8")

    blocked = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
        apply=True,
    )
    assert blocked["status"] == "apply_blocked"
    assert registry.read_text(encoding="utf-8") == original

    applied = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
        apply=True,
        allow_missing_validation=True,
        timestamp="20260712_120003",
        install_id="install-no-validation",
        applied_at="2026-07-12T12:00:03-04:00",
    )
    assert applied["status"] == "applied"


def test_preview_writes_beginner_friendly_input_errors(tmp_path) -> None:
    suggestion, validation_md, validation_csv, registry, outputs = _paths(tmp_path)

    missing_suggestion = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
    )
    assert missing_suggestion["status"] == "missing_suggestion"

    suggestion.write_text("{bad-json", encoding="utf-8")
    malformed = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
    )
    assert malformed["status"] == "malformed_suggestion"

    _suggestion(suggestion)
    missing_registry = process_odds_profile_install(
        suggestion,
        validation_md,
        validation_csv,
        registry,
        outputs,
    )
    assert missing_registry["status"] == "missing_registry"
    assert missing_registry["json"].exists()
    assert missing_registry["markdown"].exists()


def test_unreadable_existing_audit_blocks_before_registry_write(tmp_path) -> None:
    suggestion, validation_md, validation_csv, registry, outputs = _paths(tmp_path)
    _suggestion(suggestion)
    original = _registry(registry)
    _validation(validation_md, validation_csv, VERDICT_READY)
    outputs.mkdir()
    (outputs / "odds_profile_install_audit.csv").write_text("wrong,columns\n1,2\n", encoding="utf-8")

    with pytest.raises(ValueError):
        process_odds_profile_install(
            suggestion,
            validation_md,
            validation_csv,
            registry,
            outputs,
            apply=True,
        )

    assert registry.read_text(encoding="utf-8") == original
    assert not (tmp_path / "backups").exists()
