from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.current_odds_status import build_current_odds_status
from epl_betting_lab.reports.stale_current_odds_archive import (
    CONFIRMATION_METADATA_FILENAME,
)
from epl_betting_lab.reports.stale_current_odds_archive_confirmation import (
    build_stale_current_odds_archive_confirmation_status,
)
from epl_betting_lab.reports.thursday_archive_pair import (
    build_thursday_archive_count_change_risk,
    build_thursday_archive_pair,
)
from epl_betting_lab.reports.thursday_best_bets_comparison import (
    build_recommended_next_action,
    build_top_card_movement_reason,
)
from epl_betting_lab.thursday_readiness import build_thursday_readiness


@dataclass(frozen=True)
class ThursdayCommandCenter:
    thursday_status: str
    current_odds_status: str
    odds_completion: str
    serious_validation_issues: str
    validation_warnings: str
    archive_pair_label: str
    count_change_risk_flag: str
    top_card_movement_reason: str
    recommended_next_action: str
    detail_cue: str
    explanation: str
    archive_confirmation_status: str
    archive_confirmation_id: str
    archive_confirmation_level: str
    archive_confirmation_message: str


def _format_percent(value: float | None) -> str:
    if value is None:
        return "Missing"
    return f"{value:.1%}"


def _format_count(value: int | None) -> str:
    if value is None:
        return "Missing"
    return str(int(value))


def _archive_confirmation_home_signal(
    summary: dict[str, object],
) -> tuple[str, str]:
    status = str(summary.get("status", "Not checked"))
    stale_value = summary.get("current_stale_row_count", "")
    try:
        stale_rows = int(stale_value) if stale_value not in {"", None} else None
    except (TypeError, ValueError):
        stale_rows = None

    if status == "Ready":
        return (
            "success",
            (
                "Archive apply receipt is ready. Use the Terminal apply command from "
                "Tools / Diagnostics if you still want to archive stale rows."
            ),
        )
    if status == "Odds changed after preview":
        return "warning", "Run stale odds archive preview again before applying."
    if status == "Missing receipt":
        if stale_rows:
            return (
                "warning",
                (
                    f"{stale_rows} stale odds row(s) need attention. "
                    "Run stale odds archive preview before applying."
                ),
            )
        return (
            "info",
            "No archive receipt exists, but no stale odds rows currently need archiving.",
        )
    if status == "Invalid receipt":
        return (
            "warning",
            "The receipt is invalid. Run stale odds archive preview again before applying.",
        )
    if status == "Missing current_odds.csv":
        return (
            "error",
            "Current odds are missing. Create or import odds before reviewing an archive receipt.",
        )
    if status == "Unreadable current_odds.csv":
        return (
            "error",
            "Current odds are unreadable. Fix the CSV before reviewing an archive receipt.",
        )
    return "info", "Archive confirmation status is not available yet."


COUNTED_ACTION_GROUPS = (
    "Review price",
    "Likely remove from card",
    "Candidate upgrade",
    "Recheck odds",
    "Recheck validation",
)


def _load_decision_queue_counts(output_dir: Path) -> tuple[dict[str, int] | None, str]:
    queue_path = output_dir / "thursday_decision_queue.csv"
    comparison_path = output_dir / "thursday_best_bets_comparison.csv"
    if not queue_path.exists():
        return None, "play counts unavailable - generate the Thursday decision queue"
    if comparison_path.exists() and comparison_path.stat().st_mtime > queue_path.stat().st_mtime:
        return None, "play counts need refresh - regenerate the Thursday decision queue"

    try:
        queue = pd.read_csv(queue_path)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return None, "play counts unavailable - regenerate the Thursday decision queue"
    if queue.empty:
        return {}, "no affected plays are currently listed"
    if "action_needed" not in queue.columns:
        return None, "play counts unavailable - regenerate the Thursday decision queue"

    actions = queue["action_needed"].fillna("").astype(str).str.strip()
    if not actions.ne("").any():
        return None, "play counts unavailable - regenerate the Thursday decision queue"
    counts = actions.value_counts().to_dict()
    return {action: int(counts.get(action, 0)) for action in COUNTED_ACTION_GROUPS}, ""


