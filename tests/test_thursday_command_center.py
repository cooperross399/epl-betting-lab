from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.stale_current_odds_archive import archive_stale_current_odds
from epl_betting_lab.thursday_command_center import build_thursday_command_center, build_thursday_detail_cue


def _write_completeness(output_dir: Path, completion: str = "100.0%", incomplete: int = 0) -> None:
    pd.DataFrame(columns=["severity", "issue"]).to_csv(output_dir / "current_odds_completeness.csv", index=False)
    (output_dir / "current_odds_completeness.md").write_text(
        "\n".join([
            "# Current Odds Entry Completeness",
            "",
            "## Summary",
            "",
            f"- Completion percentage: {completion}",
            f"- Matches incomplete: {incomplete}",
        ]),
        encoding="utf-8",
    )


def _write_validation(output_dir: Path, rows: list[dict[str, str]] | None = None) -> None:
    pd.DataFrame(rows or [], columns=["severity", "issue"]).to_csv(output_dir / "current_odds_validation.csv", index=False)
    (output_dir / "current_odds_validation.md").write_text("# Current Odds Validation\n", encoding="utf-8")


def _write_archive(output_dir: Path, generated_at: str) -> None:
    archive_dir = output_dir / "archive" / "thursday_best_bets" / generated_at[:10]
    archive_dir.mkdir(parents=True, exist_ok=True)
    time_label = generated_at[11:19].replace(":", "")
    csv_path = archive_dir / f"{time_label}_thursday_best_bets.csv"
    pd.DataFrame([{"section": "Best bets", "home_team": "Arsenal"}]).to_csv(csv_path, index=False)
    (archive_dir / f"{time_label}_thursday_best_bets_metadata.json").write_text(
        json.dumps({
            "generated_at": generated_at,
            "best_bets": 1,
            "leans": 0,
            "passes": 0,
            "validation_status": "ready",
            "csv": str(csv_path),
            "markdown": str(archive_dir / f"{time_label}_thursday_best_bets.md"),
        }),
        encoding="utf-8",
    )


def _write_current_odds(
    path: Path,
    *,
    match_date: str = "2099-01-01",
    american_odds: str = "-120",
) -> None:
    pd.DataFrame([
        {
            "date": match_date,
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "market": "1x2",
            "selection": "home",
            "american_odds": american_odds,
            "book": "ExampleBook",
        }
    ]).to_csv(path, index=False)


def test_command_center_reports_missing_state(tmp_path) -> None:
    summary = build_thursday_command_center(tmp_path, tmp_path / "current_odds.csv")

    assert summary.thursday_status == "Not checked"
    assert summary.current_odds_status == "Not checked"
    assert summary.odds_completion == "Missing"
    assert summary.serious_validation_issues == "Missing"
    assert summary.validation_warnings == "Missing"
    assert summary.archive_pair_label == "No archive pair yet"
    assert summary.count_change_risk_flag == "Not enough archive history"
    assert summary.top_card_movement_reason == "Not enough archive history"
    assert summary.recommended_next_action.startswith("Generate a Thursday archive first")
    assert summary.detail_cue == "Thursday readiness refresh and Thursday best-bets report"
    assert summary.archive_confirmation_status == "Missing current_odds.csv"
    assert summary.archive_confirmation_level == "error"
    assert summary.archive_confirmation_id == ""


def test_command_center_summarizes_ready_workflow(tmp_path) -> None:
    _write_current_odds(tmp_path / "current_odds.csv")
    _write_completeness(tmp_path)
    _write_validation(tmp_path)
    (tmp_path / "thursday_best_bets.md").write_text("# Thursday\n", encoding="utf-8")
    _write_archive(tmp_path, "2026-07-08T12:00:00")
    _write_archive(tmp_path, "2026-07-09T12:00:00")
    pd.DataFrame([
        {
            "movement_category": "Tier upgraded",
            "action_needed": "Candidate upgrade",
            "importance_score": 80,
        }
    ]).to_csv(tmp_path / "thursday_best_bets_comparison.csv", index=False)
    pd.DataFrame([
        {"action_needed": "Candidate upgrade"},
        {"action_needed": "Candidate upgrade"},
    ]).to_csv(tmp_path / "thursday_decision_queue.csv", index=False)

    summary = build_thursday_command_center(tmp_path, tmp_path / "current_odds.csv")

    assert summary.thursday_status == "Ready"
    assert summary.current_odds_status == "Ready"
    assert summary.odds_completion == "100.0%"
    assert summary.serious_validation_issues == "0"
    assert summary.validation_warnings == "0"
    assert summary.archive_pair_label == "Comparing: 2026-07-09 12:00:00 vs 2026-07-08 12:00:00"
    assert summary.count_change_risk_flag == "Stable card"
    assert summary.top_card_movement_reason == "Mostly tier/status changes"
    assert summary.recommended_next_action.startswith("Review candidate upgrades")
    assert summary.detail_cue == "Thursday decision queue: Candidate upgrade - Candidate upgrade: 2 plays"
    assert summary.archive_confirmation_status == "Missing receipt"
    assert summary.archive_confirmation_level == "info"
    assert "no stale odds rows" in summary.archive_confirmation_message.lower()


