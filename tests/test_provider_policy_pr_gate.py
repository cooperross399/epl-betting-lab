from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pandas as pd

from epl_betting_lab.reports import provider_policy_pr_gate as gate_module
from epl_betting_lab.reports.provider_allowlist_evidence_bundle_verification import (
    VERIFIED_VERDICT as VERIFIED_BUNDLE_VERDICT,
)
from epl_betting_lab.reports.provider_allowlist_pr_conformance import (
    CONFORMS_VERDICT,
    UNSAFE_AUTOMATION_STATUS,
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    READY_STATUS,
    REQUIRED_VERIFICATION_VERDICT,
)
from epl_betting_lab.reports.provider_policy_pr_gate import (
    BLOCKED_VERDICT,
    BOUND_STATUS,
    CONFORMANCE_FAILED_STATUS,
    DIGEST_MISMATCH_STATUS,
    FAILED_STATUS,
    FAILED_VERDICT,
    GATE_STATUSES,
    GATE_VERDICTS,
    MISSING_CHANGED_FILE_DIGEST_STATUS,
    MISSING_CONFORMANCE_STATUS,
    MISSING_EVIDENCE_DIGEST_STATUS,
    MISSING_GIT_CONTEXT_STATUS,
    MISSING_VERIFIED_BUNDLE_STATUS,
    NOT_APPLICABLE_STATUS,
    NOT_APPLICABLE_VERDICT,
    PASSED_STATUS,
    PASSED_VERDICT,
    POLICY_RELATIVE_PATH,
    RECEIPT_FAILED_STATUS,
    RECEIPT_BINDING_STATUSES,
    UNSAFE_AUTOMATION_STATUS_GATE,
    build_provider_policy_pr_gate,
    calculate_provider_policy_gate_receipt_identity,
    detect_provider_policy_change,
    save_provider_policy_pr_gate,
)


RUN_AT = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _prepare_reports(root: Path) -> dict[str, object]:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "tests@example.com")
    _git(root, "config", "user.name", "Tests")
    outputs = root / "data" / "outputs"
    policy = root / POLICY_RELATIVE_PATH
    bundle = outputs / "archive" / "bundle.json"
    _write_json(policy, {"provider_allowlist_entries": {}})
    (root / "README.md").write_text("Provider gate fixture\n", encoding="utf-8")
    _git(root, "add", POLICY_RELATIVE_PATH, "README.md")
    _git(root, "commit", "-qm", "base")
    base_sha = _git(root, "rev-parse", "HEAD")

    _write_json(policy, {"provider_allowlist_entries": {"The Odds API": {}}})
    _write_json(bundle, {"bundle": "evidence"})
    _write_json(
        outputs / "provider_allowlist_evidence_bundle_verification.json",
        {
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "verdict": VERIFIED_BUNDLE_VERDICT,
            "conformance_verdict": CONFORMS_VERDICT,
            "bundle_path": bundle.relative_to(root).as_posix(),
            "bundle_id": "odds-api-allowlist-evidence-1234",
            "bundle_checksum_sha256": "a" * 64,
        },
    )
    _write_json(
        outputs / "provider_allowlist_pr_preview.json",
        {
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "status": READY_STATUS,
            "proposed_allowlist_status": "Allowed",
        },
    )
    _write_json(
        outputs / "provider_human_acceptance_receipt_verification.json",
        {
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "verdict": REQUIRED_VERIFICATION_VERDICT,
        },
    )
    _write_json(
        outputs / "provider_allowlist_pr_conformance.json",
        {
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "verdict": CONFORMS_VERDICT,
            "policy": {"checksum_sha256": "policy-checksum"},
            "checks": [],
        },
    )
    _git(root, "add", "data")
    _git(root, "commit", "-qm", "allowlist evidence")
    head_sha = _git(root, "rev-parse", "HEAD")
    return {
        "outputs": outputs,
        "policy": policy,
        "bundle": bundle,
        "base_sha": base_sha,
        "head_sha": head_sha,
    }


