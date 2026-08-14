from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.provider_policy_pr_gate_receipt_verification import (
    CHANGED_VERDICT,
    VERIFIED_VERDICT,
)
from epl_betting_lab.reports.provider_policy_pr_gate_verification_archive import (
    ARCHIVED_STATUS,
    ARCHIVE_CSV_FILENAME,
    ARCHIVE_JSON_FILENAME,
    ARCHIVE_MARKDOWN_FILENAME,
    FAILED_VERDICT,
    MISSING_STATUS,
    NOT_READY_VERDICT,
    READY_VERDICT,
    build_provider_policy_pr_gate_verification_archive,
    collect_github_run_metadata,
    save_provider_policy_pr_gate_verification_archive,
)


RUN_AT = datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc)


def _write_reports(
    output_dir: Path,
    *,
    verification_verdict: str = VERIFIED_VERDICT,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    gate = {
        "provider_key": "odds_api",
        "verdict": "Provider policy PR gate passed",
        "gate_receipt_id": "odds-api-gate-receipt",
    }
    verification = {
        "provider_key": "odds_api",
        "provider_name": "the_odds_api",
        "verdict": verification_verdict,
        "original_gate_receipt_id": "odds-api-gate-receipt",
        "recalculated_gate_receipt_id": "odds-api-gate-receipt",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "merge_base_sha": "c" * 40,
        "current_changed_files_digest": "d" * 64,
        "current_evidence_digest": "e" * 64,
        "current_policy_change_digest": "f" * 64,
    }
    (output_dir / "provider_policy_pr_gate.json").write_text(
        json.dumps(gate),
        encoding="utf-8",
    )
    (output_dir / "provider_policy_pr_gate.md").write_text(
        "# Gate\n",
        encoding="utf-8",
    )
    (output_dir / "provider_policy_pr_gate.csv").write_text(
        "status\nPassed\n",
        encoding="utf-8",
    )
    (output_dir / "provider_policy_pr_gate_receipt_verification.json").write_text(
        json.dumps(verification),
        encoding="utf-8",
    )
    (output_dir / "provider_policy_pr_gate_receipt_verification.md").write_text(
        "# Verification\n",
        encoding="utf-8",
    )
    (output_dir / "provider_policy_pr_gate_receipt_verification.csv").write_text(
        "status\nVerified\n",
        encoding="utf-8",
    )
    (output_dir / "provider_allowlist_pr_conformance.json").write_text(
        json.dumps({"verdict": "Conforms to preview"}),
        encoding="utf-8",
    )


def _github_environment() -> dict[str, str]:
    return {
        "PROVIDER_POLICY_PR_NUMBER": "94",
        "PROVIDER_POLICY_PR_URL": "https://github.com/example/repo/pull/94",
        "GITHUB_RUN_ID": "123456",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_WORKFLOW": "Provider Policy PR Gate",
        "PROVIDER_POLICY_JOB_NAME": "Provider Policy PR Gate",
        "GITHUB_ACTOR": "reviewer",
        "GITHUB_REPOSITORY": "example/repo",
        "GITHUB_EVENT_NAME": "pull_request",
    }


def test_successful_verification_creates_approval_ready_archive(tmp_path: Path) -> None:
    outputs = tmp_path / "data" / "outputs"
    _write_reports(outputs)

    result = save_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment=_github_environment(),
    )

    summary = result["summary"]
    assert summary["verdict"] == READY_VERDICT
    assert summary["approval_ready"] is True
    assert summary["pr_number"] == "94"
    assert summary["github_run_id"] == "123456"
    assert result["archive_directory"].relative_to(outputs).as_posix().startswith(
        "archive/provider_policy_pr_gate_verifications/2026-08-14/093000_odds_api"
    )
    assert result["json"].is_file()
    assert result["markdown"].is_file()
    assert result["csv"].is_file()
    assert (result["archive_directory"] / ARCHIVE_JSON_FILENAME).is_file()
    assert (result["archive_directory"] / ARCHIVE_MARKDOWN_FILENAME).is_file()
    assert (result["archive_directory"] / ARCHIVE_CSV_FILENAME).is_file()
    archived = pd.read_csv(result["csv"], keep_default_na=False)
    required = archived.loc[archived["required"]]
    assert set(required["status"]) == {ARCHIVED_STATUS}
    assert "nothing was applied" in result["markdown"].read_text(
        encoding="utf-8"
    ).casefold()


