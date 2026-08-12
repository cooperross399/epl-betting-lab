from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from epl_betting_lab.providers.base import file_sha256
from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    BLOCKED_STATUS,
    NO_CHANGE_STATUS,
    READY_STATUS,
    build_provider_allowlist_pr_preview,
    save_provider_allowlist_pr_preview,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    APPROVAL_DECISION,
    READY_VERDICT,
)


RUN_AT = datetime(2026, 8, 13, 13, 0, tzinfo=timezone.utc)
RECEIPT_AT = "2026-08-13T12:30:00+00:00"
VERIFIED_AT = "2026-08-13T12:45:00+00:00"
RECEIPT_ID = "odds_api-20260813T123000+0000-reviewed"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _policy() -> dict[str, object]:
    return {
        "allowed_provider_names": ["manual_reviewed"],
        "allowed_provider_types": [
            "manual_upload",
            "sportsbook_export",
            "odds_api",
            "fixture_provider",
        ],
        "allow_unknown_providers": False,
        "allow_missing_provenance": False,
        "max_receipt_age_hours": 12,
        "max_provider_run_age_hours": 12,
        "timezone": "America/New_York",
        "thursday_cutoff_time": "10:00",
    }


def _prepare_verified_evidence(
    root: Path,
    *,
    verification_verdict: str = "Verified for allowlist PR review",
    verification_provider: str = "odds_api",
    bind_policy: bool = True,
    already_allowed: bool = False,
) -> tuple[Path, Path, Path]:
    outputs = root / "data" / "outputs"
    policy_path = root / "data" / "manual" / "staging_provider_policy.json"
    policy = _policy()
    if already_allowed:
        policy["allowed_provider_names"] = ["manual_reviewed", "the_odds_api"]
    _write_json(policy_path, policy)
    policy_checksum = file_sha256(policy_path)

    receipt_path = outputs / "provider_human_acceptance_receipt.json"
    policy_evidence = (
        {
            "status": "Bound",
            "path": str(policy_path),
            "checksum_sha256": policy_checksum,
        }
        if bind_policy
        else {"status": "Not available", "path": "", "checksum_sha256": ""}
    )
    _write_json(
        receipt_path,
        {
            "schema_version": 1,
            "receipt_id": RECEIPT_ID,
            "created_at": RECEIPT_AT,
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "reviewer_name": "Cooper Ross",
            "decision": APPROVAL_DECISION,
            "checklist_verdict": READY_VERDICT,
            "approval_gate": {
                "status": "Passed",
                "override_used": False,
            },
            "evidence": {"provider_policy": policy_evidence},
        },
    )
    receipt_checksum = file_sha256(receipt_path)

    verification_path = outputs / "provider_human_acceptance_receipt_verification.json"
    policy_check = {
        "category": "Evidence",
        "check": "Provider policy checksum",
        "status": "Verified",
        "expected": policy_checksum,
        "observed": policy_checksum,
        "evidence_path": str(policy_path),
        "details": "Policy matched during verification.",
    }
    _write_json(
        verification_path,
        {
            "generated_at": VERIFIED_AT,
            "provider_key": verification_provider,
            "provider_name": "The Odds API",
            "receipt_path": str(receipt_path),
            "receipt_checksum_sha256": receipt_checksum,
            "receipt_id": RECEIPT_ID,
            "reviewer_name": "Cooper Ross",
            "decision": APPROVAL_DECISION,
            "receipt_created_at": RECEIPT_AT,
            "checklist_verdict": READY_VERDICT,
            "verdict": verification_verdict,
            "checks": [
                {
                    "category": "Receipt fields",
                    "check": "Receipt ID",
                    "status": "Verified",
                    "expected": RECEIPT_ID,
                    "observed": RECEIPT_ID,
                    "evidence_path": str(receipt_path),
                    "details": "Receipt ID verified.",
                },
                policy_check,
            ],
            "safety": {"read_only_evidence_check": True},
        },
    )
    return outputs, policy_path, verification_path


def _build(
    root: Path,
    outputs: Path,
    policy_path: Path,
    verification_path: Path,
):
    return build_provider_allowlist_pr_preview(
        "odds_api",
        outputs,
        verification_path=verification_path,
        policy_path=policy_path,
        repository_root=root,
        run_at=RUN_AT,
    )


def test_verified_receipt_builds_exact_read_only_policy_proposal(
    tmp_path: Path,
) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(tmp_path)
    original_policy = policy_path.read_bytes()

    changes, summary = _build(
        tmp_path,
        outputs,
        policy_path,
        verification_path,
    )

    assert summary["status"] == READY_STATUS
    assert summary["blockers"] == []
    assert policy_path.read_bytes() == original_policy
    assert summary["before_policy"]["allowed_provider_names"] == ["manual_reviewed"]
    assert summary["after_policy"]["allowed_provider_names"] == [
        "manual_reviewed",
        "the_odds_api",
    ]
    entry = summary["proposed_provider_entry"]
    assert entry["provider_name"] == "the_odds_api"
    assert entry["provider_type"] == "odds_api"
    assert entry["allowlist_status"] == "allowed"
    assert entry["max_provider_run_age_hours"] == 12.0
    assert entry["cutoff_policy"] == {
        "day": "Thursday",
        "time": "10:00",
        "timezone": "America/New_York",
    }
    assert entry["required_markets"] == ["1x2", "total_2_5"]
    assert any("BTTS is not requested" in item for item in entry["known_limitations"])
    assert entry["evidence_receipt_id"] == RECEIPT_ID
    assert entry["verification_report_checksum_sha256"] == file_sha256(
        verification_path
    )
    assert entry["reviewer_name"] == "Cooper Ross"
    assert entry["reviewed_at"] == VERIFIED_AT
    assert entry["approved_at"] == RECEIPT_AT
    assert "the_odds_api" in summary["policy_diff"]
    assert summary["recommended_pr_title"] == (
        "Allowlist the_odds_api staging provider"
    )
    assert not changes.empty
    assert summary["safety"]["provider_policy_edited"] is False
    assert summary["safety"]["receipt_verified_by_side_effect"] is False