def _mock_current_checks(monkeypatch) -> None:
    def fake_bundle(*args, **kwargs):
        return pd.DataFrame(), {
            "provider_key": "odds_api",
            "verdict": VERIFIED_BUNDLE_VERDICT,
            "conformance_verdict": CONFORMS_VERDICT,
            "bundle_id": "odds-api-allowlist-evidence-1234",
            "bundle_checksum_sha256": "a" * 64,
        }

    def fake_conformance(*args, **kwargs):
        return pd.DataFrame([{"status": "Match"}]), {
            "provider_key": "odds_api",
            "verdict": CONFORMS_VERDICT,
            "policy": {"checksum_sha256": "policy-checksum"},
        }

    monkeypatch.setattr(
        gate_module,
        "build_provider_allowlist_evidence_bundle_verification",
        fake_bundle,
    )
    monkeypatch.setattr(
        gate_module,
        "build_provider_allowlist_pr_conformance",
        fake_conformance,
    )


def _build(root: Path, fixture: dict[str, object]):
    return build_provider_policy_pr_gate(
        "odds_api",
        fixture["outputs"],
        repository_root=root,
        base_ref=str(fixture["base_sha"]),
        head_ref=str(fixture["head_sha"]),
        run_at=RUN_AT,
    )


def test_gate_statuses_and_verdicts_are_explicit() -> None:
    assert GATE_STATUSES == (
        "Passed",
        "Not applicable",
        "Missing verified bundle",
        "Missing conformance report",
        "Conformance failed",
        "Receipt verification failed",
        "Unsafe automation change",
        "Failed",
        "Bound",
        "Missing Git context",
        "Missing changed-file digest",
        "Missing evidence digest",
        "Digest mismatch",
    )
    assert RECEIPT_BINDING_STATUSES == (
        BOUND_STATUS,
        MISSING_GIT_CONTEXT_STATUS,
        MISSING_CHANGED_FILE_DIGEST_STATUS,
        MISSING_EVIDENCE_DIGEST_STATUS,
        DIGEST_MISMATCH_STATUS,
        NOT_APPLICABLE_STATUS,
    )
    assert GATE_VERDICTS == (
        "Provider policy PR gate passed",
        "Provider policy PR gate not applicable",
        "Provider policy PR gate blocked",
        "Provider policy PR gate failed",
    )


def test_gate_is_not_applicable_when_policy_did_not_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def unexpected(*args, **kwargs):
        raise AssertionError("Evidence checks must not run for an unrelated PR.")

    monkeypatch.setattr(
        gate_module,
        "build_provider_allowlist_evidence_bundle_verification",
        unexpected,
    )
    checks, summary = build_provider_policy_pr_gate(
        "odds_api",
        tmp_path / "data" / "outputs",
        repository_root=tmp_path,
        changed_files=["README.md"],
        run_at=RUN_AT,
    )

    assert summary["verdict"] == NOT_APPLICABLE_VERDICT
    assert summary["policy_changed"] is False
    assert checks.iloc[0]["status"] == NOT_APPLICABLE_STATUS


def test_gate_passes_with_verified_current_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)

    checks, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == PASSED_VERDICT
    assert summary["policy_changed"] is True
    assert set(checks["status"]) == {PASSED_STATUS, BOUND_STATUS}
    assert summary["receipt_binding_status"] == BOUND_STATUS
    assert summary["gate_receipt_id"].startswith(
        "odds_api-provider-policy-gate-"
    )
    assert summary["base_sha"] == fixture["base_sha"]
    assert summary["head_sha"] == fixture["head_sha"]
    assert summary["merge_base_sha"] == fixture["base_sha"]
    assert summary["gate_mode"] == "local_git"
    assert summary["safety"]["read_only_gate"] is True
    assert summary["safety"]["secrets_required"] is False


