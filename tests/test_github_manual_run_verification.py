from __future__ import annotations

import copy
import json
from pathlib import Path

from epl_betting_lab.reports.github_manual_run_verification import (
    build_github_manual_run_verification,
    save_github_manual_run_verification,
)


def _handoff(*, allowed: bool = True) -> dict[str, object]:
    return {
        "run_timestamp": "2026-08-06T12:00:00+00:00",
        "status": "Warnings only" if allowed else "Blocked",
        "github_ref": "refs/heads/weekly-odds",
        "github_sha": "a" * 40,
        "current_odds_path": "data/manual/current_odds.csv",
        "current_odds_checksum_sha256": "b" * 64 if allowed else "",
        "fixtures_path": "data/manual/upcoming_fixtures.csv",
        "fixtures_checksum_sha256": "c" * 64,
        "current_odds_freshness_status": "Fresh" if allowed else "Not checked",
        "fixtures_freshness_status": "Fresh",
        "validation_status": "Ready" if allowed else "Blocked",
        "validation_serious_issue_count": 0 if allowed else 1,
        "validation_warning_count": 1 if allowed else 0,
        "completion_percentage": 1.0 if allowed else 0.0,
        "completeness_status": "Complete" if allowed else "Blocked",
        "card_generation_allowed": allowed,
        "blockers": [] if allowed else ["Current odds input is missing."],
        "warnings": ["Review totals-under caution."] if allowed else [],
    }


def _write_run(output_dir: Path, *, allowed: bool = True) -> dict[str, Path]:
    output_dir.mkdir(parents=True)
    handoff = _handoff(allowed=allowed)
    handoff_json = output_dir / "github_runner_input_handoff.json"
    handoff_md = output_dir / "github_runner_input_handoff.md"
    scheduled_json = output_dir / "scheduled_thursday_workflow_summary.json"
    scheduled_md = output_dir / "scheduled_thursday_workflow_summary.md"
    validation_csv = output_dir / "current_odds_validation.csv"
    validation_md = output_dir / "current_odds_validation.md"
    completeness_csv = output_dir / "current_odds_completeness.csv"
    completeness_md = output_dir / "current_odds_completeness.md"
    expected = [
        handoff_json,
        handoff_md,
        validation_csv,
        validation_md,
        completeness_csv,
        completeness_md,
        scheduled_json,
        scheduled_md,
    ]
    if allowed:
        expected.extend(
            [
                output_dir / "thursday_best_bets.csv",
                output_dir / "thursday_best_bets.md",
                output_dir
                / "archive/thursday_best_bets/2026-08-06/120000_thursday_best_bets.csv",
                output_dir
                / "archive/thursday_best_bets/2026-08-06/120000_thursday_best_bets.md",
                output_dir
                / "archive/thursday_best_bets/2026-08-06/120000_thursday_best_bets_metadata.json",
            ]
        )
    for path in expected:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".csv":
            path.write_text("status\nplaceholder\n", encoding="utf-8")
        elif path.suffix == ".json":
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.write_text("# Placeholder\n", encoding="utf-8")

    scheduled = {
        "run_timestamp": handoff["run_timestamp"],
        "status": "Warnings only" if allowed else "Blocked",
        "input_handoff": copy.deepcopy(handoff),
        "output_files_created": [str(path) for path in expected],
        "key_blockers": [] if allowed else ["Current odds input is missing."],
        "key_warnings": ["Review totals-under caution."] if allowed else [],
        "steps": [
            {
                "step": "GitHub runner input handoff",
                "status": "Completed with warnings" if allowed else "Blocked",
            },
            {
                "step": "Thursday best-bets generation",
                "status": "Completed" if allowed else "Skipped",
            },
        ],
    }
    handoff_json.write_text(json.dumps(handoff), encoding="utf-8")
    scheduled_json.write_text(json.dumps(scheduled), encoding="utf-8")
    return {
        "handoff_json": handoff_json,
        "handoff_md": handoff_md,
        "scheduled_json": scheduled_json,
        "scheduled_md": scheduled_md,
        "card_csv": output_dir / "thursday_best_bets.csv",
    }


def test_verification_reports_verified_ready_run(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    _write_run(output_dir, allowed=True)

    checks, summary = build_github_manual_run_verification(output_dir)

    assert summary["verdict"] == "Verified ready run"
    assert summary["github_ref"] == "refs/heads/weekly-odds"
    assert summary["github_sha"] == "a" * 40
    assert summary["completion_percentage"] == 1.0
    assert summary["card_generation_allowed"] is True
    assert summary["missing_outputs"] == []
    assert checks.iloc[0]["actual"] == "Verified ready run"


def test_verification_reports_verified_blocked_run(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    _write_run(output_dir, allowed=False)

    _, summary = build_github_manual_run_verification(output_dir)

    assert summary["verdict"] == "Verified blocked run"
    assert summary["card_generation_allowed"] is False
    assert summary["scheduled_workflow_status"] == "Blocked"
    assert summary["key_blockers"] == ["Current odds input is missing."]
    assert summary["missing_outputs"] == []


def test_verification_reports_missing_handoff_proof(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    paths = _write_run(output_dir)
    paths["handoff_json"].unlink()

    _, summary = build_github_manual_run_verification(output_dir)

    assert summary["verdict"] == "Missing handoff proof"
    assert "github_runner_input_handoff.json" in summary["next_step"]


def test_verification_reports_missing_scheduled_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    paths = _write_run(output_dir)
    paths["scheduled_json"].unlink()

    _, summary = build_github_manual_run_verification(output_dir)

    assert summary["verdict"] == "Missing scheduled workflow summary"
    assert "scheduled_thursday_workflow_summary.json" in summary["next_step"]


def test_verification_reports_incomplete_run_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    paths = _write_run(output_dir)
    paths["card_csv"].unlink()

    _, summary = build_github_manual_run_verification(output_dir)

    assert summary["verdict"] == "Incomplete run artifacts"
    assert "data/outputs/thursday_best_bets.csv" in summary["missing_outputs"]


def test_verification_rejects_mismatched_embedded_handoff(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    paths = _write_run(output_dir)
    scheduled = json.loads(paths["scheduled_json"].read_text(encoding="utf-8"))
    scheduled["input_handoff"]["current_odds_checksum_sha256"] = "d" * 64
    paths["scheduled_json"].write_text(json.dumps(scheduled), encoding="utf-8")

    _, summary = build_github_manual_run_verification(output_dir)

    assert summary["verdict"] == "Failed/untrusted run"
    assert any("current_odds_checksum_sha256" in item for item in summary["trust_failures"])


def test_verification_rejects_card_generated_after_block(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    paths = _write_run(output_dir, allowed=False)
    scheduled = json.loads(paths["scheduled_json"].read_text(encoding="utf-8"))
    scheduled["steps"][1]["status"] = "Completed"
    paths["scheduled_json"].write_text(json.dumps(scheduled), encoding="utf-8")

    _, summary = build_github_manual_run_verification(output_dir)

    assert summary["verdict"] == "Failed/untrusted run"
    assert any("denied" in item for item in summary["trust_failures"])


def test_save_verification_writes_csv_and_markdown(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    _write_run(output_dir)

    paths = save_github_manual_run_verification(output_dir)

    assert paths["verdict"] == "Verified ready run"
    assert Path(paths["csv"]).exists()
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "# GitHub Manual Thursday Run Verification" in markdown
    assert "Verified ready run" in markdown
    assert "does not edit odds" in markdown
