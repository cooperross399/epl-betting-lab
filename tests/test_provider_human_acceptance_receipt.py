from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.providers.base import file_sha256
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    APPROVAL_DECISION,
    RECEIPT_ARCHIVE_ROOT,
    RECEIPT_CSV_FILENAME,
    RECEIPT_JSON_FILENAME,
    RECEIPT_MARKDOWN_FILENAME,
    SUPPORTED_DECISIONS,
    ProviderHumanAcceptanceReceiptError,
    process_provider_human_acceptance_receipt,
)


RUN_AT = datetime(2026, 8, 7, 14, 30, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _prepare_evidence(
    root: Path,
    *,
    verdict: str = "Ready for human allowlist review",
    include_comparison: bool = True,
    include_policy: bool = True,
) -> tuple[Path, Path]:
    outputs = root / "data" / "outputs"
    reviewed_runs: list[dict[str, object]] = []
    for index, hour in enumerate((12, 13), start=1):
        relative = Path("archive") / "provider_shadow_runs" / "2026-08-07" / (
            f"{hour:02d}0000_odds_api"
        )
        archive = outputs / relative
        verification_path = archive / "provider_shadow_verification.json"
        _write_json(
            verification_path,
            {
                "provider_key": "odds_api",
                "provider_name": "The Odds API",
                "mode": "Live shadow run",
                "verdict": "Needs provider policy review",
                "run": index,
            },
        )
        _write_json(
            archive / "archive_metadata.json",
            {
                "archive_id": relative.as_posix(),
                "provider_key": "odds_api",
                "mode": "Live shadow run",
                "generated_at": f"2026-08-07T{hour:02d}:00:00+00:00",
                "files": {
                    "shadow_json": {
                        "status": "Archived",
                        "archive_path": "provider_shadow_verification.json",
                        "checksum_sha256": file_sha256(verification_path),
                    }
                },
            },
        )
        reviewed_runs.append(
            {
                "generated_at": f"2026-08-07T{hour:02d}:00:00+00:00",
                "archive_path": relative.as_posix(),
                "archive_integrity_status": "Verified",
                "provider_run_status": "Completed",
                "shadow_verdict": "Needs provider policy review",
                "staging_verdict": "Needs fixes",
            }
        )

    _write_json(
        outputs / "provider_acceptance_checklist.json",
        {
            "generated_at": "2026-08-07T14:00:00+00:00",
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "verdict": verdict,
            "review_window": 5,
            "reviewed_runs": reviewed_runs,
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
    return outputs, policy


def test_supported_human_decisions_are_explicit() -> None:
    assert SUPPORTED_DECISIONS == (
        "approved_for_allowlist_pr",
        "rejected",
        "needs_more_shadow_runs",
    )


def test_preview_binds_exact_evidence_without_writing_receipt_files(
    tmp_path: Path,
) -> None:
    outputs, policy = _prepare_evidence(tmp_path)

    result = process_provider_human_acceptance_receipt(
        "odds_api",
        "Cooper Ross",
        APPROVAL_DECISION,
        notes="Reviewed stable live evidence.",
        output_dir=outputs,
        policy_path=policy,
        run_at=RUN_AT,
    )

    receipt = result["receipt"]
    assert result["written"] is False
    assert receipt["approval_gate"]["status"] == "Passed"
    assert receipt["safety"]["provider_allowlisted"] is False
    assert len(receipt["evidence"]["reviewed_shadow_archives"]) == 2
    assert all(
        len(item["checksum_sha256"]) == 64
        for item in receipt["evidence"]["reviewed_shadow_archives"]
    )
    assert receipt["evidence"]["comparison"]["status"] == "Bound"
    assert receipt["evidence"]["provider_policy"]["status"] == "Bound"
    assert not (outputs / RECEIPT_JSON_FILENAME).exists()
    assert not (outputs / RECEIPT_MARKDOWN_FILENAME).exists()
    assert not (outputs / RECEIPT_CSV_FILENAME).exists()
    assert not (outputs / RECEIPT_ARCHIVE_ROOT).exists()


def test_write_receipt_creates_latest_reports_and_unique_archives(
    tmp_path: Path,
) -> None:
    outputs, policy = _prepare_evidence(tmp_path)
    kwargs = {
        "notes": "Human evidence review complete.",
        "output_dir": outputs,
        "policy_path": policy,
        "write_receipt": True,
        "run_at": RUN_AT,
    }

    first = process_provider_human_acceptance_receipt(
        "odds_api",
        "Cooper Ross",
        APPROVAL_DECISION,
        **kwargs,
    )
    second = process_provider_human_acceptance_receipt(
        "odds_api",
        "Cooper Ross",
        APPROVAL_DECISION,
        **kwargs,
    )

    assert Path(first["json"]).is_file()
    assert Path(first["markdown"]).is_file()
    assert Path(first["csv"]).is_file()
    assert Path(first["archive_directory"]).is_dir()
    assert Path(second["archive_directory"]).is_dir()
    assert first["archive_directory"] != second["archive_directory"]
    archived_names = {path.name for path in Path(first["archive_directory"]).iterdir()}
    assert archived_names == {
        RECEIPT_JSON_FILENAME,
        RECEIPT_MARKDOWN_FILENAME,
        RECEIPT_CSV_FILENAME,
    }
    stored = json.loads(Path(first["json"]).read_text(encoding="utf-8"))
    assert stored["decision"] == APPROVAL_DECISION
    assert stored["receipt_storage"]["archive_directory"]
    markdown = Path(first["markdown"]).read_text(encoding="utf-8")
    assert "does **not** allowlist the provider" in markdown
    assert "cron remains disabled" in markdown
    rows = pd.read_csv(first["csv"])
    assert set(rows["evidence_type"]) == {
        "acceptance_checklist",
        "reviewed_shadow_archive",
        "latest_live_shadow_archive_set",
        "latest_shadow_comparison",
        "provider_policy",
    }


def test_non_ready_approval_is_blocked_without_terminal_override(
    tmp_path: Path,
) -> None:
    outputs, policy = _prepare_evidence(
        tmp_path,
        verdict="Needs more shadow runs",
    )

    with pytest.raises(
        ProviderHumanAcceptanceReceiptError,
        match="Approval receipt blocked",
    ):
        process_provider_human_acceptance_receipt(
            "odds_api",
            "Cooper Ross",
            APPROVAL_DECISION,
            output_dir=outputs,
            policy_path=policy,
            run_at=RUN_AT,
        )

    assert not (outputs / RECEIPT_JSON_FILENAME).exists()


def test_non_ready_approval_override_is_prominently_recorded(
    tmp_path: Path,
) -> None:
    outputs, policy = _prepare_evidence(
        tmp_path,
        verdict="Needs more shadow runs",
    )

    result = process_provider_human_acceptance_receipt(
        "odds_api",
        "Cooper Ross",
        APPROVAL_DECISION,
        output_dir=outputs,
        policy_path=policy,
        allow_not_ready_approval=True,
        run_at=RUN_AT,
    )

    receipt = result["receipt"]
    assert receipt["approval_gate"]["status"] == "Override used"
    assert receipt["approval_gate"]["override_used"] is True
    assert any("Terminal override used" in item for item in receipt["warnings"])
    assert receipt["safety"]["provider_policy_edited"] is False


def test_conservative_non_approval_decision_can_document_non_ready_checklist(
    tmp_path: Path,
) -> None:
    outputs, policy = _prepare_evidence(
        tmp_path,
        verdict="Needs mapping fixes",
        include_comparison=False,
        include_policy=False,
    )

    result = process_provider_human_acceptance_receipt(
        "odds_api",
        "Cooper Ross",
        "needs_more_shadow_runs",
        output_dir=outputs,
        policy_path=policy,
        run_at=RUN_AT,
    )

    receipt = result["receipt"]
    assert receipt["approval_gate"]["status"] == "Not applicable"
    assert receipt["evidence"]["comparison"]["status"] == "Not available"
    assert receipt["evidence"]["provider_policy"]["status"] == "Not available"
    assert len(receipt["warnings"]) == 2


def test_receipt_checksum_binding_reflects_archive_content(
    tmp_path: Path,
) -> None:
    outputs, policy = _prepare_evidence(tmp_path)
    first = process_provider_human_acceptance_receipt(
        "odds_api",
        "Cooper Ross",
        "rejected",
        output_dir=outputs,
        policy_path=policy,
        run_at=RUN_AT,
    )["receipt"]
    archive_path = outputs / "archive/provider_shadow_runs/2026-08-07/120000_odds_api"
    evidence_file = archive_path / "provider_shadow_verification.json"
    old_file_checksum = file_sha256(evidence_file)
    evidence_file.write_text('{"changed": true}\n', encoding="utf-8")
    assert file_sha256(evidence_file) != old_file_checksum

    second = process_provider_human_acceptance_receipt(
        "odds_api",
        "Cooper Ross",
        "rejected",
        output_dir=outputs,
        policy_path=policy,
        run_at=RUN_AT,
    )["receipt"]

    first_checksum = first["evidence"]["reviewed_shadow_archives"][0][
        "checksum_sha256"
    ]
    second_checksum = second["evidence"]["reviewed_shadow_archives"][0][
        "checksum_sha256"
    ]
    assert first_checksum != second_checksum
    assert first["receipt_id"] != second["receipt_id"]


def test_approval_blocks_archive_changed_after_checklist(tmp_path: Path) -> None:
    outputs, policy = _prepare_evidence(tmp_path)
    evidence_file = (
        outputs
        / "archive/provider_shadow_runs/2026-08-07/120000_odds_api"
        / "provider_shadow_verification.json"
    )
    evidence_file.write_text('{"changed": true}\n', encoding="utf-8")

    with pytest.raises(
        ProviderHumanAcceptanceReceiptError,
        match="no longer Verified and Completed",
    ):
        process_provider_human_acceptance_receipt(
            "odds_api",
            "Cooper Ross",
            APPROVAL_DECISION,
            output_dir=outputs,
            policy_path=policy,
            run_at=RUN_AT,
        )


def test_approval_blocks_newer_live_archive_than_checklist(tmp_path: Path) -> None:
    outputs, policy = _prepare_evidence(tmp_path)
    relative = Path("archive/provider_shadow_runs/2026-08-07/140000_odds_api")
    archive = outputs / relative
    verification_path = archive / "provider_shadow_verification.json"
    _write_json(
        verification_path,
        {
            "generated_at": "2026-08-07T14:00:00+00:00",
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
            "generated_at": "2026-08-07T14:00:00+00:00",
            "provider_key": "odds_api",
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

    with pytest.raises(
        ProviderHumanAcceptanceReceiptError,
        match="different live shadow archives",
    ):
        process_provider_human_acceptance_receipt(
            "odds_api",
            "Cooper Ross",
            APPROVAL_DECISION,
            output_dir=outputs,
            policy_path=policy,
            run_at=RUN_AT,
        )


def test_checklist_for_different_provider_is_rejected(tmp_path: Path) -> None:
    outputs, policy = _prepare_evidence(tmp_path)
    checklist_path = outputs / "provider_acceptance_checklist.json"
    checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
    checklist["provider_key"] = "manual"
    checklist["provider_name"] = "manual_reviewed"
    _write_json(checklist_path, checklist)

    with pytest.raises(
        ProviderHumanAcceptanceReceiptError,
        match="different provider",
    ):
        process_provider_human_acceptance_receipt(
            "odds_api",
            "Cooper Ross",
            "rejected",
            output_dir=outputs,
            policy_path=policy,
            run_at=RUN_AT,
        )
