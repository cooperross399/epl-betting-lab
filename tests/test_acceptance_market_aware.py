"""Acceptance checklist judges coverage market-aware, consistently with validation."""

from __future__ import annotations

from epl_betting_lab.reports.provider_acceptance_checklist import (
    _technical_staging_success,
)


def _summary(**overrides) -> dict:
    base = {
        "verdict": "Needs provider policy review",
        "staging_validation": {"verdict": "Needs fixes"},
        "checksums": {
            "provenance_status": "Verified",
            "source_odds_checksum_status": "Verified",
            "source_fixtures_checksum_status": "Verified",
            "staging_odds_checksum_status": "Verified",
            "staging_fixtures_checksum_status": "Verified",
            "odds_checksum_pair_status": "Verified",
            "fixtures_checksum_pair_status": "Verified",
        },
        "raw_evidence": {"checksum_status": "Verified"},
        "provider_age": {"status": "Fresh"},
        "team_mapping": {"status": "Verified"},
        "fixture_matching": {"status": "Verified"},
        "market_coverage": {"status": "Incomplete"},
        "odds_completeness": {"completion_percentage": 1.0},
        "market_eligibility": {
            "any_market_eligible": True,
            "eligible_markets": ["1x2", "btts"],
            "excluded_markets": ["total_2_5"],
        },
    }
    base.update(overrides)
    return base


def test_excluded_market_does_not_fail_an_otherwise_clean_run() -> None:
    """total_2_5 incomplete must not sink a run whose eligible markets are complete."""
    assert _technical_staging_success(_summary()) is True


def test_no_eligible_market_is_still_a_technical_failure() -> None:
    assert (
        _technical_staging_success(
            _summary(
                market_eligibility={
                    "any_market_eligible": False,
                    "eligible_markets": [],
                    "excluded_markets": ["1x2", "total_2_5", "btts"],
                }
            )
        )
        is False
    )


def test_records_without_eligibility_fall_back_to_all_markets() -> None:
    """Older archived runs predate market eligibility and keep the old bar."""
    summary = _summary()
    summary.pop("market_eligibility")

    assert _technical_staging_success(summary) is False

    summary["market_coverage"] = {"status": "Complete"}
    assert _technical_staging_success(summary) is True


def test_incomplete_eligible_scope_still_fails() -> None:
    assert (
        _technical_staging_success(
            _summary(odds_completeness={"completion_percentage": 0.9})
        )
        is False
    )


def test_unverified_mapping_still_fails() -> None:
    assert (
        _technical_staging_success(_summary(team_mapping={"status": "Needs review"}))
        is False
    )


def test_checksum_failure_still_fails() -> None:
    assert (
        _technical_staging_success(
            _summary(raw_evidence={"checksum_status": "Mismatch"})
        )
        is False
    )


def test_stale_provider_run_still_fails() -> None:
    assert _technical_staging_success(_summary(provider_age={"status": "Stale"})) is False


def test_ready_for_handoff_short_circuits_to_success() -> None:
    assert (
        _technical_staging_success(
            {"staging_validation": {"verdict": "Ready for handoff"}}
        )
        is True
    )


def test_a_non_policy_shadow_verdict_is_not_a_technical_success() -> None:
    """Only a policy-only block may count as technically successful."""
    assert _technical_staging_success(_summary(verdict="Blocked")) is False
    assert _technical_staging_success(_summary(verdict="Needs mapping fixes")) is False
