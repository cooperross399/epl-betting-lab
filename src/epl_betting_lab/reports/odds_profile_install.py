from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.odds_export_conversion import (
    validate_odds_import_profile,
)
from epl_betting_lab.reports.odds_export_profile_suggestion_validation import (
    VERDICT_INVALID,
    VERDICT_NEEDS_EDITS,
    VERDICT_READY,
)


DEFAULT_SUGGESTION_PATH = OUTPUTS_DIR / "odds_export_profile_suggestion.json"
DEFAULT_VALIDATION_MARKDOWN_PATH = OUTPUTS_DIR / "odds_export_profile_suggestion_validation.md"
DEFAULT_VALIDATION_CSV_PATH = OUTPUTS_DIR / "odds_export_profile_suggestion_validation.csv"
DEFAULT_REGISTRY_PATH = MANUAL_DIR / "odds_import_profiles.json"
AUDIT_COLUMNS = [
    "install_id",
    "applied_at",
    "install_status",
    "install_action",
    "profile_name",
    "validation_verdict",
    "suggestion_path",
    "registry_path",
    "backup_path",
    "profile_count_before",
    "profile_count_after",
    "warnings",
    "before_profile",
    "after_profile",
]
FATAL_INSTALL_PREVIEW_STATUSES = {
    "missing_suggestion",
    "malformed_suggestion",
    "missing_registry",
    "malformed_registry",
    "invalid_profile",
}


class OddsProfileInstallPreviewError(RuntimeError):
    """Raised by the dashboard when an installation preview cannot be built."""


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _read_json_object(path: Path, label: str) -> tuple[dict[str, object] | None, str]:
    if not path.exists():
        return None, f"Missing {label} file `{path}`."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"The {label} file `{path}` is malformed or unreadable: {exc}"
    if not isinstance(payload, dict):
        return None, f"The {label} file `{path}` must contain one JSON object."
    return payload, ""


def _validation_details(
    markdown_path: Path,
    csv_path: Path,
) -> tuple[str, int | None, list[str]]:
    warnings: list[str] = []
    verdict = "Not available"
    invalid_rows: int | None = None
    if markdown_path.exists():
        try:
            markdown = markdown_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            warnings.append(f"Validation markdown is unreadable: {exc}")
        else:
            match = re.search(r"^## Verdict:\s*(.+?)\s*$", markdown, flags=re.MULTILINE)
            if match:
                verdict = match.group(1).strip()
            else:
                warnings.append("Validation markdown does not contain a recognized verdict.")
    else:
        warnings.append(
            "Validation report is missing. Run `python scripts/validate_odds_export_profile_suggestion.py`."
        )

    if csv_path.exists():
        try:
            validation = pd.read_csv(csv_path, dtype=str).fillna("")
        except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
            warnings.append(f"Validation CSV is unreadable: {exc}")
        else:
            if "validation_status" not in validation.columns:
                warnings.append("Validation CSV is missing the `validation_status` column.")
            else:
                invalid_rows = int(validation["validation_status"].str.lower().eq("invalid").sum())
                if invalid_rows:
                    warnings.append(f"Validation CSV contains {invalid_rows} invalid row(s).")
    return verdict, invalid_rows, warnings


def _review_needed_fields(suggestion: dict[str, object]) -> list[str]:
    fields: set[str] = set()
    for value in suggestion.get("missing_required_fields", []):
        if _clean(value):
            fields.add(_clean(value))
    for key in ["field_suggestions", "review_needed"]:
        items = suggestion.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not bool(item.get("required")):
                continue
            source_column = _clean(item.get("suggested_source_column"))
            if bool(item.get("review_needed")) or source_column == "REVIEW_NEEDED":
                field = _clean(item.get("standard_field"))
                if field:
                    fields.add(field)
    return sorted(fields)


