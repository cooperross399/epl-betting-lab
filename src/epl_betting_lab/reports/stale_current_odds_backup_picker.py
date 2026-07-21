from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.stale_current_odds import build_stale_current_odds_report


DEFAULT_BACKUPS_DIR = MANUAL_DIR / "backups"
BACKUP_SUFFIXES = {
    "_current_odds_pre_stale_archive_rollback.csv": "Pre-rollback recovery",
    "_current_odds_pre_stale_archive.csv": "Pre-archive",
}
BACKUP_PATTERNS = [f"*{suffix}" for suffix in BACKUP_SUFFIXES]
BACKUP_LIST_COLUMNS = [
    "backup_path",
    "backup_type",
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


def build_stale_current_odds_backup_list(
    backups_dir: Path | None = None,
    *,
    today: date | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """List known stale-odds backups without changing any source file."""
    backups_dir = backups_dir or DEFAULT_BACKUPS_DIR
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
    valid_count = int(backup_list["valid"].eq("Yes").sum())
    invalid_count = len(backup_list) - valid_count
    malformed_filenames = int(backup_list["filename_status"].ne("Parsed").sum())
    summary = {
        "status": "ready" if valid_count else "needs_review",
        "message": (
            f"Found {len(backup_list)} backup file(s); {valid_count} can be selected for rollback preview."
        ),
        "backups_dir": str(backups_dir),
        "checked_date": local_today.isoformat(),
        "backups_found": len(backup_list),
        "valid_backups": valid_count,
        "invalid_backups": invalid_count,
        "malformed_filename_count": malformed_filenames,
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
            "The dashboard provides the same selection and preview without an apply button.",
        ]
    )
    return "\n".join(lines)


def save_stale_current_odds_backup_list(
    backups_dir: Path | None = None,
    output_dir: Path | None = None,
    *,
    today: date | None = None,
) -> dict[str, Path | str]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_list, summary = build_stale_current_odds_backup_list(backups_dir, today=today)
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
