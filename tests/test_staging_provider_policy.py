from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from epl_betting_lab.staging_provider_policy import (
    evaluate_provider_run_age,
    evaluate_staging_provider_policy,
    load_staging_provider_policy,
)


POLICY = {
    "allowed_provider_names": ["manual_reviewed", "trusted_feed"],
    "allowed_provider_types": ["manual_upload", "odds_api"],
    "allow_unknown_providers": False,
    "allow_missing_provenance": False,
    "max_receipt_age_hours": 12,
    "max_provider_run_age_hours": 12,
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
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(payload or POLICY), encoding="utf-8")
    return load_staging_provider_policy(policy_path, repository_root=root)


def _provenance(
    provider_name: str = "manual_reviewed",
    provider_type: str = "manual_upload",
) -> dict[str, object]:
    return {
        "provider_name": provider_name,
        "provider_type": provider_type,
        "provenance_status": "Verified",
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


def test_missing_provenance_is_blocked_unless_policy_explicitly_allows_it(
    tmp_path: Path,
) -> None:
    missing_provenance = {
        "provider_name": "",
        "provider_type": "unknown",
        "provenance_status": "Missing",
        "blockers": [],
        "warnings": [],
    }
    policy = _load_policy(tmp_path)

    blocked = evaluate_staging_provider_policy(
        policy,
        missing_provenance,
        receipt_generated_at=THURSDAY_BEFORE_CUTOFF,
        evaluated_at=THURSDAY_BEFORE_CUTOFF,
    )

    assert blocked["allowed"] is False
    assert blocked["provider_policy_status"] == "Missing provenance blocked"

    permissive_policy = dict(POLICY, allow_missing_provenance=True)
    allowed = evaluate_staging_provider_policy(
        _load_policy(tmp_path, permissive_policy),
        missing_provenance,
        receipt_generated_at=THURSDAY_BEFORE_CUTOFF,
        evaluated_at=THURSDAY_BEFORE_CUTOFF,
    )

    assert allowed["allowed"] is True
    assert allowed["provider_policy_status"] == "Missing provenance allowed"
    assert allowed["warnings"]


def test_provider_run_age_is_timezone_aware_and_fresh(tmp_path: Path) -> None:
    policy = _load_policy(tmp_path)

    result = evaluate_provider_run_age(
        policy,
        "2026-08-06T08:59:00-04:00",
        evaluated_at=THURSDAY_BEFORE_CUTOFF,
    )

    assert result["provider_age_status"] == "Fresh"
    assert result["provider_run_age_minutes"] == 60.0
    assert result["fresh"] is True


def test_provider_run_age_blocks_old_future_missing_and_invalid_timestamps(
    tmp_path: Path,
) -> None:
    policy = _load_policy(tmp_path)
    cases = (
        ("2026-08-05T20:00:00+00:00", "Too old"),
        ("2026-08-06T14:00:00+00:00", "Future timestamp"),
        ("", "Missing"),
        ("not-a-timestamp", "Invalid"),
        ("2026-08-06T12:00:00", "Invalid"),
    )

    for timestamp, expected_status in cases:
        result = evaluate_provider_run_age(
            policy,
            timestamp,
            evaluated_at=THURSDAY_BEFORE_CUTOFF,
        )
        assert result["provider_age_status"] == expected_status
        assert result["fresh"] is False


def test_provider_run_age_fails_closed_when_policy_is_unavailable(
    tmp_path: Path,
) -> None:
    missing_policy = load_staging_provider_policy(
        tmp_path / "data" / "manual" / "missing.json",
        repository_root=tmp_path,
    )

    result = evaluate_provider_run_age(
        missing_policy,
        THURSDAY_BEFORE_CUTOFF,
        evaluated_at=THURSDAY_BEFORE_CUTOFF,
    )

    assert result["provider_age_status"] == "Policy unavailable"
    assert result["fresh"] is False


# --- the Thursday cutoff applies on Thursdays -------------------------------
#
# It used to be measured against "this week's Thursday", computed as today plus
# (3 - weekday). On Friday, Saturday and Sunday that lands on the Thursday just
# gone, so a receipt made on any of those days was always after it. Every
# weekend run was blocked by a rule about Thursday — and the card is built five
# days a week, three of them the matchdays. Week 1 is a Friday, a Saturday and
# a Sunday, so every card that mattered would have been refused, citing a
# Thursday policy.


def _at(day: int, hour: int) -> datetime:
    """A receipt at a given hour on a given weekday of the same week."""
    monday = datetime(2026, 8, 17, tzinfo=timezone.utc)  # a Monday
    return (monday + timedelta(days=day)).replace(hour=hour + 4)  # 04:00 UTC = 00:00 ET


def _evaluate(
    tmp_path: Path, when: datetime, *, run_trigger: str = "schedule"
) -> dict:
    return evaluate_staging_provider_policy(
        _load_policy(tmp_path),
        _provenance(),
        receipt_generated_at=when,
        evaluated_at=when + timedelta(minutes=5),
        run_trigger=run_trigger,
    )


def test_a_friday_receipt_is_not_blocked_by_the_thursday_cutoff(
    tmp_path: Path,
) -> None:
    result = _evaluate(tmp_path, _at(4, 9))

    assert result["cutoff_policy_status"] == "Not a Thursday"
    assert not any("cutoff" in str(b).lower() for b in result["blockers"])


def test_a_saturday_receipt_is_not_blocked(tmp_path: Path) -> None:
    result = _evaluate(tmp_path, _at(5, 9))

    assert result["cutoff_policy_status"] == "Not a Thursday"


def test_a_sunday_receipt_is_not_blocked(tmp_path: Path) -> None:
    result = _evaluate(tmp_path, _at(6, 9))

    assert result["cutoff_policy_status"] == "Not a Thursday"


def test_a_thursday_receipt_before_the_cutoff_passes(tmp_path: Path) -> None:
    result = _evaluate(tmp_path, _at(3, 9))

    assert result["cutoff_policy_status"] == "Before cutoff"


def test_a_thursday_receipt_after_the_cutoff_is_still_blocked(
    tmp_path: Path,
) -> None:
    """The rule still does the job it was written for."""
    result = _evaluate(tmp_path, _at(3, 11))

    assert result["cutoff_policy_status"] == "After cutoff"
    assert any("cutoff" in str(b).lower() for b in result["blockers"])


def test_every_day_the_card_runs_can_pass_the_cutoff(tmp_path: Path) -> None:
    """Thursday, Friday, Saturday, Sunday and Monday all build cards."""
    for day, hour in ((3, 9), (4, 9), (5, 5), (6, 5), (0, 9)):
        result = _evaluate(tmp_path, _at(day, hour))
        assert result["cutoff_policy_status"] in {"Before cutoff", "Not a Thursday"}, (
            day,
            result["cutoff_policy_status"],
        )


# --- the cutoff is an automation deadline, so a manual dispatch passes it ----


def test_a_manual_thursday_run_after_the_cutoff_passes(tmp_path: Path) -> None:
    """A human dispatching the workflow is not automation racing a deadline."""
    result = _evaluate(tmp_path, _at(3, 11), run_trigger="workflow_dispatch")

    assert result["cutoff_policy_status"] == "Manual run"
    assert not any("cutoff" in str(b).lower() for b in result["blockers"])


def test_a_scheduled_thursday_run_after_the_cutoff_stays_blocked(
    tmp_path: Path,
) -> None:
    result = _evaluate(tmp_path, _at(3, 11), run_trigger="schedule")

    assert result["cutoff_policy_status"] == "After cutoff"
    assert any("cutoff" in str(b).lower() for b in result["blockers"])


def test_the_trigger_is_read_from_the_actions_environment(
    tmp_path: Path, monkeypatch
) -> None:
    """With no explicit trigger, GITHUB_EVENT_NAME decides — and its absence
    fails closed: an unknown trigger is treated as automation."""
    when = _at(3, 11)
    common = dict(
        receipt_generated_at=when, evaluated_at=when + timedelta(minutes=5)
    )

    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    dispatched = evaluate_staging_provider_policy(
        _load_policy(tmp_path), _provenance(), **common
    )
    assert dispatched["cutoff_policy_status"] == "Manual run"

    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    unknown = evaluate_staging_provider_policy(
        _load_policy(tmp_path), _provenance(), **common
    )
    assert unknown["cutoff_policy_status"] == "After cutoff"
