from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.thursday_archive_pair import (
    build_thursday_archive_count_change_note,
    build_thursday_archive_count_change_risk,
    build_thursday_archive_pair,
)
from epl_betting_lab.reports.thursday_best_bets_comparison import (
    build_recommended_next_action,
    build_top_card_movement_reason,
)


ACTION_PRIORITY = [
    "Candidate upgrade",
    "Review price",
    "Likely remove from card",
    "Recheck odds",
    "Recheck validation",
    "Watch only",
    "No action",
]

QUEUE_COLUMNS = [
    "action_needed",
    "action_reason",
    "movement_category",
    "importance_score",
    "home_team",
    "away_team",
    "market",
    "selection",
    "previous_status",
    "latest_status",
    "previous_confidence_tier",
    "latest_confidence_tier",
    "previous_american_odds",
    "latest_american_odds",
    "calibrated_edge_change",
    "suggested_units_change",
]


def missing_comparison_message(output_dir: Path | None = None) -> str:
    output_dir = output_dir or OUTPUTS_DIR
    comparison_path = output_dir / "thursday_best_bets_comparison.csv"
    return (
        "Thursday decision queue is not available yet because the comparison report is missing. "
        f"Run `python scripts/compare_thursday_best_bets.py` first to create `{comparison_path}`."
    )


def _ensure_queue_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in QUEUE_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df


