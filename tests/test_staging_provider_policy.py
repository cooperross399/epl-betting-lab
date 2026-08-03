from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.staging_provider_policy import (
    evaluate_staging_provider_policy,
    load_staging_provider_policy,
)


POLICY = {
    "allowed_provider_names": ["manual_reviewed", "trusted_feed"],
    "allowed_provider_types": ["manual_upload", "odds_api"],
    "allow_unknown_providers": False,
    "max_receipt_age_hours": 12,
    "timezone": "America/New_York",
    "thursday_cutoff_time": "10:00",
}
THURSDAY_BEFORE_CUTOFF = datetime(
    2026,
    8,
    6,
    13,
    59,
    tzinfo=timezone.utc,
)


def _load_policy(root: Path, payload: dict[str, object] | None = None):
    policy_path = root / "data" / "manual" / "staging_provider_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(json.dumps(payload or POLICY), encoding="utf-8")
    return load_staging_provider_policy(policy_path, repository_root=root)


def _provenance(
    provider_name: str = "manual_reviewed",
    provider_type: str = "manual_upload",
) -> dict[str, object]:
    return {
        "provider_name": provider_name,
        "provider_type": provider_type,
        "blockers": [],
        "warnings": [],
    }


def test_allowed_provider_is_fresh_and_before_new_york_cutoff(
    tmp_path: Path,
) -> None:
    policy = _load_policy(tmp_path)

    result = evaluate_staging_provider_policy(
        policy,
        _provenance(),
        receipt_generated_at=THURSDAY_BEFORE_CUTOFF,
        evaluated_at=datetime(2026, 8, 6, 14, 30, tzinfo=timezone.utc),
    )

    assert result["allowed"] is True
    assert result["provider_policy_status"] == "Provider allowed"
    assert result["receipt_age_status"] == "Within age limit"
    assert result["receipt_age_hours"] == 0.517
    assert result["cutoff_policy_status"] == "Before cutoff"
    assert result["cutoff_at"] == "2026-08-06T10:00-04:00"


def test_provider_and_unknown_provider_are_blocked_by_policy(tmp_path: Path) -> None:
    policy = _load_policy(tmp_path)

    disallowed = evaluate_staging_provider_policy(
        policy,
        _provenance("unapproved_feed", "odds_api"),
        receipt_generated_at=THURSDAY_BEFORE_CUTOFF,
        evaluated_at=THURSDAY_BEFORE_CUTOFF,
    )
    unknown = evaluate_staging_provider_policy(
        policy,
        _provenance("", "unknown"),
        receipt_generated_at=THURSDAY_BEFORE_CUTOFF,
        evaluated_at=THURSDAY_BEFORE_CUTOFF,
    )

    assert disallowed["provider_policy_status"] == "Provider not allowed"
    assert disallowed["allowed"] is False
    assert unknown["provider_policy_status"] == "Unknown provider"
    assert unknown["allowed"] is False


def test_receipt_older_than_policy_limit_is_blocked(tmp_path: Path) -> None:
    policy = _load_policy(tmp_path)

    result = evaluate_staging_provider_policy(
        policy,
        _provenance(),
        receipt_generated_at=THURSDAY_BEFORE_CUTOFF,
        evaluated_at=datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc),
    )

    assert result["receipt_age_status"] == "Receipt too old"
    assert result["allowed"] is False
    assert any("at most 12 hours" in item for item in result["blockers"])


def test_receipt_after_thursday_cutoff_is_blocked_in_policy_timezone(
    tmp_path: Path,
) -> None:
    policy = _load_policy(tmp_path)
    after_cutoff = datetime(2026, 8, 6, 14, 1, tzinfo=timezone.utc)

    result = evaluate_staging_provider_policy(
        policy,
        _provenance(),
        receipt_generated_at=after_cutoff,
        evaluated_at=after_cutoff,
    )

    assert result["receipt_age_status"] == "Within age limit"
    assert result["cutoff_policy_status"] == "After cutoff"
    assert result["allowed"] is False


def test_missing_or_malformed_policy_fails_closed(tmp_path: Path) -> None:
    missing_path = tmp_path / "data" / "manual" / "missing.json"
    missing = load_staging_provider_policy(
        missing_path,
        repository_root=tmp_path,
    )
    malformed = _load_policy(
        tmp_path,
        {
            "allowed_provider_names": "manual_reviewed",
            "allowed_provider_types": [],
            "allow_unknown_providers": "no",
            "max_receipt_age_hours": 0,
            "timezone": "not-a-timezone",
            "thursday_cutoff_time": "tomorrow",
        },
    )

    for policy in (missing, malformed):
        result = evaluate_staging_provider_policy(
            policy,
            _provenance(),
            receipt_generated_at=THURSDAY_BEFORE_CUTOFF,
            evaluated_at=THURSDAY_BEFORE_CUTOFF,
        )
        assert result["allowed"] is False
        assert result["blockers"]
        assert result["provider_policy_status"] in {
            "Policy missing",
            "Policy malformed",
        }
