from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import epl_betting_lab.dashboard_actions as dashboard_actions
from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    archive_latest_epl_weekly_pipeline,
)
from epl_betting_lab.reports.epl_weekly_pipeline_receipt_verification import (
    save_epl_weekly_pipeline_receipt_verification,
)
from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar import (
    save_epl_weekly_pipeline_verification_sidecar,
)
from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar_verification import (
    build_epl_weekly_pipeline_verification_sidecar_verification,
    save_epl_weekly_pipeline_verification_sidecar_verification,
)


RUN_AT = datetime(2026, 8, 13, 9, 45, 30, tzinfo=timezone.utc)


def _pipeline_summary(output_dir: Path) -> dict[str, object]:
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
            }
        ],
    }


def _archive_snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


def _sidecar_bundle(
    tmp_path: Path,
    *,
    pipeline_status: str = "Ready for card review",
) -> tuple[Path, Path, Path]:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    summary = _pipeline_summary(output_dir)
    summary["status"] = pipeline_status
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
    receipt_verification = save_epl_weekly_pipeline_receipt_verification(
        archive_path=archived["archive_dir"],
        output_dir=output_dir,
        generated_at=RUN_AT,
    )
    verification = receipt_verification["summary"]
    verification_status = (
        "Verified"
        if verification["verdict"] == "Weekly pipeline receipt verified"
        else "Not ready"
    )
    sidecar = save_epl_weekly_pipeline_verification_sidecar(
        pipeline_archive_path=archived["archive_dir"],
        pipeline_receipt_id=str(archived["receipt_id"]),
        verification_paths={
            "json": receipt_verification["json"],
            "markdown": receipt_verification["markdown"],
            "csv": receipt_verification["csv"],
        },
        verification_verdict=str(verification["verdict"]),
        verification_status=verification_status,
        original_receipt_id=str(verification["original_receipt_id"]),
        recalculated_receipt_id=str(verification["recalculated_receipt_id"]),
        mismatch_count=int(verification["mismatch_count"]),
        output_dir=output_dir,
        archived_at=RUN_AT + timedelta(seconds=1),
    )
    return output_dir, Path(archived["archive_dir"]), Path(sidecar["archive_dir"])


def _statuses(summary: dict[str, object]) -> dict[tuple[str, str], str]:
    return {
        (str(row["category"]), str(row["item"])): str(row["status"])
        for row in summary["checks"]
    }


def test_latest_unchanged_sidecar_verifies_and_writes_reports(tmp_path) -> None:
    output_dir, pipeline_archive, sidecar_dir = _sidecar_bundle(tmp_path)
    pipeline_before = _archive_snapshot(pipeline_archive)
    sidecar_before = _archive_snapshot(sidecar_dir)

    result = save_epl_weekly_pipeline_verification_sidecar_verification(
        output_dir=output_dir,
        generated_at=RUN_AT,
    )
    summary = result["summary"]

    assert result["verdict"] == "Weekly verification sidecar verified"
    assert Path(summary["sidecar_archive_path"]) == sidecar_dir
    assert summary["original_sidecar_receipt_id"] == summary[
        "recalculated_sidecar_receipt_id"
    ]
    assert summary["mismatch_count"] == 0
    assert result["json"].is_file()
    assert result["markdown"].is_file()
    assert result["csv"].is_file()
    assert _archive_snapshot(pipeline_archive) == pipeline_before
    assert _archive_snapshot(sidecar_dir) == sidecar_before


def test_provided_sidecar_json_path_can_be_verified(tmp_path) -> None:
    output_dir, _, sidecar_dir = _sidecar_bundle(tmp_path)

    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        sidecar_path=sidecar_dir / "epl_weekly_pipeline_verification_sidecar.json",
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly verification sidecar verified"
    assert Path(summary["sidecar_archive_path"]) == sidecar_dir


