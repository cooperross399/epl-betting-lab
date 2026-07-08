from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.thursday_best_bets import list_recent_thursday_archives


COMPARISON_COLUMNS = [
    "change_type",
    "home_team",
    "away_team",
    "market",
    "selection",
    "book",
    "previous_status",
    "latest_status",
    "previous_confidence_tier",
    "latest_confidence_tier",
    "previous_ranking_score",
    "latest_ranking_score",
    "ranking_score_change",
    "previous_american_odds",
    "latest_american_odds",
    "american_odds_change",
    "previous_calibrated_edge",
    "latest_calibrated_edge",
    "calibrated_edge_change",
    "previous_suggested_units",
    "latest_suggested_units",
    "suggested_units_change",
    "previous_archive",
    "latest_archive",
    "details",
]
KEY_COLUMNS = ["home_team", "away_team", "market", "selection"]
WATCH_COLUMNS = ["status", "confidence_tier", "ranking_score", "american_odds", "calibrated_edge", "suggested_units"]


def _blank_row(key: tuple[str, ...], previous_archive: str, latest_archive: str) -> dict[str, object]:
    home_team, away_team, market, selection = key
    return {
        "change_type": "",
        "home_team": home_team,
        "away_team": away_team,
        "market": market,
        "selection": selection,
        "book": "",
        "previous_status": "",
        "latest_status": "",
        "previous_confidence_tier": "",
        "latest_confidence_tier": "",
        "previous_ranking_score": "",
        "latest_ranking_score": "",
        "ranking_score_change": "",
        "previous_american_odds": "",
        "latest_american_odds": "",
        "american_odds_change": "",
        "previous_calibrated_edge": "",
        "latest_calibrated_edge": "",
        "calibrated_edge_change": "",
        "previous_suggested_units": "",
        "latest_suggested_units": "",
        "suggested_units_change": "",
        "previous_archive": previous_archive,
        "latest_archive": latest_archive,
        "details": "",
    }


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _as_float(value: object) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    return float(numeric)


def _format_number(value: object) -> object:
    numeric = _as_float(value)
    if numeric is None:
        return "" if pd.isna(value) else value
    return round(numeric, 4)


def _delta(previous: object, latest: object) -> object:
    previous_number = _as_float(previous)
    latest_number = _as_float(latest)
    if previous_number is None or latest_number is None:
        return ""
    return round(latest_number - previous_number, 4)


def _row_key(row: pd.Series) -> tuple[str, ...]:
    return tuple(_clean(row.get(column)).lower() for column in KEY_COLUMNS)


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in KEY_COLUMNS + WATCH_COLUMNS + ["book"]:
        if column not in out.columns:
            out[column] = ""
    return out


