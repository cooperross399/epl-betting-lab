from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
import json
import os
from pathlib import Path
import re
import shlex
import shutil
from tempfile import NamedTemporaryFile
from uuid import uuid4

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256
from epl_betting_lab.reports.stale_current_odds_backup_picker import (
    get_stale_current_odds_backup_checksum_status,
)


DEFAULT_CURRENT_ODDS_PATH = MANUAL_DIR / "current_odds.csv"
CONFIRMATION_SCHEMA_VERSION = 1
CONFIRMATION_METADATA_FILENAME = "stale_current_odds_archive_rollback_preview.json"
CHECKSUM_REPORT_COLUMNS = [
    "checksum_status",
    "recorded_checksum_sha256",
    "current_checksum_sha256",
    "checksum_gate_result",
    "checksum_gate_note",
]
CONFIRMATION_REPORT_COLUMNS = [
    "confirm_id",
    "confirm_id_status",
    "preview_current_checksum_sha256",
    "apply_current_checksum_sha256",
    "preview_backup_checksum_sha256",
    "apply_backup_checksum_sha256",
    "confirmation_gate_result",
    "confirmation_gate_note",
]
PREVIEW_PREFIX_COLUMNS = [
    "rollback_action",
    "rollback_reason",
    *CHECKSUM_REPORT_COLUMNS,
    *CONFIRMATION_REPORT_COLUMNS,
    "source_file",
    "source_row_number",
]
LEGACY_AUDIT_COLUMNS = [
    "rollback_id",
    "applied_at",
    "status",
    "current_odds_path",
    "selected_backup_path",
    "pre_rollback_backup_path",
    "current_sha256_before",
    "selected_backup_sha256",
    "current_sha256_after",
    "current_rows_before",
    "backup_rows",
    "rows_restored",
    "rows_removed_or_replaced",
    "unchanged_rows",
    "rows_after",
]
AUDIT_CHECKSUM_COLUMNS = [
    "backup_checksum_sha256",
    "recovery_backup_checksum_sha256",
    *CHECKSUM_REPORT_COLUMNS,
]
AUDIT_CONFIRMATION_COLUMNS = [*CONFIRMATION_REPORT_COLUMNS]
AUDIT_COLUMNS = [
    *LEGACY_AUDIT_COLUMNS[:8],
    *AUDIT_CHECKSUM_COLUMNS,
    *AUDIT_CONFIRMATION_COLUMNS,
    *LEGACY_AUDIT_COLUMNS[8:],
]


def _checksum_gate(checksum_status: object, *, allow_mismatch: bool) -> tuple[str, str]:
    status = str(checksum_status).strip()
    if status == "Verified":
        return "Allowed", "The selected backup matches its recorded checksum. Rollback apply is allowed."
    if status == "Mismatch" and allow_mismatch:
        return (
            "Override used",
            "WARNING: The selected backup may have changed after creation. An explicit Terminal-only "
            "checksum mismatch override was used after manual inspection.",
        )
    if status == "Mismatch":
        return (
            "Blocked",
            "The selected backup does not match its recorded checksum. Rollback apply is blocked by "
            "default; inspect the file manually before considering an override.",
        )
    return (
        "Allowed with warning",
        "No usable audit checksum is available for this backup. Rollback apply is allowed, but its "
        "original integrity cannot be confirmed.",
    )


def _canonical_path(path: Path) -> str:
    try:
        return str(path.expanduser().resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return str(path.expanduser())


def _confirmation_payload(
    *,
    current_odds_path: Path,
    backup_path: Path,
    current_checksum: str,
    backup_checksum: str,
    generated_at: str,
) -> dict[str, object]:
    return {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "generated_at": generated_at,
        "current_odds_path": _canonical_path(current_odds_path),
        "selected_backup_path": _canonical_path(backup_path),
        "preview_current_checksum_sha256": current_checksum,
        "preview_backup_checksum_sha256": backup_checksum,
    }


def _confirmation_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _build_confirmation_metadata(
    *,
    current_odds_path: Path,
    backup_path: Path,
    current_checksum: str,
    backup_checksum: str,
    generated_at: str | None = None,
) -> dict[str, object]:
    payload = _confirmation_payload(
        current_odds_path=current_odds_path,
        backup_path=backup_path,
        current_checksum=current_checksum,
        backup_checksum=backup_checksum,
        generated_at=generated_at or datetime.now().astimezone().isoformat(timespec="microseconds"),
    )
    return {**payload, "confirm_id": _confirmation_id(payload)}


def _error_confirmation_metadata(
    *,
    current_odds_path: Path,
    backup_path: Path | None,
    status: str,
) -> dict[str, object]:
    return {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="microseconds"),
        "current_odds_path": _canonical_path(current_odds_path),
        "selected_backup_path": _canonical_path(backup_path) if backup_path is not None else "",
        "preview_current_checksum_sha256": "",
        "preview_backup_checksum_sha256": "",
        "confirm_id": "",
        "status": status,
    }