def test_nonpassing_verification_is_archived_but_not_approval_ready(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "data" / "outputs"
    _write_reports(outputs, verification_verdict=CHANGED_VERDICT)

    result = save_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment={},
    )

    assert result["verdict"] == NOT_READY_VERDICT
    assert result["summary"]["approval_ready"] is False
    assert result["archive_directory"].is_dir()
    assert any("not approval-ready" in item for item in result["summary"]["blockers"])


def test_missing_required_report_fails_closed_but_keeps_diagnostic_archive(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "data" / "outputs"
    _write_reports(outputs)
    (outputs / "provider_policy_pr_gate_receipt_verification.csv").unlink()

    result = save_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment={},
    )

    assert result["verdict"] == FAILED_VERDICT
    assert result["summary"]["approval_ready"] is False
    assert MISSING_STATUS in set(result["evidence"]["status"])
    assert result["archive_directory"].is_dir()


def test_archive_receipt_is_deterministic_for_identical_files_and_metadata(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "data" / "outputs"
    _write_reports(outputs)

    _, first = build_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment=_github_environment(),
    )
    _, second = build_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=datetime(2026, 8, 14, 10, 45, tzinfo=timezone.utc),
        environment=_github_environment(),
    )

    assert first["archive_receipt_id"] == second["archive_receipt_id"]
    assert (
        first["archive_receipt_checksum_sha256"]
        == second["archive_receipt_checksum_sha256"]
    )


def test_archive_receipt_changes_when_evidence_content_changes(tmp_path: Path) -> None:
    outputs = tmp_path / "data" / "outputs"
    _write_reports(outputs)
    _, before = build_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment=_github_environment(),
    )

    (outputs / "provider_policy_pr_gate.md").write_text(
        "# Gate changed\n",
        encoding="utf-8",
    )
    _, after = build_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment=_github_environment(),
    )

    assert before["archive_receipt_id"] != after["archive_receipt_id"]


def test_archive_receipt_changes_when_github_run_metadata_changes(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "data" / "outputs"
    _write_reports(outputs)
    first_environment = _github_environment()
    second_environment = {**first_environment, "GITHUB_RUN_ATTEMPT": "3"}

    _, before = build_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment=first_environment,
    )
    _, after = build_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment=second_environment,
    )

    assert before["archive_receipt_id"] != after["archive_receipt_id"]


def test_github_metadata_is_captured_without_secret_environment_values() -> None:
    metadata = collect_github_run_metadata(_github_environment())

    assert metadata == {
        "pr_number": "94",
        "pr_url": "https://github.com/example/repo/pull/94",
        "github_run_id": "123456",
        "github_run_attempt": "2",
        "github_run_url": "https://github.com/example/repo/actions/runs/123456",
        "workflow_name": "Provider Policy PR Gate",
        "job_name": "Provider Policy PR Gate",
        "actor": "reviewer",
        "repository": "example/repo",
        "event_name": "pull_request",
    }


def test_missing_github_environment_is_safe_for_local_archives(tmp_path: Path) -> None:
    outputs = tmp_path / "data" / "outputs"
    _write_reports(outputs)

    _, summary = build_provider_policy_pr_gate_verification_archive(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        run_at=RUN_AT,
        environment={},
    )

    assert summary["approval_ready"] is True
    assert summary["pr_number"] == ""
    assert summary["github_run_id"] == ""
    assert summary["archive_receipt_id"]


def test_pr_workflow_archives_receipts_and_exposes_stable_required_check() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (
        root / ".github" / "workflows" / "provider-policy-pr-gate.yml"
    ).read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "schedule:" not in workflow
    assert "    paths:" not in workflow
    assert "name: Provider Policy PR Gate" in workflow
    assert "scripts/archive_provider_policy_pr_gate_verification.py" in workflow
    assert "provider_policy_pr_gate_verification_archive.json" in workflow
    assert "archive/provider_policy_pr_gate_verifications/**" in workflow
    assert "PROVIDER_POLICY_PR_NUMBER" in workflow
    assert "PROVIDER_POLICY_PR_URL" in workflow
    assert "secrets." not in workflow
    assert "--live" not in workflow


def test_dashboard_displays_latest_gate_verification_archive() -> None:
    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")

    assert "Archive provider policy gate verification" in app_source
    assert "Latest provider policy gate verification archive" in app_source
    assert "Archive receipt ID:" in app_source
    assert "GitHub run:" in app_source
