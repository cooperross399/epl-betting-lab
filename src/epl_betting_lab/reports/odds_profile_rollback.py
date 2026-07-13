from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256


DEFAULT_REGISTRY_PATH = MANUAL_DIR / "odds_import_profiles.json"
AUDIT_COLUMNS = [
    "rollback_id",
    "applied_at",
    "rollback_status",
    "registry_path",
    "selected_backup_path",
    "pre_rollback_backup_path",
    "current_registry_sha256",
    "selected_backup_sha256",
    "current_profile_count",
    "backup_profile_count",
    "profiles_added_by_rollback",
    "profiles_removed_by_rollback",
    "profiles_changed_by_rollback",
]


def _read_registry(path: Path, label: str) -> tuple[dict[str, object] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"The {label} `{path}` is unreadable: {exc}"
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict):
        return None, f"The {label} `{path}` must contain a `profiles` JSON object."
    return payload, ""


def build_odds_profile_rollback_preview(
    current_registry: dict[str, object],
    backup_registry: dict[str, object],
    *,
    registry_path: Path,
    backup_path: Path,
) -> dict[str, object]:
    current_profiles = current_registry["profiles"]
    backup_profiles = backup_registry["profiles"]
    current_names = set(current_profiles)
    backup_names = set(backup_profiles)
    added = sorted(backup_names - current_names)
    removed = sorted(current_names - backup_names)
    changed = sorted(
        name
        for name in current_names & backup_names
        if current_profiles[name] != backup_profiles[name]
    )
    no_changes = not added and not removed and not changed
    warning = (
        "ROLLBACK WARNING: applying this rollback replaces odds_import_profiles.json "
        "with the selected backup file."
    )
    return {
        "status": "no_changes" if no_changes else "preview_ready",
        "message": (
            "The selected backup is already equivalent to the current registry."
            if no_changes
            else "Rollback preview created. The registry was not modified."
        ),
        "registry_path": str(registry_path),
        "backup_path": str(backup_path),
        "current_profile_count": len(current_profiles),
        "backup_profile_count": len(backup_profiles),
        "profiles_added_by_rollback": added,
        "profiles_removed_by_rollback": removed,
        "profiles_changed_by_rollback": changed,
        "warning": warning,
        "applied": False,
        "pre_rollback_backup_path": "",
    }


def render_odds_profile_rollback_preview(preview: dict[str, object]) -> str:
    lines = [
        "# Odds Profile Registry Rollback Preview",
        "",
        f"**{preview.get('warning', 'Rollback replaces the current profile registry.')}**",
        "",
        "Default mode is preview only. No profile registry or odds file is changed.",
        "",
        "## Summary",
        "",
        f"- Status: {preview.get('status', 'unknown')}",
        f"- Applied: {'yes' if preview.get('applied') else 'no'}",
        f"- Current registry: `{preview.get('registry_path', '')}`",
        f"- Selected backup: `{preview.get('backup_path', '')}`",
        f"- Current profile count: {int(preview.get('current_profile_count', 0))}",
        f"- Backup profile count: {int(preview.get('backup_profile_count', 0))}",
        "- Profiles added by rollback: "
        f"{', '.join(preview.get('profiles_added_by_rollback', [])) or 'none'}",
        "- Profiles removed by rollback: "
        f"{', '.join(preview.get('profiles_removed_by_rollback', [])) or 'none'}",
        "- Profiles changed by rollback: "
        f"{', '.join(preview.get('profiles_changed_by_rollback', [])) or 'none'}",
        f"- Backup of current registry: `{preview.get('pre_rollback_backup_path', '') or 'not created in preview mode'}`",
        f"- Message: {preview.get('message', '')}",
        "",
        "## Next step",
        "",
    ]
    if preview.get("applied"):
        lines.append(
            "Rollback completed from Terminal. Review the audit and rerun installed-profile verification."
        )
    elif preview.get("status") == "preview_ready":
        lines.append(
            "Review the profile changes above. Apply only from Terminal with "
            "`python scripts/rollback_odds_profile_registry.py --backup-path PATH --apply`."
        )
    elif preview.get("status") == "no_changes":
        lines.append("No rollback is needed because the selected backup matches the current registry.")
    else:
        lines.append("Fix the input problem shown above, then run rollback preview again.")
    return "\n".join(lines)


