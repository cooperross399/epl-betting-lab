from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256
from epl_betting_lab.reports.stale_current_odds import build_stale_current_odds_report


DEFAULT_BACKUPS_DIR = MANUAL_DIR / "backups"
DEFAULT_ARCHIVE_AUDIT_PATH = OUTPUTS_DIR / "stale_current_odds_archive_audit.csv"
DEFAULT_ROLLBACK_AUDIT_PATH = OUTPUTS_DIR / "stale_current_odds_archive_rollback_audit.csv"
BACKUP_SUFFIXES = {
    "_current_odds_pre_stale_archive_rollback.csv": "Pre-rollback recovery",
    "_current_odds_pre_stale_archive.csv": "Pre-archive",
}
BACKUP_PATTERNS = [f"*{suffix}" for suffix in BACKUP_SUFFIXES]
BACKUP_LIST_COLUMNS = [
    "backup_path",
    "backup_type",
    "created_by_operation",
    "audit_timestamp",
    "audit_file_path",
    "audit_markdown_path",
    "archive_file_path",
    "rows_archived",
    "rows_restored",
    "rows_replaced",
    "operation_status",
    "audit_note",
    "recorded_checksum_sha256",
    "current_checksum_sha256",
    "checksum_status",
    "checksum_note",
    "filename_timestamp",
    "filename_status",
    "file_modified_at",
    "row_count",
    "earliest_odds_date",
    "latest_odds_date",
    "stale_rows",
    "current_rows",
    "invalid_date_rows",
    "blank_date_rows",
    "readable",
    "valid",
    "status",
    "message",
]
TIMESTAMP_FORMATS = [
    "%Y-%m-%d_%H%M%S_%f",
    "%Y-%m-%d_%H%M%S",
    "%Y%m%d_%H%M%S_%f",
    "%Y%m%d_%H%M%S",
]


def _empty_backup_list() -> pd.DataFrame:
    return pd.DataFrame(columns=BACKUP_LIST_COLUMNS)


def _filename_details(path: Path) -> tuple[str, str, str]:
    backup_type = "Unknown backup type"
    timestamp_text = ""
    for suffix, kind in BACKUP_SUFFIXES.items():
        if path.name.endswith(suffix):
            backup_type = kind
            timestamp_text = path.name.removesuffix(suffix)
            break

    for timestamp_format in TIMESTAMP_FORMATS:
        try:
            parsed = datetime.strptime(timestamp_text, timestamp_format)
        except ValueError:
            continue
        return backup_type, parsed.isoformat(timespec="seconds"), "Parsed"
    return backup_type, "", "Malformed filename timestamp"


def _modified_time(path: Path) -> tuple[str, str]:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    except OSError as exc:
        return "", f"File modified time could not be read: {exc}"
    return modified.isoformat(timespec="seconds"), ""


def _base_record(path: Path) -> dict[str, object]:
    backup_type, filename_timestamp, filename_status = _filename_details(path)
    modified_at, modified_error = _modified_time(path)
    return {
        "backup_path": str(path),
        "backup_type": backup_type,
        "created_by_operation": "unknown",
        "audit_timestamp": "",
        "audit_file_path": "",
        "audit_markdown_path": "",
        "archive_file_path": "",
        "rows_archived": "",
        "rows_restored": "",
        "rows_replaced": "",
        "operation_status": "",
        "audit_note": "Audit history has not been checked yet.",
        "recorded_checksum_sha256": "",
        "current_checksum_sha256": source_file_sha256(path),
        "checksum_status": "Not available",
        "checksum_note": "No linked audit checksum is available yet.",
        "filename_timestamp": filename_timestamp,
        "filename_status": filename_status,
        "file_modified_at": modified_at,
        "row_count": 0,
        "earliest_odds_date": "",
        "latest_odds_date": "",
        "stale_rows": 0,
        "current_rows": 0,
        "invalid_date_rows": 0,
        "blank_date_rows": 0,
        "readable": "No",
        "valid": "No",
        "status": "Not checked",
        "message": modified_error,
    }