def build_odds_profile_install_preview(
    suggestion: dict[str, object],
    registry: dict[str, object],
    *,
    validation_verdict: str = "Not available",
    validation_invalid_rows: int | None = None,
    validation_warnings: list[str] | None = None,
) -> dict[str, object]:
    profile_name = _clean(suggestion.get("profile_name"))
    suggested_profile = suggestion.get("suggested_profile")
    profiles = registry.get("profiles")
    if not profile_name:
        return {
            "status": "invalid_profile",
            "message": "The suggestion does not contain a profile name.",
            "warnings": ["Regenerate the suggestion with `--profile-name`."],
        }
    if not isinstance(suggested_profile, dict):
        return {
            "status": "invalid_profile",
            "message": "The suggestion does not contain a valid `suggested_profile` object.",
            "profile_name": profile_name,
            "warnings": [],
        }
    if not isinstance(profiles, dict):
        return {
            "status": "malformed_registry",
            "message": "The registry must contain a `profiles` JSON object.",
            "profile_name": profile_name,
            "warnings": [],
        }

    _, profile_issues = validate_odds_import_profile(profile_name, suggested_profile)
    if profile_issues:
        return {
            "status": "invalid_profile",
            "message": "The suggested profile is structurally incomplete or invalid.",
            "profile_name": profile_name,
            "profile_issues": profile_issues,
            "warnings": list(profile_issues),
            "exact_json_block": {profile_name: suggested_profile},
        }

    profile_exists = profile_name in profiles
    review_needed = _review_needed_fields(suggestion)
    warnings = list(validation_warnings or [])
    if profile_exists:
        warnings.append(
            f"Profile `{profile_name}` already exists. Apply requires `--replace-existing`."
        )
    if validation_verdict == VERDICT_INVALID:
        warnings.append("Validation verdict is invalid; installation is blocked.")
    elif validation_verdict == VERDICT_NEEDS_EDITS:
        warnings.append(
            "Validation says the draft needs edits. Apply requires `--allow-needs-edits`."
        )
    elif validation_verdict != VERDICT_READY:
        warnings.append(
            "A ready validation verdict is not available. Apply requires `--allow-missing-validation`."
        )
    if validation_invalid_rows:
        warnings.append(
            "Validation contains invalid rows. Apply requires `--allow-needs-edits`."
        )
    if review_needed:
        warnings.append(
            f"REVIEW_NEEDED required fields remain: {', '.join(review_needed)}. "
            "Apply requires `--allow-needs-edits`."
        )

    current_count = len(profiles)
    return {
        "status": "preview_ready",
        "message": "Installation preview created. The registry was not modified.",
        "profile_name": profile_name,
        "profile_exists": profile_exists,
        "install_action": "replace_existing" if profile_exists else "add_new",
        "current_registry_profile_count": current_count,
        "new_registry_profile_count": current_count if profile_exists else current_count + 1,
        "validation_verdict": validation_verdict,
        "validation_invalid_rows": validation_invalid_rows,
        "review_needed_fields": review_needed,
        "warnings": warnings,
        "exact_json_block": {profile_name: suggested_profile},
        "before_profile": profiles.get(profile_name, {}),
        "after_profile": suggested_profile,
        "applied": False,
        "backup_path": "",
    }


def render_odds_profile_install_preview(preview: dict[str, object]) -> str:
    warnings = preview.get("warnings", [])
    lines = [
        "# Odds Profile Registry Installation Preview",
        "",
        "Preview mode is read-only. It does not edit `odds_import_profiles.json`, either odds CSV, "
        "the import file, the ledger, or the model.",
        "",
        "## Summary",
        "",
        f"- Status: {preview.get('status', 'unknown')}",
        f"- Applied: {'yes' if preview.get('applied') else 'no'}",
        f"- Profile name: {preview.get('profile_name', 'not available')}",
        f"- Profile already exists: {'yes' if preview.get('profile_exists') else 'no'}",
        f"- Install action: {preview.get('install_action', 'not available')}",
        f"- Current registry profile count: {int(preview.get('current_registry_profile_count', 0))}",
        f"- New registry profile count: {int(preview.get('new_registry_profile_count', 0))}",
        f"- Validation verdict: {preview.get('validation_verdict', 'Not available')}",
        f"- Backup path: `{preview.get('backup_path', '') or 'not created in preview mode'}`",
        f"- Message: {preview.get('message', '')}",
        "",
        "## Warnings",
        "",
        "\n".join(f"- {warning}" for warning in warnings) if warnings else "No warnings found.",
        "",
        "## Exact JSON block to add or replace",
        "",
        "```json",
        json.dumps(preview.get("exact_json_block", {}), indent=2),
        "```",
        "",
        "## Next step",
        "",
    ]
    if preview.get("applied"):
        lines.append(
            "The Terminal apply completed. Review the backup and audit files, then rerun the profile diagnostic."
        )
    elif preview.get("status") == "preview_ready":
        lines.append(
            "Review this exact block and every warning. Installation remains Terminal-only with "
            "`python scripts/preview_install_odds_profile.py --apply`."
        )
    else:
        lines.append("Fix the input problem shown above, then generate the preview again.")
    return "\n".join(lines)