def build_thursday_decision_queue(output_dir: Path | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    output_dir = output_dir or OUTPUTS_DIR
    archive_pair = build_thursday_archive_pair(output_dir)
    count_change = build_thursday_archive_count_change_note(output_dir)
    count_risk = build_thursday_archive_count_change_risk(output_dir)
    top_reason = build_top_card_movement_reason(output_dir)
    next_action = build_recommended_next_action(output_dir)
    comparison_path = output_dir / "thursday_best_bets_comparison.csv"
    if not comparison_path.exists():
        return pd.DataFrame(columns=QUEUE_COLUMNS), {
            "available": False,
            "message": missing_comparison_message(output_dir),
            "comparison_path": str(comparison_path),
            "comparison_label": "Comparison not available yet",
            "archive_pair_label": archive_pair["label"],
            "count_change_note": count_change["note"],
            "count_change_risk_flag": count_risk["risk_flag"],
            "count_change_risk_reason": count_risk["risk_reason"],
            "top_movement_reason": top_reason["top_movement_reason"],
            "movement_reason_detail": top_reason["movement_reason_detail"],
            "recommended_next_action": next_action["recommended_next_action"],
            "next_action_reason": next_action["next_action_reason"],
            "total_rows": 0,
        }

    comparison = pd.read_csv(comparison_path).fillna("")
    comparison = _ensure_queue_columns(comparison)
    if comparison.empty:
        next_action = build_recommended_next_action(output_dir, comparison, comparison)
        return pd.DataFrame(columns=QUEUE_COLUMNS), {
            "available": True,
            "message": "The comparison report exists, but it has no changed plays to review.",
            "comparison_path": str(comparison_path),
            "comparison_label": archive_pair["label"],
            "archive_pair_label": archive_pair["label"],
            "count_change_note": count_change["note"],
            "count_change_risk_flag": count_risk["risk_flag"],
            "count_change_risk_reason": count_risk["risk_reason"],
            "top_movement_reason": top_reason["top_movement_reason"],
            "movement_reason_detail": top_reason["movement_reason_detail"],
            "recommended_next_action": next_action["recommended_next_action"],
            "next_action_reason": next_action["next_action_reason"],
            "total_rows": 0,
            "action_counts": {},
        }

    priority = {action: index for index, action in enumerate(ACTION_PRIORITY)}
    queue = comparison[QUEUE_COLUMNS].copy()
    queue["importance_score"] = pd.to_numeric(queue["importance_score"], errors="coerce").fillna(0.0)
    queue["_action_order"] = queue["action_needed"].map(priority).fillna(len(ACTION_PRIORITY)).astype(int)
    queue = queue.sort_values(
        ["_action_order", "importance_score", "home_team", "away_team", "market", "selection"],
        ascending=[True, False, True, True, True, True],
    ).drop(columns=["_action_order"])
    queue = queue.reset_index(drop=True)
    next_action = build_recommended_next_action(output_dir, comparison, queue)

    return queue, {
        "available": True,
        "message": "Decision queue created from the latest Thursday comparison report.",
        "comparison_path": str(comparison_path),
        "comparison_label": archive_pair["label"],
        "archive_pair_label": archive_pair["label"],
        "count_change_note": count_change["note"],
        "count_change_risk_flag": count_risk["risk_flag"],
        "count_change_risk_reason": count_risk["risk_reason"],
        "top_movement_reason": top_reason["top_movement_reason"],
        "movement_reason_detail": top_reason["movement_reason_detail"],
        "recommended_next_action": next_action["recommended_next_action"],
        "next_action_reason": next_action["next_action_reason"],
        "total_rows": int(len(queue)),
        "action_counts": queue["action_needed"].value_counts().to_dict(),
    }


def _format_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none"}:
        return ""
    return text


def _format_change(value: object) -> str:
    text = _format_value(value)
    if not text:
        return "n/a"
    try:
        return f"{float(text):+.3f}"
    except ValueError:
        return text


def _play_label(row: pd.Series) -> str:
    home = _format_value(row.get("home_team")) or "Unknown home"
    away = _format_value(row.get("away_team")) or "Unknown away"
    market = _format_value(row.get("market")) or "unknown market"
    selection = _format_value(row.get("selection")) or "unknown selection"
    return f"{home} vs {away} - {market} {selection}"


def _transition(previous: object, latest: object) -> str:
    previous_text = _format_value(previous) or "n/a"
    latest_text = _format_value(latest) or "n/a"
    return f"{previous_text} -> {latest_text}"


def render_thursday_decision_queue(queue: pd.DataFrame, summary: dict[str, Any]) -> str:
    lines = [
        "# Thursday Decision Queue",
        "",
        "This read-only queue groups changed Thursday recommendations by the action to review first. It does not edit odds, edit the ledger, place bets, or fetch prices.",
        "",
    ]

    if not summary.get("available", False):
        lines.extend([
            str(summary.get("comparison_label", "Comparison not available yet")),
            str(summary.get("archive_pair_label", "")),
            str(summary.get("count_change_note", "Card count changes: comparison not available yet.")),
            f"Count-change risk: {summary.get('count_change_risk_flag', 'Not enough archive history')}. {summary.get('count_change_risk_reason', '')}",
            f"Top card movement reason: {summary.get('top_movement_reason', 'No comparison report yet')}. {summary.get('movement_reason_detail', '')}",
            f"Recommended next action: {summary.get('recommended_next_action', 'Generate comparison first: no comparison report is available yet.')}",
            f"Why: {summary.get('next_action_reason', '')}",
            "",
            str(summary.get("message", missing_comparison_message())),
            "",
            "Command to run first:",
            "",
            "```bash",
            "python scripts/compare_thursday_best_bets.py",
            "```",
            "",
        ])
        return "\n".join(lines)

    if queue.empty:
        lines.extend([
            str(summary.get("comparison_label", "Comparison not available yet")),
            str(summary.get("count_change_note", "Card count changes: unavailable.")),
            f"Count-change risk: {summary.get('count_change_risk_flag', 'Stable card')}. {summary.get('count_change_risk_reason', '')}",
            f"Top card movement reason: {summary.get('top_movement_reason', 'No meaningful movement')}. {summary.get('movement_reason_detail', '')}",
            f"Recommended next action: {summary.get('recommended_next_action', 'No urgent action: the card is stable and there are no meaningful recommendation changes.')}",
            f"Why: {summary.get('next_action_reason', '')}",
            "",
            str(summary.get("message", "No changed plays are available to review.")),
            "",
        ])
        return "\n".join(lines)

    lines.extend([
        str(summary.get("comparison_label", "Comparison not available yet")),
        str(summary.get("count_change_note", "Card count changes: unavailable.")),
        f"Count-change risk: {summary.get('count_change_risk_flag', 'Stable card')}. {summary.get('count_change_risk_reason', '')}",
        f"Top card movement reason: {summary.get('top_movement_reason', 'No meaningful movement')}. {summary.get('movement_reason_detail', '')}",
        f"Recommended next action: {summary.get('recommended_next_action', 'Review the decision queue.')}",
        f"Why: {summary.get('next_action_reason', '')}",
        "",
        f"Total changed plays in queue: {int(summary.get('total_rows', len(queue)))}",
        "",
        "Review order: Candidate upgrade, Review price, Likely remove from card, Recheck odds, Recheck validation, Watch only, then No action.",
        "",
    ])

    action_counts = summary.get("action_counts", {})
    if action_counts:
        lines.append("## Queue counts")
        for action in ACTION_PRIORITY:
            count = int(action_counts.get(action, 0))
            if count:
                lines.append(f"- {action}: {count}")
        lines.append("")

    for action in ACTION_PRIORITY:
        subset = queue[queue["action_needed"] == action]
        if subset.empty:
            continue
        lines.append(f"## {action}")
        for _, row in subset.iterrows():
            lines.extend([
                f"- {_play_label(row)}",
                f"  - Why: {_format_value(row.get('action_reason')) or 'No action reason provided.'}",
                f"  - Movement: {_format_value(row.get('movement_category')) or 'n/a'}",
                f"  - Importance: {float(row.get('importance_score', 0.0)):.1f}",
                f"  - Status: {_transition(row.get('previous_status'), row.get('latest_status'))}",
                f"  - Tier: {_transition(row.get('previous_confidence_tier'), row.get('latest_confidence_tier'))}",
                f"  - Odds: {_transition(row.get('previous_american_odds'), row.get('latest_american_odds'))}",
                f"  - Edge change: {_format_change(row.get('calibrated_edge_change'))}",
                f"  - Unit change: {_format_change(row.get('suggested_units_change'))}",
            ])
        lines.append("")

    unknown = queue[~queue["action_needed"].isin(ACTION_PRIORITY)]
    if not unknown.empty:
        lines.append("## Other")
        for _, row in unknown.iterrows():
            lines.extend([
                f"- {_play_label(row)}",
                f"  - Action: {_format_value(row.get('action_needed')) or 'No action label'}",
                f"  - Why: {_format_value(row.get('action_reason')) or 'No action reason provided.'}",
                f"  - Importance: {float(row.get('importance_score', 0.0)):.1f}",
            ])
        lines.append("")

    return "\n".join(lines)


def save_thursday_decision_queue(output_dir: Path | None = None) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    queue, summary = build_thursday_decision_queue(output_dir)
    csv_path = output_dir / "thursday_decision_queue.csv"
    markdown_path = output_dir / "thursday_decision_queue.md"
    queue.to_csv(csv_path, index=False)
    markdown_path.write_text(render_thursday_decision_queue(queue, summary), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}
