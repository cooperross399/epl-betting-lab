from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar import (
    SIDECAR_ARCHIVED_VERDICT,
    SIDECAR_FAILED_VERDICT,
    SIDECAR_MISSING_VERDICT,
    SIDECAR_NOT_READY_VERDICT,
    archive_latest_epl_weekly_pipeline_verification,
    calculate_epl_weekly_pipeline_verification_sidecar_identity,
    list_recent_epl_weekly_pipeline_verification_sidecars,
    save_epl_weekly_pipeline_verification_sidecar,
)


RUN_AT = datetime(2026, 8, 13, 9, 22, 30, tzinfo=timezone.utc)
RECEIPT_ID = "epl-weekly-0123456789abcdef"


def _fixture(
    tmp_path: Path,
    *,
    receipt_id: str = RECEIPT_ID,
    verdict: str = "Weekly pipeline receipt verified",
    mismatch_count: int = 0,
) -> tuple[Path, Path, dict[str, Path]]:
    output_dir = tmp_path / "outputs"
    archive_dir = output_dir / "archive/epl_weekly_pipeline/2026-08-13/092230"
    archive_dir.mkdir(parents=True)
    (archive_dir / "epl_weekly_pipeline.json").write_text(
        '{"sealed": true}\n',
        encoding="utf-8",
    )
    (archive_dir / "epl_weekly_pipeline.md").write_text(
        "# Sealed weekly pipeline\n",
        encoding="utf-8",
    )
    (archive_dir / "epl_weekly_pipeline.csv").write_text(
        "step,status\narchive,Completed\n",
        encoding="utf-8",
    )
    verification = {
        "archive_path": str(archive_dir),
        "verdict": verdict,
        "original_receipt_id": receipt_id,
        "recalculated_receipt_id": receipt_id,
        "mismatch_count": mismatch_count,
        "checks": [],
    }
    paths = {
        "json": output_dir / "epl_weekly_pipeline_receipt_verification.json",
        "markdown": output_dir / "epl_weekly_pipeline_receipt_verification.md",
        "csv": output_dir / "epl_weekly_pipeline_receipt_verification.csv",
    }
    paths["json"].write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["markdown"].write_text(
        f"# Receipt verification\n\nVerdict: {verdict}\n",
        encoding="utf-8",
    )
    paths["csv"].write_text("category,item,status\nReceipt,id,Match\n", encoding="utf-8")
    return output_dir, archive_dir, paths


def _save(
    output_dir: Path,
    archive_dir: Path,
    paths: dict[str, Path | None],
    *,
    receipt_id: str = RECEIPT_ID,
    verdict: str = "Weekly pipeline receipt verified",
    status: str = "Verified",
    mismatch_count: int = 0,
):
    return save_epl_weekly_pipeline_verification_sidecar(
        pipeline_archive_path=archive_dir,
        pipeline_receipt_id=receipt_id,
        verification_paths=paths,
        verification_verdict=verdict,
        verification_status=status,
        original_receipt_id=receipt_id,
        recalculated_receipt_id=receipt_id,
        mismatch_count=mismatch_count,
        output_dir=output_dir,
        archived_at=RUN_AT,
    )


def _sealed_snapshot(archive_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(archive_dir).as_posix(): path.read_bytes()
        for path in archive_dir.rglob("*")
        if path.is_file()
    }


def test_sidecar_archives_exact_reports_with_stable_receipt_and_no_sealed_edits(
    tmp_path,
) -> None:
    output_dir, archive_dir, paths = _fixture(tmp_path)
    sealed_before = _sealed_snapshot(archive_dir)

    first = _save(output_dir, archive_dir, paths)
    second = _save(output_dir, archive_dir, paths)

    assert first["verdict"] == SIDECAR_ARCHIVED_VERDICT
    assert first["summary"]["sidecar_receipt_id"] == second["summary"][
        "sidecar_receipt_id"
    ]
    assert first["archive_dir"] != second["archive_dir"]
    assert second["archive_dir"].name.endswith("_02")
    for source in paths.values():
        assert source is not None
        copied = first["archive_dir"] / source.name
        assert copied.read_bytes() == source.read_bytes()
    for filename in (
        "epl_weekly_pipeline_verification_sidecar.json",
        "epl_weekly_pipeline_verification_sidecar.md",
        "epl_weekly_pipeline_verification_sidecar.csv",
    ):
        assert (first["archive_dir"] / filename).is_file()
    assert _sealed_snapshot(archive_dir) == sealed_before


def test_sidecar_receipt_changes_when_verification_report_content_changes(
    tmp_path,
) -> None:
    output_dir, archive_dir, paths = _fixture(tmp_path)
    first = _save(output_dir, archive_dir, paths)

    paths["markdown"].write_text("# Receipt verification changed\n", encoding="utf-8")
    second = _save(output_dir, archive_dir, paths)

    assert first["summary"]["sidecar_receipt_id"] != second["summary"][
        "sidecar_receipt_id"
    ]


