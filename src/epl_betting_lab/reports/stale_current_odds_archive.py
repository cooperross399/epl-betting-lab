from __future__ import annotations

from datetime import date, datetime
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
from epl_betting_lab.reports.stale_current_odds import (
    REPORT_COLUMNS,
    build_stale_current_odds_report,
)


CONFIRMATION_SCHEMA_VERSION = 1
CONFIRMATION_METADATA_FILENAME = "stale_current_odds_archive_preview.json"
CONFIRMATION_REPORT_COLUMNS = [
    "confirm_id",
    "confirm_id_status",
    "preview_current_checksum_sha256",
    "apply_current_checksum_sha256",
    "preview_stale_row_count",
    "apply_stale_row_count",
    "preview_keep_row_count",
    "apply_keep_row_count",
    "preview_manual_review_row_count",
    "apply_manual_review_row_count",
    "confirmation_gate_result",
    "confirmation_gate_note",
]
PREVIEW_COLUMNS = REPORT_COLUMNS + [
    "archive_action",
    "archive_reason",
    *CONFIRMATION_REPORT_COLUMNS,
]
LEGACY_AUDIT_COLUMNS = [
    "archive_id",
    "applied_at",
    "status",
    "current_odds_path",
    "source_sha256_before",
    "current_sha256_after",
    "backup_path",
    "stale_archive_path",
    "rows_before",
    "stale_rows_archived",
    "current_rows_kept",
    "date_fix_rows_kept",
    "rows_after",
]
AUDIT_CHECKSUM_COLUMNS = [
    "backup_checksum_sha256",
    "archive_file_checksum_sha256",
]
AUDIT_CONFIRMATION_COLUMNS = [*CONFIRMATION_REPORT_COLUMNS]
AUDIT_COLUMNS = [
    *LEGACY_AUDIT_COLUMNS[:8],
    *AUDIT_CHECKSUM_COLUMNS,
    *AUDIT_CONFIRMATION_COLUMNS,
    *LEGACY_AUDIT_COLUMNS[8:],
]
FATAL_SOURCE_STATUSES = {
    "Missing file": "missing_file",
    "Empty file": "empty_file",
    "Missing date column": "missing_date_column",
    "Unreadable file": "unreadable_file",
}


def _canonical_path(path: Path) -> str:
    try:
        return str(path.expanduser().resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return str(path.expanduser())


def _confirmation_payload(
    *,
    odds_path: Path,
    current_checksum: str,
    stale_row_count: int,
    keep_row_count: int,
    manual_review_row_count: int,
    generated_at: str,
) -> dict[str, object]:
    return {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "generated_at": generated_at,
        "current_odds_path": _canonical_path(odds_path),
        "preview_current_checksum_sha256": current_checksum,
        "preview_stale_row_count": stale_row_count,
        "preview_keep_row_count": keep_row_count,
        "preview_manual_review_row_count": manual_review_row_count,
    }


def _confirmation_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _build_confirmation_metadata(
    *,
    odds_path: Path,
    current_checksum: str,
    stale_row_count: int,
    keep_row_count: int,
    manual_review_row_count: int,
    generated_at: str | None = None,
) -> dict[str, object]:
    payload = _confirmation_payload(
        odds_path=odds_path,
        current_checksum=current_checksum,
        stale_row_count=stale_row_count,
        keep_row_count=keep_row_count,
        manual_review_row_count=manual_review_row_count,
        generated_at=generated_at or datetime.now().astimezone().isoformat(timespec="microseconds"),
    )
    return {**payload, "confirm_id": _confirmation_id(payload)}


def _error_confirmation_metadata(
    *,
    odds_path: Path,
    status: str,
) -> dict[str, object]:
    return {
        "schema_version": CONFIRMATION_SCHEMA_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="microseconds"),
        "current_odds_path": _canonical_path(odds_path),
        "preview_current_checksum_sha256": "",
        "preview_stale_row_count": 0,
        "preview_keep_row_count": 0,
        "preview_manual_review_row_count": 0,
        "confirm_id": "",
        "status": status,
    }