def _inspect_backup(path: Path, *, today: date) -> dict[str, object]:
    record = _base_record(path)
    try:
        backup = pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        record.update(
            {
                "readable": "Yes",
                "status": "Empty backup",
                "message": "The backup file is empty and cannot be selected for rollback.",
            }
        )
        return record
    except pd.errors.ParserError as exc:
        record.update(
            {
                "status": "Malformed CSV",
                "message": f"The backup CSV is malformed and cannot be selected: {exc}",
            }
        )
        return record
    except (OSError, UnicodeError) as exc:
        record.update(
            {
                "status": "Unreadable backup",
                "message": f"The backup could not be read and cannot be selected: {exc}",
            }
        )
        return record

    record["readable"] = "Yes"
    record["row_count"] = len(backup)
    if backup.empty:
        record.update(
            {
                "status": "Empty backup",
                "message": "The backup contains column headers but no odds rows.",
            }
        )
        return record
    if "date" not in backup.columns:
        record.update(
            {
                "status": "Missing date column",
                "message": "The backup is readable but is missing the required `date` column.",
            }
        )
        return record

    _, date_summary = build_stale_current_odds_report(path, today=today)
    if date_summary.get("status") != "Checked":
        record.update(
            {
                "valid": "No",
                "status": "Unreadable backup",
                "message": str(
                    date_summary.get(
                        "message",
                        "The backup changed while it was being checked. Refresh the list and try again.",
                    )
                ),
            }
        )
        return record
    record.update(
        {
            "earliest_odds_date": date_summary.get("earliest_odds_date", ""),
            "latest_odds_date": date_summary.get("latest_odds_date", ""),
            "stale_rows": int(date_summary.get("stale_rows", 0)),
            "current_rows": int(date_summary.get("current_rows", 0)),
            "invalid_date_rows": int(date_summary.get("invalid_date_rows", 0)),
            "blank_date_rows": int(date_summary.get("blank_date_rows", 0)),
            "valid": "Yes",
            "status": "Ready",
            "message": "This backup is readable and can be selected for rollback preview.",
        }
    )
    if record["filename_status"] != "Parsed":
        record["message"] = (
            "The backup is readable, but its filename timestamp could not be parsed. "
            "Use the file modified time and review the path carefully."
        )
    return record


def _canonical_path(path_value: object) -> str:
    text = str(path_value).strip()
    if not text:
        return ""
    try:
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return ""


def _read_audit_markdown(audit_path: Path) -> tuple[str, str]:
    markdown_path = audit_path.with_suffix(".md")
    if not markdown_path.exists():
        return "", ""
    try:
        markdown_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return "", f"Audit markdown `{markdown_path}` is unreadable: {exc}"
    return str(markdown_path), ""


def _audit_text(row: pd.Series, column: str) -> str:
    if column not in row.index:
        return ""
    return str(row[column]).strip()


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(value).strip()))


def _audit_checksum(row: pd.Series, *columns: str) -> str:
    values = [_audit_text(row, column) for column in columns]
    values = [value for value in values if value]
    for value in values:
        if _is_sha256(value):
            return value.lower()
    return values[0] if values else ""


def _checksum_verification(
    recorded_checksum: object,
    current_checksum: object,
    operation: object,
) -> tuple[str, str]:
    recorded = str(recorded_checksum).strip()
    current = str(current_checksum).strip()
    creator = str(operation).strip()
    if not recorded:
        if creator == "unknown":
            return "Not available", "No linked audit checksum is available for this backup."
        return (
            "Not available",
            "The linked audit does not contain a usable backup checksum. Older audit rows may predate "
            "checksum recording.",
        )
    if not _is_sha256(recorded):
        return "Not available", "The recorded audit checksum is malformed and cannot be verified."
    if not _is_sha256(current):
        return "Not available", "The backup file could not be checksummed, so its integrity is not confirmed."
    if recorded.lower() == current.lower():
        return "Verified", "The backup matches the SHA-256 checksum recorded when it was created."
    return (
        "Mismatch",
        "The backup no longer matches its recorded SHA-256 checksum. Do not trust it for rollback "
        "unless it is manually inspected.",
    )