def test_gate_receipt_identity_is_stable_for_identical_sorted_inputs() -> None:
    changed = [
        {"path": "z.txt", "checksum_sha256": "b" * 64},
        {"path": "a.txt", "checksum_sha256": "a" * 64},
    ]
    evidence = [
        {"field": "preview", "path": "preview.json", "checksum_sha256": "c" * 64},
        {"field": "receipt", "path": "receipt.json", "checksum_sha256": "d" * 64},
    ]
    kwargs = {
        "provider_key": "odds_api",
        "base_sha": "1" * 40,
        "head_sha": "2" * 40,
        "changed_file_digests": changed,
        "changed_files_digest": "3" * 64,
        "policy_checksum_after_sha256": "4" * 64,
        "evidence_checksums": evidence,
        "evidence_digest": "5" * 64,
        "final_verdict": PASSED_VERDICT,
    }

    first = calculate_provider_policy_gate_receipt_identity(**kwargs)
    second = calculate_provider_policy_gate_receipt_identity(
        **{
            **kwargs,
            "changed_file_digests": list(reversed(changed)),
            "evidence_checksums": list(reversed(evidence)),
        }
    )

    assert first == second


def test_gate_receipt_changes_when_policy_content_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)
    _, before = _build(tmp_path, fixture)

    _write_json(
        fixture["policy"],
        {"provider_allowlist_entries": {"The Odds API": {"reviewed": True}}},
    )
    _, after = _build(tmp_path, fixture)

    assert before["receipt_binding_status"] == BOUND_STATUS
    assert after["receipt_binding_status"] == BOUND_STATUS
    assert before["policy_checksum_after_sha256"] != after[
        "policy_checksum_after_sha256"
    ]
    assert before["gate_receipt_id"] != after["gate_receipt_id"]


def test_gate_receipt_changes_when_evidence_checksum_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)
    _, before = _build(tmp_path, fixture)
    preview_path = fixture["outputs"] / "provider_allowlist_pr_preview.json"
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    preview["review_note"] = "Updated human-readable evidence note"
    _write_json(preview_path, preview)

    _, after = _build(tmp_path, fixture)

    assert before["receipt_binding_status"] == BOUND_STATUS
    assert after["receipt_binding_status"] == BOUND_STATUS
    assert before["preview_report_checksum_sha256"] != after[
        "preview_report_checksum_sha256"
    ]
    assert before["evidence_digest"] != after["evidence_digest"]
    assert before["gate_receipt_id"] != after["gate_receipt_id"]


def test_gate_receipt_changes_when_changed_file_list_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)
    common = {
        "repository_root": tmp_path,
        "base_ref": str(fixture["base_sha"]),
        "head_ref": str(fixture["head_sha"]),
        "run_at": RUN_AT,
    }
    _, policy_only = build_provider_policy_pr_gate(
        "odds_api",
        fixture["outputs"],
        changed_files=[POLICY_RELATIVE_PATH],
        **common,
    )
    _, policy_and_readme = build_provider_policy_pr_gate(
        "odds_api",
        fixture["outputs"],
        changed_files=[POLICY_RELATIVE_PATH, "README.md"],
        **common,
    )

    assert policy_only["receipt_binding_status"] == BOUND_STATUS
    assert policy_and_readme["receipt_binding_status"] == BOUND_STATUS
    assert policy_only["changed_files_digest"] != policy_and_readme[
        "changed_files_digest"
    ]
    assert policy_only["gate_receipt_id"] != policy_and_readme["gate_receipt_id"]


def test_policy_change_without_git_context_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)

    checks, summary = build_provider_policy_pr_gate(
        "odds_api",
        fixture["outputs"],
        repository_root=tmp_path,
        changed_files=[POLICY_RELATIVE_PATH],
        run_at=RUN_AT,
    )

    assert summary["verdict"] == BLOCKED_VERDICT
    assert summary["receipt_binding_status"] == MISSING_GIT_CONTEXT_STATUS
    assert summary["gate_receipt_id"] == ""
    binding_row = checks.loc[
        checks["check"] == "Deterministic PR comparison receipt"
    ].iloc[0]
    assert binding_row["status"] == MISSING_GIT_CONTEXT_STATUS