def test_save_writes_reports_without_changing_policy(tmp_path: Path) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(tmp_path)
    original_policy = policy_path.read_bytes()

    result = save_provider_allowlist_pr_preview(
        "odds_api",
        outputs,
        verification_path=verification_path,
        policy_path=policy_path,
        repository_root=tmp_path,
        run_at=RUN_AT,
    )

    assert result["status"] == READY_STATUS
    assert Path(result["json"]).is_file()
    assert Path(result["markdown"]).is_file()
    assert Path(result["csv"]).is_file()
    markdown = Path(result["markdown"]).read_text(encoding="utf-8")
    assert "Preview only: nothing was applied" in markdown
    assert "## Diff preview" in markdown
    assert "## Recommended separate PR" in markdown
    assert policy_path.read_bytes() == original_policy


def test_non_verified_receipt_report_blocks_policy_proposal(tmp_path: Path) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(
        tmp_path,
        verification_verdict="Evidence changed",
    )

    _, summary = _build(tmp_path, outputs, policy_path, verification_path)

    assert summary["status"] == BLOCKED_STATUS
    assert summary["after_policy"] == summary["before_policy"]
    assert summary["proposed_provider_entry"] == {}
    assert any("Verified for allowlist PR review" in item for item in summary["blockers"])


def test_changed_receipt_after_verification_blocks_preview(tmp_path: Path) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(tmp_path)
    receipt_path = outputs / "provider_human_acceptance_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["notes"] = "Changed after verification"
    _write_json(receipt_path, receipt)

    _, summary = _build(tmp_path, outputs, policy_path, verification_path)

    assert summary["status"] == BLOCKED_STATUS
    assert any("receipt changed after verification" in item for item in summary["blockers"])


def test_changed_policy_after_verification_blocks_preview(tmp_path: Path) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(tmp_path)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["max_provider_run_age_hours"] = 6
    _write_json(policy_path, policy)

    _, summary = _build(tmp_path, outputs, policy_path, verification_path)

    assert summary["status"] == BLOCKED_STATUS
    assert any("policy changed after human approval" in item for item in summary["blockers"])


def test_unbound_policy_evidence_blocks_preview(tmp_path: Path) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(
        tmp_path,
        bind_policy=False,
    )

    _, summary = _build(tmp_path, outputs, policy_path, verification_path)

    assert summary["status"] == BLOCKED_STATUS
    assert "The human receipt did not bind the provider policy." in summary["blockers"]


def test_provider_mismatch_blocks_preview(tmp_path: Path) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(
        tmp_path,
        verification_provider="manual",
    )

    _, summary = _build(tmp_path, outputs, policy_path, verification_path)

    assert summary["status"] == BLOCKED_STATUS
    assert any("not `odds_api`" in item for item in summary["blockers"])


def test_already_allowed_provider_needs_no_policy_change(tmp_path: Path) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(
        tmp_path,
        already_allowed=True,
    )

    _, summary = _build(tmp_path, outputs, policy_path, verification_path)

    assert summary["status"] == NO_CHANGE_STATUS
    assert summary["after_policy"] == summary["before_policy"]
    assert summary["proposed_provider_entry"] == {}
    assert any("already" in item for item in summary["warnings"])


def test_malformed_existing_provider_metadata_blocks_preview(tmp_path: Path) -> None:
    outputs, policy_path, verification_path = _prepare_verified_evidence(tmp_path)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["provider_allowlist_entries"] = []
    _write_json(policy_path, policy)
    new_checksum = file_sha256(policy_path)

    receipt_path = outputs / "provider_human_acceptance_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["evidence"]["provider_policy"]["checksum_sha256"] = new_checksum
    _write_json(receipt_path, receipt)
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    verification["receipt_checksum_sha256"] = file_sha256(receipt_path)
    verification["checks"][1]["expected"] = new_checksum
    verification["checks"][1]["observed"] = new_checksum
    _write_json(verification_path, verification)

    _, summary = _build(tmp_path, outputs, policy_path, verification_path)

    assert summary["status"] == BLOCKED_STATUS
    assert "`provider_allowlist_entries` must be a JSON object." in summary["blockers"]


def test_missing_verification_writes_blocked_beginner_reports(tmp_path: Path) -> None:
    outputs = tmp_path / "data" / "outputs"
    policy_path = tmp_path / "data" / "manual" / "staging_provider_policy.json"
    _write_json(policy_path, _policy())
    missing_verification = outputs / "missing_verification.json"

    result = save_provider_allowlist_pr_preview(
        "odds_api",
        outputs,
        verification_path=missing_verification,
        policy_path=policy_path,
        repository_root=tmp_path,
        run_at=RUN_AT,
    )

    assert result["status"] == BLOCKED_STATUS
    assert Path(result["markdown"]).is_file()
    markdown = Path(result["markdown"]).read_text(encoding="utf-8")
    assert "Receipt verification report is missing" in markdown
    assert "nothing was applied" in markdown