def _add_play_counts(cue: str, groups: tuple[str, ...], output_dir: Path | None) -> str:
    if not groups or output_dir is None:
        return cue
    counts, fallback = _load_decision_queue_counts(output_dir)
    if fallback:
        return f"{cue} ({fallback})"

    labels = [
        f"{group}: {counts[group]} {'play' if counts[group] == 1 else 'plays'}"
        for group in groups
        if counts[group]
    ]
    if not labels:
        return f"{cue} (no matching affected plays are listed)"
    return f"{cue} - {'; '.join(labels)}"


def build_thursday_detail_cue(recommended_next_action: object, output_dir: Path | None = None) -> str:
    action = str(recommended_next_action or "").strip().lower()
    cues = (
        ("generate a thursday archive first", "Thursday readiness refresh and Thursday best-bets report", ()),
        (
            "generate one more thursday archive first",
            "Thursday readiness refresh and Recent Thursday report archives",
            (),
        ),
        (
            "generate comparison first",
            "Post-refresh Thursday review and Latest Thursday snapshot comparison",
            (),
        ),
        ("check data/odds first", "Current odds validation and Odds entry completeness", ("Recheck validation",)),
        (
            "review removals first",
            "Thursday decision queue: Likely remove from card",
            ("Likely remove from card",),
        ),
        ("review prices first", "Thursday decision queue: Review price", ("Review price", "Recheck odds")),
        ("review candidate upgrades", "Thursday decision queue: Candidate upgrade", ("Candidate upgrade",)),
        ("generate decision queue first", "Thursday decision queue", COUNTED_ACTION_GROUPS),
        ("review the decision queue", "Thursday decision queue", COUNTED_ACTION_GROUPS),
        ("no urgent action", "Archive comparison and latest Thursday best-bets summary", ()),
    )
    for prefix, cue, groups in cues:
        if action.startswith(prefix):
            return _add_play_counts(cue, groups, output_dir)
    return "Thursday readiness and report details below"


def build_thursday_command_center(
    output_dir: Path | None = None,
    current_odds: Path | None = None,
) -> ThursdayCommandCenter:
    output_dir = output_dir or OUTPUTS_DIR
    current_odds = current_odds or MANUAL_DIR / "current_odds.csv"

    readiness = build_thursday_readiness(output_dir, current_odds)
    validation_status = build_current_odds_status(
        output_dir / "current_odds_validation.csv",
        output_dir / "current_odds_validation.md",
        current_odds,
    )
    archive_pair = build_thursday_archive_pair(output_dir)
    count_risk = build_thursday_archive_count_change_risk(output_dir)
    top_reason = build_top_card_movement_reason(output_dir)
    next_action = build_recommended_next_action(output_dir)
    _, archive_confirmation = build_stale_current_odds_archive_confirmation_status(
        current_odds,
        output_dir / CONFIRMATION_METADATA_FILENAME,
    )
    archive_confirmation_level, archive_confirmation_message = (
        _archive_confirmation_home_signal(archive_confirmation)
    )

    if archive_pair["available"]:
        archive_label = str(archive_pair["label"])
    elif archive_pair["status"] == "one_archive":
        archive_label = str(archive_pair["label"])
    else:
        archive_label = "No archive pair yet"

    return ThursdayCommandCenter(
        thursday_status=readiness.thursday_report_status,
        current_odds_status=validation_status.status,
        odds_completion=_format_percent(readiness.odds_completion_percentage),
        serious_validation_issues=_format_count(readiness.serious_validation_issues),
        validation_warnings=_format_count(readiness.validation_warnings),
        archive_pair_label=archive_label,
        count_change_risk_flag=str(count_risk["risk_flag"]),
        top_card_movement_reason=str(top_reason["top_movement_reason"]),
        recommended_next_action=str(next_action["recommended_next_action"]),
        detail_cue=build_thursday_detail_cue(next_action.get("recommended_next_action"), output_dir),
        explanation=readiness.explanation,
        archive_confirmation_status=str(archive_confirmation["status"]),
        archive_confirmation_id=str(archive_confirmation.get("confirm_id", "")),
        archive_confirmation_level=archive_confirmation_level,
        archive_confirmation_message=archive_confirmation_message,
    )
