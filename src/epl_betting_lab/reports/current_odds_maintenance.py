from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_template import (
    CURRENT_ODDS_COLUMNS,
    build_current_odds_template,
)


KEY_COLUMNS = ["date", "home_team", "away_team", "market", "selection", "book"]
MAINTENANCE_PREVIEW_COLUMNS = CURRENT_ODDS_COLUMNS + ["maintenance_action"]


def _key_value(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def _row_key(row: pd.Series, key_columns: list[str] = KEY_COLUMNS) -> tuple[str, ...]:
    return tuple(_key_value(row.get(column, "")) for column in key_columns)


def _ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = ""
    return out


def load_existing_current_odds(path: Path | None = None) -> pd.DataFrame:
    path = path or MANUAL_DIR / "current_odds.csv"
    if not path.exists():
        return pd.DataFrame(columns=CURRENT_ODDS_COLUMNS)
    return pd.read_csv(path, dtype=str).fillna("")


def build_current_odds_maintenance_preview(
    fixtures: pd.DataFrame,
    existing: pd.DataFrame | None = None,
    *,
    book: str = "",
    week: str | int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    existing = pd.DataFrame(columns=CURRENT_ODDS_COLUMNS) if existing is None else existing.fillna("")
    expected = build_current_odds_template(fixtures, book=book, week=week).fillna("")
    existing_for_keys = _ensure_columns(existing, KEY_COLUMNS)
    existing_keys = {_row_key(row) for _, row in existing_for_keys.iterrows()}

    missing_rows = []
    for _, row in expected.iterrows():
        if _row_key(row) not in existing_keys:
            new_row = row.to_dict()
            new_row["maintenance_action"] = "add_missing_row"
            missing_rows.append(new_row)

    preview = pd.DataFrame(missing_rows, columns=MAINTENANCE_PREVIEW_COLUMNS)
    return preview, expected


def render_current_odds_maintenance_report(
    preview: pd.DataFrame,
    *,
    applied: bool = False,
    backup_path: Path | None = None,
    odds_path: Path | None = None,
) -> str:
    odds_path = odds_path or MANUAL_DIR / "current_odds.csv"
    action = "applied" if applied else "previewed"
    lines = [
        "# Current Odds Maintenance",
        "",
        "This report checks for missing fixture/market rows in `data/manual/current_odds.csv`. It does not fabricate odds or place bets.",
        "",
        "## Summary",
        "",
        f"- Missing rows {action}: {len(preview)}",
        f"- Current odds file: `{odds_path}`",
        "- Existing odds, books, notes, closing odds, and extra columns are preserved.",
    ]
    if backup_path is not None:
        lines.append(f"- Backup written to: `{backup_path}`")
    if not applied:
        lines.append("- This was a dry run. Run `python scripts/maintain_current_odds.py --apply` to add the rows.")
    lines.extend([
        "",
        "## Missing rows",
        "",
        preview.to_markdown(index=False) if not preview.empty else "No missing rows found.",
    ])
    return "\n".join(lines)


def backup_current_odds(path: Path, timestamp: str | None = None) -> Path:
    timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"current_odds_{timestamp}.csv"
    shutil.copy2(path, backup_path)
    return backup_path


def save_current_odds_maintenance_reports(
    preview: pd.DataFrame,
    output_dir: Path | None = None,
    *,
    applied: bool = False,
    backup_path: Path | None = None,
    odds_path: Path | None = None,
) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "current_odds_maintenance_preview.csv"
    markdown_path = output_dir / "current_odds_maintenance_report.md"
    preview.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_current_odds_maintenance_report(preview, applied=applied, backup_path=backup_path, odds_path=odds_path),
        encoding="utf-8",
    )
    return {"csv": csv_path, "markdown": markdown_path}


def maintain_current_odds(
    fixtures: pd.DataFrame,
    odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    apply: bool = False,
    book: str = "",
    week: str | int | None = None,
    timestamp: str | None = None,
) -> dict[str, Path]:
    odds_path = odds_path or MANUAL_DIR / "current_odds.csv"
    existing = load_existing_current_odds(odds_path)
    preview, _ = build_current_odds_maintenance_preview(fixtures, existing, book=book, week=week)

    backup_path = None
    if apply and not preview.empty:
        odds_path.parent.mkdir(parents=True, exist_ok=True)
        if odds_path.exists():
            backup_path = backup_current_odds(odds_path, timestamp=timestamp)
        combined = pd.concat([
            existing,
            preview.drop(columns=["maintenance_action"], errors="ignore"),
        ], ignore_index=True, sort=False).fillna("")
        combined.to_csv(odds_path, index=False)

    paths = save_current_odds_maintenance_reports(
        preview,
        output_dir,
        applied=apply,
        backup_path=backup_path,
        odds_path=odds_path,
    )
    if backup_path is not None:
        paths["backup"] = backup_path
    if apply:
        paths["current_odds"] = odds_path
    return paths
