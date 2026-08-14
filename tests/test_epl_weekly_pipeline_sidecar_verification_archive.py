from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epl_betting_lab.reports.epl_weekly_pipeline_sidecar_verification_archive import (
    SIDECAR_VERIFICATION_ARCHIVED_VERDICT,
    SIDECAR_VERIFICATION_ARCHIVE_FAILED_VERDICT,
    SIDECAR_VERIFICATION_MISSING_VERDICT,
    archive_latest_epl_weekly_pipeline_sidecar_verification,
    calculate_epl_weekly_pipeline_sidecar_verification_archive_identity,
    list_recent_epl_weekly_pipeline_sidecar_verification_archives,
    save_epl_weekly_pipeline_sidecar_verification_archive,
)


RUN_AT = datetime(2026, 8, 14, 9, 30, 15, tzinfo=timezone.utc)
PIPELINE_RECEIPT_ID = "epl-weekly-pipeline-0123456789abcdef"
SIDECAR_RECEIPT_ID = "epl-weekly-verification-0123456789abcdef"


def _snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


def _fixture(
    tmp_path: Path,
    *,
    sidecar_receipt_id: str = SIDECAR_RECEIPT_ID,
    verdict: str = "Weekly verification sidecar verified",
    status: str = "Verified",
    mismatch_count: int = 0,
) -> tuple[Path, Path, Path, dict[str, Path]]:
    output_dir = tmp_path / "outputs"
    pipeline_dir = output_dir / "archive/epl_weekly_pipeline/2026-08-14/093015"
    sidecar_dir = (
        output_dir
        / "archive/epl_weekly_pipeline_verifications/2026-08-14/093015_receipt"
    )
    pipeline_dir.mkdir(parents=True)
    sidecar_dir.mkdir(parents=True)
    (pipeline_dir / "epl_weekly_pipeline.json").write_text(
        '{"sealed": true}\n', encoding="utf-8"
    )
    (sidecar_dir / "epl_weekly_pipeline_verification_sidecar.json").write_text(
        '{"sealed": true}\n', encoding="utf-8"
    )
    verification = {
        "verdict": verdict,
        "sidecar_archive_path": str(sidecar_dir),
        "original_sidecar_receipt_id": sidecar_receipt_id,
        "recalculated_sidecar_receipt_id": sidecar_receipt_id,
        "referenced_pipeline_archive_path": str(pipeline_dir),
        "referenced_pipeline_receipt_id": PIPELINE_RECEIPT_ID,
        "mismatch_count": mismatch_count,
        "checks": [],
    }
    paths = {
        "json": output_dir
        / "epl_weekly_pipeline_verification_sidecar_verification.json",
        "markdown": output_dir
        / "epl_weekly_pipeline_verification_sidecar_verification.md",
        "csv": output_dir
        / "epl_weekly_pipeline_verification_sidecar_verification.csv",
    }
    paths["json"].write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["markdown"].write_text(
        f"# Sidecar verification\n\nVerdict: {verdict}\n",
        encoding="utf-8",
    )
    paths["csv"].write_text(
        "category,item,status\nSidecar,receipt,Verified\n",
        encoding="utf-8",
    )
    return output_dir, pipeline_dir, sidecar_dir, paths


def _save(
    output_dir: Path,
    pipeline_dir: Path,
    sidecar_dir: Path,
    paths: dict[str, Path | None],
    *,
    sidecar_receipt_id: str = SIDECAR_RECEIPT_ID,
    verdict: str = "Weekly verification sidecar verified",
    status: str = "Verified",
    mismatch_count: int = 0,
):
    return save_epl_weekly_pipeline_sidecar_verification_archive(
        sidecar_archive_path=sidecar_dir,
        sidecar_receipt_id=sidecar_receipt_id,
        verification_paths=paths,
        sidecar_verification_verdict=verdict,
        sidecar_verification_status=status,
        original_sidecar_receipt_id=sidecar_receipt_id,
        recalculated_sidecar_receipt_id=sidecar_receipt_id,
        mismatch_count=mismatch_count,
        referenced_pipeline_archive_path=pipeline_dir,
        referenced_pipeline_receipt_id=PIPELINE_RECEIPT_ID,
        output_dir=output_dir,
        archived_at=RUN_AT,
    )