def test_missing_bundle_verification_blocks_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)
    (
        fixture["outputs"]
        / "provider_allowlist_evidence_bundle_verification.json"
    ).unlink()

    checks, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == BLOCKED_VERDICT
    assert summary["receipt_binding_status"] == MISSING_EVIDENCE_DIGEST_STATUS
    assert summary["gate_receipt_id"] == ""
    row = checks.loc[checks["check"] == "Verified allowlist evidence bundle"].iloc[0]
    assert row["status"] == MISSING_VERIFIED_BUNDLE_STATUS


def test_missing_conformance_report_blocks_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)
    (fixture["outputs"] / "provider_allowlist_pr_conformance.json").unlink()

    checks, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == BLOCKED_VERDICT
    row = checks.loc[
        checks["check"] == "Current policy conforms to reviewed preview"
    ].iloc[0]
    assert row["status"] == MISSING_CONFORMANCE_STATUS


def test_missing_changed_file_digest_blocks_receipt_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)

    checks, summary = build_provider_policy_pr_gate(
        "odds_api",
        fixture["outputs"],
        repository_root=tmp_path,
        base_ref=str(fixture["base_sha"]),
        head_ref=str(fixture["head_sha"]),
        changed_files=[POLICY_RELATIVE_PATH, "missing-review-file.json"],
        run_at=RUN_AT,
    )

    assert summary["verdict"] == BLOCKED_VERDICT
    assert summary["receipt_binding_status"] == MISSING_CHANGED_FILE_DIGEST_STATUS
    binding_row = checks.loc[
        checks["check"] == "Deterministic PR comparison receipt"
    ].iloc[0]
    assert binding_row["status"] == MISSING_CHANGED_FILE_DIGEST_STATUS


def test_checked_out_head_mismatch_blocks_receipt_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)
    (tmp_path / "later.txt").write_text("later commit\n", encoding="utf-8")
    _git(tmp_path, "add", "later.txt")
    _git(tmp_path, "commit", "-qm", "later")

    checks, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == BLOCKED_VERDICT
    assert summary["comparison_context_status"] == DIGEST_MISMATCH_STATUS
    assert summary["receipt_binding_status"] == DIGEST_MISMATCH_STATUS
    binding_row = checks.loc[
        checks["check"] == "Deterministic PR comparison receipt"
    ].iloc[0]
    assert binding_row["status"] == DIGEST_MISMATCH_STATUS


def test_nonconforming_policy_blocks_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)
    report_path = fixture["outputs"] / "provider_allowlist_pr_conformance.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["verdict"] = "Does not conform"
    _write_json(report_path, report)

    checks, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == BLOCKED_VERDICT
    row = checks.loc[
        checks["check"] == "Current policy conforms to reviewed preview"
    ].iloc[0]
    assert row["status"] == CONFORMANCE_FAILED_STATUS


def test_unverified_human_receipt_blocks_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)
    report_path = (
        fixture["outputs"]
        / "provider_human_acceptance_receipt_verification.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["verdict"] = "Evidence changed"
    _write_json(report_path, report)

    checks, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == BLOCKED_VERDICT
    row = checks.loc[checks["check"] == "Verified human acceptance receipt"].iloc[0]
    assert row["status"] == RECEIPT_FAILED_STATUS


def test_unsafe_automation_change_blocks_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)

    def fake_bundle(*args, **kwargs):
        return pd.DataFrame(), {
            "verdict": VERIFIED_BUNDLE_VERDICT,
            "conformance_verdict": CONFORMS_VERDICT,
            "bundle_id": "odds-api-allowlist-evidence-1234",
            "bundle_checksum_sha256": "a" * 64,
        }

    def unsafe_conformance(*args, **kwargs):
        return pd.DataFrame([{"status": UNSAFE_AUTOMATION_STATUS}]), {
            "verdict": "Unsafe automation change detected",
            "policy": {"checksum_sha256": "policy-checksum"},
        }

    monkeypatch.setattr(
        gate_module,
        "build_provider_allowlist_evidence_bundle_verification",
        fake_bundle,
    )
    monkeypatch.setattr(
        gate_module,
        "build_provider_allowlist_pr_conformance",
        unsafe_conformance,
    )

    checks, summary = _build(tmp_path, fixture)

    assert summary["verdict"] == BLOCKED_VERDICT
    assert UNSAFE_AUTOMATION_STATUS_GATE in set(checks["status"])


