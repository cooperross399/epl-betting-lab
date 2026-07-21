from __future__ import annotations

from collections import Counter
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
from tempfile import NamedTemporaryFile
from uuid import uuid4

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256


DEFAULT_CURRENT_ODDS_PATH = MANUAL_DIR / "current_odds.csv"
PREVIEW_PREFIX_COLUMNS = [
    "rollback_action",
    "rollback_reason",
    "source_file",
    "source_row_number",
]
AUDIT_COLUMNS = [
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
    elif summary.get("status") == "preview_ready":
        lines.append(
            "Review the differences above. Apply only from Terminal with "
            "`python scripts/rollback_stale_current_odds_archive.py --backup-path PATH --apply`."
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


def save_stale_current_odds_archive_rollback_preview(
    preview: pd.DataFrame,
    summary: dict[str, object],
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "stale_current_odds_archive_rollback_preview.csv"
    markdown_path = output_dir / "stale_current_odds_archive_rollback_preview.md"
    _write_csv_atomic(preview, csv_path)
    markdown_path.write_text(
        render_stale_current_odds_archive_rollback_preview(preview, summary),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "status": str(summary.get("status", "not_checked")),
        "message": str(summary.get("message", "")),
    }


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
    missing = [column for column in AUDIT_COLUMNS if column not in audit.columns]
    if missing:
        raise ValueError(
            "Existing stale-odds rollback audit is missing required columns and was not overwritten: "
            f"{', '.join(missing)}."
        )
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
    lines.extend(
        [
            "## Latest Rollback",
            "",
            f"- Rollback ID: `{latest['rollback_id']}`",
            f"- Applied at: {latest['applied_at']}",
            f"- Selected backup: `{latest['selected_backup_path']}`",
            f"- Pre-rollback backup: `{latest['pre_rollback_backup_path']}`",
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

    if selected_backup is None:
        preview, summary = _error_preview(
            "missing_backup_path",
            "Choose a pre-archive CSV backup path before previewing rollback.",
            current_odds_path=current_odds_path,
            backup_path=None,
        )
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
    if not current_odds_path.exists() or not current_odds_path.is_file():
        preview, summary = _error_preview(
            "missing_current_odds",
            f"Missing current odds file `{current_odds_path}`. Nothing was restored.",
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
        )
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
    if selected_backup.suffix.lower() != ".csv":
        preview, summary = _error_preview(
            "invalid_backup_path",
            f"Selected backup `{selected_backup}` must be a CSV file.",
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
        )
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
    if not selected_backup.exists() or not selected_backup.is_file():
        preview, summary = _error_preview(
            "missing_backup_path",
            f"Selected backup `{selected_backup}` does not exist or is not a file.",
            current_odds_path=current_odds_path,
            backup_path=selected_backup,
        )
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
    try:
        if current_odds_path.resolve() == selected_backup.resolve():
            preview, summary = _error_preview(
                "backup_equals_current",
                "The selected backup is current_odds.csv itself. Choose a separate pre-archive backup.",
                current_odds_path=current_odds_path,
                backup_path=selected_backup,
            )
            return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
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
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
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
        return save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)

    preview, summary = build_stale_current_odds_archive_rollback_preview(
        current,
        backup,
        current_odds_path=current_odds_path,
        backup_path=selected_backup,
    )
    paths = save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir)
    if not apply or summary["status"] != "preview_ready":
        return paths

    existing_audit = _load_existing_audit(output_dir)
    current_sha = str(summary["current_sha256_before"])
    backup_sha = str(summary["selected_backup_sha256"])
    if not current_sha or source_file_sha256(current_odds_path) != current_sha:
        raise ValueError("Current odds changed after preview. Rollback was not applied; run preview again.")
    if not backup_sha or source_file_sha256(selected_backup) != backup_sha:
        raise ValueError("The selected backup changed after preview. Rollback was not applied; run preview again.")

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
    if source_file_sha256(pre_rollback_backup) != current_sha:
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

    summary.update(
        {
            "status": "applied",
            "message": "The selected pre-archive backup was restored from Terminal.",
            "applied": True,
            "pre_rollback_backup_path": str(pre_rollback_backup),
            "rollback_id": resolved_rollback_id,
            "applied_at": resolved_applied_at,
        }
    )
    paths.update(save_stale_current_odds_archive_rollback_preview(preview, summary, output_dir))
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