def _save_preview(
    preview: dict[str, object],
    output_dir: Path,
) -> dict[str, Path | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "odds_profile_rollback_preview.json"
    markdown_path = output_dir / "odds_profile_rollback_preview.md"
    json_path.write_text(json.dumps(preview, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_odds_profile_rollback_preview(preview), encoding="utf-8")
    return {
        "json": json_path,
        "markdown": markdown_path,
        "status": str(preview.get("status", "unknown")),
        "message": str(preview.get("message", "")),
    }


def _error_preview(
    status: str,
    message: str,
    registry_path: Path,
    backup_path: Path,
) -> dict[str, object]:
    return {
        "status": status,
        "message": message,
        "registry_path": str(registry_path),
        "backup_path": str(backup_path),
        "warning": "ROLLBACK WARNING: rollback replaces odds_import_profiles.json with the selected backup file.",
        "applied": False,
    }


def _load_existing_audit(output_dir: Path) -> pd.DataFrame:
    path = output_dir / "odds_profile_rollback_audit.csv"
    if not path.exists():
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    try:
        audit = pd.read_csv(path, dtype=str).fillna("")
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ValueError(f"Existing rollback audit is unreadable and was not overwritten: {exc}") from exc
    missing = [column for column in AUDIT_COLUMNS if column not in audit.columns]
    if missing:
        raise ValueError(
            "Existing rollback audit is missing required columns and was not overwritten: "
            f"{', '.join(missing)}."
        )
    return audit[AUDIT_COLUMNS]


def render_odds_profile_rollback_audit(audit: pd.DataFrame) -> str:
    lines = [
        "# Odds Profile Rollback Audit",
        "",
        "This history records explicit Terminal rollback operations on the profile registry.",
        "",
    ]
    if audit.empty:
        lines.append("No rollback operations have been recorded.")
    else:
        lines.extend(["## Rollback history", "", audit.to_markdown(index=False)])
    return "\n".join(lines)


def _save_audit(
    batch: pd.DataFrame,
    existing: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    audit = pd.concat([existing, batch], ignore_index=True)
    csv_path = output_dir / "odds_profile_rollback_audit.csv"
    markdown_path = output_dir / "odds_profile_rollback_audit.md"
    audit.to_csv(csv_path, index=False)
    markdown_path.write_text(render_odds_profile_rollback_audit(audit), encoding="utf-8")
    return {"audit_csv": csv_path, "audit_markdown": markdown_path}


def process_odds_profile_rollback(
    backup_path: Path,
    registry_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    apply: bool = False,
    timestamp: str | None = None,
    rollback_id: str | None = None,
    applied_at: str | None = None,
) -> dict[str, Path | str]:
    registry_path = registry_path or DEFAULT_REGISTRY_PATH
    output_dir = output_dir or OUTPUTS_DIR

    if not registry_path.exists():
        preview = _error_preview(
            "missing_registry",
            f"Missing current profile registry `{registry_path}`.",
            registry_path,
            backup_path,
        )
        return _save_preview(preview, output_dir)
    if not backup_path.exists() or not backup_path.is_file():
        preview = _error_preview(
            "invalid_backup_path",
            f"Backup path `{backup_path}` does not exist or is not a file.",
            registry_path,
            backup_path,
        )
        return _save_preview(preview, output_dir)
    try:
        if registry_path.resolve() == backup_path.resolve():
            preview = _error_preview(
                "invalid_backup_path",
                "The backup path must be different from the current registry path.",
                registry_path,
                backup_path,
            )
            return _save_preview(preview, output_dir)
    except OSError:
        pass

    current, current_error = _read_registry(registry_path, "current registry")
    if current is None:
        preview = _error_preview(
            "unreadable_registry",
            current_error,
            registry_path,
            backup_path,
        )
        return _save_preview(preview, output_dir)
    backup, backup_error = _read_registry(backup_path, "selected backup")
    if backup is None:
        preview = _error_preview(
            "unreadable_backup",
            backup_error,
            registry_path,
            backup_path,
        )
        return _save_preview(preview, output_dir)

    preview = build_odds_profile_rollback_preview(
        current,
        backup,
        registry_path=registry_path,
        backup_path=backup_path,
    )
    if not apply or preview["status"] != "preview_ready":
        return _save_preview(preview, output_dir)

    existing_audit = _load_existing_audit(output_dir)
    applied_at = applied_at or datetime.now().astimezone().isoformat(timespec="seconds")
    timestamp = timestamp or datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    rollback_id = rollback_id or f"odds-profile-rollback-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    backup_dir = registry_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    pre_rollback_backup = backup_dir / f"odds_import_profiles_pre_rollback_{timestamp}.json"
    if pre_rollback_backup.exists():
        raise FileExistsError(
            f"Pre-rollback backup `{pre_rollback_backup}` already exists; rollback was not applied."
        )
    shutil.copy2(registry_path, pre_rollback_backup)
    current_sha = source_file_sha256(registry_path)
    backup_sha = source_file_sha256(backup_path)
    shutil.copy2(backup_path, registry_path)

    preview.update(
        {
            "status": "applied",
            "message": "The selected backup replaced the profile registry from Terminal.",
            "applied": True,
            "pre_rollback_backup_path": str(pre_rollback_backup),
            "rollback_id": rollback_id,
            "applied_at": applied_at,
        }
    )
    paths = _save_preview(preview, output_dir)
    audit_row = pd.DataFrame(
        [
            {
                "rollback_id": rollback_id,
                "applied_at": applied_at,
                "rollback_status": "applied",
                "registry_path": str(registry_path),
                "selected_backup_path": str(backup_path),
                "pre_rollback_backup_path": str(pre_rollback_backup),
                "current_registry_sha256": current_sha,
                "selected_backup_sha256": backup_sha,
                "current_profile_count": preview["current_profile_count"],
                "backup_profile_count": preview["backup_profile_count"],
                "profiles_added_by_rollback": "; ".join(preview["profiles_added_by_rollback"]),
                "profiles_removed_by_rollback": "; ".join(preview["profiles_removed_by_rollback"]),
                "profiles_changed_by_rollback": "; ".join(preview["profiles_changed_by_rollback"]),
            }
        ],
        columns=AUDIT_COLUMNS,
    )
    paths.update(_save_audit(audit_row, existing_audit, output_dir))
    paths["pre_rollback_backup"] = pre_rollback_backup
    paths["registry"] = registry_path
    return paths