def _load_confirmation_metadata(
    output_dir: Path,
) -> tuple[dict[str, object] | None, str, str]:
    metadata_path = output_dir / CONFIRMATION_METADATA_FILENAME
    if not metadata_path.exists():
        return (
            None,
            "Missing preview",
            "No rollback preview confirmation metadata exists. Run preview mode first.",
        )
    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return (
            None,
            "Invalid preview",
            f"Rollback preview confirmation metadata is unreadable or malformed: {exc}",
        )
    if not isinstance(raw, dict):
        return None, "Invalid preview", "Rollback preview confirmation metadata is not a JSON object."

    required = [
        "schema_version",
        "generated_at",
        "current_odds_path",
        "selected_backup_path",
        "preview_current_checksum_sha256",
        "preview_backup_checksum_sha256",
        "confirm_id",
    ]
    missing = [field for field in required if field not in raw]
    if missing:
        return (
            None,
            "Invalid preview",
            "Rollback preview confirmation metadata is missing: " + ", ".join(missing) + ".",
        )
    if raw.get("schema_version") != CONFIRMATION_SCHEMA_VERSION:
        return None, "Invalid preview", "Rollback preview confirmation metadata uses an unsupported version."

    payload = {field: raw[field] for field in required if field != "confirm_id"}
    expected_id = _confirmation_id(payload)
    stored_id = str(raw.get("confirm_id", "")).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", stored_id) or not compare_digest(stored_id, expected_id):
        return (
            None,
            "Invalid preview",
            "Rollback preview confirmation metadata failed its own confirmation-ID check.",
        )
    preview_current = str(raw.get("preview_current_checksum_sha256", "")).strip()
    preview_backup = str(raw.get("preview_backup_checksum_sha256", "")).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", preview_current) or not re.fullmatch(
        r"[0-9a-f]{64}",
        preview_backup,
    ):
        return (
            None,
            "Invalid preview",
            "Rollback preview confirmation metadata does not contain valid file checksums.",
        )
    return raw, "Available", "The saved rollback preview confirmation metadata is readable."


def _confirmation_gate(
    metadata: dict[str, object] | None,
    *,
    metadata_status: str,
    metadata_note: str,
    provided_confirm_id: str | None,
    current_odds_path: Path,
    backup_path: Path,
    apply_current_checksum: str,
    apply_backup_checksum: str,
    allow_unconfirmed: bool,
) -> dict[str, str]:
    preview_id = str(metadata.get("confirm_id", "")).strip() if metadata else ""
    preview_current = (
        str(metadata.get("preview_current_checksum_sha256", "")).strip() if metadata else ""
    )
    preview_backup = (
        str(metadata.get("preview_backup_checksum_sha256", "")).strip() if metadata else ""
    )
    supplied_id = str(provided_confirm_id or "").strip()

    if metadata is None:
        status = metadata_status
        note = metadata_note
    elif _canonical_path(current_odds_path) != str(metadata.get("current_odds_path", "")):
        status = "Current path mismatch"
        note = "The current_odds.csv path does not match the reviewed rollback preview."
    elif _canonical_path(backup_path) != str(metadata.get("selected_backup_path", "")):
        status = "Backup path mismatch"
        note = "The selected backup path does not match the reviewed rollback preview."
    elif apply_current_checksum != preview_current:
        status = "Current odds changed"
        note = "current_odds.csv changed after the reviewed preview. Run preview mode again."
    elif apply_backup_checksum != preview_backup:
        status = "Backup changed"
        note = "The selected backup changed after the reviewed preview. Run preview mode again."
    elif not supplied_id:
        status = "Missing"
        note = "No confirmation ID was provided. Copy the exact apply command from the preview report."
    elif not re.fullmatch(r"[0-9a-f]{64}", supplied_id) or not compare_digest(
        supplied_id,
        preview_id,
    ):
        status = "Invalid"
        note = "The provided confirmation ID does not match the reviewed rollback preview."
    else:
        return {
            "confirm_id": preview_id,
            "confirm_id_status": "Matched",
            "preview_current_checksum_sha256": preview_current,
            "apply_current_checksum_sha256": apply_current_checksum,
            "preview_backup_checksum_sha256": preview_backup,
            "apply_backup_checksum_sha256": apply_backup_checksum,
            "confirmation_gate_result": "Allowed",
            "confirmation_gate_note": (
                "The confirmation ID, selected paths, and both file checksums match the reviewed preview."
            ),
        }

    if allow_unconfirmed:
        return {
            "confirm_id": preview_id or supplied_id,
            "confirm_id_status": "Override used",
            "preview_current_checksum_sha256": preview_current,
            "apply_current_checksum_sha256": apply_current_checksum,
            "preview_backup_checksum_sha256": preview_backup,
            "apply_backup_checksum_sha256": apply_backup_checksum,
            "confirmation_gate_result": "Override used",
            "confirmation_gate_note": (
                f"WARNING: {note} The explicit Terminal-only unconfirmed rollback override was used, "
                "so apply did not match a reviewed preview."
            ),
        }
    return {
        "confirm_id": preview_id,
        "confirm_id_status": status,
        "preview_current_checksum_sha256": preview_current,
        "apply_current_checksum_sha256": apply_current_checksum,
        "preview_backup_checksum_sha256": preview_backup,
        "apply_backup_checksum_sha256": apply_backup_checksum,
        "confirmation_gate_result": "Blocked",
        "confirmation_gate_note": note,
    }


def _read_csv(
    path: Path,
    *,
    label: str,
    allow_header_only: bool,
    require_date: bool,
) -> tuple[pd.DataFrame | None, str, str]:
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return None, "empty", f"The {label} `{path}` is empty."
    except pd.errors.ParserError as exc:
        return None, "malformed", f"The {label} `{path}` is malformed CSV: {exc}"
    except (OSError, UnicodeError) as exc:
        return None, "unreadable", f"The {label} `{path}` is unreadable: {exc}"

    if not len(frame.columns):
        return None, "malformed", f"The {label} `{path}` has no CSV columns."
    if frame.empty and not allow_header_only:
        return None, "empty", f"The {label} `{path}` contains column headers but no odds rows."
    if require_date and "date" not in frame.columns:
        return None, "malformed", f"The {label} `{path}` is missing the required `date` column."
    return frame.fillna(""), "ok", ""


