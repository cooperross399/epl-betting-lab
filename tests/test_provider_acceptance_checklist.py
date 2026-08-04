from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from epl_betting_lab.reports.provider_acceptance_checklist import (
    ACCEPTANCE_VERDICTS,
    build_provider_acceptance_checklist,
    save_provider_acceptance_checklist,
)
from epl_betting_lab.reports.provider_shadow_history import (
    archive_provider_shadow_run,
    load_provider_shadow_run_history,
)


CHECKSUM_FIELDS = (
    "provenance_status",
    "source_odds_checksum_status",
    "source_fixtures_checksum_status",
    "staging_odds_checksum_status",
    "staging_fixtures_checksum_status",
    "odds_checksum_pair_status",
    "fixtures_checksum_pair_status",
)


def _summary(
    generated_at: str,
    *,
    verdict: str = "Needs provider policy review",
    team_status: str = "Verified",
    team_coverage: float = 1.0,
    fixture_status: str = "Verified",
    fixture_coverage: float = 1.0,
    bookmakers: list[str] | None = None,
    one_x_two_rows: int = 3,
    totals_rows: int = 2,
    btts_rows: int = 2,
    market_status: str = "Complete",
    completeness: float = 1.0,
    provider_age: str = "Fresh",
    policy_status: str = "Provider not allowed",
    provider_allowed: bool = False,
    quota_remaining: str = "498",
    blockers: list[str] | None = None,
) -> dict[str, object]:
    selected_books = bookmakers or ["Example Book"]
    missing_markets = ["btts"] if btts_rows == 0 else []
    return {
        "generated_at": generated_at,
        "provider_key": "odds_api",
        "provider_name": "The Odds API",
        "provider_type": "odds_api",
        "mode": "Live shadow run",
        "verdict": verdict,
        "provider_run": {
            "status": "Completed",
            "fixture_count": 1,
            "odds_row_count": one_x_two_rows + totals_rows + btts_rows,
        },
        "raw_evidence": {"checksum_status": "Verified"},
        "checksums": {field: "Verified" for field in CHECKSUM_FIELDS},
        "provider_age": {"status": provider_age},
        "team_mapping": {
            "status": team_status,
            "coverage_percentage": team_coverage,
            "unmapped_team_count": 0 if team_status == "Verified" else 1,
        },
        "fixture_matching": {
            "status": fixture_status,
            "coverage_percentage": fixture_coverage,
        },
        "bookmaker_coverage": {
            "status": "Available" if selected_books else "Missing",
            "bookmaker_count": len(selected_books),
            "bookmakers": selected_books,
        },
        "market_coverage": {
            "status": market_status,
            "market_counts": {
                "1x2": one_x_two_rows,
                "total_2_5": totals_rows,
                "btts": btts_rows,
            },
            "coverage_percentage": completeness,
            "missing_markets": missing_markets,
        },
        "odds_completeness": {
            "status": "Complete" if completeness == 1.0 else "Incomplete",
            "completion_percentage": completeness,
        },
        "staging_validation": {
            "verdict": "Needs fixes" if not provider_allowed else "Ready for handoff",
            "handoff_eligible": provider_allowed,
        },
        "provider_policy": {
            "provider_policy_status": policy_status,
            "provider_allowed": provider_allowed,
            "all_policy_gates_allowed": provider_allowed,
        },
        "api_quota": {
            "status": "Available",
            "requests_remaining": quota_remaining,
            "requests_used": "2",
            "requests_last": "1",
        },
        "warnings": [],
        "blockers": blockers
        or [
            "Provider `the_odds_api` with type `odds_api` is not allowed by the "
            "staging provider policy."
        ],
    }


def _archive(root: Path, summary: dict[str, object], marker: str) -> Path:
    outputs = root / "data" / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    verification = {
        "json": outputs / "provider_shadow_verification.json",
        "markdown": outputs / "provider_shadow_verification.md",
        "csv": outputs / "provider_shadow_verification.csv",
    }
    verification["json"].write_text(json.dumps(summary), encoding="utf-8")
    verification["markdown"].write_text(f"shadow {marker}\n", encoding="utf-8")
    verification["csv"].write_text(
        "category,check,status,value,details\n",
        encoding="utf-8",
    )
    result = archive_provider_shadow_run(
        summary,
        verification_paths=verification,
        output_dir=outputs,
        archived_at=datetime.fromisoformat(str(summary["generated_at"])),
    )
    return Path(result["directory"])


def _stable_archives(root: Path, count: int = 3) -> None:
    for index in range(count):
        _archive(
            root,
            _summary(f"2026-08-06T{12 + index:02d}:00:00+00:00"),
            f"run-{index + 1}",
        )


def test_acceptance_verdicts_are_explicit() -> None:
    assert ACCEPTANCE_VERDICTS == (
        "Ready for human allowlist review",
        "Needs more shadow runs",
        "Needs mapping fixes",
        "Needs market coverage review",
        "Needs quota review",
        "Needs provider policy review",
        "Not trusted",
    )