def _audit_link(
    row: pd.Series,
    *,
    operation: str,
    audit_path: Path,
    audit_markdown_path: str,
) -> dict[str, object]:
    if operation == "archive_apply":
        operation_id = _audit_text(row, "archive_id") or "ID not recorded"
        note = f"Archive apply `{operation_id}` created this pre-archive backup."
        archive_file_path = _audit_text(row, "stale_archive_path")
        rows_archived = _audit_text(row, "stale_rows_archived")
        rows_restored = ""
        rows_replaced = ""
        recorded_checksum = _audit_checksum(
            row,
            "backup_checksum_sha256",
            "source_sha256_before",
        )
    else:
        operation_id = _audit_text(row, "rollback_id") or "ID not recorded"
        note = (
            f"Rollback apply `{operation_id}` created this recovery backup before restoring "
            "the selected older file."
        )
        archive_file_path = ""
        rows_archived = ""
        rows_restored = _audit_text(row, "rows_restored")
        rows_replaced = _audit_text(row, "rows_removed_or_replaced")
        recorded_checksum = _audit_checksum(
            row,
            "recovery_backup_checksum_sha256",
            "current_sha256_before",
        )

    audit_timestamp = _audit_text(row, "applied_at")
    if not audit_timestamp:
        note = f"{note} The audit timestamp was not recorded."
    return {
        "created_by_operation": operation,
        "audit_timestamp": audit_timestamp,
        "audit_file_path": str(audit_path),
        "audit_markdown_path": audit_markdown_path,
        "archive_file_path": archive_file_path,
        "rows_archived": rows_archived,
        "rows_restored": rows_restored,
        "rows_replaced": rows_replaced,
        "operation_status": _audit_text(row, "status"),
        "audit_note": note,
        "recorded_checksum_sha256": recorded_checksum,
    }