def test_archives_reports_with_stable_receipt_without_touching_sealed_archives(
    tmp_path,
) -> None:
    output_dir, pipeline_dir, sidecar_dir, paths = _fixture(tmp_path)
    pipeline_before = _snapshot(pipeline_dir)
    sidecar_before = _snapshot(sidecar_dir)

    first = _save(output_dir, pipeline_dir, sidecar_dir, paths)
    second = _save(output_dir, pipeline_dir, sidecar_dir, paths)

    assert first["verdict"] == SIDECAR_VERIFICATION_ARCHIVED_VERDICT
    assert first["summary"]["sidecar_verification_archive_receipt_id"] == second[
        "summary"
    ]["sidecar_verification_archive_receipt_id"]
    assert first["archive_dir"] != second["archive_dir"]
    assert second["archive_dir"].name.endswith("_02")
    for source in paths.values():
        assert source is not None
        assert (first["archive_dir"] / source.name).read_bytes() == source.read_bytes()
    assert _snapshot(pipeline_dir) == pipeline_before
    assert _snapshot(sidecar_dir) == sidecar_before


def test_archive_receipt_changes_when_verification_report_content_changes(
    tmp_path,
) -> None:
    output_dir, pipeline_dir, sidecar_dir, paths = _fixture(tmp_path)
    first = _save(output_dir, pipeline_dir, sidecar_dir, paths)

    paths["markdown"].write_text(
        "# Sidecar verification changed\n", encoding="utf-8"
    )
    second = _save(output_dir, pipeline_dir, sidecar_dir, paths)

    assert first["summary"]["sidecar_verification_archive_receipt_id"] != second[
        "summary"
    ]["sidecar_verification_archive_receipt_id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("referenced_pipeline_receipt_id", "different-pipeline"),
        ("sidecar_receipt_id", "different-sidecar"),
        ("sidecar_archive_path", "archive/different-sidecar"),
        ("sidecar_verification_verdict", "Weekly verification sidecar changed"),
        ("mismatch_count", 1),
    ],
)
def test_identity_is_deterministic_and_binds_receipts_and_evidence(
    field,
    value,
) -> None:
    evidence = [
        {
            "evidence_type": "sidecar_verification_json",
            "archive_member_path": "verification.json",
            "checksum_sha256": "a" * 64,
            "size_bytes": 10,
            "status": "Archived",
        }
    ]
    kwargs = {
        "referenced_pipeline_receipt_id": PIPELINE_RECEIPT_ID,
        "sidecar_receipt_id": SIDECAR_RECEIPT_ID,
        "sidecar_archive_path": "archive/sidecar",
        "sidecar_verification_verdict": "Weekly verification sidecar verified",
        "sidecar_verification_status": "Verified",
        "original_sidecar_receipt_id": SIDECAR_RECEIPT_ID,
        "recalculated_sidecar_receipt_id": SIDECAR_RECEIPT_ID,
        "mismatch_count": 0,
        "archive_verdict": SIDECAR_VERIFICATION_ARCHIVED_VERDICT,
        "evidence_records": evidence,
    }

    first = calculate_epl_weekly_pipeline_sidecar_verification_archive_identity(
        **kwargs
    )
    second = calculate_epl_weekly_pipeline_sidecar_verification_archive_identity(
        **kwargs
    )
    changed = calculate_epl_weekly_pipeline_sidecar_verification_archive_identity(
        **{**kwargs, field: value}
    )

    assert first == second
    assert first != changed


