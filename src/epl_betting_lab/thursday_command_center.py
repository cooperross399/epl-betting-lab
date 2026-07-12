from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.current_odds_status import build_current_odds_status
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


def _format_percent(value: float | None) -> str:
    if value is None:
        return "Missing"
    return f"{value:.1%}"


def _format_count(value: int | None) -> str:
    if value is None:
        return "Missing"
    return str(int(value))


def build_thursday_detail_cue(recommended_next_action: object) -> str:
    action = str(recommended_next_action or "").strip().lower()
    cues = (
        ("generate a thursday archive first", "Thursday readiness refresh and Thursday best-bets report"),
        ("generate one more thursday archive first", "Thursday readiness refresh and Recent Thursday report archives"),
        ("generate comparison first", "Post-refresh Thursday review and Latest Thursday snapshot comparison"),
        ("check data/odds first", "Current odds validation and Odds entry completeness"),
        ("review removals first", "Thursday decision queue: Likely remove from card"),
        ("review prices first", "Thursday decision queue: Review price"),
        ("review candidate upgrades", "Thursday decision queue: Candidate upgrade"),
        ("generate decision queue first", "Thursday decision queue"),
        ("review the decision queue", "Thursday decision queue"),
        ("no urgent action", "Archive comparison and latest Thursday best-bets summary"),
    )
    for prefix, cue in cues:
        if action.startswith(prefix):
            return cue
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
        detail_cue=build_thursday_detail_cue(next_action.get("recommended_next_action")),
        explanation=readiness.explanation,
    )