def test_missing_verification_report_fails_closed_and_writes_sidecar_receipt(
    tmp_path,
) -> None:
    output_dir, archive_dir, paths = _fixture(tmp_path)
    paths["csv"].unlink()

    result = _save(output_dir, archive_dir, paths)

    assert result["verdict"] == SIDECAR_MISSING_VERDICT
    assert result["json"].is_file()
    assert result["markdown"].is_file()
    assert result["csv"].is_file()
    assert result["summary"]["evidence_status_counts"]["Missing"] == 1


@pytest.mark.parametrize(
    ("unsafe_receipt", "expected_status", "folder_fragment"),
    [
        ("../../outside", "Invalid", "invalid-receipt-"),
        ("", "Missing", "missing-receipt"),
    ],
)
def test_unsafe_or_missing_pipeline_receipt_uses_fallback_without_path_escape(
    tmp_path,
    unsafe_receipt: str,
    expected_status: str,
    folder_fragment: str,
) -> None:
    output_dir, archive_dir, paths = _fixture(
        tmp_path,
        receipt_id=unsafe_receipt,
    )

    result = _save(
        output_dir,
        archive_dir,
        paths,
        receipt_id=unsafe_receipt,
    )

    assert result["verdict"] == SIDECAR_NOT_READY_VERDICT
    assert result["archive_dir"].name.startswith(f"092230_{folder_fragment}")
    assert result["archive_dir"].is_relative_to(
        output_dir / "archive/epl_weekly_pipeline_verifications"
    )
    assert result["summary"]["pipeline_receipt_path_status"] == expected_status
    assert result["summary"]["blockers"]


def test_sidecar_identity_binds_every_required_receipt_input() -> None:
    evidence = [
        {
            "evidence_type": "verification_json",
            "archive_member_path": "verification.json",
            "checksum_sha256": "a" * 64,
            "size_bytes": 10,
            "status": "Archived",
        }
    ]
    base = {
        "pipeline_receipt_id": RECEIPT_ID,
        "pipeline_archive_path": "archive/epl_weekly_pipeline/run-a",
        "verification_verdict": "Weekly pipeline receipt verified",
        "verification_status": "Verified",
        "original_receipt_id": RECEIPT_ID,
        "recalculated_receipt_id": RECEIPT_ID,
        "mismatch_count": 0,
        "sidecar_verdict": SIDECAR_ARCHIVED_VERDICT,
        "evidence_records": evidence,
    }
    original = calculate_epl_weekly_pipeline_verification_sidecar_identity(**base)
    assert original == calculate_epl_weekly_pipeline_verification_sidecar_identity(
        **base
    )

    changes = (
        {"pipeline_receipt_id": "epl-weekly-other"},
        {"pipeline_archive_path": "archive/epl_weekly_pipeline/run-b"},
        {"verification_verdict": "Weekly pipeline receipt changed"},
        {"mismatch_count": 1},
        {
            "evidence_records": [
                {
                    **evidence[0],
                    "checksum_sha256": "b" * 64,
                }
            ]
        },
    )
    for change in changes:
        candidate = {**base, **change}
        assert (
            calculate_epl_weekly_pipeline_verification_sidecar_identity(**candidate)
            != original
        )


def test_mismatched_verification_receipt_is_archived_but_marked_failed(
    tmp_path,
) -> None:
    output_dir, archive_dir, paths = _fixture(tmp_path)
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    payload["recalculated_receipt_id"] = "epl-weekly-changed"
    paths["json"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = _save(output_dir, archive_dir, paths)

    assert result["verdict"] == SIDECAR_FAILED_VERDICT
    assert any("does not match" in item for item in result["summary"]["blockers"])


def test_archive_latest_uses_pipeline_summary_and_recent_list_is_read_only(
    tmp_path,
) -> None:
    output_dir, archive_dir, paths = _fixture(tmp_path)
    pipeline = {
        "archive_path": str(archive_dir),
        "archive_receipt_id": RECEIPT_ID,
        "receipt_verification_verdict": "Weekly pipeline receipt verified",
        "receipt_verification_status": "Verified",
        "receipt_verification_original_id": RECEIPT_ID,
        "receipt_verification_recalculated_id": RECEIPT_ID,
        "receipt_verification_mismatch_count": 0,
    }
    (output_dir / "epl_weekly_pipeline.json").write_text(
        json.dumps(pipeline, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source_before = {key: value.read_bytes() for key, value in paths.items()}

    result = archive_latest_epl_weekly_pipeline_verification(
        output_dir,
        archived_at=RUN_AT,
    )
    recent = list_recent_epl_weekly_pipeline_verification_sidecars(output_dir)

    assert result["verdict"] == SIDECAR_ARCHIVED_VERDICT
    assert len(recent) == 1
    assert recent.iloc[0]["pipeline_receipt_id"] == RECEIPT_ID
    assert {key: value.read_bytes() for key, value in paths.items()} == source_before


def test_dashboard_sidecar_surfaces_are_display_only() -> None:
    app_source = Path("app.py").read_text(encoding="utf-8")

    assert "Weekly pipeline verification sidecars" in app_source
    assert "Latest weekly verification sidecar" in app_source
    assert "list_recent_epl_weekly_pipeline_verification_sidecars" in app_source
    assert 'st.button("Archive Weekly Pipeline Verification' not in app_source
