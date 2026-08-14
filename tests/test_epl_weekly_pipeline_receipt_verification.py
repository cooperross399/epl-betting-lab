from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import epl_betting_lab.dashboard_actions as dashboard_actions
from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    archive_latest_epl_weekly_pipeline,
)
from epl_betting_lab.reports.epl_weekly_pipeline_receipt_verification import (
    build_epl_weekly_pipeline_receipt_verification,
    save_epl_weekly_pipeline_receipt_verification,
)


RUN_AT = datetime(2026, 8, 13, 9, 15, 30, tzinfo=timezone.utc)


def _summary(output_dir: Path) -> dict[str, object]:
    validation = output_dir / "current_odds_validation.csv"
    completeness = output_dir / "current_odds_completeness.csv"
    card = output_dir / "thursday_best_bets.csv"
    validation.write_text("severity,message\ninfo,ready\n", encoding="utf-8")
    completeness.write_text("status,count\ncomplete,7\n", encoding="utf-8")
    card.write_text("section,selection\nBest bets,home\n", encoding="utf-8")
    return {
        "run_timestamp": RUN_AT.isoformat(timespec="seconds"),
        "status": "Ready for card review",
        "key_blockers": [],
        "key_warnings": [],
        "generated_report_paths": [str(validation), str(completeness), str(card)],
        "card_counts": {
            "best_bets": 1,
            "leans": 0,
            "passes": 0,
            "total_candidates": 1,
        },
        "decision_queue_counts": {"Review price": 1},
        "ledger_health_summary": {
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
        },
        "recommended_next_action": "Review the card manually.",
        "steps": [
            {
                "step": "Current odds validation",
                "status": "Completed",
                "warnings": [],
                "blockers": [],
            },
            {
                "step": "Thursday best-bets generation",
                "status": "Completed",
                "warnings": [],
                "blockers": [],
            },
        ],
    }


def _archive(tmp_path: Path) -> tuple[Path, Path]:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    summary = _summary(output_dir)
    (output_dir / "epl_weekly_pipeline.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "epl_weekly_pipeline.md").write_text(
        "# Weekly pipeline\n",
        encoding="utf-8",
    )
    (output_dir / "epl_weekly_pipeline.csv").write_text(
        "step,status\nvalidation,Completed\n",
        encoding="utf-8",
    )
    archived = archive_latest_epl_weekly_pipeline(output_dir, archived_at=RUN_AT)
    return output_dir, archived["archive_dir"]


def _statuses(summary: dict[str, object]) -> dict[tuple[str, str], str]:
    return {
        (str(row["category"]), str(row["item"])): str(row["status"])
        for row in summary["checks"]
    }


def test_latest_unchanged_archive_verifies_and_writes_reports(tmp_path) -> None:
    output_dir, archive_dir = _archive(tmp_path)

    result = save_epl_weekly_pipeline_receipt_verification(
        output_dir=output_dir,
        generated_at=RUN_AT,
    )
    summary = result["summary"]

    assert result["verdict"] == "Weekly pipeline receipt verified"
    assert Path(summary["archive_path"]) == archive_dir
    assert summary["original_receipt_id"] == summary["recalculated_receipt_id"]
    assert summary["mismatch_count"] == 0
    assert result["json"].exists()
    assert result["markdown"].exists()
    assert result["csv"].exists()
    assert summary["safety"]["manual_files_edited"] is False
    assert summary["safety"]["bets_placed"] is False


def test_provided_archive_receipt_path_can_be_verified(tmp_path) -> None:
    output_dir, archive_dir = _archive(tmp_path)

    summary = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archive_dir / "epl_weekly_pipeline_archive.json",
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly pipeline receipt verified"
    assert Path(summary["archive_path"]) == archive_dir


