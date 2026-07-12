from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR


AUDIT_COLUMNS = [
    "batch_id",
    "applied_at",
    "batch_status",
    "source_import_path",
    "source_sha256",
    "backup_path",
    "rows_added",
    "rows_updated",
    "rows_unchanged",
    "rows_skipped_invalid",
    "duplicate_count",
    "source_row_number",
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "book",
    "row_action",
    "issues",
    "warnings",
    "before_values",
    "after_values",
]
BATCH_SUMMARY_COLUMNS = [
    "batch_id",
    "applied_at",
    "batch_status",
    "source_import_path",
    "source_sha256",
    "backup_path",
    "rows_added",
    "rows_updated",
    "rows_unchanged",
    "rows_skipped_invalid",
    "duplicate_count",
]


def source_file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def new_import_batch_id(applied_at: str | None = None) -> str:
    if applied_at:
        try:
            timestamp = datetime.fromisoformat(applied_at).strftime("%Y%m%d-%H%M%S")
        except ValueError:
            timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    else:
        timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"odds-import-{timestamp}-{uuid4().hex[:8]}"


def _json_values(values: dict[str, object] | None) -> str:
    if not values:
        return "{}"
    clean = {
        str(key): "" if pd.isna(value) else str(value)
        for key, value in values.items()
    }
    return json.dumps(clean, sort_keys=True)


def build_current_odds_import_audit_rows(
    preview: pd.DataFrame,
    summary: dict[str, object],
    *,
    batch_id: str,
    applied_at: str,
    source_import_path: Path,
    source_sha256: str,
    backup_path: Path | None,
    snapshots: dict[int, tuple[dict[str, object], dict[str, object]]] | None = None,
) -> pd.DataFrame:
    snapshots = snapshots or {}
    metadata = {
        "batch_id": batch_id,
        "applied_at": applied_at,
        "batch_status": "applied" if summary.get("applied") else "no_changes",
        "source_import_path": str(source_import_path),
        "source_sha256": source_sha256,
        "backup_path": str(backup_path) if backup_path else "",
        "rows_added": int(summary.get("add_rows", 0)),
        "rows_updated": int(summary.get("update_rows", 0)),
        "rows_unchanged": int(summary.get("no_change_rows", 0)),
        "rows_skipped_invalid": int(summary.get("invalid_rows", 0)),
        "duplicate_count": int(summary.get("duplicate_rows", 0)),
    }
    rows: list[dict[str, object]] = []
    for _, row in preview.iterrows():
        source_row = int(row["source_row_number"]) if str(row.get("source_row_number", "")).strip() else 0
        before, after = snapshots.get(source_row, ({}, {}))
        rows.append({
            **metadata,
            "source_row_number": source_row or "",
            "date": row.get("date", ""),
            "home_team": row.get("home_team", ""),
            "away_team": row.get("away_team", ""),
            "market": row.get("market", ""),
            "selection": row.get("selection", ""),
            "book": row.get("book", ""),
            "row_action": row.get("import_action", ""),
            "issues": row.get("issues", ""),
            "warnings": row.get("warnings", ""),
            "before_values": _json_values(before),
            "after_values": _json_values(after),
        })
    if not rows:
        rows.append({
            **metadata,
            "row_action": "no_rows",
            "issues": summary.get("message", "No import rows were available."),
            "before_values": "{}",
            "after_values": "{}",
        })
    return pd.DataFrame(rows, columns=AUDIT_COLUMNS).fillna("")