def test_intact_blocked_sidecar_is_reported_not_ready(tmp_path) -> None:
    output_dir, _, sidecar_dir = _sidecar_bundle(
        tmp_path,
        pipeline_status="Needs odds",
    )

    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        sidecar_path=sidecar_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly verification sidecar not ready"
    assert summary["mismatch_count"] == 0


def test_verification_fails_when_sidecar_metadata_changes(tmp_path) -> None:
    output_dir, _, sidecar_dir = _sidecar_bundle(tmp_path)
    metadata_path = sidecar_dir / "epl_weekly_pipeline_verification_sidecar.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["verification_status"] = "Failed"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        sidecar_path=sidecar_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly verification sidecar changed"
    assert summary["mismatch_count"] > 0


def test_verification_fails_when_archived_verification_content_changes(
    tmp_path,
) -> None:
    output_dir, _, sidecar_dir = _sidecar_bundle(tmp_path)
    (sidecar_dir / "epl_weekly_pipeline_receipt_verification.md").write_text(
        "# Altered verification report\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        sidecar_path=sidecar_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly verification sidecar changed"
    assert _statuses(summary)[
        (
            "Archived verification evidence",
            "epl_weekly_pipeline_receipt_verification.md",
        )
    ] == "Checksum mismatch"


def test_verification_fails_when_sidecar_receipt_id_is_altered(tmp_path) -> None:
    output_dir, _, sidecar_dir = _sidecar_bundle(tmp_path)
    metadata_path = sidecar_dir / "epl_weekly_pipeline_verification_sidecar.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["sidecar_receipt_id"] = "epl-weekly-verification-altered"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        sidecar_path=sidecar_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Weekly verification sidecar changed"
    assert _statuses(summary)[
        ("Sidecar identity", "sidecar_receipt_id")
    ] == "Sidecar receipt ID mismatch"


def test_verification_fails_when_referenced_pipeline_archive_is_missing(
    tmp_path,
) -> None:
    output_dir, pipeline_archive, sidecar_dir = _sidecar_bundle(tmp_path)
    pipeline_archive.rename(output_dir / "moved_pipeline_archive")

    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        sidecar_path=sidecar_dir,
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Referenced pipeline archive changed"
    assert _statuses(summary)[
        ("Referenced pipeline archive", "pipeline_archive_path")
    ] == "Missing referenced archive"


def test_missing_sidecar_is_handled_safely(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()

    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Missing weekly verification sidecar"
    assert summary["mismatch_count"] == 1


def test_malformed_sidecar_is_handled_safely(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    sidecar_dir = (
        output_dir
        / "archive/epl_weekly_pipeline_verifications/2026-08-13/094531_receipt"
    )
    sidecar_dir.mkdir(parents=True)
    (sidecar_dir / "epl_weekly_pipeline_verification_sidecar.json").write_text(
        "{not-json",
        encoding="utf-8",
    )

    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        output_dir=output_dir,
        generated_at=RUN_AT,
    )

    assert summary["verdict"] == "Malformed weekly verification sidecar"
    assert summary["mismatch_count"] == 1


def test_dashboard_sidecar_verifier_is_read_only(tmp_path) -> None:
    output_dir, pipeline_archive, sidecar_dir = _sidecar_bundle(tmp_path)
    pipeline_before = _archive_snapshot(pipeline_archive)
    sidecar_before = _archive_snapshot(sidecar_dir)

    result = (
        dashboard_actions.run_epl_weekly_pipeline_verification_sidecar_verification(
            output_dir=output_dir,
            sidecar_path=sidecar_dir,
        )
    )
    app_source = Path("app.py").read_text(encoding="utf-8")

    assert result["verdict"] == "Weekly verification sidecar verified"
    assert "Verify Weekly Verification Sidecar" in app_source
    assert "run_epl_weekly_pipeline_verification_sidecar_verification" in app_source
    assert _archive_snapshot(pipeline_archive) == pipeline_before
    assert _archive_snapshot(sidecar_dir) == sidecar_before