def load_stale_current_odds_archive_confirmation_metadata(
    metadata_path: Path,
) -> tuple[dict[str, object] | None, str, str]:
    """Load and validate an archive preview confirmation receipt."""
    if not metadata_path.exists():
        return (
            None,
            "Missing preview",
            "No stale-odds archive preview confirmation metadata exists. Run preview mode first.",
        )
    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return (
            None,
            "Invalid preview",
            f"Archive preview confirmation metadata is unreadable or malformed: {exc}",
        )
    if not isinstance(raw, dict):
        return None, "Invalid preview", "Archive preview confirmation metadata is not a JSON object."

    required = [
        "schema_version",
        "generated_at",
        "current_odds_path",
        "preview_current_checksum_sha256",
        "preview_stale_row_count",
        "preview_keep_row_count",
        "preview_manual_review_row_count",
        "confirm_id",
    ]
    missing = [field for field in required if field not in raw]
    if missing:
        return (
            None,
            "Invalid preview",
            "Archive preview confirmation metadata is missing: " + ", ".join(missing) + ".",
        )
    if raw.get("schema_version") != CONFIRMATION_SCHEMA_VERSION:
        return None, "Invalid preview", "Archive preview confirmation metadata uses an unsupported version."

    payload = {field: raw[field] for field in required if field != "confirm_id"}
    expected_id = _confirmation_id(payload)
    stored_id = str(raw.get("confirm_id", "")).strip()
    current_checksum = str(raw.get("preview_current_checksum_sha256", "")).strip()
    if not re.fullmatch(r"[0-9a-f]{64}", stored_id) or not compare_digest(stored_id, expected_id):
        return (
            None,
            "Invalid preview",
            "Archive preview confirmation metadata failed its own confirmation-ID check.",
        )
    if not re.fullmatch(r"[0-9a-f]{64}", current_checksum):
        return (
            None,
            "Invalid preview",
            "Archive preview confirmation metadata does not contain a valid current-odds checksum.",
        )
    for field in [
        "preview_stale_row_count",
        "preview_keep_row_count",
        "preview_manual_review_row_count",
    ]:
        value = raw.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return (
                None,
                "Invalid preview",
                f"Archive preview confirmation metadata contains an invalid `{field}` value.",
            )
    return raw, "Available", "The saved archive preview confirmation metadata is readable."


