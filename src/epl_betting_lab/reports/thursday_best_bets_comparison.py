from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.thursday_archive_pair import (
    build_thursday_archive_count_change_note,
    build_thursday_archive_pair,
)


COMPARISON_COLUMNS = [
    "change_type",
    "movement_category",
    "importance_score",
    "movement_reason",
    "action_needed",
    "action_reason",
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
        "movement_category": "",
        "importance_score": 0.0,
        "movement_reason": "",
        "action_needed": "No action",
        "action_reason": "",
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


def _status_rank(status: object) -> int:
    text = _clean(status).upper()
    if text == "BETTABLE":
        return 3
    if text == "LEAN":
        return 2
    return 1


def _tier_rank(tier: object) -> int:
    return {"A": 4, "B": 3, "C": 2, "PASS/AVOID": 1}.get(_clean(tier).upper(), 1)


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


def _movement(row: dict[str, object]) -> tuple[str, float, str]:
    change_type = _clean(row.get("change_type"))
    previous_status = row.get("previous_status", "")
    latest_status = row.get("latest_status", "")
    previous_tier = row.get("previous_confidence_tier", "")
    latest_tier = row.get("latest_confidence_tier", "")
    edge_change = _as_float(row.get("calibrated_edge_change"))
    latest_edge = _as_float(row.get("latest_calibrated_edge"))
    odds_change = _as_float(row.get("american_odds_change"))
    units_change = _as_float(row.get("suggested_units_change"))
    score_change = abs(_as_float(row.get("ranking_score_change")) or 0.0)

    category = "Updated"
    base_score = 25.0
    reason = "Several recommendation fields changed."

    if change_type == "added":
        category = "New play"
        base_score = 82.0
        reason = "This play appears on the latest card but was not on the previous card."
    elif change_type == "removed":
        category = "Removed play"
        base_score = 78.0
        reason = "This play was on the previous card but is no longer on the latest card."
    elif _clean(latest_status).upper() == "BETTABLE" and _clean(previous_status).upper() != "BETTABLE":
        category = "Became BETTABLE"
        base_score = 100.0
        reason = "The play moved into BETTABLE status."
    elif "PASS" in _clean(latest_status).upper() and "PASS" not in _clean(previous_status).upper():
        category = "Became PASS/Avoid"
        base_score = 94.0
        reason = "The play moved out of playable range and is now a pass or avoid."
    elif _clean(latest_status).upper() == "LEAN" and _status_rank(previous_status) > _status_rank(latest_status):
        category = "Fell to LEAN"
        base_score = 76.0
        reason = "The play dropped from a stronger recommendation to LEAN."
    elif (
        latest_edge is not None
        and latest_edge <= 0
        and (_as_float(row.get("previous_calibrated_edge")) or 0.0) > 0
    ):
        category = "Edge disappeared"
        base_score = 88.0
        reason = "The calibrated edge is now zero or negative."
    elif _tier_rank(latest_tier) > _tier_rank(previous_tier):
        category = "Tier upgraded"
        base_score = 72.0
        reason = "The confidence tier improved."
    elif _tier_rank(latest_tier) < _tier_rank(previous_tier):
        category = "Tier downgraded"
        base_score = 70.0
        reason = "The confidence tier got worse."
    elif units_change is not None and units_change > 0:
        category = "Suggested units increased"
        base_score = 62.0
        reason = "The suggested unit size increased."
    elif units_change is not None and units_change < 0:
        category = "Suggested units decreased"
        base_score = 60.0
        reason = "The suggested unit size decreased."
    elif edge_change is not None and edge_change > 0:
        category = "Edge improved"
        base_score = 54.0
        reason = "The calibrated edge improved."
    elif odds_change is not None and odds_change > 0:
        category = "Odds moved in our favor"
        base_score = 50.0
        reason = "The American odds moved to a better price for this selection."
    elif odds_change is not None and odds_change < 0:
        category = "Odds moved against us"
        base_score = 50.0
        reason = "The American odds moved to a worse price for this selection."

    edge_points = min(10.0, abs(edge_change or 0.0) * 200)
    score_points = min(8.0, score_change / 5)
    unit_points = min(6.0, abs(units_change or 0.0) * 12)
    importance_score = round(min(100.0, base_score + edge_points + score_points + unit_points), 1)
    return category, importance_score, reason


def _action_needed(row: dict[str, object]) -> tuple[str, str]:
    category = _clean(row.get("movement_category"))
    latest_status = _clean(row.get("latest_status")).upper()
    previous_tier = row.get("previous_confidence_tier", "")
    latest_tier = row.get("latest_confidence_tier", "")
    edge_change = _as_float(row.get("calibrated_edge_change"))
    latest_edge = _as_float(row.get("latest_calibrated_edge"))
    odds_change = _as_float(row.get("american_odds_change"))
    details = " ".join([
        _clean(row.get("details")).lower(),
        _clean(row.get("previous_status")).lower(),
        _clean(row.get("latest_status")).lower(),
    ])

    if any(token in details for token in ["validation", "missing", "unmatched", "blank", "nan"]):
        return "Recheck validation", "This row may be affected by missing or validation-related data."
    if category == "Became BETTABLE":
        return "Review price", "The play became BETTABLE, so confirm the current sportsbook price before trusting it."
    if category == "New play":
        return "Review price", "This is new on the latest card, so verify the price and book before considering it."
    if category == "Tier upgraded":
        if _clean(latest_tier).upper() in {"A", "B"} or latest_status == "BETTABLE":
            return "Candidate upgrade", "The tier improved into a more playable range."
        return "Review price", "The tier improved, but the current price still needs a manual check."
    if odds_change is not None and odds_change > 0 and edge_change is not None and edge_change > 0:
        return "Candidate upgrade", "The price and calibrated edge both improved."
    if category == "Edge improved" and latest_status == "BETTABLE":
        return "Candidate upgrade", "The calibrated edge improved while the play remains BETTABLE."
    if category == "Odds moved against us":
        return "Review price", "The price moved against this play, so confirm it is still playable."
    if category == "Odds moved in our favor":
        return "Recheck odds", "The price moved in a useful direction, but the edge did not clearly improve."
    if category in {"Became PASS/Avoid", "Edge disappeared"}:
        return "Likely remove from card", "The play no longer has a playable profile."
    if category == "Removed play":
        return "Likely remove from card", "The play disappeared from the latest card."
    if category == "Tier downgraded":
        if _tier_rank(previous_tier) - _tier_rank(latest_tier) >= 2:
            return "Likely remove from card", "The tier dropped sharply."
        return "Watch only", "The tier got worse, so keep it off the main card unless the price improves."
    if category in {"Fell to LEAN", "Suggested units decreased"}:
        return "Watch only", "The recommendation weakened, so treat it as a watchlist play."
    if category == "Suggested units increased":
        return "Review price", "The suggested size increased, so verify the current price before upgrading."
    if latest_edge is not None and latest_edge <= 0:
        return "Likely remove from card", "The latest calibrated edge is zero or negative."
    return "No action", "No specific action is needed beyond normal review."


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


def _finalize_row(row: dict[str, object]) -> dict[str, object]:
    category, score, reason = _movement(row)
    row["movement_category"] = category
    row["importance_score"] = score
    row["movement_reason"] = reason
    action, action_reason = _action_needed(row)
    row["action_needed"] = action
    row["action_reason"] = action_reason
    return row


def build_thursday_best_bets_comparison(output_dir: Path | None = None) -> tuple[pd.DataFrame, dict[str, object]]:
    output_dir = output_dir or OUTPUTS_DIR
    archive_pair = build_thursday_archive_pair(output_dir)
    count_change = build_thursday_archive_count_change_note(output_dir)
    if not archive_pair["available"]:
        return pd.DataFrame(columns=COMPARISON_COLUMNS), {
            "available": False,
            "message": "Comparison is not available yet. Generate at least two Thursday best-bets archive snapshots first.",
            "latest_archive": "",
            "previous_archive": "",
            "latest_archive_label": archive_pair["latest"]["label"] if archive_pair["latest"] else "",
            "previous_archive_label": "",
            "comparison_label": archive_pair["label"],
            "archive_pair_status": archive_pair["status"],
            "count_change_note": count_change["note"],
        }

    latest_archive = Path(str(archive_pair["latest"]["csv"]))
    previous_archive = Path(str(archive_pair["previous"]["csv"]))
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
            rows.append(_finalize_row(row))
        elif latest_row is None:
            row["change_type"] = "removed"
            row["details"] = "Play was on the previous archived card but not the latest one."
            rows.append(_finalize_row(row))
        else:
            changed = _changed_fields(previous_row, latest_row)
            if changed:
                row["change_type"] = _change_type(changed)
                row["details"] = "Changed fields: " + ", ".join(changed) + "."
                rows.append(_finalize_row(row))

    comparison = pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
    if not comparison.empty:
        comparison = comparison.sort_values(["importance_score", "home_team", "market"], ascending=[False, True, True]).reset_index(drop=True)
    summary = {
        "available": True,
        "message": "",
        "latest_archive": str(latest_archive),
        "previous_archive": str(previous_archive),
        "latest_archive_label": archive_pair["latest"]["label"],
        "previous_archive_label": archive_pair["previous"]["label"],
        "comparison_label": archive_pair["label"],
        "archive_pair_status": archive_pair["status"],
        "count_change_note": count_change["note"],
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
            f"- {summary.get('comparison_label', 'Comparison not available yet')}",
            f"- {summary.get('count_change_note', 'Card count changes: comparison not available yet.')}",
            "",
            str(summary.get("message", "Comparison is not available yet.")),
            "",
            "Run `python scripts/generate_thursday_best_bets.py` on at least two different refreshes to create enough archived snapshots.",
        ])
        return "\n".join(lines)

    lines.extend([
        f"- {summary['comparison_label']}",
        f"- {summary.get('count_change_note', 'Card count changes: unavailable.')}",
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

    action_counts = comparison["action_needed"].value_counts().to_dict()
    lines.extend([
        "## Action needed",
        "",
        "Use this as a review checklist, not an automatic bet slip.",
        "",
    ])
    for action in [
        "Candidate upgrade",
        "Review price",
        "Likely remove from card",
        "Watch only",
        "Recheck odds",
        "Recheck validation",
        "No action",
    ]:
        count = int(action_counts.get(action, 0))
        if count:
            lines.append(f"- {action}: {count}")
    lines.append("")

    biggest = comparison.sort_values("importance_score", ascending=False).head(8)
    lines.extend([
        "## Biggest changes",
        "",
        "These are the recommendation moves most worth reviewing first.",
        "",
    ])
    for _, row in biggest.iterrows():
        matchup = f"{row['home_team']} vs {row['away_team']}"
        play = f"{row['market']} {row['selection']}"
        lines.append(
            f"- {row['movement_category']} ({float(row['importance_score']):.1f}/100): "
            f"{matchup}, {play}. {row['movement_reason']} Action: {row['action_needed']}."
        )
    lines.append("")

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
            lines.append(
                f"- {matchup}, {play}: {row['movement_category']} "
                f"({float(row['importance_score']):.1f}/100). {row['movement_reason']}"
            )
            lines.append(f"  Action needed: {row['action_needed']}. {row['action_reason']}")
            lines.append(f"  Details: {row['details']}")
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