def _ordered_union(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


def _normalized_rows(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame.reindex(columns=columns, fill_value="").fillna("").astype(str)


def _row_signatures(frame: pd.DataFrame, columns: list[str]) -> list[tuple[str, ...]]:
    normalized = _normalized_rows(frame, columns)
    return [tuple(row) for row in normalized.itertuples(index=False, name=None)]


def _changed_row_preview(
    current: pd.DataFrame,
    backup: pd.DataFrame,
    *,
    current_path: Path,
    backup_path: Path,
) -> tuple[pd.DataFrame, dict[str, int], list[str]]:
    data_columns = _ordered_union(current.columns.tolist(), backup.columns.tolist())
    current_rows = _normalized_rows(current, data_columns)
    backup_rows = _normalized_rows(backup, data_columns)
    current_signatures = _row_signatures(current_rows, data_columns)
    backup_signatures = _row_signatures(backup_rows, data_columns)
    current_counts = Counter(current_signatures)
    backup_counts = Counter(backup_signatures)
    restore_counts = backup_counts - current_counts
    remove_counts = current_counts - backup_counts
    records: list[dict[str, object]] = []

    for position, (signature, (_, row)) in enumerate(
        zip(backup_signatures, backup_rows.iterrows()),
        start=2,
    ):
        if restore_counts[signature] <= 0:
            continue
        restore_counts[signature] -= 1
        records.append(
            {
                "rollback_action": "Restore from backup",
                "rollback_reason": "This row exists in the selected backup but not in the current file.",
                "source_file": str(backup_path),
                "source_row_number": position,
                **row.to_dict(),
            }
        )

    for position, (signature, (_, row)) in enumerate(
        zip(current_signatures, current_rows.iterrows()),
        start=2,
    ):
        if remove_counts[signature] <= 0:
            continue
        remove_counts[signature] -= 1
        records.append(
            {
                "rollback_action": "Remove or replace current",
                "rollback_reason": "This current row is not present in the selected backup.",
                "source_file": str(current_path),
                "source_row_number": position,
                **row.to_dict(),
            }
        )

    preview_columns = [*PREVIEW_PREFIX_COLUMNS, *data_columns]
    preview = pd.DataFrame(records, columns=preview_columns).fillna("")
    counts = {
        "rows_restored": int(sum((backup_counts - current_counts).values())),
        "rows_removed_or_replaced": int(sum((current_counts - backup_counts).values())),
        "unchanged_rows": int(sum((current_counts & backup_counts).values())),
    }
    return preview, counts, data_columns


def build_stale_current_odds_archive_rollback_preview(
    current: pd.DataFrame,
    backup: pd.DataFrame,
    *,
    current_odds_path: Path,
    backup_path: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Compare current odds with a selected pre-archive backup in memory."""
    preview, counts, _ = _changed_row_preview(
        current,
        backup,
        current_path=current_odds_path,
        backup_path=backup_path,
    )
    current_columns = current.columns.tolist()
    backup_columns = backup.columns.tolist()
    columns_added = [column for column in backup_columns if column not in current_columns]
    columns_removed = [column for column in current_columns if column not in backup_columns]
    exact_match = current_columns == backup_columns and current.equals(backup)
    status = "no_changes" if exact_match else "preview_ready"
    message = (
        "The selected backup already matches current_odds.csv. No rollback is needed."
        if exact_match
        else "Rollback preview created. No input files were changed."
    )
    summary = {
        "status": status,
        "message": message,
        "current_odds_path": str(current_odds_path),
        "selected_backup_path": str(backup_path),
        "current_row_count": len(current),
        "backup_row_count": len(backup),
        **counts,
        "columns_added_by_rollback": columns_added,
        "columns_removed_by_rollback": columns_removed,
        "column_order_changes": current_columns != backup_columns,
        "warning": (
            "ROLLBACK WARNING: apply replaces current_odds.csv with the selected backup. "
            "Review the row differences first."
        ),
        "applied": False,
        "pre_rollback_backup_path": "",
        "current_sha256_before": source_file_sha256(current_odds_path),
        "selected_backup_sha256": source_file_sha256(backup_path),
    }
    return preview, summary


def _error_preview(
    status: str,
    message: str,
    *,
    current_odds_path: Path,
    backup_path: Path | None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    preview = pd.DataFrame(columns=PREVIEW_PREFIX_COLUMNS)
    return preview, {
        "status": status,
        "message": message,
        "current_odds_path": str(current_odds_path),
        "selected_backup_path": str(backup_path) if backup_path is not None else "",
        "current_row_count": 0,
        "backup_row_count": 0,
        "rows_restored": 0,
        "rows_removed_or_replaced": 0,
        "unchanged_rows": 0,
        "columns_added_by_rollback": [],
        "columns_removed_by_rollback": [],
        "column_order_changes": False,
        "warning": (
            "ROLLBACK WARNING: apply replaces current_odds.csv with the selected backup. "
            "No apply is allowed until this input problem is fixed."
        ),
        "applied": False,
        "pre_rollback_backup_path": "",
        "current_sha256_before": "",
        "selected_backup_sha256": "",
        "checksum_status": "Not available",
        "recorded_checksum_sha256": "",
        "current_checksum_sha256": "",
        "checksum_gate_result": "Not checked",
        "checksum_gate_note": "Checksum safety was not checked because the selected input could not be read.",
        "confirm_id": "",
        "confirm_id_status": "Not available",
        "preview_current_checksum_sha256": "",
        "apply_current_checksum_sha256": "",
        "preview_backup_checksum_sha256": "",
        "apply_backup_checksum_sha256": "",
        "confirmation_gate_result": "Not checked",
        "confirmation_gate_note": (
            "Preview confirmation was not created because the selected input could not be read."
        ),
    }


def render_stale_current_odds_archive_rollback_preview(
    preview: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    restored = (
        preview[preview["rollback_action"] == "Restore from backup"]
        if not preview.empty
        else preview
    )
    removed = (
        preview[preview["rollback_action"] == "Remove or replace current"]
        if not preview.empty
        else preview
    )
    lines = [
        "# Stale Current Odds Archive Rollback Preview",
        "",
        f"**{summary.get('warning', 'Rollback replaces current_odds.csv with the selected backup.')}**",
        "",
        (
            "**Rollback was explicitly applied from Terminal; review the audit below.**"
            if summary.get("applied")
            else "**Default mode is preview only. No odds, import, ledger, profile, or model files were changed.**"
        ),
        "",
        "## Summary",
        "",
        f"- Status: {summary.get('status', 'not_checked')}",
        f"- Applied: {'yes' if summary.get('applied') else 'no'}",
        f"- Current odds file: `{summary.get('current_odds_path', '')}`",
        f"- Selected backup: `{summary.get('selected_backup_path', '') or 'Not provided'}`",
        f"- Current row count: {int(summary.get('current_row_count', 0))}",
        f"- Backup row count: {int(summary.get('backup_row_count', 0))}",
        f"- Rows restored from backup: {int(summary.get('rows_restored', 0))}",
        f"- Current rows removed or replaced: {int(summary.get('rows_removed_or_replaced', 0))}",
        f"- Rows unchanged: {int(summary.get('unchanged_rows', 0))}",
        "- Columns added by rollback: "
        f"{', '.join(summary.get('columns_added_by_rollback', [])) or 'none'}",
        "- Columns removed by rollback: "
        f"{', '.join(summary.get('columns_removed_by_rollback', [])) or 'none'}",
        f"- Backup of current odds: `{summary.get('pre_rollback_backup_path', '') or 'not created in preview mode'}`",
        f"- Message: {summary.get('message', '')}",
        "",
        "## Checksum Safety Gate",
        "",
        f"- Checksum status: {summary.get('checksum_status', 'Not available')}",
        f"- Recorded checksum: `{summary.get('recorded_checksum_sha256', '') or 'Not available'}`",
        f"- Current backup checksum: `{summary.get('current_checksum_sha256', '') or 'Not available'}`",
        f"- Gate result: {summary.get('checksum_gate_result', 'Not checked')}",
        f"- Gate note: {summary.get('checksum_gate_note', '') or 'Checksum safety was not checked.'}",
        "",
        "## Preview Confirmation Gate",
        "",
        f"- Confirmation ID: `{summary.get('confirm_id', '') or 'Not available'}`",
        f"- Confirmation ID status: {summary.get('confirm_id_status', 'Not available')}",
        "- Preview current odds checksum: "
        f"`{summary.get('preview_current_checksum_sha256', '') or 'Not available'}`",
        "- Apply current odds checksum: "
        f"`{summary.get('apply_current_checksum_sha256', '') or 'Not checked in preview mode'}`",
        "- Preview backup checksum: "
        f"`{summary.get('preview_backup_checksum_sha256', '') or 'Not available'}`",
        "- Apply backup checksum: "
        f"`{summary.get('apply_backup_checksum_sha256', '') or 'Not checked in preview mode'}`",
        f"- Gate result: {summary.get('confirmation_gate_result', 'Not checked')}",
        "- Gate note: "
        f"{summary.get('confirmation_gate_note', '') or 'Preview confirmation was not checked.'}",
        "",
        "## Rows Restored From Backup",
        "",
        restored.to_markdown(index=False) if not restored.empty else "No backup-only rows found.",
        "",
        "## Current Rows Removed Or Replaced",
        "",
        removed.to_markdown(index=False) if not removed.empty else "No current-only rows found.",
        "",
        "## Next Step",
        "",
    ]
    if summary.get("applied"):
        lines.append("Rollback completed from Terminal. Review the rollback audit before continuing.")
    elif summary.get("status") == "confirmation_blocked":
        lines.append(
            "Rollback was not applied because this command did not match the reviewed preview. "
            "Run preview mode again, review the new report, then copy its exact apply command."
        )
    elif summary.get("status") == "checksum_mismatch_blocked":
        lines.append(
            "Rollback was not applied because the selected backup failed checksum verification. "
            "Inspect it manually before deciding whether the Terminal-only "
            "`--allow-checksum-mismatch` override is appropriate."
        )
    elif summary.get("status") == "preview_ready":
        confirm_id = str(summary.get("confirm_id", "")).strip()
        if confirm_id:
            command = (
                "python scripts/rollback_stale_current_odds_archive.py "
                f"--backup-path {shlex.quote(str(summary.get('selected_backup_path', '')))} "
                f"--current-odds {shlex.quote(str(summary.get('current_odds_path', '')))} "
                f"--apply --confirm-id {shlex.quote(confirm_id)}"
            )
            lines.extend(
                [
                    "After reviewing this report, copy and run this exact Terminal command:",
                    "",
                    "```bash",
                    command,
                    "```",
                ]
            )
        if summary.get("checksum_gate_result") == "Blocked":
            lines.extend(
                [
                    "",
                    "The checksum gate still blocks normal apply. Only after manually inspecting the backup "
                    "may you add the Terminal-only `--allow-checksum-mismatch` override.",
                ]
            )
        elif summary.get("checksum_gate_result") == "Allowed with warning":
            lines.extend(
                [
                    "",
                    "No audit checksum is available. Review the backup especially carefully before applying.",
                ]
            )
    elif summary.get("status") == "no_changes":
        lines.append("No rollback is needed because the selected backup already matches the current file.")
    else:
        lines.append("Fix the input problem shown above, then run rollback preview again.")
    return "\n".join(lines)


def _write_csv_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            frame.to_csv(handle, index=False)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _write_json_atomic(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def save_stale_current_odds_archive_rollback_preview(
    preview: pd.DataFrame,
    summary: dict[str, object],
    output_dir: Path | None = None,
    *,
    confirmation_metadata: dict[str, object] | None = None,
) -> dict[str, Path | str]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "stale_current_odds_archive_rollback_preview.csv"
    markdown_path = output_dir / "stale_current_odds_archive_rollback_preview.md"
    metadata_path = output_dir / CONFIRMATION_METADATA_FILENAME
    _write_csv_atomic(preview, csv_path)
    markdown_path.write_text(
        render_stale_current_odds_archive_rollback_preview(preview, summary),
        encoding="utf-8",
    )
    if confirmation_metadata is not None:
        _write_json_atomic(confirmation_metadata, metadata_path)
    result: dict[str, Path | str] = {
        "csv": csv_path,
        "markdown": markdown_path,
        "metadata": metadata_path,
        "status": str(summary.get("status", "not_checked")),
        "message": str(summary.get("message", "")),
    }
    for column in [*CHECKSUM_REPORT_COLUMNS, *CONFIRMATION_REPORT_COLUMNS]:
        result[column] = str(summary.get(column, ""))
    return result


def _safe_timestamp(timestamp: str | None = None) -> str:
    value = timestamp or datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S_%f")
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Rollback timestamp may contain only letters, numbers, hyphens, and underscores.")
    return value


def _load_existing_audit(output_dir: Path) -> pd.DataFrame:
    audit_path = output_dir / "stale_current_odds_archive_rollback_audit.csv"
    if not audit_path.exists():
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    try:
        audit = pd.read_csv(audit_path, dtype=str, keep_default_na=False)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ValueError(f"Existing stale-odds rollback audit is unreadable and was not overwritten: {exc}") from exc
    missing = [column for column in LEGACY_AUDIT_COLUMNS if column not in audit.columns]
    if missing:
        raise ValueError(
            "Existing stale-odds rollback audit is missing required columns and was not overwritten: "
            f"{', '.join(missing)}."
        )
    for column in [*AUDIT_CHECKSUM_COLUMNS, *AUDIT_CONFIRMATION_COLUMNS]:
        if column not in audit.columns:
            audit[column] = ""
    return audit[AUDIT_COLUMNS]


def render_stale_current_odds_archive_rollback_audit(audit: pd.DataFrame) -> str:
    lines = [
        "# Stale Current Odds Archive Rollback Audit",
        "",
        "This history records explicit Terminal rollback operations. Dashboard previews never restore odds.",
        "",
    ]
    if audit.empty:
        lines.append("No stale current-odds archive rollbacks have been applied.")
        return "\n".join(lines)
    latest = audit.iloc[-1]
    gate_warning = (
        "**WARNING: This rollback used an explicit checksum mismatch override. "
        "The selected backup may have changed after creation.**"
        if latest["checksum_gate_result"] == "Override used"
        else ""
    )
    confirmation_warning = (
        "**WARNING: This rollback used the unconfirmed rollback override and did not match a reviewed preview.**"
        if latest["confirmation_gate_result"] == "Override used"
        else ""
    )
    lines.extend(["## Latest Rollback", ""])
    if gate_warning:
        lines.extend([gate_warning, ""])
    if confirmation_warning:
        lines.extend([confirmation_warning, ""])
    lines.extend(
        [
            f"- Rollback ID: `{latest['rollback_id']}`",
            f"- Applied at: {latest['applied_at']}",
            f"- Selected backup: `{latest['selected_backup_path']}`",
            f"- Selected backup SHA-256: `{latest['backup_checksum_sha256'] or 'Not recorded'}`",
            f"- Pre-rollback backup: `{latest['pre_rollback_backup_path']}`",
            f"- Recovery backup SHA-256: `{latest['recovery_backup_checksum_sha256'] or 'Not recorded'}`",
            f"- Checksum status: {latest['checksum_status'] or 'Not available'}",
            f"- Recorded checksum: `{latest['recorded_checksum_sha256'] or 'Not available'}`",
            f"- Current backup checksum: `{latest['current_checksum_sha256'] or 'Not available'}`",
            f"- Checksum gate: {latest['checksum_gate_result'] or 'Not recorded'}",
            f"- Checksum gate note: {latest['checksum_gate_note'] or 'Not recorded'}",
            f"- Preview confirmation ID: `{latest['confirm_id'] or 'Not recorded'}`",
            f"- Confirmation ID status: {latest['confirm_id_status'] or 'Not recorded'}",
            "- Preview current odds checksum: "
            f"`{latest['preview_current_checksum_sha256'] or 'Not recorded'}`",
            "- Apply current odds checksum: "
            f"`{latest['apply_current_checksum_sha256'] or 'Not recorded'}`",
            f"- Preview backup checksum: `{latest['preview_backup_checksum_sha256'] or 'Not recorded'}`",
            f"- Apply backup checksum: `{latest['apply_backup_checksum_sha256'] or 'Not recorded'}`",
            f"- Confirmation gate: {latest['confirmation_gate_result'] or 'Not recorded'}",
            f"- Confirmation gate note: {latest['confirmation_gate_note'] or 'Not recorded'}",
            f"- Rows before: {latest['current_rows_before']}",
            f"- Rows after: {latest['rows_after']}",
            "",
            "## Rollback History",
            "",
            audit.to_markdown(index=False),
        ]
    )
    return "\n".join(lines)


def _save_audit(
    batch: pd.DataFrame,
    existing: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    audit = pd.concat([existing, batch], ignore_index=True).reindex(columns=AUDIT_COLUMNS).fillna("")
    csv_path = output_dir / "stale_current_odds_archive_rollback_audit.csv"
    markdown_path = output_dir / "stale_current_odds_archive_rollback_audit.md"
    _write_csv_atomic(audit, csv_path)
    markdown_path.write_text(
        render_stale_current_odds_archive_rollback_audit(audit),
        encoding="utf-8",
    )
    return {"audit_csv": csv_path, "audit_markdown": markdown_path}


def _replace_from_backup_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            with source.open("rb") as source_handle:
                shutil.copyfileobj(source_handle, handle)
        shutil.copystat(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def process_stale_current_odds_archive_rollback(
    backup_path: Path | str | None,
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    apply: bool = False,
    allow_checksum_mismatch: bool = False,
    confirm_id: str | None = None,
    allow_unconfirmed_rollback: bool = False,
    timestamp: str | None = None,
    rollback_id: str | None = None,
    applied_at: str | None = None,
) -> dict[str, Path | str]:
    """Preview or explicitly restore a selected pre-archive current-odds backup."""
    current_odds_path = current_odds_path or DEFAULT_CURRENT_ODDS_PATH
    output_dir = output_dir or OUTPUTS_DIR
    selected_backup: Path | None = None
    if backup_path is not None and str(backup_path).strip():
        selected_backup = Path(str(backup_path).strip()).expanduser()

    def save_input_error(
        preview_frame: pd.DataFrame,
        error_summary: dict[str, object],
    ) -> dict[str, Path | str]:
        metadata = None
        if not apply:
            metadata_backup = (
                Path(str(error_summary["selected_backup_path"]))
                if error_summary.get("selected_backup_path")
                else None
            )
            metadata = _error_confirmation_metadata(
                current_odds_path=current_odds_path,
                backup_path=metadata_backup,
                status=str(error_summary.get("status", "not_checked")),
            )
        return save_stale_current_odds_archive_rollback_preview(
            preview_frame,
            error_summary,
            output_dir,
            confirmation_metadata=metadata,
        )

    if selected_backup is None:
        preview, summary = _error_preview(
            "missing_backup_path",
            "Choose a pre-archive CSV backup path before previewing rollback.",
            current_odds_path=current_odds_path,
            backup_path=None,
        )
        return save_input_error(preview, summary)
    if not current_odds_path.exists() or not current_odds_path.is_file():
        preview, summary = _error_preview(
            "missing_current_odds",
            f"Missing current odds file `{current_odds_path}`. Nothing was restored.",
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
        )
        return save_input_error(preview, summary)
    if selected_backup.suffix.lower() != ".csv":
        preview, summary = _error_preview(
            "invalid_backup_path",
            f"Selected backup `{selected_backup}` must be a CSV file.",
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
        )
        return save_input_error(preview, summary)
    if not selected_backup.exists() or not selected_backup.is_file():
        preview, summary = _error_preview(
            "missing_backup_path",
            f"Selected backup `{selected_backup}` does not exist or is not a file.",
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
        )
        return save_input_error(preview, summary)
    try:
        if current_odds_path.resolve() == selected_backup.resolve():
            preview, summary = _error_preview(
                "backup_equals_current",
                "The selected backup is current_odds.csv itself. Choose a separate pre-archive backup.",
                current_odds_path=current_odds_path,
                backup_path=selected_backup,
            )
            return save_input_error(preview, summary)
    except OSError:
        pass

    current, current_read_status, current_error = _read_csv(
        current_odds_path,
        label="current odds file",
        allow_header_only=True,
        require_date=False,
    )
    if current is None:
        preview, summary = _error_preview(
            f"{current_read_status}_current_odds",
            current_error,
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
        )
        return save_input_error(preview, summary)
    backup, backup_read_status, backup_error = _read_csv(
        selected_backup,
        label="selected backup",
        allow_header_only=False,
        require_date=True,
    )
    if backup is None:
        preview, summary = _error_preview(
            f"{backup_read_status}_backup",
            f"{backup_error} Rollback was not applied.",
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
        )
        return save_input_error(preview, summary)

    preview, summary = build_stale_current_odds_archive_rollback_preview(
        current,
        backup,
        current_odds_path=current_odds_path,
        backup_path=selected_backup,
    )
    checksum_details = get_stale_current_odds_backup_checksum_status(
        selected_backup,
        archive_audit_path=output_dir / "stale_current_odds_archive_audit.csv",
        rollback_audit_path=output_dir / "stale_current_odds_archive_rollback_audit.csv",
    )
    override_active = bool(apply and allow_checksum_mismatch)
    checksum_gate_result, checksum_gate_note = _checksum_gate(
        checksum_details["checksum_status"],
        allow_mismatch=override_active,
    )
    summary.update(
        {
            "checksum_status": checksum_details["checksum_status"],
            "recorded_checksum_sha256": checksum_details["recorded_checksum_sha256"],
            "current_checksum_sha256": checksum_details["current_checksum_sha256"],
            "checksum_gate_result": checksum_gate_result,
            "checksum_gate_note": checksum_gate_note,
        }
    )
    confirmation_metadata: dict[str, object] | None = None
    if apply:
        stored_metadata, metadata_status, metadata_note = _load_confirmation_metadata(output_dir)
        confirmation_fields = _confirmation_gate(
            stored_metadata,
            metadata_status=metadata_status,
            metadata_note=metadata_note,
            provided_confirm_id=confirm_id,
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
            apply_current_checksum=str(summary["current_sha256_before"]),
            apply_backup_checksum=str(summary["selected_backup_sha256"]),
            allow_unconfirmed=allow_unconfirmed_rollback,
        )
    else:
        confirmation_metadata = _build_confirmation_metadata(
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
            current_checksum=str(summary["current_sha256_before"]),
            backup_checksum=str(summary["selected_backup_sha256"]),
        )
        confirmation_fields = {
            "confirm_id": str(confirmation_metadata["confirm_id"]),
            "confirm_id_status": (
                "Preview ready" if summary["status"] == "preview_ready" else "No rollback needed"
            ),
            "preview_current_checksum_sha256": str(
                confirmation_metadata["preview_current_checksum_sha256"]
            ),
            "apply_current_checksum_sha256": "",
            "preview_backup_checksum_sha256": str(
                confirmation_metadata["preview_backup_checksum_sha256"]
            ),
            "apply_backup_checksum_sha256": "",
            "confirmation_gate_result": (
                "Preview ready" if summary["status"] == "preview_ready" else "Not needed"
            ),
            "confirmation_gate_note": (
                "Review this preview, then use its confirmation ID in the exact Terminal apply command."
                if summary["status"] == "preview_ready"
                else "The selected backup already matches current_odds.csv, so no apply is needed."
            ),
        }
    summary.update(confirmation_fields)
    for column in [*CHECKSUM_REPORT_COLUMNS, *CONFIRMATION_REPORT_COLUMNS]:
        preview[column] = str(summary[column])

    if checksum_gate_result == "Blocked":
        summary["message"] = (
            "Rollback preview created, but the selected backup has a checksum mismatch. "
            "Normal rollback apply is blocked."
        )
        if apply and summary["status"] == "preview_ready":
            summary["status"] = "checksum_mismatch_blocked"
    elif checksum_gate_result == "Allowed with warning":
        summary["message"] = (
            "Rollback preview created. No audit checksum is available, so apply is allowed with caution."
        )
    elif checksum_gate_result == "Override used":
        summary["message"] = (
            "Checksum mismatch override requested from Terminal. The backup may have changed after creation."
        )
    if (
        apply
        and summary["status"] == "preview_ready"
        and summary["confirmation_gate_result"] == "Blocked"
    ):
        summary["status"] = "confirmation_blocked"
        summary["message"] = (
            "Rollback was not applied because the confirmation ID or previewed file state did not match. "
            "Run preview mode again and copy its exact apply command."
        )
    paths = save_stale_current_odds_archive_rollback_preview(
        preview,
        summary,
        output_dir,
        confirmation_metadata=confirmation_metadata,
    )
    if not apply or summary["status"] != "preview_ready":
        return paths

    existing_audit = _load_existing_audit(output_dir)
    current_sha = str(summary["apply_current_checksum_sha256"])
    backup_sha = str(summary["apply_backup_checksum_sha256"])
    try:
        latest_current_sha = source_file_sha256(current_odds_path)
        latest_backup_sha = source_file_sha256(selected_backup)
    except OSError as exc:
        summary.update(
            {
                "status": "confirmation_blocked",
                "message": "A rollback input became unreadable after confirmation. No file was changed.",
                "confirm_id_status": "File became unreadable",
                "confirmation_gate_result": "Blocked",
                "confirmation_gate_note": (
                    f"A rollback input became unreadable before the recovery backup was created: {exc}"
                ),
            }
        )
        for column in CONFIRMATION_REPORT_COLUMNS:
            preview[column] = str(summary[column])
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
    if not current_sha or latest_current_sha != current_sha:
        summary.update(
            {
                "status": "confirmation_blocked",
                "message": "current_odds.csv changed after confirmation. No file was changed.",
                "confirm_id_status": "Current odds changed",
                "apply_current_checksum_sha256": latest_current_sha,
                "confirmation_gate_result": "Blocked",
                "confirmation_gate_note": (
                    "current_odds.csv changed after the confirmation gate. Run preview mode again."
                ),
            }
        )
        for column in CONFIRMATION_REPORT_COLUMNS:
            preview[column] = str(summary[column])
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
    if not backup_sha or latest_backup_sha != backup_sha:
        summary.update(
            {
                "status": "confirmation_blocked",
                "message": "The selected backup changed after confirmation. No file was changed.",
                "confirm_id_status": "Backup changed",
                "apply_backup_checksum_sha256": latest_backup_sha,
                "confirmation_gate_result": "Blocked",
                "confirmation_gate_note": (
                    "The selected backup changed after the confirmation gate. Run preview mode again."
                ),
            }
        )
        for column in CONFIRMATION_REPORT_COLUMNS:
            preview[column] = str(summary[column])
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)

    resolved_timestamp = _safe_timestamp(timestamp)
    pre_rollback_backup = (
        current_odds_path.parent
        / "backups"
        / f"{resolved_timestamp}_current_odds_pre_stale_archive_rollback.csv"
    )
    if pre_rollback_backup.exists():
        raise FileExistsError(
            f"Pre-rollback backup `{pre_rollback_backup}` already exists. Rollback was not applied."
        )
    pre_rollback_backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current_odds_path, pre_rollback_backup)
    recovery_backup_checksum_sha256 = source_file_sha256(pre_rollback_backup)
    if recovery_backup_checksum_sha256 != current_sha:
        raise OSError("Pre-rollback backup verification failed. current_odds.csv was not replaced.")

    try:
        _replace_from_backup_atomic(selected_backup, current_odds_path)
        if source_file_sha256(current_odds_path) != backup_sha:
            raise OSError("Restored current_odds.csv did not match the selected backup.")
        restored, _, restored_error = _read_csv(
            current_odds_path,
            label="restored current odds file",
            allow_header_only=False,
            require_date=True,
        )
        if restored is None or not restored.equals(backup):
            raise OSError(restored_error or "Restored current_odds.csv did not match the selected backup data.")
    except Exception as exc:
        _replace_from_backup_atomic(pre_rollback_backup, current_odds_path)
        if source_file_sha256(current_odds_path) != current_sha:
            raise OSError(
                "Rollback failed and the pre-rollback backup could not be restored automatically. "
                f"Recovery backup: `{pre_rollback_backup}`. Original error: {exc}"
            ) from exc
        raise OSError(f"Rollback failed, so the pre-rollback backup was restored: {exc}") from exc

    resolved_applied_at = applied_at or datetime.now().astimezone().isoformat(timespec="seconds")
    resolved_rollback_id = rollback_id or f"stale-odds-rollback-{resolved_timestamp}-{uuid4().hex[:8]}"
    current_sha_after = source_file_sha256(current_odds_path)
    audit_row = pd.DataFrame(
        [
            {
                "rollback_id": resolved_rollback_id,
                "applied_at": resolved_applied_at,
                "status": "applied",
                "current_odds_path": str(current_odds_path),
                "selected_backup_path": str(selected_backup),
                "pre_rollback_backup_path": str(pre_rollback_backup),
                "current_sha256_before": current_sha,
                "selected_backup_sha256": backup_sha,
                "backup_checksum_sha256": backup_sha,
                "recovery_backup_checksum_sha256": recovery_backup_checksum_sha256,
                "checksum_status": summary["checksum_status"],
                "recorded_checksum_sha256": summary["recorded_checksum_sha256"],
                "current_checksum_sha256": summary["current_checksum_sha256"],
                "checksum_gate_result": summary["checksum_gate_result"],
                "checksum_gate_note": summary["checksum_gate_note"],
                "confirm_id": summary["confirm_id"],
                "confirm_id_status": summary["confirm_id_status"],
                "preview_current_checksum_sha256": summary[
                    "preview_current_checksum_sha256"
                ],
                "apply_current_checksum_sha256": summary["apply_current_checksum_sha256"],
                "preview_backup_checksum_sha256": summary["preview_backup_checksum_sha256"],
                "apply_backup_checksum_sha256": summary["apply_backup_checksum_sha256"],
                "confirmation_gate_result": summary["confirmation_gate_result"],
                "confirmation_gate_note": summary["confirmation_gate_note"],
                "current_sha256_after": current_sha_after,
                "current_rows_before": len(current),
                "backup_rows": len(backup),
                "rows_restored": int(summary["rows_restored"]),
                "rows_removed_or_replaced": int(summary["rows_removed_or_replaced"]),
                "unchanged_rows": int(summary["unchanged_rows"]),
                "rows_after": len(backup),
            }
        ],
        columns=AUDIT_COLUMNS,
    )
    try:
        paths.update(_save_audit(audit_row, existing_audit, output_dir))
    except Exception as exc:
        _replace_from_backup_atomic(pre_rollback_backup, current_odds_path)
        raise OSError(
            "Rollback audit could not be written, so the previous current_odds.csv was restored. "
            f"The recovery backup remains at `{pre_rollback_backup}`: {exc}"
            ) from exc

    if (
        summary["checksum_gate_result"] == "Override used"
        and summary["confirmation_gate_result"] == "Override used"
    ):
        applied_message = (
            "The selected pre-archive backup was restored with checksum and unconfirmed rollback "
            "overrides. WARNING: the backup may have changed, and apply did not match a reviewed preview."
        )
    elif summary["confirmation_gate_result"] == "Override used":
        applied_message = (
            "The selected pre-archive backup was restored with the unconfirmed rollback override. "
            "WARNING: apply did not match a reviewed preview."
        )
    elif summary["checksum_gate_result"] == "Override used":
        applied_message = (
            "The selected pre-archive backup was restored with an explicit checksum mismatch override. "
            "WARNING: the backup may have changed after creation."
        )
    elif summary["checksum_gate_result"] == "Allowed with warning":
        applied_message = (
            "The selected pre-archive backup was restored. WARNING: no audit checksum was available "
            "to confirm its original integrity."
        )
    else:
        applied_message = "The verified pre-archive backup was restored from Terminal."
    summary.update(
        {
            "status": "applied",
            "message": applied_message,
            "applied": True,
            "pre_rollback_backup_path": str(pre_rollback_backup),
            "rollback_id": resolved_rollback_id,
            "applied_at": resolved_applied_at,
        }
    )
    paths.update(
        save_stale_current_odds_archive_rollback_preview(
            preview,
            summary,
            output_dir,
        )
    )
    paths.update(
        {
            "status": "applied",
            "message": str(summary["message"]),
            "current_odds": current_odds_path,
            "selected_backup": selected_backup,
            "pre_rollback_backup": pre_rollback_backup,
            "rollback_id": resolved_rollback_id,
        }
    )
    return paths