def _load_audit_links(
    audit_path: Path,
    *,
    operation: str,
    backup_column: str,
) -> dict[str, object]:
    markdown_path, markdown_warning = _read_audit_markdown(audit_path)
    result: dict[str, object] = {
        "status": "no_history",
        "message": f"No {operation.replace('_', ' ')} audit history exists yet.",
        "audit_path": str(audit_path),
        "audit_markdown_path": markdown_path,
        "matches": {},
        "malformed_rows": 0,
        "warnings": [markdown_warning] if markdown_warning else [],
    }
    if not audit_path.exists():
        if markdown_path:
            result["message"] = (
                f"Audit markdown exists at `{markdown_path}`, but `{audit_path}` is missing. "
                "CSV rows are required for backup matching."
            )
        return result
    try:
        audit = pd.read_csv(audit_path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        result["message"] = f"Audit file `{audit_path}` is empty; no history can be matched yet."
        return result
    except pd.errors.ParserError as exc:
        result.update(
            {
                "status": "malformed",
                "message": f"Audit file `{audit_path}` is malformed CSV: {exc}",
            }
        )
        return result
    except (OSError, UnicodeError) as exc:
        result.update(
            {
                "status": "unreadable",
                "message": f"Audit file `{audit_path}` is unreadable: {exc}",
            }
        )
        return result

    if audit.empty:
        result["message"] = f"Audit file `{audit_path}` has headers but no history rows."
        return result
    if backup_column not in audit.columns:
        result.update(
            {
                "status": "malformed",
                "message": (
                    f"Audit file `{audit_path}` is missing the required `{backup_column}` column."
                ),
            }
        )
        return result

    matches: dict[str, dict[str, object]] = {}
    malformed_rows = 0
    for _, row in audit.iterrows():
        canonical_path = _canonical_path(_audit_text(row, backup_column))
        if not canonical_path:
            malformed_rows += 1
            continue
        matches[canonical_path] = _audit_link(
            row,
            operation=operation,
            audit_path=audit_path,
            audit_markdown_path=markdown_path,
        )

    status = "ready" if matches else "malformed"
    message = f"Loaded {len(matches)} usable {operation.replace('_', ' ')} audit path(s)."
    if malformed_rows:
        message = f"{message} Skipped {malformed_rows} malformed row(s) with blank or invalid paths."
    result.update(
        {
            "status": status,
            "message": message,
            "matches": matches,
            "malformed_rows": malformed_rows,
        }
    )
    return result


def _unknown_audit_note(audit_results: list[dict[str, object]]) -> str:
    statuses = {str(result["status"]) for result in audit_results}
    malformed_rows = sum(int(result.get("malformed_rows", 0)) for result in audit_results)
    if statuses == {"no_history"}:
        return "No archive or rollback audit history is available yet. Operation is unknown."
    problems = [
        str(result["message"])
        for result in audit_results
        if result["status"] in {"unreadable", "malformed"}
    ]
    if problems:
        return "Audit linkage could not be confirmed. " + " ".join(problems)
    note = "This backup path was not found in the available archive or rollback audit rows."
    if malformed_rows:
        note = f"{note} {malformed_rows} malformed audit row(s) were skipped."
    return f"{note} Operation is unknown."


def get_stale_current_odds_backup_checksum_status(
    backup_path: Path | str,
    *,
    archive_audit_path: Path | None = None,
    rollback_audit_path: Path | None = None,
) -> dict[str, str]:
    """Return read-only checksum evidence for one selected stale-odds backup."""
    path = Path(backup_path).expanduser()
    archive_result = _load_audit_links(
        archive_audit_path or DEFAULT_ARCHIVE_AUDIT_PATH,
        operation="archive_apply",
        backup_column="backup_path",
    )
    rollback_result = _load_audit_links(
        rollback_audit_path or DEFAULT_ROLLBACK_AUDIT_PATH,
        operation="rollback_apply",
        backup_column="pre_rollback_backup_path",
    )
    audit_results = [archive_result, rollback_result]
    canonical_path = _canonical_path(path)
    match = archive_result["matches"].get(canonical_path)
    if match is None:
        match = rollback_result["matches"].get(canonical_path)

    details = {
        "created_by_operation": "unknown",
        "audit_file_path": "",
        "audit_note": _unknown_audit_note(audit_results),
        "recorded_checksum_sha256": "",
        "current_checksum_sha256": source_file_sha256(path),
    }
    if match is not None:
        for key in details:
            if key in match:
                details[key] = str(match[key])

    checksum_status, checksum_note = _checksum_verification(
        details["recorded_checksum_sha256"],
        details["current_checksum_sha256"],
        details["created_by_operation"],
    )
    if match is None and details["audit_note"]:
        checksum_note = f"{checksum_note} {details['audit_note']}"
    details.update(
        {
            "checksum_status": checksum_status,
            "checksum_note": checksum_note,
        }
    )
    return details


def _link_backup_audits(
    backup_list: pd.DataFrame,
    *,
    archive_audit_path: Path,
    rollback_audit_path: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    archive_result = _load_audit_links(
        archive_audit_path,
        operation="archive_apply",
        backup_column="backup_path",
    )
    rollback_result = _load_audit_links(
        rollback_audit_path,
        operation="rollback_apply",
        backup_column="pre_rollback_backup_path",
    )
    audit_results = [archive_result, rollback_result]
    unknown_note = _unknown_audit_note(audit_results)
    linked = backup_list.copy()
    matched = 0
    for index, row in linked.iterrows():
        canonical_path = _canonical_path(row["backup_path"])
        match = archive_result["matches"].get(canonical_path)
        if match is None:
            match = rollback_result["matches"].get(canonical_path)
        if match is None:
            linked.at[index, "audit_note"] = unknown_note
            continue
        matched += 1
        for column, value in match.items():
            linked.at[index, column] = value

    for index, row in linked.iterrows():
        checksum_status, checksum_note = _checksum_verification(
            row["recorded_checksum_sha256"],
            row["current_checksum_sha256"],
            row["created_by_operation"],
        )
        linked.at[index, "checksum_status"] = checksum_status
        linked.at[index, "checksum_note"] = checksum_note

    malformed_rows = sum(int(result.get("malformed_rows", 0)) for result in audit_results)
    warning_messages = [
        str(warning)
        for result in audit_results
        for warning in result.get("warnings", [])
        if warning
    ]
    warning_count = malformed_rows + len(warning_messages)
    problem_statuses = {"unreadable", "malformed"}
    if matched == len(linked):
        link_status = "linked"
    elif matched:
        link_status = "partial"
    elif all(result["status"] == "no_history" for result in audit_results):
        link_status = "no_history"
    elif any(result["status"] in problem_statuses for result in audit_results):
        link_status = "needs_review"
    else:
        link_status = "no_matches"
    verified_checksums = int(linked["checksum_status"].eq("Verified").sum())
    mismatched_checksums = int(linked["checksum_status"].eq("Mismatch").sum())
    unavailable_checksums = int(linked["checksum_status"].eq("Not available").sum())
    summary = {
        "audit_link_status": link_status,
        "archive_audit_status": archive_result["status"],
        "rollback_audit_status": rollback_result["status"],
        "matched_backups": matched,
        "unmatched_backups": len(linked) - matched,
        "malformed_audit_rows": malformed_rows,
        "audit_warning_count": warning_count,
        "audit_warning_messages": " ".join(warning_messages),
        "archive_audit_message": archive_result["message"],
        "rollback_audit_message": rollback_result["message"],
        "verified_checksums": verified_checksums,
        "mismatched_checksums": mismatched_checksums,
        "unavailable_checksums": unavailable_checksums,
    }
    return linked.reindex(columns=BACKUP_LIST_COLUMNS).fillna(""), summary


def build_stale_current_odds_backup_list(
    backups_dir: Path | None = None,
    *,
    today: date | None = None,
    archive_audit_path: Path | None = None,
    rollback_audit_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """List known stale-odds backups without changing any source file."""
    backups_dir = backups_dir or DEFAULT_BACKUPS_DIR
    archive_audit_path = archive_audit_path or DEFAULT_ARCHIVE_AUDIT_PATH
    rollback_audit_path = rollback_audit_path or DEFAULT_ROLLBACK_AUDIT_PATH
    local_today = today or date.today()
    paths: set[Path] = set()
    if backups_dir.exists() and backups_dir.is_dir():
        for pattern in BACKUP_PATTERNS:
            paths.update(path for path in backups_dir.glob(pattern) if path.is_file())

    if not paths:
        summary = {
            "status": "no_backups",
            "message": (
                "No stale current-odds backups were found. Backups appear here only after an explicit "
                "Terminal archive or rollback apply operation."
            ),
            "backups_dir": str(backups_dir),
            "checked_date": local_today.isoformat(),
            "backups_found": 0,
            "valid_backups": 0,
            "invalid_backups": 0,
            "malformed_filename_count": 0,
            "audit_link_status": "not_checked",
            "archive_audit_status": "not_checked",
            "rollback_audit_status": "not_checked",
            "matched_backups": 0,
            "unmatched_backups": 0,
            "malformed_audit_rows": 0,
            "audit_warning_count": 0,
            "audit_warning_messages": "",
            "archive_audit_message": "No backups were available to match.",
            "rollback_audit_message": "No backups were available to match.",
            "verified_checksums": 0,
            "mismatched_checksums": 0,
            "unavailable_checksums": 0,
        }
        return _empty_backup_list(), summary

    records = [_inspect_backup(path, today=local_today) for path in paths]
    backup_list = pd.DataFrame(records, columns=BACKUP_LIST_COLUMNS).fillna("")
    backup_list["_sort_time"] = backup_list["filename_timestamp"].where(
        backup_list["filename_timestamp"].ne(""),
        backup_list["file_modified_at"],
    )
    backup_list = (
        backup_list.sort_values(
            ["_sort_time", "backup_path"],
            ascending=[False, True],
            kind="stable",
        )
        .drop(columns="_sort_time")
        .reset_index(drop=True)
    )
    backup_list, audit_summary = _link_backup_audits(
        backup_list,
        archive_audit_path=archive_audit_path,
        rollback_audit_path=rollback_audit_path,
    )
    valid_count = int(backup_list["valid"].eq("Yes").sum())
    invalid_count = len(backup_list) - valid_count
    malformed_filenames = int(backup_list["filename_status"].ne("Parsed").sum())
    mismatched_checksums = int(audit_summary["mismatched_checksums"])
    summary = {
        "status": "ready" if valid_count and not mismatched_checksums else "needs_review",
        "message": (
            f"Found {len(backup_list)} backup file(s); {valid_count} can be selected for rollback preview, "
            f"{audit_summary['matched_backups']} matched a creator audit entry, and "
            f"{audit_summary['verified_checksums']} passed checksum verification."
        ),
        "backups_dir": str(backups_dir),
        "checked_date": local_today.isoformat(),
        "backups_found": len(backup_list),
        "valid_backups": valid_count,
        "invalid_backups": invalid_count,
        "malformed_filename_count": malformed_filenames,
        **audit_summary,
    }
    return backup_list, summary


def render_stale_current_odds_backup_list(
    backup_list: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    lines = [
        "# Available Stale Odds Backups",
        "",
        "**Read-only report: no odds, import, ledger, profile, or model files were changed.**",
        "",
        "This report lists backups created by explicit stale-odds archive or rollback operations.",
        "",
        "## Summary",
        "",
        f"- Status: {summary.get('status', 'not_checked')}",
        f"- Backup folder: `{summary.get('backups_dir', '')}`",
        f"- Date checked against: {summary.get('checked_date', '')}",
        f"- Backups found: {int(summary.get('backups_found', 0))}",
        f"- Valid/selectable backups: {int(summary.get('valid_backups', 0))}",
        f"- Backups needing review: {int(summary.get('invalid_backups', 0))}",
        f"- Malformed filename timestamps: {int(summary.get('malformed_filename_count', 0))}",
        f"- Message: {summary.get('message', '')}",
        "",
        "## Audit Linkage",
        "",
        f"- Link status: {summary.get('audit_link_status', 'not_checked')}",
        f"- Backups matched to creator operations: {int(summary.get('matched_backups', 0))}",
        f"- Backups with unknown operations: {int(summary.get('unmatched_backups', 0))}",
        f"- Malformed audit rows skipped: {int(summary.get('malformed_audit_rows', 0))}",
        f"- Audit warnings: {summary.get('audit_warning_messages', '') or 'none'}",
        f"- Archive audit: {summary.get('archive_audit_status', 'not_checked')}",
        f"- Archive audit note: {summary.get('archive_audit_message', '')}",
        f"- Rollback audit: {summary.get('rollback_audit_status', 'not_checked')}",
        f"- Rollback audit note: {summary.get('rollback_audit_message', '')}",
        "",
        "## Checksum Verification",
        "",
        f"- Verified backups: {int(summary.get('verified_checksums', 0))}",
        f"- Checksum mismatches: {int(summary.get('mismatched_checksums', 0))}",
        f"- Checksums not available: {int(summary.get('unavailable_checksums', 0))}",
        (
            "- Safety warning: A checksum mismatch means the backup changed after creation. "
            "Do not trust it for rollback unless it is manually inspected."
            if int(summary.get("mismatched_checksums", 0))
            else "- Safety note: Only `Verified` backups have a confirmed byte-for-byte audit match."
        ),
        "",
        "## Backup Details",
        "",
    ]
    if backup_list.empty:
        lines.extend(
            [
                "No backups found.",
                "",
                "Do not apply an archive just to create a backup. A backup will appear automatically "
                "after a stale-odds archive or rollback is intentionally applied from Terminal.",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            backup_list.to_markdown(index=False),
            "",
            "## Next Step",
            "",
            "Choose a row marked `valid = Yes`, then preview it with "
            "`python scripts/rollback_stale_current_odds_archive.py --backup-path PATH`. "
            "Prefer a backup with a linked `archive_apply` or `rollback_apply` creator when possible. "
            "Treat `Mismatch` as unsafe until manually inspected; `Not available` means the older audit "
            "did not provide enough checksum evidence. "
            "The dashboard provides the same selection and preview without an apply button.",
        ]
    )
    return "\n".join(lines)


def save_stale_current_odds_backup_list(
    backups_dir: Path | None = None,
    output_dir: Path | None = None,
    *,
    today: date | None = None,
    archive_audit_path: Path | None = None,
    rollback_audit_path: Path | None = None,
) -> dict[str, Path | str]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_list, summary = build_stale_current_odds_backup_list(
        backups_dir,
        today=today,
        archive_audit_path=archive_audit_path,
        rollback_audit_path=rollback_audit_path,
    )
    csv_path = output_dir / "stale_current_odds_backup_list.csv"
    markdown_path = output_dir / "stale_current_odds_backup_list.md"
    backup_list.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_stale_current_odds_backup_list(backup_list, summary),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "status": str(summary.get("status", "not_checked")),
        "message": str(summary.get("message", "")),
    }