def test_verification_fails_when_archived_pipeline_report_changes(tmp_path) -> None:
    output_dir, archive_dir = _archive(tmp_path)
    (archive_dir / "epl_weekly_pipeline.md").write_text(
        "# Changed weekly pipeline\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archive_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly pipeline receipt changed"
    assert _statuses(summary)[
        ("Archived checksum", "epl_weekly_pipeline.md")
    ] == "Checksum mismatch"


def test_verification_fails_when_derived_archive_view_changes(tmp_path) -> None:
    output_dir, archive_dir = _archive(tmp_path)
    (archive_dir / "epl_weekly_pipeline_archive.md").write_text(
        "# Altered receipt view\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archive_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly pipeline receipt changed"
    assert _statuses(summary)[
        ("Derived archive view", "epl_weekly_pipeline_archive.md")
    ] == "Checksum mismatch"


def test_verification_fails_when_archived_bound_report_changes(tmp_path) -> None:
    output_dir, archive_dir = _archive(tmp_path)
    archived_validation = archive_dir / "reports/current_odds_validation.csv"
    archived_validation.write_text(
        "severity,message\nerror,changed\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archive_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly pipeline receipt changed"
    assert _statuses(summary)[
        ("Archived report", "current_odds_validation.csv")
    ] == "Checksum mismatch"


def test_verification_fails_when_live_referenced_report_changes(tmp_path) -> None:
    output_dir, archive_dir = _archive(tmp_path)
    (output_dir / "current_odds_validation.csv").write_text(
        "severity,message\nwarning,new output\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archive_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly pipeline receipt changed"
    assert _statuses(summary)[
        ("Referenced report", "current_odds_validation.csv")
    ] == "Referenced report changed"


def test_verification_fails_when_receipt_id_is_altered(tmp_path) -> None:
    output_dir, archive_dir = _archive(tmp_path)
    manifest_path = archive_dir / "epl_weekly_pipeline_archive.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["receipt_id"] = "epl-weekly-altered"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archive_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly pipeline receipt changed"
    assert _statuses(summary)[("Receipt identity", "receipt_id")] == "Receipt ID mismatch"


def test_missing_archive_is_handled_safely(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()

    summary = build_epl_weekly_pipeline_receipt_verification(
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Missing weekly pipeline archive"
    assert summary["mismatch_count"] == 1
    assert summary["checks"][0]["status"] == "Missing archive"


def test_malformed_archive_is_handled_safely(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    archive_dir = output_dir / "archive/epl_weekly_pipeline/2026-08-13/091530"
    archive_dir.mkdir(parents=True)
    (archive_dir / "epl_weekly_pipeline_archive.json").write_text(
        "{not valid json\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_receipt_verification(
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Malformed weekly pipeline archive"
    assert any(row["status"] == "Malformed archive" for row in summary["checks"])


def test_intact_blocked_pipeline_receipt_is_not_ready(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    summary = _summary(output_dir)
    summary["status"] = "Needs odds fixes"
    summary["key_blockers"] = ["Odds are incomplete."]
    (output_dir / "epl_weekly_pipeline.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "epl_weekly_pipeline.md").write_text(
        "# Weekly pipeline\n",
        encoding="utf-8",
    )
    (output_dir / "epl_weekly_pipeline.csv").write_text(
        "step,status\nvalidation,Blocked\n",
        encoding="utf-8",
    )
    archived = archive_latest_epl_weekly_pipeline(output_dir, archived_at=RUN_AT)

    verification = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archived["archive_dir"],
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert verification["verdict"] == "Weekly pipeline receipt not ready"
    assert verification["mismatch_count"] == 0


def test_dashboard_verification_action_is_read_only_delegation(
    tmp_path, monkeypatch
) -> None:
    expected = {"verdict": "Weekly pipeline receipt verified"}
    calls: list[tuple[Path | None, Path]] = []

    def fake_verify(*, archive_path, output_dir):
        calls.append((archive_path, output_dir))
        return expected

    monkeypatch.setattr(
        dashboard_actions,
        "save_epl_weekly_pipeline_receipt_verification",
        fake_verify,
    )

    result = dashboard_actions.run_epl_weekly_pipeline_receipt_verification(
        tmp_path,
        archive_path=tmp_path / "archive",
    )

    assert result == expected
    assert calls == [(tmp_path / "archive", tmp_path)]


def test_dashboard_exposes_receipt_verification_without_apply_control() -> None:
    app_source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")

    assert '"Verify Weekly Pipeline Receipt"' in app_source
    assert "Latest receipt verification" in app_source
    assert '"epl_weekly_pipeline_receipt_verification.md"' in app_source
    assert "apply_epl_weekly_pipeline_receipt" not in app_source
