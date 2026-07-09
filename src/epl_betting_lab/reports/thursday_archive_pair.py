from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR


SNAPSHOT_COLUMNS = [
    "generated_at",
    "label",
    "csv",
    "markdown",
    "metadata",
    "source",
    "validation_status",
    "best_bets",
    "leans",
    "passes",
]
DETAIL_COLUMNS = [
    "snapshot",
    "archive_label",
    "generated_at",
    "validation_status",
    "best_bets",
    "leans",
    "passes",
    "total_rows",
    "markdown",
    "csv",
    "metadata",
    "notes",
]


def _archive_root(output_dir: Path) -> Path:
    return output_dir / "archive" / "thursday_best_bets"


def _format_label(generated_at: str) -> str:
    text = str(generated_at).strip()
    if not text:
        return "Unknown archive time"
    try:
        timestamp = datetime.fromisoformat(text)
    except ValueError:
        return text.replace("T", " ")
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _generated_at_from_csv(path: Path) -> str:
    date_label = path.parent.name
    time_label = path.name.split("_thursday_best_bets", 1)[0].split("_", 1)[0]
    if len(time_label) == 6 and time_label.isdigit():
        return f"{date_label}T{time_label[:2]}:{time_label[2:4]}:{time_label[4:6]}"
    return f"{date_label}T00:00:00"


def list_thursday_archive_snapshots(output_dir: Path | None = None, limit: int | None = None) -> pd.DataFrame:
    output_dir = output_dir or OUTPUTS_DIR
    archive_root = _archive_root(output_dir)
    if not archive_root.exists():
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)

    rows: list[dict[str, str]] = []
    seen_csvs: set[str] = set()
    for metadata_path in archive_root.glob("*/*_metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        csv_path = Path(str(metadata.get("csv", "")))
        if not csv_path.exists():
            continue
        generated_at = str(metadata.get("generated_at", "")).strip() or _generated_at_from_csv(csv_path)
        rows.append({
            "generated_at": generated_at,
            "label": _format_label(generated_at),
            "csv": str(csv_path),
            "markdown": str(metadata.get("markdown", "")),
            "metadata": str(metadata_path),
            "source": "metadata",
            "validation_status": str(metadata.get("validation_status", "")),
            "best_bets": metadata.get("best_bets", ""),
            "leans": metadata.get("leans", ""),
            "passes": metadata.get("passes", ""),
        })
        seen_csvs.add(str(csv_path))

    for csv_path in archive_root.glob("*/*_thursday_best_bets.csv"):
        if str(csv_path) in seen_csvs:
            continue
        generated_at = _generated_at_from_csv(csv_path)
        rows.append({
            "generated_at": generated_at,
            "label": _format_label(generated_at),
            "csv": str(csv_path),
            "markdown": "",
            "metadata": "",
            "source": "csv_filename",
            "validation_status": "",
            "best_bets": "",
            "leans": "",
            "passes": "",
        })

    if not rows:
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    snapshots = pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)
    snapshots = snapshots.sort_values("generated_at", ascending=False).reset_index(drop=True)
    if limit is not None:
        snapshots = snapshots.head(limit).reset_index(drop=True)
    return snapshots


def build_thursday_archive_pair(output_dir: Path | None = None) -> dict[str, Any]:
    snapshots = list_thursday_archive_snapshots(output_dir=output_dir, limit=2)
    if snapshots.empty:
        return {
            "status": "no_archives",
            "available": False,
            "label": "No archived snapshots found",
            "message": "No archived Thursday best-bets snapshots found yet.",
            "latest": None,
            "previous": None,
            "count": 0,
        }
    latest = snapshots.iloc[0].to_dict()
    if len(snapshots) == 1:
        return {
            "status": "one_archive",
            "available": False,
            "label": f"Only one archived snapshot found: {latest['label']}",
            "message": "Only one archived Thursday best-bets snapshot found. Generate one more Thursday report before comparing.",
            "latest": latest,
            "previous": None,
            "count": 1,
        }

    previous = snapshots.iloc[1].to_dict()
    return {
        "status": "ready",
        "available": True,
        "label": f"Comparing: {latest['label']} vs {previous['label']}",
        "message": "",
        "latest": latest,
        "previous": previous,
        "count": 2,
    }


def _csv_summary(csv_path: str) -> tuple[int | str, int | str, int | str, int | str, str]:
    path = Path(str(csv_path))
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return "", "", "", "", f"Could not read archived CSV: {exc}"

    total_rows = int(len(df))
    if "section" not in df.columns:
        return "", "", "", total_rows, "CSV readable; section counts are unavailable because `section` is missing."

    sections = df["section"].astype(str)
    return (
        int((sections == "Best bets").sum()),
        int((sections == "Leans").sum()),
        int((sections == "Passes / notable avoids").sum()),
        total_rows,
        "",
    )