def test_missing_history_needs_more_shadow_runs_and_writes_reports(
    tmp_path: Path,
) -> None:
    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
        run_at=datetime.fromisoformat("2026-08-07T12:00:00+00:00"),
    )

    assert result["summary"]["verdict"] == "Needs more shadow runs"
    assert result["summary"]["completed_live_run_count"] == 0
    assert Path(result["json"]).is_file()
    assert Path(result["markdown"]).is_file()
    assert Path(result["csv"]).is_file()


def test_default_minimum_requires_three_completed_live_runs(tmp_path: Path) -> None:
    _stable_archives(tmp_path, count=2)

    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
    )

    assert result["summary"]["verdict"] == "Needs more shadow runs"
    assert result["summary"]["minimum_live_runs"] == 3


def test_stable_policy_pending_runs_are_ready_for_human_review(tmp_path: Path) -> None:
    _stable_archives(tmp_path)

    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
    )
    checks = result["checklist"].set_index("requirement")

    assert result["summary"]["verdict"] == "Ready for human allowlist review"
    assert result["summary"]["provider_currently_allowed"] is False
    assert checks.loc["Provider policy state", "status"] == "Pending human review"
    assert result["summary"]["safety"]["provider_allowlisted"] is False
    assert result["summary"]["safety"]["cron_enabled"] is False


def test_mapping_failure_gets_specific_verdict(tmp_path: Path) -> None:
    _stable_archives(tmp_path, count=2)
    _archive(
        tmp_path,
        _summary(
            "2026-08-06T14:00:00+00:00",
            verdict="Needs mapping fixes",
            team_status="Needs review",
            team_coverage=0.5,
            blockers=[],
        ),
        "mapping",
    )

    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
    )

    assert result["summary"]["verdict"] == "Needs mapping fixes"


def test_market_failure_gets_specific_verdict_and_reports_missing_btts(
    tmp_path: Path,
) -> None:
    _stable_archives(tmp_path, count=2)
    _archive(
        tmp_path,
        _summary(
            "2026-08-06T14:00:00+00:00",
            verdict="Needs market coverage review",
            totals_rows=0,
            btts_rows=0,
            market_status="Incomplete",
            completeness=3 / 7,
            blockers=[],
        ),
        "markets",
    )

    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
    )
    checks = result["checklist"].set_index("requirement")

    assert result["summary"]["verdict"] == "Needs market coverage review"
    assert "Unavailable" in checks.loc[
        "BTTS availability explicitly reported", "observed"
    ]


def test_explicitly_unavailable_btts_remains_a_market_review(
    tmp_path: Path,
) -> None:
    _stable_archives(tmp_path, count=2)
    _archive(
        tmp_path,
        _summary(
            "2026-08-06T14:00:00+00:00",
            verdict="Needs market coverage review",
            btts_rows=0,
            market_status="Incomplete",
            completeness=5 / 7,
            blockers=[],
        ),
        "btts-unavailable",
    )

    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
    )
    checks = result["checklist"].set_index("requirement")

    assert result["summary"]["verdict"] == "Needs market coverage review"
    assert checks.loc[
        "BTTS availability explicitly reported", "status"
    ] == "Pass"
    assert "Unavailable" in checks.loc[
        "BTTS availability explicitly reported", "observed"
    ]


def test_malformed_available_quota_needs_review(tmp_path: Path) -> None:
    _stable_archives(tmp_path, count=2)
    _archive(
        tmp_path,
        _summary(
            "2026-08-06T14:00:00+00:00",
            quota_remaining="unknown",
        ),
        "quota",
    )

    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
    )

    assert result["summary"]["verdict"] == "Needs quota review"


def test_changing_or_unknown_policy_needs_manual_policy_review(
    tmp_path: Path,
) -> None:
    _stable_archives(tmp_path, count=2)
    _archive(
        tmp_path,
        _summary(
            "2026-08-06T14:00:00+00:00",
            policy_status="Unknown provider",
        ),
        "policy",
    )

    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
    )

    assert result["summary"]["verdict"] == "Needs provider policy review"


def test_tampered_archive_is_not_trusted(tmp_path: Path) -> None:
    _stable_archives(tmp_path, count=2)
    latest = _archive(
        tmp_path,
        _summary("2026-08-06T14:00:00+00:00"),
        "tamper",
    )
    (latest / "provider_shadow_verification.md").write_text(
        "changed after archive\n",
        encoding="utf-8",
    )

    result = save_provider_acceptance_checklist(
        "odds_api",
        tmp_path / "data" / "outputs",
    )

    assert result["summary"]["verdict"] == "Not trusted"


def test_checklist_is_read_only_and_preserves_provider_policy(tmp_path: Path) -> None:
    _stable_archives(tmp_path)
    policy = tmp_path / "data" / "manual" / "staging_provider_policy.json"
    policy.parent.mkdir(parents=True)
    original = b'{"allowed_provider_names": ["manual_reviewed"]}\n'
    policy.write_bytes(original)
    records = load_provider_shadow_run_history(
        tmp_path / "data" / "outputs",
        provider_name="odds_api",
    )

    checks, summary = build_provider_acceptance_checklist(
        records,
        provider_name="odds_api",
    )

    assert not checks.empty
    assert summary["safety"]["read_only"] is True
    assert policy.read_bytes() == original