def test_change_detection_failure_returns_failed_verdict(tmp_path: Path) -> None:
    checks, summary = build_provider_policy_pr_gate(
        "odds_api",
        tmp_path / "data" / "outputs",
        repository_root=tmp_path,
        base_ref="--unsafe-ref",
        head_ref="HEAD",
        run_at=RUN_AT,
    )

    assert summary["verdict"] == FAILED_VERDICT
    assert checks.iloc[0]["status"] == FAILED_STATUS


def test_detect_policy_change_from_explicit_git_base_and_head(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tests"],
        cwd=tmp_path,
        check=True,
    )
    policy = tmp_path / POLICY_RELATIVE_PATH
    _write_json(policy, {"version": 1})
    subprocess.run(["git", "add", POLICY_RELATIVE_PATH], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _write_json(policy, {"version": 2})
    subprocess.run(["git", "add", POLICY_RELATIVE_PATH], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "policy"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    detection = detect_provider_policy_change(
        tmp_path,
        base_ref=base,
        head_ref=head,
    )

    assert detection.error == ""
    assert detection.policy_changed is True
    assert detection.changed_files == (POLICY_RELATIVE_PATH,)
    assert detection.source == "Explicit base/head Git diff"


def test_save_gate_writes_json_markdown_and_csv(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = _prepare_reports(tmp_path)
    _mock_current_checks(monkeypatch)

    result = save_provider_policy_pr_gate(
        "odds_api",
        fixture["outputs"],
        repository_root=tmp_path,
        base_ref=str(fixture["base_sha"]),
        head_ref=str(fixture["head_sha"]),
        run_at=RUN_AT,
    )

    assert result["verdict"] == PASSED_VERDICT
    assert result["json"].is_file()
    assert result["markdown"].is_file()
    assert result["csv"].is_file()
    markdown = result["markdown"].read_text(encoding="utf-8")
    assert "Read-only PR check: nothing was applied" in markdown
    assert "Provider policy PR gate passed" in markdown
    assert "## Gate receipt" in markdown
    assert result["summary"]["gate_receipt_id"] in markdown
    saved_checks = pd.read_csv(result["csv"], keep_default_na=False)
    assert set(saved_checks["receipt_binding_status"]) == {BOUND_STATUS}
    assert set(saved_checks["gate_receipt_id"]) == {
        result["summary"]["gate_receipt_id"]
    }


def test_pr_workflow_checks_exact_head_and_publishes_receipt_summary() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    workflow = (
        repository_root / ".github" / "workflows" / "provider-policy-pr-gate.yml"
    ).read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "schedule:" not in workflow
    assert "ref: ${{ github.event.pull_request.head.sha }}" in workflow
    assert '--base-ref "${{ github.event.pull_request.base.sha }}"' in workflow
    assert '--head-ref "${{ github.event.pull_request.head.sha }}"' in workflow
    assert "Add gate receipt report to job summary" in workflow
    assert "provider_policy_pr_gate.md" in workflow


def test_dashboard_displays_latest_gate_receipt_fields() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    app_source = (repository_root / "app.py").read_text(encoding="utf-8")

    assert "Latest provider policy gate receipt" in app_source
    assert '"Receipt binding"' in app_source
    assert '"Base SHA"' in app_source
    assert '"Head SHA"' in app_source
    assert '"Changed files"' in app_source
    assert "Gate receipt ID:" in app_source