def test_command_center_shows_ready_archive_confirmation(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    _write_current_odds(odds_path, match_date="2000-01-01")
    preview = archive_stale_current_odds(odds_path, tmp_path)

    summary = build_thursday_command_center(tmp_path, odds_path)

    assert summary.archive_confirmation_status == "Ready"
    assert summary.archive_confirmation_level == "success"
    assert summary.archive_confirmation_id == preview["confirm_id"]
    assert summary.archive_confirmation_message == (
        "Archive apply receipt is ready. Use the Terminal apply command from "
        "Tools / Diagnostics if you still want to archive stale rows."
    )


def test_command_center_warns_when_archive_receipt_is_invalidated(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    _write_current_odds(odds_path, match_date="2000-01-01")
    archive_stale_current_odds(odds_path, tmp_path)
    _write_current_odds(odds_path, match_date="2000-01-01", american_odds="-115")

    summary = build_thursday_command_center(tmp_path, odds_path)

    assert summary.archive_confirmation_status == "Odds changed after preview"
    assert summary.archive_confirmation_level == "warning"
    assert summary.archive_confirmation_message == (
        "Run stale odds archive preview again before applying."
    )


def test_command_center_elevates_missing_receipt_only_when_stale_odds_exist(
    tmp_path,
) -> None:
    odds_path = tmp_path / "current_odds.csv"
    _write_current_odds(odds_path, match_date="2099-01-01")

    current = build_thursday_command_center(tmp_path, odds_path)

    assert current.archive_confirmation_status == "Missing receipt"
    assert current.archive_confirmation_level == "info"

    _write_current_odds(odds_path, match_date="2000-01-01")
    stale = build_thursday_command_center(tmp_path, odds_path)

    assert stale.archive_confirmation_status == "Missing receipt"
    assert stale.archive_confirmation_level == "warning"
    assert "1 stale odds row(s) need attention" in stale.archive_confirmation_message


def test_command_center_surfaces_invalid_receipt_and_unreadable_odds(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    receipt_path = tmp_path / "stale_current_odds_archive_preview.json"
    _write_current_odds(odds_path)
    receipt_path.write_text("{not-json", encoding="utf-8")

    invalid = build_thursday_command_center(tmp_path, odds_path)

    assert invalid.archive_confirmation_status == "Invalid receipt"
    assert invalid.archive_confirmation_level == "warning"

    odds_path.write_bytes(b"\xff\xfe\x00\x00")
    unreadable = build_thursday_command_center(tmp_path, odds_path)

    assert unreadable.archive_confirmation_status == "Unreadable current_odds.csv"
    assert unreadable.archive_confirmation_level == "error"


def test_detail_cue_maps_recommended_actions_to_dashboard_sections() -> None:
    expected = {
        "Generate a Thursday archive first: no archive exists.": "Thursday readiness refresh and Thursday best-bets report",
        "Generate one more Thursday archive first: only one exists.": "Thursday readiness refresh and Recent Thursday report archives",
        "Generate comparison first: no comparison exists.": "Post-refresh Thursday review and Latest Thursday snapshot comparison",
        "Check data/odds first: validation needs attention.": "Current odds validation and Odds entry completeness",
        "Review removals first: one play changed.": "Thursday decision queue: Likely remove from card",
        "Review prices first: odds moved against us.": "Thursday decision queue: Review price",
        "Review candidate upgrades: one play improved.": "Thursday decision queue: Candidate upgrade",
        "Review the decision queue: changed plays exist.": "Thursday decision queue",
        "No urgent action: the card is stable.": "Archive comparison and latest Thursday best-bets summary",
    }

    for action, cue in expected.items():
        assert build_thursday_detail_cue(action) == cue


def test_detail_cue_has_beginner_friendly_fallback() -> None:
    assert build_thursday_detail_cue(None) == "Thursday readiness and report details below"
    assert build_thursday_detail_cue("Unexpected action") == "Thursday readiness and report details below"


def test_detail_cue_shows_relevant_decision_queue_counts(tmp_path) -> None:
    pd.DataFrame([
        {"action_needed": "Review price"},
        {"action_needed": "Review price"},
        {"action_needed": "Review price"},
        {"action_needed": "Likely remove from card"},
        {"action_needed": "Candidate upgrade"},
        {"action_needed": "Candidate upgrade"},
        {"action_needed": "Recheck odds"},
        {"action_needed": "Recheck odds"},
        {"action_needed": "Recheck validation"},
    ]).to_csv(tmp_path / "thursday_decision_queue.csv", index=False)

    assert build_thursday_detail_cue("Review prices first", tmp_path).endswith(
        "Review price: 3 plays; Recheck odds: 2 plays"
    )
    assert build_thursday_detail_cue("Review removals first", tmp_path).endswith(
        "Likely remove from card: 1 play"
    )
    assert build_thursday_detail_cue("Review candidate upgrades", tmp_path).endswith(
        "Candidate upgrade: 2 plays"
    )
    assert build_thursday_detail_cue("Check data/odds first", tmp_path).endswith(
        "Recheck validation: 1 play"
    )


def test_detail_cue_handles_missing_stale_empty_and_malformed_queue(tmp_path) -> None:
    action = "Review prices first"
    missing = build_thursday_detail_cue(action, tmp_path)
    assert "play counts unavailable" in missing
    assert "generate the Thursday decision queue" in missing

    queue_path = tmp_path / "thursday_decision_queue.csv"
    pd.DataFrame(columns=["action_needed"]).to_csv(queue_path, index=False)
    assert "no affected plays are currently listed" in build_thursday_detail_cue(action, tmp_path)

    pd.DataFrame([{"market": "1x2"}]).to_csv(queue_path, index=False)
    assert "regenerate the Thursday decision queue" in build_thursday_detail_cue(action, tmp_path)

    pd.DataFrame([{"action_needed": "Review price"}]).to_csv(queue_path, index=False)
    comparison_path = tmp_path / "thursday_best_bets_comparison.csv"
    comparison_path.write_text("action_needed\nReview price\n", encoding="utf-8")
    newer = queue_path.stat().st_mtime + 10
    os.utime(comparison_path, (newer, newer))
    assert "play counts need refresh" in build_thursday_detail_cue(action, tmp_path)
