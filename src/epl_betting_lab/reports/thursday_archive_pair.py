from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR


SNAPSHOT_COLUMNS = ["generated_at", "label", "csv", "metadata", "source"]


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
            "metadata": str(metadata_path),
            "source": "metadata",
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
            "metadata": "",
            "source": "csv_filename",
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