def _save_preview(
    preview: dict[str, object],
    output_dir: Path,
) -> dict[str, Path | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "odds_profile_install_preview.json"
    markdown_path = output_dir / "odds_profile_install_preview.md"
    json_path.write_text(json.dumps(preview, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_odds_profile_install_preview(preview), encoding="utf-8")
    return {
        "json": json_path,
        "markdown": markdown_path,
        "status": str(preview.get("status", "unknown")),
        "message": str(preview.get("message", "")),
    }


def _backup_registry(registry_path: Path, timestamp: str) -> Path:
    backup_dir = registry_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"odds_import_profiles_{timestamp}.json"
    if backup_path.exists():
        raise FileExistsError(f"Registry backup `{backup_path}` already exists; nothing was installed.")
    shutil.copy2(registry_path, backup_path)
    return backup_path


def _audit_row(
    preview: dict[str, object],
    *,
    install_id: str,
    applied_at: str,
    suggestion_path: Path,
    registry_path: Path,
    backup_path: Path,
) -> pd.DataFrame:
    row = {
        "install_id": install_id,
        "applied_at": applied_at,
        "install_status": "applied",
        "install_action": preview.get("install_action", ""),
        "profile_name": preview.get("profile_name", ""),
        "validation_verdict": preview.get("validation_verdict", ""),
        "suggestion_path": str(suggestion_path),
        "registry_path": str(registry_path),
        "backup_path": str(backup_path),
        "profile_count_before": preview.get("current_registry_profile_count", 0),
        "profile_count_after": preview.get("new_registry_profile_count", 0),
        "warnings": "; ".join(str(value) for value in preview.get("warnings", [])),
        "before_profile": json.dumps(preview.get("before_profile", {}), sort_keys=True),
        "after_profile": json.dumps(preview.get("after_profile", {}), sort_keys=True),
    }
    return pd.DataFrame([row], columns=AUDIT_COLUMNS)


def render_odds_profile_install_audit(audit: pd.DataFrame) -> str:
    lines = [
        "# Odds Profile Install Audit",
        "",
        "This file records explicit Terminal installations into `odds_import_profiles.json`.",
        "",
    ]
    if audit.empty:
        lines.append("No profile installations have been recorded.")
    else:
        lines.extend(["## Install history", "", audit.to_markdown(index=False)])
    return "\n".join(lines)


def _load_existing_audit(output_dir: Path) -> pd.DataFrame:
    csv_path = output_dir / "odds_profile_install_audit.csv"
    if not csv_path.exists():
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    try:
        existing = pd.read_csv(csv_path, dtype=str).fillna("")
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ValueError(f"Existing install audit is unreadable; it was not overwritten: {exc}") from exc
    missing = [column for column in AUDIT_COLUMNS if column not in existing.columns]
    if missing:
        raise ValueError(
            "Existing install audit is missing required columns and was not overwritten: "
            f"{', '.join(missing)}."
        )
    return existing[AUDIT_COLUMNS]


def _save_audit(
    batch: pd.DataFrame,
    existing: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    csv_path = output_dir / "odds_profile_install_audit.csv"
    markdown_path = output_dir / "odds_profile_install_audit.md"
    audit = pd.concat([existing, batch], ignore_index=True)
    audit.to_csv(csv_path, index=False)
    markdown_path.write_text(render_odds_profile_install_audit(audit), encoding="utf-8")
    return {"audit_csv": csv_path, "audit_markdown": markdown_path}


def _apply_blockers(
    preview: dict[str, object],
    *,
    allow_needs_edits: bool,
    allow_missing_validation: bool,
    replace_existing: bool,
) -> list[str]:
    blockers: list[str] = []
    verdict = preview.get("validation_verdict")
    if verdict == VERDICT_INVALID:
        blockers.append("Invalid draft suggestions can never be installed.")
    elif verdict == VERDICT_NEEDS_EDITS and not allow_needs_edits:
        blockers.append("Use `--allow-needs-edits` only after manually accepting every validation issue.")
    elif verdict not in {VERDICT_READY, VERDICT_NEEDS_EDITS, VERDICT_INVALID} and not allow_missing_validation:
        blockers.append("Use `--allow-missing-validation` only after manually confirming why validation is absent.")
    if preview.get("validation_invalid_rows") and not allow_needs_edits:
        blockers.append("Validation contains invalid rows; `--allow-needs-edits` is required.")
    if preview.get("review_needed_fields") and not allow_needs_edits:
        blockers.append("REVIEW_NEEDED fields remain; `--allow-needs-edits` is required.")
    if preview.get("profile_exists") and not replace_existing:
        blockers.append("The profile name already exists; `--replace-existing` is required.")
    return blockers


def process_odds_profile_install(
    suggestion_path: Path | None = None,
    validation_markdown_path: Path | None = None,
    validation_csv_path: Path | None = None,
    registry_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    apply: bool = False,
    allow_needs_edits: bool = False,
    allow_missing_validation: bool = False,
    replace_existing: bool = False,
    timestamp: str | None = None,
    install_id: str | None = None,
    applied_at: str | None = None,
) -> dict[str, Path | str]:
    suggestion_path = suggestion_path or DEFAULT_SUGGESTION_PATH
    validation_markdown_path = validation_markdown_path or DEFAULT_VALIDATION_MARKDOWN_PATH
    validation_csv_path = validation_csv_path or DEFAULT_VALIDATION_CSV_PATH
    registry_path = registry_path or DEFAULT_REGISTRY_PATH
    output_dir = output_dir or OUTPUTS_DIR

    suggestion, suggestion_error = _read_json_object(suggestion_path, "suggestion")
    if suggestion is None:
        status = "missing_suggestion" if not suggestion_path.exists() else "malformed_suggestion"
        preview = {"status": status, "message": suggestion_error, "warnings": [suggestion_error], "applied": False}
        return _save_preview(preview, output_dir)
    registry, registry_error = _read_json_object(registry_path, "registry")
    if registry is None:
        status = "missing_registry" if not registry_path.exists() else "malformed_registry"
        preview = {"status": status, "message": registry_error, "warnings": [registry_error], "applied": False}
        return _save_preview(preview, output_dir)

    verdict, invalid_rows, validation_warnings = _validation_details(
        validation_markdown_path,
        validation_csv_path,
    )
    preview = build_odds_profile_install_preview(
        suggestion,
        registry,
        validation_verdict=verdict,
        validation_invalid_rows=invalid_rows,
        validation_warnings=validation_warnings,
    )
    preview.update(
        {
            "suggestion_path": str(suggestion_path),
            "registry_path": str(registry_path),
            "validation_markdown_path": str(validation_markdown_path),
            "validation_csv_path": str(validation_csv_path),
        }
    )
    if not apply or preview.get("status") != "preview_ready":
        return _save_preview(preview, output_dir)

    blockers = _apply_blockers(
        preview,
        allow_needs_edits=allow_needs_edits,
        allow_missing_validation=allow_missing_validation,
        replace_existing=replace_existing,
    )
    if blockers:
        preview.update(
            {
                "status": "apply_blocked",
                "message": "Installation was blocked. The registry was not modified.",
                "apply_blockers": blockers,
                "warnings": [*preview.get("warnings", []), *blockers],
            }
        )
        return _save_preview(preview, output_dir)

    applied_at = applied_at or datetime.now().astimezone().isoformat(timespec="seconds")
    timestamp = timestamp or datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    install_id = install_id or f"odds-profile-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    existing_audit = _load_existing_audit(output_dir)
    backup_path = _backup_registry(registry_path, timestamp)
    profiles = registry["profiles"]
    profiles[str(preview["profile_name"])] = preview["after_profile"]
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    preview.update(
        {
            "status": "applied",
            "message": "Profile installed from Terminal after explicit safety checks.",
            "applied": True,
            "backup_path": str(backup_path),
            "install_id": install_id,
            "applied_at": applied_at,
        }
    )
    paths = _save_preview(preview, output_dir)
    audit_paths = _save_audit(
        _audit_row(
            preview,
            install_id=install_id,
            applied_at=applied_at,
            suggestion_path=suggestion_path,
            registry_path=registry_path,
            backup_path=backup_path,
        ),
        existing_audit,
        output_dir,
    )
    paths.update(audit_paths)
    paths["backup"] = backup_path
    paths["registry"] = registry_path
    return paths
