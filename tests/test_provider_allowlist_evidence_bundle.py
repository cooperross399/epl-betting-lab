from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from epl_betting_lab.providers.base import file_sha256
from epl_betting_lab.reports.provider_allowlist_evidence_bundle import (
    BUNDLE_JSON_FILENAME,
    BUNDLE_VERDICTS,
    EVIDENCE_STATUSES,
    build_provider_allowlist_evidence_bundle,
    calculate_provider_allowlist_evidence_bundle_identity,
    save_provider_allowlist_evidence_bundle,
)
from epl_betting_lab.reports.provider_allowlist_evidence_bundle_verification import (
    VERIFICATION_STATUSES,
    VERIFICATION_VERDICTS,
    VERIFIED_VERDICT,
    build_provider_allowlist_evidence_bundle_verification,
    save_provider_allowlist_evidence_bundle_verification,
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import READY_STATUS
from epl_betting_lab.reports.provider_allowlist_pr_conformance import (
    CONFORMS_VERDICT,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    APPROVAL_DECISION,
    READY_VERDICT,
    calculate_shadow_archive_bundle_checksum,
)


RUN_AT = datetime(2026, 8, 14, 13, 30, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _repository_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _write_shadow_archive(
    root: Path,
    outputs: Path,
    *,
    hour: int,
) -> dict[str, object]:
    relative = Path("archive") / "provider_shadow_runs" / "2026-08-14" / (
        f"{hour:02d}0000_odds_api"
    )
    archive = outputs / relative
    shadow_path = archive / "provider_shadow_verification.json"
    _write_json(
        shadow_path,
        {
            "generated_at": f"2026-08-14T{hour:02d}:00:00+00:00",
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "mode": "Live shadow run",
            "verdict": "Shadow ready for review",
        },
    )
    metadata_path = archive / "archive_metadata.json"
    _write_json(
        metadata_path,
        {
            "schema_version": 1,
            "archive_id": relative.as_posix(),
            "generated_at": f"2026-08-14T{hour:02d}:00:00+00:00",
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "mode": "Live shadow run",
            "verdict": "Shadow ready for review",
            "files": {
                "shadow_json": {
                    "status": "Archived",
                    "archive_path": "provider_shadow_verification.json",
                    "checksum_sha256": file_sha256(shadow_path),
                }
            },
        },
    )
    bundle_checksum, file_count = calculate_shadow_archive_bundle_checksum(archive)
    return {
        "archive": archive,
        "archive_path": _repository_path(root, archive),
        "checklist_archive_path": relative.as_posix(),
        "metadata_path": _repository_path(root, metadata_path),
        "metadata_checksum_sha256": file_sha256(metadata_path),
        "checksum_sha256": bundle_checksum,
        "file_count": file_count,
        "generated_at": f"2026-08-14T{hour:02d}:00:00+00:00",
        "archive_integrity_status": "Verified",
        "current_integrity_status": "Verified",
        "provider_run_status": "Completed",
        "shadow_verdict": "Shadow ready for review",
        "staging_verdict": "Ready for handoff",
    }


def _prepare_ready_evidence(root: Path) -> dict[str, object]:
    outputs = root / "data" / "outputs"
    policy_path = root / "data" / "manual" / "staging_provider_policy.json"
    archives = [
        _write_shadow_archive(root, outputs, hour=12),
        _write_shadow_archive(root, outputs, hour=13),
    ]
    checklist_path = outputs / "provider_acceptance_checklist.json"
    reviewed_runs = [
        {
            "archive_path": item["checklist_archive_path"],
            "generated_at": item["generated_at"],
            "archive_integrity_status": "Verified",
            "provider_run_status": "Completed",
            "shadow_verdict": item["shadow_verdict"],
            "staging_verdict": item["staging_verdict"],
        }
        for item in archives
    ]
    _write_json(
        checklist_path,
        {
            "schema_version": 1,
            "generated_at": "2026-08-14T13:10:00+00:00",
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "verdict": READY_VERDICT,
            "review_window": 2,
            "reviewed_runs": reviewed_runs,
        },
    )
    comparison_path = outputs / "provider_shadow_run_comparison.json"
    _write_json(
        comparison_path,
        {
            "schema_version": 1,
            "generated_at": "2026-08-14T13:12:00+00:00",
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "verdict": "Stable enough for review",
            "previous_run": {
                "archive_path": archives[0]["checklist_archive_path"],
                "generated_at": archives[0]["generated_at"],
            },
            "latest_run": {
                "archive_path": archives[1]["checklist_archive_path"],
                "generated_at": archives[1]["generated_at"],
            },
        },
    )
    policy = {
        "allowed_provider_names": ["manual_reviewed"],
        "allowed_provider_types": ["manual_upload", "odds_api"],
        "allow_unknown_providers": False,
        "allow_missing_provenance": False,
        "max_receipt_age_hours": 12,
        "max_provider_run_age_hours": 12,
        "timezone": "America/New_York",
        "thursday_cutoff_time": "10:00",
    }
    _write_json(policy_path, policy)

    receipt_path = outputs / "provider_human_acceptance_receipt.json"
    receipt_id = "odds-api-human-review-123"
    receipt = {
        "schema_version": 1,
        "receipt_id": receipt_id,
        "created_at": "2026-08-14T13:15:00+00:00",
        "provider_key": "odds_api",
        "provider_name": "The Odds API",
        "reviewer_name": "Cooper Ross",
        "decision": APPROVAL_DECISION,
        "checklist_verdict": READY_VERDICT,
        "approval_gate": {"status": "Passed", "override_used": False},
        "evidence": {
            "checklist": {
                "path": _repository_path(root, checklist_path),
                "checksum_sha256": file_sha256(checklist_path),
                "status": "Bound",
                "verdict": READY_VERDICT,
            },
            "reviewed_shadow_archives": [
                {
                    key: item[key]
                    for key in (
                        "archive_path",
                        "checksum_sha256",
                        "metadata_path",
                        "metadata_checksum_sha256",
                        "file_count",
                        "generated_at",
                        "archive_integrity_status",
                        "current_integrity_status",
                        "provider_run_status",
                        "shadow_verdict",
                        "staging_verdict",
                    )
                }
                for item in archives
            ],
            "comparison": {
                "path": _repository_path(root, comparison_path),
                "checksum_sha256": file_sha256(comparison_path),
                "status": "Bound",
                "verdict": "Stable enough for review",
            },
            "provider_policy": {
                "path": _repository_path(root, policy_path),
                "checksum_sha256": file_sha256(policy_path),
                "status": "Bound",
            },
        },
    }
    _write_json(receipt_path, receipt)

    verification_path = (
        outputs / "provider_human_acceptance_receipt_verification.json"
    )
    verification = {
        "schema_version": 1,
        "generated_at": "2026-08-14T13:20:00+00:00",
        "provider_key": "odds_api",
        "provider_name": "The Odds API",
        "verdict": "Verified for allowlist PR review",
        "receipt_path": _repository_path(root, receipt_path),
        "receipt_checksum_sha256": file_sha256(receipt_path),
        "receipt_id": receipt_id,
        "reviewer_name": "Cooper Ross",
        "decision": APPROVAL_DECISION,
        "checklist_verdict": READY_VERDICT,
        "receipt_created_at": "2026-08-14T13:15:00+00:00",
    }
    _write_json(verification_path, verification)

    preview_path = outputs / "provider_allowlist_pr_preview.json"
    preview = {
        "schema_version": 1,
        "generated_at": "2026-08-14T13:25:00+00:00",
        "status": READY_STATUS,
        "provider_key": "odds_api",
        "provider_name": "The Odds API",
        "provider_type": "odds_api",
        "verification": {
            "path": _repository_path(root, verification_path),
            "checksum_sha256": file_sha256(verification_path),
            "verdict": "Verified for allowlist PR review",
            "receipt_path": _repository_path(root, receipt_path),
            "receipt_checksum_sha256": file_sha256(receipt_path),
            "receipt_id": receipt_id,
        },
        "policy": {
            "path": _repository_path(root, policy_path),
            "checksum_sha256": file_sha256(policy_path),
        },
        "before_policy": policy,
        "after_policy": {**policy, "preview_only_provider": "the_odds_api"},
        "recommended_pr_title": "Allowlist The Odds API staging provider",
        "recommended_pr_description": "Apply only the reviewed provider policy change.",
    }
    _write_json(preview_path, preview)
    return {
        "outputs": outputs,
        "policy": policy_path,
        "archives": archives,
        "checklist": checklist_path,
        "comparison": comparison_path,
        "receipt": receipt_path,
        "verification": verification_path,
        "preview": preview_path,
    }


def _build(root: Path, fixture: dict[str, object]):
    return build_provider_allowlist_evidence_bundle(
        "odds_api",
        fixture["outputs"],
        policy_path=fixture["policy"],
        repository_root=root,
        run_at=RUN_AT,
    )


def _write_conformance(
    root: Path,
    fixture: dict[str, object],
    *,
    preview_checksum: str | None = None,
) -> Path:
    preview = json.loads(fixture["preview"].read_text(encoding="utf-8"))
    _write_json(fixture["policy"], preview["after_policy"])
    conformance_path = (
        fixture["outputs"] / "provider_allowlist_pr_conformance.json"
    )
    _write_json(
        conformance_path,
        {
            "schema_version": 1,
            "generated_at": "2026-08-14T13:28:00+00:00",
            "verdict": CONFORMS_VERDICT,
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "preview": {
                "path": _repository_path(root, fixture["preview"]),
                "checksum_sha256": preview_checksum
                or file_sha256(fixture["preview"]),
            },
            "policy": {
                "path": _repository_path(root, fixture["policy"]),
                "checksum_sha256": file_sha256(fixture["policy"]),
            },
            "expected_policy": preview["after_policy"],
            "actual_policy": preview["after_policy"],
        },
    )
    return conformance_path


def test_statuses_and_verdicts_are_explicit() -> None:
    assert EVIDENCE_STATUSES == (
        "Included",
        "Missing",
        "Checksum mismatch",
        "Stale",
        "Not applicable",
    )
    assert BUNDLE_VERDICTS == (
        "Evidence bundle ready for PR review",
        "Missing required evidence",
        "Evidence changed",
        "Not ready for PR review",
    )


def test_ready_bundle_binds_all_required_evidence_deterministically(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)

    evidence, summary = _build(tmp_path, fixture)
    _, repeated = _build(tmp_path, fixture)

    assert summary["verdict"] == "Evidence bundle ready for PR review"
    assert summary["bundle_id"] == repeated["bundle_id"]
    assert summary["bundle_checksum_sha256"] == repeated["bundle_checksum_sha256"]
    assert len(summary["bundle_checksum_sha256"]) == 64
    assert set(evidence.loc[evidence["required"] == "Yes", "status"]) == {
        "Included"
    }
    conformance = evidence.loc[
        evidence["evidence_type"] == "provider_allowlist_pr_conformance"
    ].iloc[0]
    assert conformance["status"] == "Not applicable"
    archive_files = evidence.loc[
        evidence["evidence_type"] == "reviewed_shadow_archive_file"
    ]
    assert len(archive_files) == 4
    assert set(archive_files["status"]) == {"Included"}


def test_changed_bound_checklist_marks_evidence_changed(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    checklist = fixture["checklist"]
    payload = json.loads(checklist.read_text(encoding="utf-8"))
    payload["changed_after_review"] = True
    _write_json(checklist, payload)

    evidence, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == "Evidence changed"
    row = evidence.loc[
        evidence["evidence_type"] == "provider_acceptance_checklist"
    ].iloc[0]
    assert row["status"] == "Checksum mismatch"


def test_missing_comparison_fails_closed(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    fixture["comparison"].unlink()

    evidence, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == "Missing required evidence"
    row = evidence.loc[
        evidence["evidence_type"] == "provider_shadow_run_comparison"
    ].iloc[0]
    assert row["status"] == "Missing"


def test_non_ready_verification_is_not_ready_without_checksum_drift(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    verification = json.loads(fixture["verification"].read_text(encoding="utf-8"))
    verification["verdict"] = "Evidence changed"
    _write_json(fixture["verification"], verification)
    preview = json.loads(fixture["preview"].read_text(encoding="utf-8"))
    preview["verification"]["checksum_sha256"] = file_sha256(
        fixture["verification"]
    )
    _write_json(fixture["preview"], preview)

    evidence, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == "Not ready for PR review"
    row = evidence.loc[
        evidence["evidence_type"]
        == "provider_human_acceptance_receipt_verification"
    ].iloc[0]
    assert row["status"] == "Stale"


def test_changed_archive_bytes_mark_evidence_changed(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    shadow = fixture["archives"][0]["archive"] / "provider_shadow_verification.json"
    payload = json.loads(shadow.read_text(encoding="utf-8"))
    payload["changed_after_review"] = True
    _write_json(shadow, payload)

    evidence, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == "Evidence changed"
    archive_rows = evidence.loc[
        evidence["evidence_type"] == "reviewed_shadow_archive_bundle"
    ]
    assert "Checksum mismatch" in set(archive_rows["status"])


def test_newer_live_archive_marks_review_window_stale(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    _write_shadow_archive(tmp_path, fixture["outputs"], hour=14)

    evidence, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == "Not ready for PR review"
    row = evidence.loc[
        evidence["evidence_type"] == "provider_shadow_run_comparison"
    ].iloc[0]
    assert row["status"] == "Stale"
    assert "Newer or different live shadow archives" in row["details"]


def test_valid_post_policy_conformance_is_included(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    _write_conformance(tmp_path, fixture)

    evidence, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == "Evidence bundle ready for PR review"
    row = evidence.loc[
        evidence["evidence_type"] == "provider_allowlist_pr_conformance"
    ].iloc[0]
    assert row["status"] == "Included"
    assert row["verdict"] == CONFORMS_VERDICT


def test_conformance_bound_to_different_preview_marks_evidence_changed(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    _write_conformance(tmp_path, fixture, preview_checksum="a" * 64)

    evidence, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == "Evidence changed"
    binding = evidence.loc[
        evidence["evidence_type"] == "conformance_preview_binding"
    ].iloc[0]
    assert binding["status"] == "Checksum mismatch"


def test_save_writes_latest_and_dated_archived_bundle(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)

    result = save_provider_allowlist_evidence_bundle(
        "odds_api",
        fixture["outputs"],
        policy_path=fixture["policy"],
        repository_root=tmp_path,
        run_at=RUN_AT,
    )

    assert result["verdict"] == "Evidence bundle ready for PR review"
    assert result["json"].is_file()
    assert result["markdown"].is_file()
    assert result["csv"].is_file()
    assert "2026-08-14" in result["archive_directory"].parts
    assert set(path.name for path in result["archive_paths"].values()) == {
        "provider_allowlist_evidence_bundle.json",
        "provider_allowlist_evidence_bundle.md",
        "provider_allowlist_evidence_bundle.csv",
    }
    assert all(path.is_file() for path in result["archive_paths"].values())
    markdown = result["markdown"].read_text(encoding="utf-8")
    assert "Nothing was applied" in markdown
    assert "Allowlist The Odds API staging provider" in markdown


def _save_ready_bundle(root: Path, fixture: dict[str, object]) -> dict[str, object]:
    return save_provider_allowlist_evidence_bundle(
        "odds_api",
        fixture["outputs"],
        policy_path=fixture["policy"],
        repository_root=root,
        run_at=RUN_AT,
    )


def _verify_bundle(
    root: Path,
    fixture: dict[str, object],
    *,
    bundle_path: Path | None = None,
):
    return build_provider_allowlist_evidence_bundle_verification(
        "odds_api",
        fixture["outputs"],
        bundle_path=bundle_path,
        repository_root=root,
        run_at=RUN_AT,
    )


def test_bundle_verification_statuses_and_verdicts_are_explicit() -> None:
    assert VERIFICATION_STATUSES == (
        "Verified",
        "Missing evidence",
        "Checksum mismatch",
        "Bundle ID mismatch",
        "Malformed bundle",
        "Not ready",
        "Not applicable",
    )
    assert VERIFICATION_VERDICTS == (
        "Evidence bundle verified for PR approval review",
        "Missing required evidence",
        "Evidence changed",
        "Bundle mismatch",
        "Malformed bundle",
        "Not ready for PR approval review",
    )


def test_latest_archived_ready_bundle_verifies(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    saved = _save_ready_bundle(tmp_path, fixture)

    checks, summary = _verify_bundle(tmp_path, fixture)

    assert summary["verdict"] == VERIFIED_VERDICT
    assert summary["bundle_source"] == "Latest archived provider bundle"
    assert summary["bundle_path"] == _repository_path(
        tmp_path,
        saved["archive_paths"]["provider_allowlist_evidence_bundle.json"],
    )
    assert summary["bundle_id"] == summary["current_evidence_bundle_id"]
    assert summary["bundle_checksum_sha256"] == (
        summary["current_evidence_bundle_checksum_sha256"]
    )
    assert set(checks["status"]) <= {"Verified", "Not applicable"}
    policy = checks.loc[checks["check"] == "Provider policy checksum"].iloc[0]
    assert policy["status"] == "Verified"


def test_bundle_verification_detects_changed_evidence(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    _save_ready_bundle(tmp_path, fixture)
    checklist = json.loads(fixture["checklist"].read_text(encoding="utf-8"))
    checklist["changed_after_bundle"] = True
    _write_json(fixture["checklist"], checklist)

    checks, summary = _verify_bundle(tmp_path, fixture)

    assert summary["verdict"] == "Evidence changed"
    changed = checks.loc[
        checks["evidence_path"] == _repository_path(
            tmp_path,
            fixture["checklist"],
        )
    ].iloc[0]
    assert changed["status"] == "Checksum mismatch"


def test_bundle_verification_detects_missing_required_evidence(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    _save_ready_bundle(tmp_path, fixture)
    fixture["comparison"].unlink()

    checks, summary = _verify_bundle(tmp_path, fixture)

    assert summary["verdict"] == "Missing required evidence"
    missing = checks.loc[
        checks["evidence_path"] == _repository_path(
            tmp_path,
            fixture["comparison"],
        )
    ].iloc[0]
    assert missing["status"] == "Missing evidence"


def test_bundle_verification_detects_internal_bundle_id_tampering(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    saved = _save_ready_bundle(tmp_path, fixture)
    bundle_path = saved["archive_paths"]["provider_allowlist_evidence_bundle.json"]
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["bundle_id"] = "odds-api-allowlist-evidence-tampered"
    _write_json(bundle_path, bundle)

    checks, summary = _verify_bundle(
        tmp_path,
        fixture,
        bundle_path=bundle_path,
    )

    assert summary["verdict"] == "Bundle mismatch"
    identity = checks.loc[
        checks["check"] == "Recorded manifest identity"
    ].iloc[0]
    assert identity["status"] == "Bundle ID mismatch"


def test_bundle_verification_rejects_omitted_required_evidence_category(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    saved = _save_ready_bundle(tmp_path, fixture)
    bundle_path = saved["archive_paths"]["provider_allowlist_evidence_bundle.json"]
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    omitted_paths = {
        row["evidence_path"]
        for row in bundle["evidence"]
        if row["evidence_type"] == "provider_acceptance_checklist"
    }
    bundle["evidence"] = [
        row
        for row in bundle["evidence"]
        if row["evidence_type"] != "provider_acceptance_checklist"
    ]
    bundle["evidence_manifest"] = [
        row
        for row in bundle["evidence_manifest"]
        if row["path"] not in omitted_paths
    ]
    bundle["evidence_file_count"] = len(bundle["evidence_manifest"])
    checksum, bundle_id = calculate_provider_allowlist_evidence_bundle_identity(
        "odds_api",
        bundle["evidence_manifest"],
    )
    bundle["bundle_checksum_sha256"] = checksum
    bundle["bundle_id"] = bundle_id
    _write_json(bundle_path, bundle)

    checks, summary = _verify_bundle(
        tmp_path,
        fixture,
        bundle_path=bundle_path,
    )

    assert summary["verdict"] == "Missing required evidence"
    missing = checks.loc[
        (checks["check"] == "Required evidence category")
        & (checks["evidence_type"] == "provider_acceptance_checklist")
    ].iloc[0]
    assert missing["status"] == "Missing evidence"


def test_bundle_verification_rejects_malformed_bundle(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    bundle_path = fixture["outputs"] / "malformed_bundle.json"
    bundle_path.write_text("{not-json", encoding="utf-8")

    checks, summary = _verify_bundle(
        tmp_path,
        fixture,
        bundle_path=bundle_path,
    )

    assert summary["verdict"] == "Malformed bundle"
    assert checks.iloc[0]["status"] == "Malformed bundle"


def test_bundle_verification_does_not_read_outside_repository(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    outside_path = tmp_path.parent / f"{tmp_path.name}_outside_bundle.json"
    _write_json(outside_path, {"verdict": "Evidence bundle ready for PR review"})

    checks, summary = _verify_bundle(
        tmp_path,
        fixture,
        bundle_path=outside_path,
    )

    assert summary["verdict"] == "Malformed bundle"
    assert checks.iloc[0]["check"] == "Bundle path safety"
    assert checks.iloc[0]["status"] == "Malformed bundle"


def test_default_latest_output_without_archive_is_not_approval_ready(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    saved = _save_ready_bundle(tmp_path, fixture)
    archived_bundle = json.loads(
        saved["archive_paths"][BUNDLE_JSON_FILENAME].read_text(encoding="utf-8")
    )
    fallback_outputs = tmp_path / "data" / "fallback_outputs"
    fallback_bundle = fallback_outputs / BUNDLE_JSON_FILENAME
    _write_json(fallback_bundle, archived_bundle)

    checks, summary = build_provider_allowlist_evidence_bundle_verification(
        "odds_api",
        fallback_outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Not ready for PR approval review"
    selection = checks.loc[
        checks["check"] == "Archived bundle selection"
    ].iloc[0]
    assert selection["status"] == "Not ready"


def test_bundle_verification_rejects_non_ready_original_bundle(
    tmp_path: Path,
) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    saved = _save_ready_bundle(tmp_path, fixture)
    bundle_path = saved["archive_paths"]["provider_allowlist_evidence_bundle.json"]
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["verdict"] = "Not ready for PR review"
    _write_json(bundle_path, bundle)

    checks, summary = _verify_bundle(
        tmp_path,
        fixture,
        bundle_path=bundle_path,
    )

    assert summary["verdict"] == "Not ready for PR approval review"
    original = checks.loc[checks["check"] == "Original bundle verdict"].iloc[0]
    assert original["status"] == "Not ready"


def test_save_bundle_verification_writes_read_only_reports(tmp_path: Path) -> None:
    fixture = _prepare_ready_evidence(tmp_path)
    _save_ready_bundle(tmp_path, fixture)

    result = save_provider_allowlist_evidence_bundle_verification(
        "odds_api",
        fixture["outputs"],
        repository_root=tmp_path,
        run_at=RUN_AT,
    )

    assert result["verdict"] == VERIFIED_VERDICT
    assert result["json"].is_file()
    assert result["markdown"].is_file()
    assert result["csv"].is_file()
    markdown = result["markdown"].read_text(encoding="utf-8")
    assert "Nothing was applied" in markdown
    assert "Evidence bundle verified for PR approval review" in markdown
