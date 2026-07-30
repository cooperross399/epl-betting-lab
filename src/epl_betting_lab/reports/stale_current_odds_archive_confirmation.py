from __future__ import annotations

from datetime import date
from pathlib import Path
import shlex

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256
from epl_betting_lab.reports.stale_current_odds_archive import (
    CONFIRMATION_METADATA_FILENAME,
    build_stale_current_odds_archive_preview,
    load_stale_current_odds_archive_confirmation_metadata,
)


STATUS_COLUMNS = [
    "confirm_id",
    "receipt_created_at",
    "preview_current_checksum_sha256",
    "current_checksum_sha256",
    "preview_stale_row_count",
    "current_stale_row_count",
    "preview_keep_row_count",
    "current_keep_row_count",
    "preview_manual_review_row_count",
    "current_manual_review_row_count",
    "status",
    "status_reason",
    "exact_apply_command",
    "receipt_path",
    "current_odds_path",
]
READABLE_CURRENT_STATUSES = {"preview_ready", "no_stale_rows"}


def _canonical_path(path: Path) -> str:
    try:
        return str(path.expanduser().resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return str(path.expanduser())


def _status_record(
    *,
    odds_path: Path,
    receipt_path: Path,
    metadata: dict[str, object] | None,
) -> dict[str, object]:
    metadata = metadata or {}
    return {
        "confirm_id": str(metadata.get("confirm_id", "")),
        "receipt_created_at": str(metadata.get("generated_at", "")),
        "preview_current_checksum_sha256": str(
            metadata.get("preview_current_checksum_sha256", "")
        ),
        "current_checksum_sha256": "",
        "preview_stale_row_count": metadata.get("preview_stale_row_count", ""),
        "current_stale_row_count": "",
        "preview_keep_row_count": metadata.get("preview_keep_row_count", ""),
        "current_keep_row_count": "",
        "preview_manual_review_row_count": metadata.get(
            "preview_manual_review_row_count",
            "",
        ),
        "current_manual_review_row_count": "",
        "status": "Not checked",
        "status_reason": "The confirmation receipt has not been checked.",
        "exact_apply_command": "",
        "receipt_path": str(receipt_path),
        "current_odds_path": str(odds_path),
    }


def _set_status(
    record: dict[str, object],
    status: str,
    reason: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    record["status"] = status
    record["status_reason"] = reason
    report = pd.DataFrame([record], columns=STATUS_COLUMNS)
    return report, record


def build_stale_current_odds_archive_confirmation_status(
    odds_path: Path | None = None,
    receipt_path: Path | None = None,
    *,
    today: date | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Check whether the latest archive preview receipt still matches current odds."""
    odds_path = odds_path or MANUAL_DIR / "current_odds.csv"
    receipt_path = receipt_path or OUTPUTS_DIR / CONFIRMATION_METADATA_FILENAME
    metadata, receipt_status, receipt_note = (
        load_stale_current_odds_archive_confirmation_metadata(receipt_path)
    )
    record = _status_record(
        odds_path=odds_path,
        receipt_path=receipt_path,
        metadata=metadata,
    )

    if not odds_path.exists() or not odds_path.is_file():
        return _set_status(
            record,
            "Missing current_odds.csv",
            (
                "The current odds file is missing, so this receipt cannot be checked or used. "
                "Create or import current odds first."
            ),
        )

    checksum_before = source_file_sha256(odds_path)
    _, current_summary = build_stale_current_odds_archive_preview(odds_path, today=today)
    checksum_after = source_file_sha256(odds_path)
    record["current_checksum_sha256"] = checksum_after
    current_status = str(current_summary.get("status", "not_checked"))
    if current_status not in READABLE_CURRENT_STATUSES or not checksum_after:
        return _set_status(
            record,
            "Unreadable current_odds.csv",
            (
                f"The current odds file could not be checked safely: "
                f"{current_summary.get('message', 'the CSV is unreadable or incomplete')} "
                "Fix the CSV, then run this read-only check again."
            ),
        )

    current_stale = int(current_summary.get("stale_rows", 0))
    current_keep = int(current_summary.get("current_rows", 0))
    current_manual = int(current_summary.get("date_fix_rows", 0))
    record["current_stale_row_count"] = current_stale
    record["current_keep_row_count"] = current_keep
    record["current_manual_review_row_count"] = current_manual

    if receipt_status == "Missing preview":
        return _set_status(
            record,
            "Missing receipt",
            (
                "No archive confirmation receipt exists yet. Run the stale odds archive preview "
                "before trying to apply an archive."
            ),
        )
    if metadata is None:
        return _set_status(
            record,
            "Invalid receipt",
            f"{receipt_note} Run the archive preview again and review the new receipt.",
        )
    if checksum_before != checksum_after:
        return _set_status(
            record,
            "Odds changed after preview",
            (
                "current_odds.csv changed while this status was being checked. "
                "Run the archive preview again before applying anything."
            ),
        )
    if _canonical_path(odds_path) != str(metadata.get("current_odds_path", "")):
        return _set_status(
            record,
            "Invalid receipt",
            (
                "The receipt was created for a different current_odds.csv path. "
                "Run preview mode for this odds file."
            ),
        )

    preview_checksum = str(metadata["preview_current_checksum_sha256"])
    if checksum_after != preview_checksum:
        return _set_status(
            record,
            "Odds changed after preview",
            (
                "The current odds checksum no longer matches the reviewed preview. "
                "Do not use the old confirmation ID; run preview mode again."
            ),
        )

    preview_counts = (
        int(metadata["preview_stale_row_count"]),
        int(metadata["preview_keep_row_count"]),
        int(metadata["preview_manual_review_row_count"]),
    )
    current_counts = (current_stale, current_keep, current_manual)
    if current_counts != preview_counts:
        return _set_status(
            record,
            "Odds changed after preview",
            (
                "The stale, current, or manual-review row counts no longer match the preview. "
                "The local date or row classification may have changed; run preview mode again."
            ),
        )

    confirm_id = str(metadata["confirm_id"])
    record["exact_apply_command"] = (
        "python scripts/archive_stale_current_odds.py "
        f"--apply --confirm-id {shlex.quote(confirm_id)}"
    )
    return _set_status(
        record,
        "Ready",
        (
            "The receipt is valid and its current-odds path, checksum, and row counts all match. "
            "Review the archive preview before copying the Terminal apply command."
        ),
    )


def render_stale_current_odds_archive_confirmation_status(
    summary: dict[str, object],
) -> str:
    """Render the status as a beginner-friendly read-only report."""
    def display(field: str) -> str:
        value = summary.get(field, "")
        return "Not available" if value in {"", None} else str(value)

    lines = [
        "# Stale Odds Archive Confirmation Status",
        "",
        (
            "This report only reads the archive preview receipt and `data/manual/current_odds.csv`. "
            "It never archives rows, applies changes, edits odds, places bets, or changes model logic."
        ),
        "",
        "## Status",
        "",
        f"- Status: **{summary.get('status', 'Not checked')}**",
        f"- Reason: {summary.get('status_reason', '')}",
        f"- Receipt: `{summary.get('receipt_path', '')}`",
        f"- Current odds: `{summary.get('current_odds_path', '')}`",
        f"- Receipt created at: {display('receipt_created_at')}",
        f"- Confirmation ID: `{display('confirm_id')}`",
        "",
        "## Receipt Compared With Current Odds",
        "",
        "- Preview/current checksum: "
        f"`{display('preview_current_checksum_sha256')}` / "
        f"`{display('current_checksum_sha256')}`",
        "- Preview/current stale rows: "
        f"{display('preview_stale_row_count')} / "
        f"{display('current_stale_row_count')}",
        "- Preview/current rows to keep: "
        f"{display('preview_keep_row_count')} / "
        f"{display('current_keep_row_count')}",
        "- Preview/current manual-review rows: "
        f"{display('preview_manual_review_row_count')} / "
        f"{display('current_manual_review_row_count')}",
        "",
        "## Next Step",
        "",
    ]
    status = str(summary.get("status", "Not checked"))
    if status == "Ready":
        lines.extend(
            [
                "The receipt matches. Review the archive preview, then copy this exact Terminal command:",
                "",
                "```bash",
                str(summary.get("exact_apply_command", "")),
                "```",
            ]
        )
    elif status == "Missing receipt":
        lines.append(
            "Run `python scripts/archive_stale_current_odds.py`, review its preview, then check again."
        )
    elif status == "Missing current_odds.csv":
        lines.append(
            "Create or import `data/manual/current_odds.csv`, then run the archive preview again."
        )
    elif status == "Unreadable current_odds.csv":
        lines.append("Fix the current odds CSV, then run the archive preview and this check again.")
    else:
        lines.append(
            "Do not use the old confirmation ID. Run "
            "`python scripts/archive_stale_current_odds.py` again and review the new preview."
        )
    return "\n".join(lines)


def save_stale_current_odds_archive_confirmation_status(
    odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    receipt_path: Path | None = None,
    today: date | None = None,
) -> dict[str, Path | str]:
    """Write read-only confirmation status outputs."""
    output_dir = output_dir or OUTPUTS_DIR
    receipt_path = receipt_path or output_dir / CONFIRMATION_METADATA_FILENAME
    output_dir.mkdir(parents=True, exist_ok=True)
    report, summary = build_stale_current_odds_archive_confirmation_status(
        odds_path,
        receipt_path,
        today=today,
    )
    csv_path = output_dir / "stale_current_odds_archive_confirmation_status.csv"
    markdown_path = output_dir / "stale_current_odds_archive_confirmation_status.md"
    report.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_stale_current_odds_archive_confirmation_status(summary),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "status": str(summary["status"]),
        "message": str(summary["status_reason"]),
        "exact_apply_command": str(summary["exact_apply_command"]),
    }
