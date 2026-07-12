from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.thursday_command_center import build_thursday_command_center


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


def test_command_center_summarizes_ready_workflow(tmp_path) -> None:
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