def _key_label(key: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(part.title() if part else "" for part in key)


def _indexed_snapshot(path: Path) -> dict[tuple[str, ...], pd.Series]:
    df = pd.read_csv(path).fillna("")
    df = _ensure_columns(df)
    df["_key"] = df.apply(_row_key, axis=1)
    deduped = df.drop_duplicates(subset=["_key"], keep="last")
    return {row["_key"]: row for _, row in deduped.iterrows()}


def _changed_fields(previous: pd.Series, latest: pd.Series) -> list[str]:
    changed = []
    for column in WATCH_COLUMNS:
        previous_value = previous.get(column, "")
        latest_value = latest.get(column, "")
        if _as_float(previous_value) is not None or _as_float(latest_value) is not None:
            if _delta(previous_value, latest_value) != 0:
                changed.append(column)
        elif _clean(previous_value) != _clean(latest_value):
            changed.append(column)
    return changed


def _change_type(changed: list[str]) -> str:
    priority = [
        ("status", "status_changed"),
        ("confidence_tier", "tier_changed"),
        ("american_odds", "odds_moved"),
        ("calibrated_edge", "edge_changed"),
        ("suggested_units", "units_changed"),
        ("ranking_score", "ranking_score_changed"),
    ]
    for column, change_type in priority:
        if column in changed:
            return change_type
    return "updated"


def _comparison_row(
    key: tuple[str, ...],
    previous: pd.Series | None,
    latest: pd.Series | None,
    previous_archive: str,
    latest_archive: str,
) -> dict[str, object]:
    row = _blank_row(_key_label(key), previous_archive, latest_archive)
    if previous is None:
        previous = pd.Series(dtype=object)
    if latest is None:
        latest = pd.Series(dtype=object)

    row["book"] = _clean(latest.get("book", previous.get("book", "")))
    row["previous_status"] = _clean(previous.get("status", ""))
    row["latest_status"] = _clean(latest.get("status", ""))
    row["previous_confidence_tier"] = _clean(previous.get("confidence_tier", ""))
    row["latest_confidence_tier"] = _clean(latest.get("confidence_tier", ""))
    row["previous_ranking_score"] = _format_number(previous.get("ranking_score", ""))
    row["latest_ranking_score"] = _format_number(latest.get("ranking_score", ""))
    row["ranking_score_change"] = _delta(previous.get("ranking_score", ""), latest.get("ranking_score", ""))
    row["previous_american_odds"] = _format_number(previous.get("american_odds", ""))
    row["latest_american_odds"] = _format_number(latest.get("american_odds", ""))
    row["american_odds_change"] = _delta(previous.get("american_odds", ""), latest.get("american_odds", ""))
    row["previous_calibrated_edge"] = _format_number(previous.get("calibrated_edge", ""))
    row["latest_calibrated_edge"] = _format_number(latest.get("calibrated_edge", ""))
    row["calibrated_edge_change"] = _delta(previous.get("calibrated_edge", ""), latest.get("calibrated_edge", ""))
    row["previous_suggested_units"] = _format_number(previous.get("suggested_units", ""))
    row["latest_suggested_units"] = _format_number(latest.get("suggested_units", ""))
    row["suggested_units_change"] = _delta(previous.get("suggested_units", ""), latest.get("suggested_units", ""))
    return row


def build_thursday_best_bets_comparison(output_dir: Path | None = None) -> tuple[pd.DataFrame, dict[str, object]]:
    output_dir = output_dir or OUTPUTS_DIR
    archives = list_recent_thursday_archives(output_dir=output_dir, limit=2)
    if len(archives) < 2:
        return pd.DataFrame(columns=COMPARISON_COLUMNS), {
            "available": False,
            "message": "Comparison is not available yet. Generate at least two Thursday best-bets archive snapshots first.",
            "latest_archive": "",
            "previous_archive": "",
        }

    latest_archive = Path(str(archives.iloc[0]["csv"]))
    previous_archive = Path(str(archives.iloc[1]["csv"]))
    latest = _indexed_snapshot(latest_archive)
    previous = _indexed_snapshot(previous_archive)

    rows = []
    for key in sorted(set(previous).union(set(latest))):
        previous_row = previous.get(key)
        latest_row = latest.get(key)
        row = _comparison_row(key, previous_row, latest_row, str(previous_archive), str(latest_archive))
        if previous_row is None:
            row["change_type"] = "added"
            row["details"] = "Play appears in the latest archived card but not the previous one."
            rows.append(row)
        elif latest_row is None:
            row["change_type"] = "removed"
            row["details"] = "Play was on the previous archived card but not the latest one."
            rows.append(row)
        else:
            changed = _changed_fields(previous_row, latest_row)
            if changed:
                row["change_type"] = _change_type(changed)
                row["details"] = "Changed fields: " + ", ".join(changed) + "."
                rows.append(row)

    comparison = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
    summary = {
        "available": True,
        "message": "",
        "latest_archive": str(latest_archive),
        "previous_archive": str(previous_archive),
        "total_changes": int(len(comparison)),
        "added": int((comparison["change_type"] == "added").sum()) if not comparison.empty else 0,
        "removed": int((comparison["change_type"] == "removed").sum()) if not comparison.empty else 0,
        "updated": int((~comparison["change_type"].isin(["added", "removed"])).sum()) if not comparison.empty else 0,
    }
    return comparison, summary


def render_thursday_best_bets_comparison(comparison: pd.DataFrame, summary: dict[str, object]) -> str:
    lines = [
        "# Thursday Best-Bets Snapshot Comparison",
        "",
        "This report compares the latest archived Thursday best-bets CSV against the previous archived CSV. It does not fetch odds, place bets, or edit manual files.",
        "",
    ]
    if not summary.get("available"):
        lines.extend([
            str(summary.get("message", "Comparison is not available yet.")),
            "",
            "Run `python scripts/generate_thursday_best_bets.py` on at least two different refreshes to create enough archived snapshots.",
        ])
        return "\n".join(lines)

    lines.extend([
        f"- Latest archive: `{summary['latest_archive']}`",
        f"- Previous archive: `{summary['previous_archive']}`",
        f"- Total changes: {summary.get('total_changes', 0)}",
        f"- Added: {summary.get('added', 0)}",
        f"- Removed: {summary.get('removed', 0)}",
        f"- Updated: {summary.get('updated', 0)}",
        "",
    ])
    if comparison.empty:
        lines.extend(["No changes were found between the latest two archived Thursday cards.", ""])
        return "\n".join(lines)

    for change_type, title in [
        ("added", "Plays Added"),
        ("removed", "Plays Removed"),
        ("status_changed", "Status Changes"),
        ("tier_changed", "Confidence Tier Changes"),
        ("ranking_score_changed", "Ranking Score Changes"),
        ("odds_moved", "Odds Movement"),
        ("edge_changed", "Calibrated Edge Changes"),
        ("units_changed", "Suggested Unit Changes"),
        ("updated", "Other Updates"),
    ]:
        subset = comparison[comparison["change_type"] == change_type]
        if subset.empty:
            continue
        lines.extend([f"## {title}", ""])
        for _, row in subset.iterrows():
            matchup = f"{row['home_team']} vs {row['away_team']}"
            play = f"{row['market']} {row['selection']}"
            lines.append(f"- {matchup}, {play}: {row['details']}")
            if row["previous_status"] or row["latest_status"]:
                lines.append(f"  Status: {row['previous_status']} -> {row['latest_status']}")
            if row["previous_confidence_tier"] or row["latest_confidence_tier"]:
                lines.append(f"  Tier: {row['previous_confidence_tier']} -> {row['latest_confidence_tier']}")
            if row["ranking_score_change"] != "":
                lines.append(f"  Ranking score change: {row['ranking_score_change']}")
            if row["american_odds_change"] != "":
                lines.append(f"  Odds movement: {row['previous_american_odds']} -> {row['latest_american_odds']}")
            if row["calibrated_edge_change"] != "":
                lines.append(f"  Calibrated edge change: {row['calibrated_edge_change']}")
            if row["suggested_units_change"] != "":
                lines.append(f"  Suggested units change: {row['suggested_units_change']}")
        lines.append("")
    return "\n".join(lines)


def save_thursday_best_bets_comparison(output_dir: Path | None = None) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison, summary = build_thursday_best_bets_comparison(output_dir)
    csv_path = output_dir / "thursday_best_bets_comparison.csv"
    markdown_path = output_dir / "thursday_best_bets_comparison.md"
    comparison.to_csv(csv_path, index=False)
    markdown_path.write_text(render_thursday_best_bets_comparison(comparison, summary), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}
