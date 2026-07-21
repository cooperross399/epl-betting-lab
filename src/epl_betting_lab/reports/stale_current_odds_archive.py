from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
import re
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


PREVIEW_COLUMNS = REPORT_COLUMNS + ["archive_action", "archive_reason"]
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
AUDIT_COLUMNS = [
    *LEGACY_AUDIT_COLUMNS[:8],
    *AUDIT_CHECKSUM_COLUMNS,
    *LEGACY_AUDIT_COLUMNS[8:],
]
FATAL_SOURCE_STATUSES = {
    "Missing file": "missing_file",
    "Empty file": "empty_file",
    "Missing date column": "missing_date_column",
    "Unreadable file": "unreadable_file",
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
        preview = preview.reindex(columns=PREVIEW_COLUMNS)

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
        "next_step": stale_summary.get("next_step", "Fix the source file, then preview again."),
    }
    return preview, summary


def render_stale_current_odds_archive_preview(
    preview: pd.DataFrame,
    summary: dict[str, object],
) -> str:
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
        "**Preview only: no input files were changed. Only the preview CSV and markdown were written.**",
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
    if summary.get("status") == "preview_ready":
        lines.append(
            "Review every row above. Apply only from Terminal with "
            "`python scripts/archive_stale_current_odds.py --apply`."
        )
    elif summary.get("status") == "no_stale_rows":
        lines.append("No apply action is needed because there are no stale rows.")
    else:
        lines.append(str(summary.get("next_step", "Fix the source file, then run preview again.")))
    return "\n".join(lines)


def save_stale_current_odds_archive_preview(
    preview: pd.DataFrame,
    summary: dict[str, object],
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "stale_current_odds_archive_preview.csv"
    markdown_path = output_dir / "stale_current_odds_archive_preview.md"
    preview.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_stale_current_odds_archive_preview(preview, summary),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "status": str(summary.get("status", "not_checked")),
        "message": str(summary.get("message", "")),
    }


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
    for column in AUDIT_CHECKSUM_COLUMNS:
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
    lines.extend(
        [
            "## Latest Apply",
            "",
            f"- Archive ID: `{latest['archive_id']}`",
            f"- Applied at: {latest['applied_at']}",
            f"- Stale rows archived: {latest['stale_rows_archived']}",
            f"- Current rows kept: {latest['current_rows_kept']}",
            f"- Date-fix rows kept: {latest['date_fix_rows_kept']}",
            f"- Backup: `{latest['backup_path']}`",
            f"- Backup SHA-256: `{latest['backup_checksum_sha256'] or 'Not recorded'}`",
            f"- Stale-row archive: `{latest['stale_archive_path']}`",
            f"- Stale-row archive SHA-256: `{latest['archive_file_checksum_sha256'] or 'Not recorded'}`",
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
    paths = save_stale_current_odds_archive_preview(preview, summary, output_dir)
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
    paths.update(
        {
            "status": "applied",
            "message": (
                f"Archived {len(stale_rows)} stale row(s). Kept {len(kept_rows)} row(s) in current_odds.csv."
            ),
            "backup": backup_path,
            "stale_archive": stale_archive_path,
            "current_odds": odds_path,
            "archive_id": archive_id,
        }
    )
    return paths