def _count_from_snapshot(snapshot: pd.Series) -> tuple[dict[str, int | None], list[str]]:
    notes: list[str] = []
    counts: dict[str, int | None] = {
        "best_bets": None,
        "leans": None,
        "passes": None,
        "total": None,
    }

    has_metadata = str(snapshot.get("metadata", "")).strip() != ""
    if has_metadata:
        metadata_counts_available = True
        for key in ["best_bets", "leans", "passes"]:
            value = pd.to_numeric(snapshot.get(key, ""), errors="coerce")
            if pd.isna(value):
                metadata_counts_available = False
                break
            counts[key] = int(value)
        if metadata_counts_available:
            counts["total"] = int(counts["best_bets"] or 0) + int(counts["leans"] or 0) + int(counts["passes"] or 0)
            return counts, notes
        notes.append("Archive metadata is missing one or more count fields; using CSV rows instead.")
    else:
        notes.append("Metadata JSON missing; using archived CSV rows for counts.")

    csv_best, csv_leans, csv_passes, total_rows, csv_note = _csv_summary(str(snapshot.get("csv", "")))
    if isinstance(csv_best, int):
        counts["best_bets"] = csv_best
        counts["leans"] = int(csv_leans)
        counts["passes"] = int(csv_passes)
    if isinstance(total_rows, int):
        counts["total"] = total_rows
    if csv_note:
        notes.append(csv_note)
    return counts, notes


def _format_count(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def _format_delta(previous: int | None, latest: int | None) -> str:
    if previous is None or latest is None:
        return "n/a"
    delta = latest - previous
    if delta > 0:
        return f"+{delta}"
    return str(delta)


def _format_count_part(label: str, previous: int | None, latest: int | None) -> str:
    return f"{label} {_format_count(previous)} -> {_format_count(latest)} ({_format_delta(previous, latest)})"


def build_thursday_archive_count_change_note(output_dir: Path | None = None) -> dict[str, object]:
    snapshots = list_thursday_archive_snapshots(output_dir=output_dir, limit=2)
    if snapshots.empty:
        return {
            "available": False,
            "status": "no_archives",
            "note": "Card count changes: no archived snapshots found yet.",
            "notes": ["No archived snapshots found yet."],
        }
    if len(snapshots) == 1:
        return {
            "available": False,
            "status": "one_archive",
            "note": "Card count changes: only one archived snapshot found.",
            "notes": ["Generate one more Thursday best-bets report before comparing count changes."],
        }

    latest_counts, latest_notes = _count_from_snapshot(snapshots.iloc[0])
    previous_counts, previous_notes = _count_from_snapshot(snapshots.iloc[1])
    parts = [
        _format_count_part("Best bets", previous_counts["best_bets"], latest_counts["best_bets"]),
        _format_count_part("Leans", previous_counts["leans"], latest_counts["leans"]),
        _format_count_part("Passes", previous_counts["passes"], latest_counts["passes"]),
        _format_count_part("Total", previous_counts["total"], latest_counts["total"]),
    ]
    return {
        "available": True,
        "status": "ready",
        "note": "Card count changes: " + ", ".join(parts),
        "latest_counts": latest_counts,
        "previous_counts": previous_counts,
        "notes": latest_notes + previous_notes,
    }


def build_thursday_archive_history_details(output_dir: Path | None = None) -> tuple[pd.DataFrame, str]:
    snapshots = list_thursday_archive_snapshots(output_dir=output_dir, limit=2)
    if snapshots.empty:
        return pd.DataFrame(columns=DETAIL_COLUMNS), "No archived snapshots found yet."

    rows: list[dict[str, object]] = []
    for index, snapshot in snapshots.iterrows():
        csv_best, csv_leans, csv_passes, total_rows, csv_note = _csv_summary(str(snapshot.get("csv", "")))
        has_metadata = str(snapshot.get("metadata", "")).strip() != ""
        notes = []
        if not has_metadata:
            notes.append("Metadata JSON missing; using archived CSV filename and CSV rows only.")
        if csv_note:
            notes.append(csv_note)

        rows.append({
            "snapshot": "Latest" if index == 0 else "Previous",
            "archive_label": snapshot.get("label", ""),
            "generated_at": snapshot.get("generated_at", ""),
            "validation_status": snapshot.get("validation_status", ""),
            "best_bets": snapshot.get("best_bets", "") if has_metadata else csv_best,
            "leans": snapshot.get("leans", "") if has_metadata else csv_leans,
            "passes": snapshot.get("passes", "") if has_metadata else csv_passes,
            "total_rows": total_rows,
            "markdown": snapshot.get("markdown", ""),
            "csv": snapshot.get("csv", ""),
            "metadata": snapshot.get("metadata", ""),
            "notes": " ".join(notes),
        })

    message = ""
    if len(rows) == 1:
        message = "Only one archived snapshot found. Generate one more Thursday best-bets report before comparing."
    return pd.DataFrame(rows, columns=DETAIL_COLUMNS), message
