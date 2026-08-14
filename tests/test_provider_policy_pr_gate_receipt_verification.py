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
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    READY_STATUS,
    REQUIRED_VERIFICATION_VERDICT,
)
from epl_betting_lab.reports.provider_policy_pr_gate import (
    BLOCKED_VERDICT,
    POLICY_RELATIVE_PATH,
    save_provider_policy_pr_gate,
)
from epl_betting_lab.reports.provider_policy_pr_gate_receipt_verification import (
    CHANGED_FILES_CHANGED_STATUS,
    CHANGED_VERDICT,
    EVIDENCE_CHECKSUM_MISMATCH_STATUS,
    GATE_NOT_PASSED_STATUS,
    GIT_CONTEXT_CHANGED_STATUS,
    MALFORMED_VERDICT,
    NOT_APPLICABLE_STATUS,
    NOT_APPLICABLE_VERDICT,
    NOT_APPROVED_VERDICT,
    POLICY_CHECKSUM_MISMATCH_STATUS,
    RECEIPT_ID_MISMATCH_STATUS,
    VERIFICATION_STATUSES,
    VERIFICATION_VERDICTS,
    VERIFIED_STATUS,
    VERIFIED_VERDICT,
    build_provider_policy_pr_gate_receipt_verification,
    save_provider_policy_pr_gate_receipt_verification,
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


def _prepare_passing_gate(tmp_path: Path, monkeypatch) -> dict[str, object]:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "tests@example.com")
    _git(tmp_path, "config", "user.name", "Tests")
    outputs = tmp_path / "data" / "outputs"
    policy = tmp_path / POLICY_RELATIVE_PATH
    bundle = outputs / "archive" / "bundle.json"
    readme = tmp_path / "README.md"
    _write_json(policy, {"provider_allowlist_entries": {}})
    readme.write_text("Provider gate base\n", encoding="utf-8")
    _git(tmp_path, "add", POLICY_RELATIVE_PATH, "README.md")
    _git(tmp_path, "commit", "-qm", "base")
    base_sha = _git(tmp_path, "rev-parse", "HEAD")

    _write_json(policy, {"provider_allowlist_entries": {"The Odds API": {}}})
    readme.write_text("Provider gate head\n", encoding="utf-8")
    _write_json(bundle, {"bundle": "evidence"})
    _write_json(
        outputs / "provider_allowlist_evidence_bundle_verification.json",
        {
            "provider_key": "odds_api",
            "provider_name": "The Odds API",
            "verdict": VERIFIED_BUNDLE_VERDICT,
            "conformance_verdict": CONFORMS_VERDICT,
            "bundle_path": bundle.relative_to(tmp_path).as_posix(),
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
    _git(tmp_path, "add", "data", "README.md")
    _git(tmp_path, "commit", "-qm", "allowlist policy and evidence")
    head_sha = _git(tmp_path, "rev-parse", "HEAD")
    _mock_current_checks(monkeypatch)
    gate_result = save_provider_policy_pr_gate(
        "odds_api",
        outputs,
        repository_root=tmp_path,
        base_ref=base_sha,
        head_ref=head_sha,
        run_at=RUN_AT,
    )
    return {
        "outputs": outputs,
        "policy": policy,
        "readme": readme,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "gate_path": gate_result["json"],
    }


def _verify(tmp_path: Path, fixture: dict[str, object]):
    return build_provider_policy_pr_gate_receipt_verification(
        "odds_api",
        gate_report_path=fixture["gate_path"],
        repository_root=tmp_path,
        run_at=RUN_AT,
    )


def test_verification_statuses_and_verdicts_are_explicit() -> None:
    assert VERIFICATION_STATUSES == (
        "Verified",
        "Missing gate report",
        "Malformed gate report",
        "Git context changed",
        "Changed files changed",
        "Policy checksum mismatch",
        "Evidence checksum mismatch",
        "Receipt ID mismatch",
        "Gate was not passed",
        "Not applicable",
    )
    assert VERIFICATION_VERDICTS == (
        "Gate receipt verified for PR approval",
        "Gate receipt not applicable",
        "Gate receipt changed",
        "Gate receipt missing evidence",
        "Gate receipt malformed",
        "Gate receipt not approved",
    )


def test_unchanged_gate_receipt_verifies(tmp_path: Path, monkeypatch) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)

    checks, summary = _verify(tmp_path, fixture)

    assert summary["verdict"] == VERIFIED_VERDICT
    assert set(checks["status"]) == {VERIFIED_STATUS}
    assert summary["original_gate_receipt_id"] == summary[
        "recalculated_gate_receipt_id"
    ]
    assert summary["comparison_context_status"] == VERIFIED_STATUS
    assert summary["safety"]["read_only"] is True


def test_changed_file_after_gate_fails_verification(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)
    fixture["readme"].write_text("Changed after gate\n", encoding="utf-8")

    checks, summary = _verify(tmp_path, fixture)

    assert summary["verdict"] == CHANGED_VERDICT
    assert CHANGED_FILES_CHANGED_STATUS in set(checks["status"])


def test_policy_change_after_gate_fails_verification(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)
    _write_json(fixture["policy"], {"provider_allowlist_entries": {}})

    checks, summary = _verify(tmp_path, fixture)

    assert summary["verdict"] == CHANGED_VERDICT
    assert POLICY_CHECKSUM_MISMATCH_STATUS in set(checks["status"])


def test_evidence_change_after_gate_fails_verification(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)
    evidence = (
        fixture["outputs"]
        / "provider_human_acceptance_receipt_verification.json"
    )
    _write_json(evidence, {"provider_key": "odds_api", "verdict": "Changed"})

    checks, summary = _verify(tmp_path, fixture)

    assert summary["verdict"] == CHANGED_VERDICT
    assert EVIDENCE_CHECKSUM_MISMATCH_STATUS in set(checks["status"])


def test_gate_that_was_not_passed_is_not_approved(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)
    gate = json.loads(fixture["gate_path"].read_text(encoding="utf-8"))
    gate["verdict"] = BLOCKED_VERDICT
    _write_json(fixture["gate_path"], gate)

    checks, summary = _verify(tmp_path, fixture)

    assert summary["verdict"] == NOT_APPROVED_VERDICT
    assert GATE_NOT_PASSED_STATUS in set(checks["status"])


def test_malformed_receipt_id_fails_closed(tmp_path: Path, monkeypatch) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)
    gate = json.loads(fixture["gate_path"].read_text(encoding="utf-8"))
    gate["gate_receipt_id"] = "not-a-valid-receipt"
    _write_json(fixture["gate_path"], gate)

    checks, summary = _verify(tmp_path, fixture)

    assert summary["verdict"] == MALFORMED_VERDICT
    assert RECEIPT_ID_MISMATCH_STATUS in set(checks["status"])


