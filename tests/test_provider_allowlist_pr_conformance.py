from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from epl_betting_lab.providers.base import file_sha256
from epl_betting_lab.reports.provider_allowlist_pr_conformance import (
    CONFORMS_VERDICT,
    DOES_NOT_CONFORM_VERDICT,
    MALFORMED_POLICY_VERDICT,
    MISSING_PREVIEW_VERDICT,
    UNSAFE_AUTOMATION_VERDICT,
    build_provider_allowlist_pr_conformance,
    save_provider_allowlist_pr_conformance,
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import READY_STATUS


RUN_AT = datetime(2026, 8, 13, 14, 0, tzinfo=timezone.utc)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _baseline_policy() -> dict[str, object]:
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


def _proposed_entry(
    verification_path: str,
    verification_checksum: str,
) -> dict[str, object]:
    return {
        "provider_key": "odds_api",
        "provider_name": "the_odds_api",
        "provider_type": "odds_api",
        "allowlist_status": "allowed",
        "max_provider_run_age_hours": 12,
        "cutoff_policy": {
            "day": "Thursday",
            "time": "10:00",
            "timezone": "America/New_York",
        },
        "required_markets": ["1x2", "total_2_5"],
        "known_limitations": [
            "BTTS is unavailable and must never be fabricated.",
            "Staging validation remains required.",
        ],
        "evidence_receipt_id": "receipt-123",
        "verification_report_path": verification_path,
        "verification_report_checksum_sha256": verification_checksum,
        "reviewer_name": "Cooper Ross",
        "reviewed_at": "2026-08-13T13:45:00+00:00",
        "approved_at": "2026-08-13T13:30:00+00:00",
    }


def _prepare_preview(root: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    outputs = root / "data" / "outputs"
    policy_path = root / "data" / "manual" / "staging_provider_policy.json"
    verification_path = (
        outputs / "provider_human_acceptance_receipt_verification.json"
    )
    _write_json(
        verification_path,
        {
            "verdict": "Verified for allowlist PR review",
            "provider_key": "odds_api",
        },
    )
    displayed_verification_path = (
        "data/outputs/provider_human_acceptance_receipt_verification.json"
    )
    verification_checksum = file_sha256(verification_path)
    proposed_entry = _proposed_entry(
        displayed_verification_path,
        verification_checksum,
    )
    baseline = _baseline_policy()
    expected = deepcopy(baseline)
    expected["allowed_provider_names"] = ["manual_reviewed", "the_odds_api"]
    expected["provider_allowlist_entries"] = {
        "the_odds_api": proposed_entry
    }
    preview_path = outputs / "provider_allowlist_pr_preview.json"
    preview = {
        "schema_version": 1,
        "generated_at": "2026-08-13T13:50:00+00:00",
        "status": READY_STATUS,
        "provider_key": "odds_api",
        "provider_name": "the_odds_api",
        "provider_type": "odds_api",
        "proposed_allowlist_status": "Allowed",
        "verification": {
            "path": displayed_verification_path,
            "checksum_sha256": verification_checksum,
        },
        "proposed_provider_entry": proposed_entry,
        "before_policy": baseline,
        "after_policy": expected,
        "safety": {"preview_only": True, "cron_enabled": False},
    }
    _write_json(preview_path, preview)
    _write_json(policy_path, expected)
    return outputs, preview_path, policy_path, expected


def _build(root: Path, outputs: Path, preview_path: Path, policy_path: Path):
    return build_provider_allowlist_pr_conformance(
        "odds_api",
        outputs,
        preview_path=preview_path,
        policy_path=policy_path,
        repository_root=root,
        run_at=RUN_AT,
    )


def test_exact_previewed_policy_conforms_without_editing_policy(
    tmp_path: Path,
) -> None:
    outputs, preview_path, policy_path, expected = _prepare_preview(tmp_path)
    original_policy = policy_path.read_bytes()

    checks, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == CONFORMS_VERDICT
    assert summary["actual_policy"] == expected
    assert summary["expected_actual_diff"] == ""
    assert set(checks["status"]) == {"Match"}
    assert summary["safety"]["read_only"] is True
    assert summary["safety"]["provider_policy_edited"] is False
    assert policy_path.read_bytes() == original_policy


def test_missing_proposed_field_does_not_conform(tmp_path: Path) -> None:
    outputs, preview_path, policy_path, expected = _prepare_preview(tmp_path)
    del expected["provider_allowlist_entries"]["the_odds_api"]["required_markets"]
    _write_json(policy_path, expected)

    checks, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == DOES_NOT_CONFORM_VERDICT
    row = checks.loc[
        checks["field"]
        == "provider_allowlist_entries.the_odds_api.required_markets"
    ].iloc[0]
    assert row["status"] == "Missing field"


def test_changed_proposed_value_is_reported(tmp_path: Path) -> None:
    outputs, preview_path, policy_path, expected = _prepare_preview(tmp_path)
    expected["provider_allowlist_entries"]["the_odds_api"][
        "max_provider_run_age_hours"
    ] = 24
    _write_json(policy_path, expected)

    checks, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == DOES_NOT_CONFORM_VERDICT
    assert "Value mismatch" in set(checks["status"])


def test_preview_cannot_omit_a_required_provider_field(tmp_path: Path) -> None:
    outputs, preview_path, policy_path, expected = _prepare_preview(tmp_path)
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    del preview["proposed_provider_entry"]["known_limitations"]
    del preview["after_policy"]["provider_allowlist_entries"]["the_odds_api"][
        "known_limitations"
    ]
    _write_json(preview_path, preview)
    del expected["provider_allowlist_entries"]["the_odds_api"][
        "known_limitations"
    ]
    _write_json(policy_path, expected)

    checks, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == DOES_NOT_CONFORM_VERDICT
    row = checks.loc[
        checks["field"]
        == "provider_allowlist_entries.the_odds_api.known_limitations"
    ].iloc[0]
    assert row["status"] == "Preview not verified"


def test_proposed_entry_must_bind_preview_verification_checksum(
    tmp_path: Path,
) -> None:
    outputs, preview_path, policy_path, expected = _prepare_preview(tmp_path)
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    preview["proposed_provider_entry"][
        "verification_report_checksum_sha256"
    ] = "b" * 64
    preview["after_policy"]["provider_allowlist_entries"]["the_odds_api"][
        "verification_report_checksum_sha256"
    ] = "b" * 64
    _write_json(preview_path, preview)
    expected["provider_allowlist_entries"]["the_odds_api"][
        "verification_report_checksum_sha256"
    ] = "b" * 64
    _write_json(policy_path, expected)

    _, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == DOES_NOT_CONFORM_VERDICT
    assert any(
        "does not bind the same verification" in item
        for item in summary["blockers"]
    )


def test_unrelated_policy_edit_is_detected(tmp_path: Path) -> None:
    outputs, preview_path, policy_path, expected = _prepare_preview(tmp_path)
    expected["allow_unknown_providers"] = True
    _write_json(policy_path, expected)

    checks, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == DOES_NOT_CONFORM_VERDICT
    row = checks.loc[checks["field"] == "allow_unknown_providers"].iloc[0]
    assert row["status"] == "Unexpected policy edit"
    assert any("unrelated or hidden" in item for item in summary["blockers"])


def test_new_cron_flag_is_blocked_as_unsafe(tmp_path: Path) -> None:
    outputs, preview_path, policy_path, expected = _prepare_preview(tmp_path)
    expected["cron_enabled"] = True
    _write_json(policy_path, expected)

    checks, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == UNSAFE_AUTOMATION_VERDICT
    row = checks.loc[checks["field"] == "cron_enabled"].iloc[-1]
    assert row["status"] == "Unsafe automation change"


def test_changed_verification_report_invalidates_preview(tmp_path: Path) -> None:
    outputs, preview_path, policy_path, _ = _prepare_preview(tmp_path)
    verification_path = (
        outputs / "provider_human_acceptance_receipt_verification.json"
    )
    _write_json(verification_path, {"verdict": "Evidence changed"})

    checks, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == DOES_NOT_CONFORM_VERDICT
    row = checks.loc[
        checks["field"] == "verification_report_checksum_sha256"
    ].iloc[0]
    assert row["status"] == "Preview not verified"


def test_missing_preview_returns_beginner_friendly_verdict(tmp_path: Path) -> None:
    outputs, _, policy_path, expected = _prepare_preview(tmp_path)
    missing_preview = outputs / "missing_preview.json"
    _write_json(policy_path, expected)

    _, summary = _build(tmp_path, outputs, missing_preview, policy_path)

    assert summary["verdict"] == MISSING_PREVIEW_VERDICT
    assert any("preview" in item.casefold() for item in summary["blockers"])


def test_malformed_policy_fails_closed(tmp_path: Path) -> None:
    outputs, preview_path, policy_path, _ = _prepare_preview(tmp_path)
    policy_path.write_text("{not-json", encoding="utf-8")

    _, summary = _build(tmp_path, outputs, preview_path, policy_path)

    assert summary["verdict"] == MALFORMED_POLICY_VERDICT
    assert summary["safety"]["provider_policy_edited"] is False


def test_save_writes_three_reports_and_keeps_policy_unchanged(
    tmp_path: Path,
) -> None:
    outputs, preview_path, policy_path, _ = _prepare_preview(tmp_path)
    original_policy = policy_path.read_bytes()

    result = save_provider_allowlist_pr_conformance(
        "odds_api",
        outputs,
        preview_path=preview_path,
        policy_path=policy_path,
        repository_root=tmp_path,
        run_at=RUN_AT,
    )

    assert result["verdict"] == CONFORMS_VERDICT
    assert Path(result["json"]).is_file()
    assert Path(result["markdown"]).is_file()
    assert Path(result["csv"]).is_file()
    markdown = Path(result["markdown"]).read_text(encoding="utf-8")
    assert "Read-only check: nothing was applied" in markdown
    assert "## Expected/actual diff" in markdown
    assert policy_path.read_bytes() == original_policy