def _confirmation_gate(
    metadata: dict[str, object] | None,
    *,
    metadata_status: str,
    metadata_note: str,
    provided_confirm_id: str | None,
    odds_path: Path,
    apply_current_checksum: str,
    apply_stale_row_count: int,
    apply_keep_row_count: int,
    apply_manual_review_row_count: int,
    allow_unconfirmed: bool,
) -> dict[str, object]:
    preview_id = str(metadata.get("confirm_id", "")).strip() if metadata else ""
    preview_checksum = (
        str(metadata.get("preview_current_checksum_sha256", "")).strip() if metadata else ""
    )
    preview_stale = int(metadata.get("preview_stale_row_count", 0)) if metadata else 0
    preview_keep = int(metadata.get("preview_keep_row_count", 0)) if metadata else 0
    preview_manual = (
        int(metadata.get("preview_manual_review_row_count", 0)) if metadata else 0
    )
    supplied_id = str(provided_confirm_id or "").strip()

    if metadata is None:
        status = metadata_status
        note = metadata_note
    elif _canonical_path(odds_path) != str(metadata.get("current_odds_path", "")):
        status = "Current path mismatch"
        note = "The current_odds.csv path does not match the reviewed archive preview."
    elif apply_current_checksum != preview_checksum:
        status = "Current odds changed"
        note = "current_odds.csv changed after the reviewed preview. Run preview mode again."
    elif (
        apply_stale_row_count != preview_stale
        or apply_keep_row_count != preview_keep
        or apply_manual_review_row_count != preview_manual
    ):
        status = "Row counts changed"
        note = (
            "The stale, keep, or manual-review row counts changed after the reviewed preview. "
            "Run preview mode again."
        )
    elif not supplied_id:
        status = "Missing"
        note = "No confirmation ID was provided. Copy the exact apply command from the preview report."
    elif not re.fullmatch(r"[0-9a-f]{64}", supplied_id) or not compare_digest(
        supplied_id,
        preview_id,
    ):
        status = "Invalid"
        note = "The provided confirmation ID does not match the reviewed archive preview."
    else:
        return {
            "confirm_id": preview_id,
            "confirm_id_status": "Matched",
            "preview_current_checksum_sha256": preview_checksum,
            "apply_current_checksum_sha256": apply_current_checksum,
            "preview_stale_row_count": preview_stale,
            "apply_stale_row_count": apply_stale_row_count,
            "preview_keep_row_count": preview_keep,
            "apply_keep_row_count": apply_keep_row_count,
            "preview_manual_review_row_count": preview_manual,
            "apply_manual_review_row_count": apply_manual_review_row_count,
            "confirmation_gate_result": "Allowed",
            "confirmation_gate_note": (
                "The confirmation ID, current-odds path, checksum, and row counts match the reviewed preview."
            ),
        }

    if allow_unconfirmed:
        return {
            "confirm_id": preview_id or supplied_id,
            "confirm_id_status": "Override used",
            "preview_current_checksum_sha256": preview_checksum,
            "apply_current_checksum_sha256": apply_current_checksum,
            "preview_stale_row_count": preview_stale,
            "apply_stale_row_count": apply_stale_row_count,
            "preview_keep_row_count": preview_keep,
            "apply_keep_row_count": apply_keep_row_count,
            "preview_manual_review_row_count": preview_manual,
            "apply_manual_review_row_count": apply_manual_review_row_count,
            "confirmation_gate_result": "Override used",
            "confirmation_gate_note": (
                f"WARNING: {note} The explicit Terminal-only unconfirmed archive override was used, "
                "so apply did not match a reviewed preview."
            ),
        }
    return {
        "confirm_id": preview_id,
        "confirm_id_status": status,
        "preview_current_checksum_sha256": preview_checksum,
        "apply_current_checksum_sha256": apply_current_checksum,
        "preview_stale_row_count": preview_stale,
        "apply_stale_row_count": apply_stale_row_count,
        "preview_keep_row_count": preview_keep,
        "apply_keep_row_count": apply_keep_row_count,
        "preview_manual_review_row_count": preview_manual,
        "apply_manual_review_row_count": apply_manual_review_row_count,
        "confirmation_gate_result": "Blocked",
        "confirmation_gate_note": note,
    }


def _archive_action(freshness_status: object) -> str:
    status = str(freshness_status)
    if status == "Stale":
        return "Archive and remove"
    if status == "Current":
        return "Keep"
    return "Keep for manual review"


def _archive_reason(freshness_status: object) -> str:
    status = str(freshness_status)
    if status == "Stale":
        return "Match date is before today."
    if status == "Current":
        return "Match date is today or in the future."
    if status == "Blank date":
        return "Date is blank and must be fixed manually."
    return "Date could not be read and must be fixed manually."