def test_not_applicable_gate_remains_safe(tmp_path: Path, monkeypatch) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)
    base_sha = fixture["head_sha"]
    fixture["readme"].write_text("Unrelated follow-up\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "unrelated change")
    head_sha = _git(tmp_path, "rev-parse", "HEAD")
    result = save_provider_policy_pr_gate(
        "odds_api",
        fixture["outputs"],
        repository_root=tmp_path,
        base_ref=base_sha,
        head_ref=head_sha,
        run_at=RUN_AT,
    )
    fixture["gate_path"] = result["json"]

    checks, summary = _verify(tmp_path, fixture)

    assert summary["verdict"] == NOT_APPLICABLE_VERDICT
    assert NOT_APPLICABLE_STATUS in set(checks["status"])


def test_missing_exact_git_context_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)
    gate = json.loads(fixture["gate_path"].read_text(encoding="utf-8"))
    gate["head_sha"] = "f" * 40
    _write_json(fixture["gate_path"], gate)

    checks, summary = _verify(tmp_path, fixture)

    assert summary["verdict"] != VERIFIED_VERDICT
    assert GIT_CONTEXT_CHANGED_STATUS in set(checks["status"])


def test_save_writes_json_markdown_and_csv(tmp_path: Path, monkeypatch) -> None:
    fixture = _prepare_passing_gate(tmp_path, monkeypatch)
    result = save_provider_policy_pr_gate_receipt_verification(
        "odds_api",
        fixture["outputs"],
        gate_report_path=fixture["gate_path"],
        repository_root=tmp_path,
        run_at=RUN_AT,
    )

    assert result["verdict"] == VERIFIED_VERDICT
    assert result["json"].exists()
    assert result["markdown"].exists()
    assert result["csv"].exists()
    assert "nothing was applied" in result["markdown"].read_text(
        encoding="utf-8"
    ).casefold()


def test_pr_workflow_runs_verifier_and_uploads_its_reports() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    workflow = (
        repository_root / ".github" / "workflows" / "provider-policy-pr-gate.yml"
    ).read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "schedule:" not in workflow
    assert "Verify provider policy PR gate receipt" in workflow
    assert "scripts/verify_provider_policy_pr_gate_receipt.py" in workflow
    assert "provider_policy_pr_gate_receipt_verification.json" in workflow
    assert "provider_policy_pr_gate_receipt_verification.md" in workflow
    assert "provider_policy_pr_gate_receipt_verification.csv" in workflow
    assert "secrets." not in workflow
    assert "--live" not in workflow