def load_current_odds_import_audit(path: Path | None = None) -> tuple[pd.DataFrame | None, str]:
    path = path or OUTPUTS_DIR / "current_odds_import_audit.csv"
    if not path.exists():
        return pd.DataFrame(columns=AUDIT_COLUMNS), (
            "No current odds import audit history yet. Run `python scripts/import_current_odds.py --apply` "
            "after reviewing a valid preview."
        )
    try:
        audit = pd.read_csv(path, dtype=str).fillna("")
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        return None, (
            f"The current odds import audit file is unreadable: {exc}. "
            "Per-batch audit files may still be available."
        )
    missing = [column for column in AUDIT_COLUMNS if column not in audit.columns]
    if missing:
        return None, f"The current odds import audit file is missing required columns: {', '.join(missing)}."
    if audit.empty:
        return audit, "No current odds import audit history yet."
    return audit[AUDIT_COLUMNS], ""


def summarize_current_odds_import_batches(audit: pd.DataFrame) -> pd.DataFrame:
    if audit.empty or "batch_id" not in audit.columns:
        return pd.DataFrame(columns=BATCH_SUMMARY_COLUMNS)
    summary = audit.drop_duplicates(subset=["batch_id"], keep="last")[BATCH_SUMMARY_COLUMNS].copy()
    summary["backup_path"] = summary["backup_path"].replace(
        "",
        "Not available (new file or no valid changes)",
    )
    return summary.sort_values("applied_at", ascending=False).reset_index(drop=True)


def render_current_odds_import_audit(audit: pd.DataFrame, warning: str = "") -> str:
    lines = [
        "# Current Odds Import Audit",
        "",
        "This read-only history records Terminal apply attempts. It does not fetch odds, edit odds, or place bets.",
        "",
    ]
    if warning:
        lines.extend([f"Warning: {warning}", ""])
    if audit.empty:
        lines.extend([
            "No import audit history exists yet.",
            "",
            "Run `python scripts/import_current_odds.py --apply` only after reviewing the preview report.",
        ])
        return "\n".join(lines)

    batches = summarize_current_odds_import_batches(audit)
    latest_batch_id = str(batches.iloc[0]["batch_id"])
    latest = audit[audit["batch_id"].astype(str) == latest_batch_id]
    lines.extend([
        "## Import batches",
        "",
        batches.to_markdown(index=False),
        "",
        f"## Latest batch: {latest_batch_id}",
        "",
        latest[
            [
                "source_row_number",
                "date",
                "home_team",
                "away_team",
                "market",
                "selection",
                "book",
                "row_action",
                "issues",
                "before_values",
                "after_values",
            ]
        ].to_markdown(index=False),
    ])
    return "\n".join(lines)


def save_current_odds_import_audit(
    batch_audit: pd.DataFrame,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_id = str(batch_audit.iloc[0]["batch_id"])
    archive_dir = output_dir / "archive" / "current_odds_imports" / batch_id
    if archive_dir.exists():
        raise FileExistsError(f"Import audit batch `{batch_id}` already exists; no audit files were overwritten.")
    archive_dir.mkdir(parents=True, exist_ok=False)

    batch_csv = archive_dir / "current_odds_import_audit.csv"
    batch_markdown = archive_dir / "current_odds_import_audit.md"
    batch_audit.to_csv(batch_csv, index=False)
    batch_markdown.write_text(render_current_odds_import_audit(batch_audit), encoding="utf-8")

    audit_csv = output_dir / "current_odds_import_audit.csv"
    audit_markdown = output_dir / "current_odds_import_audit.md"
    existing, load_message = load_current_odds_import_audit(audit_csv)
    if existing is None:
        cumulative = batch_audit
        warning = (
            f"{load_message} The cumulative CSV was left untouched. "
            f"This batch is preserved at `{batch_csv}`."
        )
    else:
        cumulative = pd.concat([existing, batch_audit], ignore_index=True).reindex(columns=AUDIT_COLUMNS).fillna("")
        cumulative.to_csv(audit_csv, index=False)
        warning = ""
    audit_markdown.write_text(render_current_odds_import_audit(cumulative, warning=warning), encoding="utf-8")
    return {
        "audit_csv": audit_csv,
        "audit_markdown": audit_markdown,
        "batch_audit_csv": batch_csv,
        "batch_audit_markdown": batch_markdown,
    }
