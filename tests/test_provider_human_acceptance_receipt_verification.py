from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import pytest

from epl_betting_lab.providers.base import file_sha256
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    APPROVAL_DECISION,
    RECEIPT_JSON_FILENAME,
    process_provider_human_acceptance_receipt,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt_verification import (
    VERDICTS,
    VERIFICATION_STATUSES,
    build_provider_human_acceptance_receipt_verification,
    save_provider_human_acceptance_receipt_verification,
)


RUN_AT = datetime(2026, 8, 7, 14, 30, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_shadow_archive(outputs: Path, hour: int) -> dict[str, object]:
    relative = Path("archive") / "provider_shadow_runs" / "2026-08-07" / (
        f"{hour:02d}0000_odds_api"
    )
    archive = outputs / relative
    verification_path = archive / "provider_shadow_verification.json"
    _write_json(
        verification_path,
        {
            "generated_at": f"2026-08-07T{hour:02d}:00:00+00:00",
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "mode": "Live shadow run",
            "verdict": "Needs provider policy review",
        },
    )
    _write_json(
        archive / "archive_metadata.json",
        {
            "archive_id": relative.as_posix(),
            "generated_at": f"2026-08-07T{hour:02d}:00:00+00:00",
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "mode": "Live shadow run",
            "files": {
                "shadow_json": {
                    "status": "Archived",
                    "archive_path": "provider_shadow_verification.json",
                    "checksum_sha256": file_sha256(verification_path),
                }
            },
        },
    )
    return {
        "generated_at": f"2026-08-07T{hour:02d}:00:00+00:00",
        "archive_path": relative.as_posix(),
        "archive_integrity_status": "Verified",
        "provider_run_status": "Completed",
        "shadow_verdict": "Needs provider policy review",
        "staging_verdict": "Needs fixes",
    }


def _prepare_receipt(
    root: Path,
    *,
    decision: str = APPROVAL_DECISION,
    checklist_verdict: str = "Ready for human allowlist review",
    allow_override: bool = False,
    include_comparison: bool = True,
    include_policy: bool = True,
) -> tuple[Path, Path, Path]:
    outputs = root / "data" / "outputs"
    reviewed = [
        _write_shadow_archive(outputs, 13),
        _write_shadow_archive(outputs, 12),
    ]
    _write_json(
        outputs / "provider_acceptance_checklist.json",
        {
            "generated_at": "2026-08-07T14:00:00+00:00",
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "verdict": checklist_verdict,
            "review_window": 5,
            "reviewed_runs": reviewed,
        },
    )
    if include_comparison:
        _write_json(
            outputs / "provider_shadow_run_comparison.json",
            {
                "generated_at": "2026-08-07T13:30:00+00:00",
                "provider_key": "odds_api",
                "provider_name": "The Odds API",
                "verdict": "Stable enough for review",
            },
        )
    policy = root / "data" / "manual" / "staging_provider_policy.json"
    if include_policy:
        _write_json(
            policy,
            {
                "allowed_provider_names": ["manual_reviewed"],
                "allowed_provider_types": ["manual_upload"],
            },
        )
    receipt = process_provider_human_acceptance_receipt(
        "odds_api",
        "Cooper Ross",
        decision,
        notes="Reviewed the exact archived evidence.",
        output_dir=outputs,
        policy_path=policy,
        allow_not_ready_approval=allow_override,
        write_receipt=True,
        run_at=RUN_AT,
    )
    return outputs, policy, Path(receipt["json"])


def test_verification_statuses_and_verdicts_are_explicit() -> None:
    assert VERIFICATION_STATUSES == (
        "Verified",
        "Missing evidence",
        "Checksum mismatch",
        "Malformed receipt",
        "Stale evidence",
        "Decision not approval",
        "Not ready",
    )
    assert VERDICTS == (
        "Verified for allowlist PR review",
        "Receipt not approval",
        "Evidence changed",
        "Missing evidence",
        "Malformed receipt",
        "Not ready for allowlist PR",
    )


def test_ready_approval_receipt_verifies_all_bound_evidence(tmp_path: Path) -> None:
    outputs, _, receipt_path = _prepare_receipt(tmp_path)

    checks, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Verified for allowlist PR review"
    assert set(checks["status"]) == {"Verified"}
    assert summary["reviewer_name"] == "Cooper Ross"
    assert summary["decision"] == APPROVAL_DECISION
    assert summary["safety"]["provider_policy_edited"] is False
    assert (
        checks.loc[
            checks["check"] == "Latest live archive set",
            "status",
        ].iloc[0]
        == "Verified"
    )


def test_optional_unbound_comparison_and_policy_do_not_fake_checksums(
    tmp_path: Path,
) -> None:
    outputs, _, receipt_path = _prepare_receipt(
        tmp_path,
        include_comparison=False,
        include_policy=False,
    )

    checks, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Verified for allowlist PR review"
    optional = checks[checks["check"].isin(
        ["Matching shadow comparison checksum", "Provider policy checksum"]
    )]
    assert set(optional["status"]) == {"Verified"}
    assert all(value in {"Not available", ""} for value in optional["observed"])


def test_changed_checklist_checksum_marks_evidence_changed(tmp_path: Path) -> None:
    outputs, _, receipt_path = _prepare_receipt(tmp_path)
    checklist = outputs / "provider_acceptance_checklist.json"
    payload = json.loads(checklist.read_text(encoding="utf-8"))
    payload["extra_note"] = "changed after receipt"
    _write_json(checklist, payload)

    checks, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Evidence changed"
    assert "Checksum mismatch" in set(checks["status"])


@pytest.mark.parametrize(
    ("relative_path", "check_name"),
    [
        (
            "data/outputs/provider_shadow_run_comparison.json",
            "Matching shadow comparison checksum",
        ),
        (
            "data/manual/staging_provider_policy.json",
            "Provider policy checksum",
        ),
    ],
)
def test_changed_optional_bound_file_marks_evidence_changed(
    tmp_path: Path,
    relative_path: str,
    check_name: str,
) -> None:
    outputs, _, receipt_path = _prepare_receipt(tmp_path)
    evidence_path = tmp_path / relative_path
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["changed_after_review"] = True
    _write_json(evidence_path, payload)

    checks, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Evidence changed"
    assert (
        checks.loc[checks["check"] == check_name, "status"].iloc[0]
        == "Checksum mismatch"
    )


def test_changed_shadow_archive_checksum_marks_evidence_changed(
    tmp_path: Path,
) -> None:
    outputs, _, receipt_path = _prepare_receipt(tmp_path)
    shadow = (
        outputs
        / "archive/provider_shadow_runs/2026-08-07/130000_odds_api"
        / "provider_shadow_verification.json"
    )
    shadow.write_text('{"changed": true}\n', encoding="utf-8")

    checks, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Evidence changed"
    archive_checks = checks[checks["check"].str.contains("archive 1")]
    assert set(archive_checks["status"]).intersection(
        {"Checksum mismatch", "Stale evidence"}
    )


def test_missing_archive_marks_missing_evidence(tmp_path: Path) -> None:
    outputs, _, receipt_path = _prepare_receipt(tmp_path)
    shutil.rmtree(
        outputs / "archive/provider_shadow_runs/2026-08-07/130000_odds_api"
    )

    _, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Missing evidence"


def test_newer_live_archive_marks_receipt_stale(tmp_path: Path) -> None:
    outputs, _, receipt_path = _prepare_receipt(tmp_path)
    _write_shadow_archive(outputs, 14)

    checks, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Evidence changed"
    assert (
        checks.loc[
            checks["check"] == "Latest live archive set",
            "status",
        ].iloc[0]
        == "Stale evidence"
    )


def test_non_approval_receipt_gets_non_approval_verdict(tmp_path: Path) -> None:
    outputs, _, receipt_path = _prepare_receipt(
        tmp_path,
        decision="rejected",
    )

    _, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Receipt not approval"


def test_not_ready_override_receipt_remains_not_ready(tmp_path: Path) -> None:
    outputs, _, receipt_path = _prepare_receipt(
        tmp_path,
        checklist_verdict="Needs more shadow runs",
        allow_override=True,
    )

    checks, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Not ready for allowlist PR"
    assert "Not ready" in set(checks["status"])


def test_tampered_human_field_makes_receipt_malformed(tmp_path: Path) -> None:
    outputs, _, receipt_path = _prepare_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["reviewer_name"] = "Different Reviewer"
    _write_json(receipt_path, receipt)

    checks, summary = build_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Malformed receipt"
    assert (
        checks.loc[checks["check"] == "Receipt ID", "status"].iloc[0]
        == "Malformed receipt"
    )


@pytest.mark.parametrize(
    ("receipt_content", "expected_verdict"),
    [
        (None, "Missing evidence"),
        ("{not-json", "Malformed receipt"),
    ],
)
def test_missing_or_malformed_receipt_still_writes_verification_reports(
    tmp_path: Path,
    receipt_content: str | None,
    expected_verdict: str,
) -> None:
    outputs = tmp_path / "data" / "outputs"
    receipt_path = outputs / RECEIPT_JSON_FILENAME
    outputs.mkdir(parents=True)
    if receipt_content is not None:
        receipt_path.write_text(receipt_content, encoding="utf-8")

    result = save_provider_human_acceptance_receipt_verification(
        "odds_api",
        outputs,
        receipt_path=receipt_path,
        run_at=RUN_AT,
    )

    assert result["verdict"] == expected_verdict
    assert Path(result["json"]).is_file()
    assert Path(result["markdown"]).is_file()
    assert Path(result["csv"]).is_file()
    assert "does not make that policy change" in Path(result["markdown"]).read_text(
        encoding="utf-8"
    )