def test_archive_latest_uses_the_live_pipeline_linkage(tmp_path) -> None:
    output_dir, pipeline_dir, sidecar_dir, paths = _fixture(tmp_path)
    (output_dir / "epl_weekly_pipeline.json").write_text(
        json.dumps(
            {
                "archive_path": str(pipeline_dir),
                "archive_receipt_id": PIPELINE_RECEIPT_ID,
                "verification_sidecar_receipt_id": SIDECAR_RECEIPT_ID,
                "verification_sidecar_archive_path": str(sidecar_dir),
                "sidecar_verification_checked_archive_path": str(sidecar_dir),
                "sidecar_verification_verdict": (
                    "Weekly verification sidecar verified"
                ),
                "sidecar_verification_status": "Verified",
                "sidecar_verification_original_id": SIDECAR_RECEIPT_ID,
                "sidecar_verification_recalculated_id": SIDECAR_RECEIPT_ID,
                "sidecar_verification_mismatch_count": 0,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = archive_latest_epl_weekly_pipeline_sidecar_verification(
        output_dir,
        archived_at=RUN_AT,
    )

    assert result["verdict"] == SIDECAR_VERIFICATION_ARCHIVED_VERDICT
    assert result["summary"]["sidecar_archive_path"].endswith(
        "archive/epl_weekly_pipeline_verifications/2026-08-14/093015_receipt"
    )
    assert set(paths) == {"json", "markdown", "csv"}


def test_missing_verification_report_fails_closed_and_writes_receipt(tmp_path) -> None:
    output_dir, pipeline_dir, sidecar_dir, paths = _fixture(tmp_path)
    paths["csv"].unlink()

    result = _save(output_dir, pipeline_dir, sidecar_dir, paths)

    assert result["verdict"] == SIDECAR_VERIFICATION_MISSING_VERDICT
    assert result["summary"]["evidence_status_counts"]["Missing"] == 1
    assert result["json"].is_file()
    assert result["markdown"].is_file()
    assert result["csv"].is_file()


@pytest.mark.parametrize("receipt_id", ["", "../../unsafe/receipt"])
def test_missing_or_unsafe_receipt_ids_use_safe_fallback_and_fail_closed(
    tmp_path,
    receipt_id,
) -> None:
    output_dir, pipeline_dir, sidecar_dir, paths = _fixture(
        tmp_path, sidecar_receipt_id=receipt_id
    )

    result = _save(
        output_dir,
        pipeline_dir,
        sidecar_dir,
        paths,
        sidecar_receipt_id=receipt_id,
    )

    assert result["verdict"] == SIDECAR_VERIFICATION_ARCHIVE_FAILED_VERDICT
    assert result["archive_dir"].is_relative_to(
        output_dir / "archive/epl_weekly_pipeline_sidecar_verifications"
    )
    assert ".." not in result["archive_dir"].name
    assert result["summary"]["blockers"]


def test_recent_archive_list_is_read_only(tmp_path) -> None:
    output_dir, pipeline_dir, sidecar_dir, paths = _fixture(tmp_path)
    result = _save(output_dir, pipeline_dir, sidecar_dir, paths)
    before = _snapshot(result["archive_dir"])

    recent = list_recent_epl_weekly_pipeline_sidecar_verification_archives(
        output_dir
    )

    assert len(recent) == 1
    assert recent.iloc[0]["verdict"] == SIDECAR_VERIFICATION_ARCHIVED_VERDICT
    assert _snapshot(result["archive_dir"]) == before


def test_dashboard_surfaces_archive_history_without_apply_controls() -> None:
    app_source = Path("app.py").read_text(encoding="utf-8")

    assert "list_recent_epl_weekly_pipeline_sidecar_verification_archives" in app_source
    assert "Sidecar-verification archive history" in app_source
    assert "Latest sidecar-verification archive receipt" in app_source
    assert "apply_sidecar_verification_archive" not in app_source