def build_stale_current_odds_archive_preview(
    odds_path: Path | None = None,
    *,
    today: date | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build a row-level archive plan without changing the odds file."""
    path = odds_path or MANUAL_DIR / "current_odds.csv"
    report, stale_summary = build_stale_current_odds_report(path, today=today)
    preview = report.copy()
    if preview.empty:
        preview = pd.DataFrame(columns=PREVIEW_COLUMNS)
    else:
        preview["archive_action"] = preview["freshness_status"].map(_archive_action)
        preview["archive_reason"] = preview["freshness_status"].map(_archive_reason)
        preview = preview.reindex(columns=PREVIEW_COLUMNS).fillna("")

    source_status = str(stale_summary.get("status", "Not checked"))
    stale_rows = int(stale_summary.get("stale_rows", 0))
    current_rows = int(stale_summary.get("current_rows", 0))
    invalid_rows = int(stale_summary.get("invalid_date_rows", 0))
    blank_rows = int(stale_summary.get("blank_date_rows", 0))
    date_fix_rows = invalid_rows + blank_rows
    status = FATAL_SOURCE_STATUSES.get(source_status)
    if status is None:
        status = "preview_ready" if stale_rows else "no_stale_rows"

    if status == "preview_ready":
        message = (
            f"Preview ready: {stale_rows} stale row(s) would be archived and removed. "
            f"{current_rows + date_fix_rows} row(s) would stay in current_odds.csv."
        )
    elif status == "no_stale_rows":
        message = "No stale rows were found. Nothing needs to be archived or removed."
    else:
        message = str(stale_summary.get("message", "The current odds file could not be checked."))

    summary = {
        "status": status,
        "message": message,
        "source_status": source_status,
        "current_odds_path": str(path),
        "checked_date": stale_summary.get("checked_date", ""),
        "rows_before": int(stale_summary.get("total_rows", 0)),
        "stale_rows": stale_rows,
        "current_rows": current_rows,
        "invalid_date_rows": invalid_rows,
        "blank_date_rows": blank_rows,
        "date_fix_rows": date_fix_rows,
        "rows_kept": current_rows + date_fix_rows,
        "applied": False,
        "next_step": stale_summary.get("next_step", "Fix the source file, then preview again."),
    }
    return preview, summary


def render_stale_current_odds_archive_preview(
    preview: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    def apply_count(field: str) -> str:
        value = summary.get(field, "")
        return "Not checked in preview mode" if value in {"", None} else str(int(value))

    stale = preview[preview["freshness_status"] == "Stale"] if not preview.empty else preview
    current = preview[preview["freshness_status"] == "Current"] if not preview.empty else preview
    date_fixes = (
        preview[preview["freshness_status"].isin(["Invalid date", "Blank date"])]
        if not preview.empty
        else preview
    )
    lines = [
        "# Stale Current Odds Archive Preview",
        "",
        (
            "**Archive apply completed from Terminal. Review the apply audit before continuing.**"
            if summary.get("applied")
            else (
                "**Preview only: no input files were changed. Only preview CSV, markdown, and JSON "
                "metadata were written.**"
            )
        ),
        "",
        "This plan reads `data/manual/current_odds.csv`. It does not fetch or fabricate odds, place bets, or change model logic.",
        "",
        "## Summary",
        "",
        f"- Status: {summary.get('status', 'not_checked')}",
        f"- Current odds file: `{summary.get('current_odds_path', '')}`",
        f"- Date checked against: {summary.get('checked_date', '') or 'Not available'}",
        f"- Total rows: {int(summary.get('rows_before', 0))}",
        f"- Stale rows to archive/remove: {int(summary.get('stale_rows', 0))}",
        f"- Current rows to keep: {int(summary.get('current_rows', 0))}",
        f"- Invalid-date rows kept for manual review: {int(summary.get('invalid_date_rows', 0))}",
        f"- Blank-date rows kept for manual review: {int(summary.get('blank_date_rows', 0))}",
        f"- Message: {summary.get('message', '')}",
        "",
        "## Preview Confirmation Gate",
        "",
        f"- Confirmation ID: `{summary.get('confirm_id', '') or 'Not available'}`",
        f"- Confirmation ID status: {summary.get('confirm_id_status', 'Not available')}",
        "- Preview current odds checksum: "
        f"`{summary.get('preview_current_checksum_sha256', '') or 'Not available'}`",
        "- Apply current odds checksum: "
        f"`{summary.get('apply_current_checksum_sha256', '') or 'Not checked in preview mode'}`",
        f"- Preview stale rows: {int(summary.get('preview_stale_row_count', 0))}",
        f"- Apply stale rows: {apply_count('apply_stale_row_count')}",
        f"- Preview current rows to keep: {int(summary.get('preview_keep_row_count', 0))}",
        f"- Apply current rows to keep: {apply_count('apply_keep_row_count')}",
        "- Preview manual-review rows: "
        f"{int(summary.get('preview_manual_review_row_count', 0))}",
        f"- Apply manual-review rows: {apply_count('apply_manual_review_row_count')}",
        f"- Gate result: {summary.get('confirmation_gate_result', 'Not checked')}",
        "- Gate note: "
        f"{summary.get('confirmation_gate_note', '') or 'Preview confirmation was not checked.'}",
        "",
        "## Rows To Archive And Remove",
        "",
        stale.to_markdown(index=False) if not stale.empty else "No stale rows found.",
        "",
        "## Current Rows To Keep",
        "",
        current.to_markdown(index=False) if not current.empty else "No today/future rows found.",
        "",
        "## Date Rows Kept For Manual Fixing",
        "",
        date_fixes.to_markdown(index=False) if not date_fixes.empty else "No blank or invalid dates found.",
        "",
        "## Next Step",
        "",
    ]
    if summary.get("status") == "applied":
        lines.append("Archive apply completed. Review the audit and keep the backup path for recovery.")
    elif summary.get("status") == "confirmation_blocked":
        lines.append(
            "Archive apply was blocked before any backup or archive file was created. "
            "Run preview mode again, review it, then copy its exact apply command."
        )
    elif summary.get("status") == "preview_ready":
        confirm_id = str(summary.get("confirm_id", "")).strip()
        lines.extend(
            [
                "Review every row above. Then copy and run this exact Terminal command:",
                "",
                "```bash",
                (
                    "python scripts/archive_stale_current_odds.py "
                    f"--apply --confirm-id {shlex.quote(confirm_id)}"
                    if confirm_id
                    else "Run preview again to create a confirmation ID."
                ),
                "```",
            ]
        )
    elif summary.get("status") == "no_stale_rows":
        lines.append("No apply action is needed because there are no stale rows.")
    else:
        lines.append(str(summary.get("next_step", "Fix the source file, then run preview again.")))
    return "\n".join(lines)


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


def save_stale_current_odds_archive_preview(
    preview: pd.DataFrame,
    summary: dict[str, object],
    output_dir: Path | None = None,
    *,
    confirmation_metadata: dict[str, object] | None = None,
) -> dict[str, Path | str]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "stale_current_odds_archive_preview.csv"
    markdown_path = output_dir / "stale_current_odds_archive_preview.md"
    metadata_path = output_dir / CONFIRMATION_METADATA_FILENAME
    preview.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_stale_current_odds_archive_preview(preview, summary),
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
    for column in CONFIRMATION_REPORT_COLUMNS:
        result[column] = str(summary.get(column, ""))
    return result


def _safe_timestamp(timestamp: str | None = None) -> str:
    value = timestamp or datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S")
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Archive timestamp may contain only letters, numbers, hyphens, and underscores.")
    return value


def _write_csv_atomic(frame: pd.DataFrame, path: Path, *, overwrite: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file `{path}`.")
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
        if not overwrite and path.exists():
            raise FileExistsError(f"Refusing to overwrite existing file `{path}`.")
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _load_existing_audit(output_dir: Path) -> pd.DataFrame:
    audit_path = output_dir / "stale_current_odds_archive_audit.csv"
    if not audit_path.exists():
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    try:
        audit = pd.read_csv(audit_path, dtype=str, keep_default_na=False)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ValueError(f"Existing stale-odds archive audit is unreadable and was not overwritten: {exc}") from exc
    missing = [column for column in LEGACY_AUDIT_COLUMNS if column not in audit.columns]
    if missing:
        raise ValueError(
            "Existing stale-odds archive audit is missing required columns and was not overwritten: "
            f"{', '.join(missing)}."
        )
    for column in [*AUDIT_CHECKSUM_COLUMNS, *AUDIT_CONFIRMATION_COLUMNS]:
        if column not in audit.columns:
            audit[column] = ""
    return audit[AUDIT_COLUMNS]


def render_stale_current_odds_archive_audit(audit: pd.DataFrame) -> str:
    lines = [
        "# Stale Current Odds Archive Audit",
        "",
        "This history records explicit Terminal apply operations. Dashboard previews never create audit entries or edit odds.",
        "",
    ]
    if audit.empty:
        lines.append("No stale current-odds archive operations have been applied.")
        return "\n".join(lines)

    latest = audit.iloc[-1]
    confirmation_warning = (
        "**WARNING: This archive apply used the unconfirmed archive override and did not match a "
        "reviewed preview.**"
        if latest["confirmation_gate_result"] == "Override used"
        else ""
    )
    lines.extend(
        [
            "## Latest Apply",
            "",
            *([confirmation_warning, ""] if confirmation_warning else []),
            f"- Archive ID: `{latest['archive_id']}`",
            f"- Applied at: {latest['applied_at']}",
            f"- Stale rows archived: {latest['stale_rows_archived']}",
            f"- Current rows kept: {latest['current_rows_kept']}",
            f"- Date-fix rows kept: {latest['date_fix_rows_kept']}",
            f"- Backup: `{latest['backup_path']}`",
            f"- Backup SHA-256: `{latest['backup_checksum_sha256'] or 'Not recorded'}`",
            f"- Stale-row archive: `{latest['stale_archive_path']}`",
            f"- Stale-row archive SHA-256: `{latest['archive_file_checksum_sha256'] or 'Not recorded'}`",
            f"- Preview confirmation ID: `{latest['confirm_id'] or 'Not recorded'}`",
            f"- Confirmation ID status: {latest['confirm_id_status'] or 'Not recorded'}",
            "- Preview current odds checksum: "
            f"`{latest['preview_current_checksum_sha256'] or 'Not recorded'}`",
            "- Apply current odds checksum: "
            f"`{latest['apply_current_checksum_sha256'] or 'Not recorded'}`",
            f"- Preview/apply stale rows: {latest['preview_stale_row_count'] or 'Not recorded'} / "
            f"{latest['apply_stale_row_count'] or 'Not recorded'}",
            f"- Preview/apply current rows to keep: {latest['preview_keep_row_count'] or 'Not recorded'} / "
            f"{latest['apply_keep_row_count'] or 'Not recorded'}",
            "- Preview/apply manual-review rows: "
            f"{latest['preview_manual_review_row_count'] or 'Not recorded'} / "
            f"{latest['apply_manual_review_row_count'] or 'Not recorded'}",
            f"- Confirmation gate: {latest['confirmation_gate_result'] or 'Not recorded'}",
            f"- Confirmation gate note: {latest['confirmation_gate_note'] or 'Not recorded'}",
            "",
            "## Apply History",
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
    csv_path = output_dir / "stale_current_odds_archive_audit.csv"
    markdown_path = output_dir / "stale_current_odds_archive_audit.md"
    _write_csv_atomic(audit, csv_path)
    markdown_path.write_text(render_stale_current_odds_archive_audit(audit), encoding="utf-8")
    return {"audit_csv": csv_path, "audit_markdown": markdown_path}


def archive_stale_current_odds(
    odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    apply: bool = False,
    confirm_id: str | None = None,
    allow_unconfirmed_archive: bool = False,
    today: date | None = None,
    timestamp: str | None = None,
    archive_id: str | None = None,
    applied_at: str | None = None,
) -> dict[str, Path | str]:
    """Preview stale-row archiving, or apply it explicitly with recovery files."""
    odds_path = odds_path or MANUAL_DIR / "current_odds.csv"
    output_dir = output_dir or OUTPUTS_DIR
    source_sha_before = source_file_sha256(odds_path)
    preview, summary = build_stale_current_odds_archive_preview(odds_path, today=today)
    confirmation_metadata: dict[str, object] | None = None
    if apply:
        stored_metadata, metadata_status, metadata_note = (
            load_stale_current_odds_archive_confirmation_metadata(
                output_dir / CONFIRMATION_METADATA_FILENAME
            )
        )
        confirmation_fields = _confirmation_gate(
            stored_metadata,
            metadata_status=metadata_status,
            metadata_note=metadata_note,
            provided_confirm_id=confirm_id,
            odds_path=odds_path,
            apply_current_checksum=source_sha_before,
            apply_stale_row_count=int(summary.get("stale_rows", 0)),
            apply_keep_row_count=int(summary.get("current_rows", 0)),
            apply_manual_review_row_count=int(summary.get("date_fix_rows", 0)),
            allow_unconfirmed=allow_unconfirmed_archive,
        )
    elif source_sha_before and summary["status"] in {"preview_ready", "no_stale_rows"}:
        confirmation_metadata = _build_confirmation_metadata(
            odds_path=odds_path,
            current_checksum=source_sha_before,
            stale_row_count=int(summary.get("stale_rows", 0)),
            keep_row_count=int(summary.get("current_rows", 0)),
            manual_review_row_count=int(summary.get("date_fix_rows", 0)),
        )
        confirmation_fields = {
            "confirm_id": str(confirmation_metadata["confirm_id"]),
            "confirm_id_status": (
                "Preview ready" if summary["status"] == "preview_ready" else "No archive needed"
            ),
            "preview_current_checksum_sha256": source_sha_before,
            "apply_current_checksum_sha256": "",
            "preview_stale_row_count": int(summary.get("stale_rows", 0)),
            "apply_stale_row_count": "",
            "preview_keep_row_count": int(summary.get("current_rows", 0)),
            "apply_keep_row_count": "",
            "preview_manual_review_row_count": int(summary.get("date_fix_rows", 0)),
            "apply_manual_review_row_count": "",
            "confirmation_gate_result": (
                "Preview ready" if summary["status"] == "preview_ready" else "Not needed"
            ),
            "confirmation_gate_note": (
                "Review this preview, then use its confirmation ID in the exact Terminal apply command."
                if summary["status"] == "preview_ready"
                else "No stale rows were found, so archive apply is not needed."
            ),
        }
    else:
        confirmation_metadata = _error_confirmation_metadata(
            odds_path=odds_path,
            status=str(summary.get("status", "not_checked")),
        )
        confirmation_fields = {
            "confirm_id": "",
            "confirm_id_status": "Not available",
            "preview_current_checksum_sha256": "",
            "apply_current_checksum_sha256": "",
            "preview_stale_row_count": int(summary.get("stale_rows", 0)),
            "apply_stale_row_count": "",
            "preview_keep_row_count": int(summary.get("current_rows", 0)),
            "apply_keep_row_count": "",
            "preview_manual_review_row_count": int(summary.get("date_fix_rows", 0)),
            "apply_manual_review_row_count": "",
            "confirmation_gate_result": "Not checked",
            "confirmation_gate_note": (
                "Preview confirmation was not created because current_odds.csv could not be checked safely."
            ),
        }
    summary.update(confirmation_fields)
    for column in CONFIRMATION_REPORT_COLUMNS:
        preview[column] = summary[column]
    if (
        apply
        and summary["status"] == "preview_ready"
        and summary["confirmation_gate_result"] == "Blocked"
    ):
        summary["status"] = "confirmation_blocked"
        summary["message"] = (
            "Archive apply was blocked because the confirmation ID or previewed current-odds state "
            "did not match. Run preview mode again and copy its exact apply command."
        )
    paths = save_stale_current_odds_archive_preview(
        preview,
        summary,
        output_dir,
        confirmation_metadata=confirmation_metadata,
    )
    if not apply or summary["status"] != "preview_ready":
        return paths
    if not source_sha_before:
        raise OSError("Current odds could not be checksummed safely. No stale rows were removed.")

    existing_audit = _load_existing_audit(output_dir)
    try:
        source = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ValueError(f"Current odds became unreadable before apply. No stale rows were removed: {exc}") from exc
    if len(source) != len(preview):
        raise ValueError("Current odds changed after preview. No stale rows were removed; run preview again.")
    if source_file_sha256(odds_path) != source_sha_before:
        raise ValueError("Current odds changed during preview. No stale rows were removed; run preview again.")

    stale_positions = [
        position
        for position, status in enumerate(preview["freshness_status"].astype(str))
        if status == "Stale"
    ]
    stale_rows = source.iloc[stale_positions].copy()
    kept_rows = source.drop(index=source.index[stale_positions]).reset_index(drop=True)
    if stale_rows.empty:
        return paths

    resolved_timestamp = _safe_timestamp(timestamp)
    backup_dir = odds_path.parent / "backups"
    stale_archive_dir = odds_path.parent / "archive" / "current_odds_stale"
    backup_path = backup_dir / f"{resolved_timestamp}_current_odds_pre_stale_archive.csv"
    stale_archive_path = stale_archive_dir / f"{resolved_timestamp}_current_odds_stale.csv"
    if backup_path.exists() or stale_archive_path.exists():
        raise FileExistsError(
            "Backup or stale archive path already exists. No rows were removed; run again with a new timestamp."
        )

    backup_dir.mkdir(parents=True, exist_ok=True)
    stale_archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(odds_path, backup_path)
    backup_checksum_sha256 = source_file_sha256(backup_path)
    if backup_checksum_sha256 != source_sha_before:
        raise OSError("Backup verification failed. No stale rows were removed from current_odds.csv.")

    _write_csv_atomic(stale_rows, stale_archive_path, overwrite=False)
    try:
        archived = pd.read_csv(stale_archive_path, dtype=str, keep_default_na=False)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise OSError(f"Stale archive verification failed. Current odds were not changed: {exc}") from exc
    expected_archive = stale_rows.reset_index(drop=True)
    if archived.columns.tolist() != source.columns.tolist() or not archived.equals(expected_archive):
        raise OSError("Stale archive verification failed. Current odds were not changed.")
    archive_file_checksum_sha256 = source_file_sha256(stale_archive_path)
    if not archive_file_checksum_sha256:
        raise OSError("Stale archive checksum failed. Current odds were not changed.")
    if source_file_sha256(odds_path) != source_sha_before:
        raise ValueError("Current odds changed before replacement. The backup and archive remain; no rows were removed.")

    _write_csv_atomic(kept_rows, odds_path)
    try:
        rewritten = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        shutil.copy2(backup_path, odds_path)
        raise OSError(f"Current odds verification failed and the backup was restored: {exc}") from exc
    if rewritten.columns.tolist() != kept_rows.columns.tolist() or not rewritten.equals(kept_rows):
        shutil.copy2(backup_path, odds_path)
        raise OSError("Current odds verification failed and the backup was restored.")
    current_sha_after = source_file_sha256(odds_path)
    applied_at = applied_at or datetime.now().astimezone().isoformat(timespec="seconds")
    archive_id = archive_id or f"stale-odds-{resolved_timestamp}-{uuid4().hex[:8]}"
    date_fix_rows = int(summary.get("date_fix_rows", 0))
    audit_row = pd.DataFrame(
        [
            {
                "archive_id": archive_id,
                "applied_at": applied_at,
                "status": "applied",
                "current_odds_path": str(odds_path),
                "source_sha256_before": source_sha_before,
                "current_sha256_after": current_sha_after,
                "backup_path": str(backup_path),
                "stale_archive_path": str(stale_archive_path),
                "backup_checksum_sha256": backup_checksum_sha256,
                "archive_file_checksum_sha256": archive_file_checksum_sha256,
                "confirm_id": summary["confirm_id"],
                "confirm_id_status": summary["confirm_id_status"],
                "preview_current_checksum_sha256": summary[
                    "preview_current_checksum_sha256"
                ],
                "apply_current_checksum_sha256": summary["apply_current_checksum_sha256"],
                "preview_stale_row_count": summary["preview_stale_row_count"],
                "apply_stale_row_count": summary["apply_stale_row_count"],
                "preview_keep_row_count": summary["preview_keep_row_count"],
                "apply_keep_row_count": summary["apply_keep_row_count"],
                "preview_manual_review_row_count": summary[
                    "preview_manual_review_row_count"
                ],
                "apply_manual_review_row_count": summary[
                    "apply_manual_review_row_count"
                ],
                "confirmation_gate_result": summary["confirmation_gate_result"],
                "confirmation_gate_note": summary["confirmation_gate_note"],
                "rows_before": len(source),
                "stale_rows_archived": len(stale_rows),
                "current_rows_kept": int(summary.get("current_rows", 0)),
                "date_fix_rows_kept": date_fix_rows,
                "rows_after": len(kept_rows),
            }
        ],
        columns=AUDIT_COLUMNS,
    )
    paths.update(_save_audit(audit_row, existing_audit, output_dir))
    if summary["confirmation_gate_result"] == "Override used":
        applied_message = (
            f"Archived {len(stale_rows)} stale row(s) with the unconfirmed archive override. "
            "WARNING: apply did not match a reviewed preview."
        )
    else:
        applied_message = (
            f"Archived {len(stale_rows)} stale row(s). "
            f"Kept {len(kept_rows)} row(s) in current_odds.csv."
        )
    summary.update(
        {
            "status": "applied",
            "message": applied_message,
            "applied": True,
        }
    )
    paths.update(save_stale_current_odds_archive_preview(preview, summary, output_dir))
    paths.update(
        {
            "status": "applied",
            "message": applied_message,
            "backup": backup_path,
            "stale_archive": stale_archive_path,
            "current_odds": odds_path,
            "archive_id": archive_id,
        }
    )
    return paths
