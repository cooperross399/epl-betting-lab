from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.provider_shadow_history import (
    COMPARISON_VERDICTS,
    archive_provider_shadow_run,
    list_recent_provider_shadow_runs,
    save_provider_shadow_run_comparison,
)


def _summary(
    generated_at: str,
    *,
    verdict: str = "Shadow ready for review",
    team_status: str = "Verified",
    bookmaker_count: int = 1,
    provider_allowed: bool = True,
    warnings: list[str] | None = None,
    blockers: list[str] | None = None,
) -> dict[str, object]:
    bookmakers = [f"Book {index + 1}" for index in range(bookmaker_count)]
    return {
        "generated_at": generated_at,
        "provider_key": "odds_api",
        "provider_name": "The Odds API",
        "provider_type": "odds_api",
        "mode": "Live shadow run",
        "verdict": verdict,
        "raw_evidence": {"checksum_status": "Verified"},
        "checksums": {
            "provenance_status": "Verified",
            "source_odds_checksum_status": "Verified",
            "source_fixtures_checksum_status": "Verified",
            "staging_odds_checksum_status": "Verified",
            "staging_fixtures_checksum_status": "Verified",
            "odds_checksum_pair_status": "Verified",
            "fixtures_checksum_pair_status": "Verified",
        },
        "provider_age": {"status": "Fresh"},
        "team_mapping": {
            "status": team_status,
            "coverage_percentage": 1.0 if team_status == "Verified" else 0.5,
            "unmapped_team_count": 0 if team_status == "Verified" else 1,
        },
        "fixture_matching": {
            "status": "Verified",
            "coverage_percentage": 1.0,
        },
        "bookmaker_coverage": {
            "status": "Available",
            "bookmaker_count": bookmaker_count,
            "bookmakers": bookmakers,
        },
        "market_coverage": {
            "status": "Complete",
            "market_counts": {"1x2": 3, "total_2_5": 2, "btts": 2},
            "coverage_percentage": 1.0,
            "missing_markets": [],
        },
        "odds_completeness": {
            "status": "Complete",
            "completion_percentage": 1.0,
        },
        "staging_validation": {
            "verdict": "Ready for handoff",
            "handoff_eligible": True,
        },
        "provider_policy": {
            "provider_policy_status": (
                "Provider allowed" if provider_allowed else "Provider not allowed"
            ),
            "provider_allowed": provider_allowed,
            "all_policy_gates_allowed": provider_allowed,
        },
        "api_quota": {
            "requests_remaining": "498",
            "requests_used": "2",
            "requests_last": "1",
        },
        "warnings": warnings or [],
        "blockers": blockers or [],
    }


def _write_source_reports(
    output_dir: Path,
    summary: dict[str, object],
    *,
    marker: str,
) -> dict[str, dict[str, Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    verification = {
        "json": output_dir / "provider_shadow_verification.json",
        "markdown": output_dir / "provider_shadow_verification.md",
        "csv": output_dir / "provider_shadow_verification.csv",
    }
    verification["json"].write_text(
        json.dumps(summary, sort_keys=True), encoding="utf-8"
    )
    verification["markdown"].write_text(f"shadow {marker}\n", encoding="utf-8")
    verification["csv"].write_text(
        f"category,check,status,value,details\nrun,verdict,{marker},,\n",
        encoding="utf-8",
    )
    provider = {
        "json": output_dir / "odds_api_staging_provider_report.json",
        "markdown": output_dir / "odds_api_staging_provider_report.md",
    }
    provider["json"].write_text(json.dumps({"marker": marker}), encoding="utf-8")
    provider["markdown"].write_text(f"provider {marker}\n", encoding="utf-8")
    staging = {
        "json": output_dir / "staging_input_validation.json",
        "markdown": output_dir / "staging_input_validation.md",
        "csv": output_dir / "staging_input_validation.csv",
    }
    staging["json"].write_text(json.dumps({"marker": marker}), encoding="utf-8")
    staging["markdown"].write_text(f"staging {marker}\n", encoding="utf-8")
    staging["csv"].write_text("check,status\nproof,Verified\n", encoding="utf-8")
    return {"verification": verification, "provider": provider, "staging": staging}


def _archive(
    root: Path,
    generated_at: str,
    *,
    marker: str,
) -> dict[str, object]:
    summary = _summary(generated_at)
    output_dir = root / "data" / "outputs"
    paths = _write_source_reports(output_dir, summary, marker=marker)
    return archive_provider_shadow_run(
        summary,
        verification_paths=paths["verification"],
        provider_report_paths=paths["provider"],
        staging_validation_paths=paths["staging"],
        output_dir=output_dir,
        archived_at=datetime.fromisoformat(generated_at),
    )


def test_comparison_verdicts_are_explicit_and_conservative() -> None:
    assert COMPARISON_VERDICTS == (
        "Stable enough for review",
        "Needs more shadow runs",
        "Coverage changed",
        "Mapping issue",
        "Market coverage issue",
        "Provider policy issue",
        "Failed/untrusted",
    )


def test_shadow_archive_copies_reports_and_verifies_checksums(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        "2026-08-06T12:00:00+00:00",
        marker="first",
    )
    archive_dir = Path(archive["directory"])

    assert archive_dir.relative_to(tmp_path).as_posix().endswith(
        "data/outputs/archive/provider_shadow_runs/2026-08-06/120000_odds_api"
    )
    assert {
        "provider_shadow_verification.json",
        "provider_shadow_verification.md",
        "provider_shadow_verification.csv",
        "provider_run_report.json",
        "provider_run_report.md",
        "staging_input_validation.json",
        "staging_input_validation.md",
        "staging_input_validation.csv",
        "archive_metadata.json",
    }.issubset({path.name for path in archive_dir.iterdir()})
    metadata = json.loads(Path(archive["metadata"]).read_text(encoding="utf-8"))
    assert metadata["provider_key"] == "odds_api"
    assert all(
        record["checksum_sha256"]
        for record in metadata["files"].values()
        if record["status"] == "Archived"
    )
    history = list_recent_provider_shadow_runs(
        tmp_path / "data" / "outputs",
        provider_name="odds_api",
    )
    assert history[0]["archive_integrity_status"] == "Verified"


def test_shadow_archive_never_overwrites_same_second_snapshot(tmp_path: Path) -> None:
    first = _archive(
        tmp_path,
        "2026-08-06T12:00:00+00:00",
        marker="first",
    )
    second = _archive(
        tmp_path,
        "2026-08-06T12:00:00+00:00",
        marker="second",
    )

    assert first["directory"] != second["directory"]
    assert Path(second["directory"]).name == "120000_odds_api_02"
    assert "first" in (
        Path(first["directory"]) / "provider_shadow_verification.md"
    ).read_text(encoding="utf-8")


def test_comparison_needs_at_least_two_archived_runs(tmp_path: Path) -> None:
    _archive(tmp_path, "2026-08-06T12:00:00+00:00", marker="one")

    result = save_provider_shadow_run_comparison(
        "odds_api",
        tmp_path / "data" / "outputs",
    )

    assert result["summary"]["verdict"] == "Needs more shadow runs"
    assert result["summary"]["archive_count"] == 1
    assert Path(result["json"]).is_file()
    assert list(pd.read_csv(result["csv"]).columns) == [
        "category",
        "metric",
        "previous_value",
        "latest_value",
        "change",
        "change_status",
        "previous_run",
        "latest_run",
        "details",
    ]


def test_comparison_detects_bookmaker_coverage_change(tmp_path: Path) -> None:
    _archive(tmp_path, "2026-08-06T12:00:00+00:00", marker="one")
    changed_summary = _summary(
        "2026-08-06T13:00:00+00:00",
        bookmaker_count=2,
    )
    output_dir = tmp_path / "data" / "outputs"
    paths = _write_source_reports(output_dir, changed_summary, marker="two")
    archive_provider_shadow_run(
        changed_summary,
        verification_paths=paths["verification"],
        provider_report_paths=paths["provider"],
        staging_validation_paths=paths["staging"],
        output_dir=output_dir,
    )

    result = save_provider_shadow_run_comparison("odds_api", output_dir)
    comparison = result["comparison"]

    assert result["summary"]["verdict"] == "Coverage changed"
    bookmaker_row = comparison[comparison["metric"] == "bookmaker_count"].iloc[0]
    assert bookmaker_row["previous_value"] == "1"
    assert bookmaker_row["latest_value"] == "2"
    assert bookmaker_row["change_status"] == "Changed"


def test_comparison_flags_mapping_and_policy_issues(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    _archive(tmp_path, "2026-08-06T12:00:00+00:00", marker="one")
    mapping_summary = _summary(
        "2026-08-06T13:00:00+00:00",
        verdict="Needs mapping fixes",
        team_status="Needs review",
    )
    mapping_paths = _write_source_reports(output_dir, mapping_summary, marker="mapping")
    archive_provider_shadow_run(
        mapping_summary,
        verification_paths=mapping_paths["verification"],
        provider_report_paths=mapping_paths["provider"],
        staging_validation_paths=mapping_paths["staging"],
        output_dir=output_dir,
    )
    assert (
        save_provider_shadow_run_comparison("odds_api", output_dir)["summary"][
            "verdict"
        ]
        == "Mapping issue"
    )

    policy_summary = _summary(
        "2026-08-06T14:00:00+00:00",
        verdict="Needs provider policy review",
        provider_allowed=False,
    )
    policy_paths = _write_source_reports(output_dir, policy_summary, marker="policy")
    archive_provider_shadow_run(
        policy_summary,
        verification_paths=policy_paths["verification"],
        provider_report_paths=policy_paths["provider"],
        staging_validation_paths=policy_paths["staging"],
        output_dir=output_dir,
    )
    assert (
        save_provider_shadow_run_comparison("odds_api", output_dir)["summary"][
            "verdict"
        ]
        == "Provider policy issue"
    )


def test_three_consistent_runs_are_stable_enough_for_manual_review(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "data" / "outputs"
    for index, hour in enumerate((12, 13, 14), start=1):
        summary = _summary(
            f"2026-08-06T{hour:02d}:00:00+00:00",
            verdict="Needs provider policy review",
            provider_allowed=False,
        )
        paths = _write_source_reports(output_dir, summary, marker=f"run-{index}")
        archive_provider_shadow_run(
            summary,
            verification_paths=paths["verification"],
            provider_report_paths=paths["provider"],
            staging_validation_paths=paths["staging"],
            output_dir=output_dir,
        )

    result = save_provider_shadow_run_comparison(
        "odds_api",
        output_dir,
    )

    assert result["summary"]["verdict"] == "Stable enough for review"
    assert result["summary"]["archive_count"] == 3
    assert result["summary"]["latest_provider_allowed"] is False
    assert result["summary"]["safety"]["provider_policy_edited"] is False
    assert result["summary"]["safety"]["cron_enabled"] is False


def test_tampered_archive_is_failed_and_untrusted(tmp_path: Path) -> None:
    _archive(tmp_path, "2026-08-06T12:00:00+00:00", marker="one")
    latest = _archive(tmp_path, "2026-08-06T13:00:00+00:00", marker="two")
    (Path(latest["directory"]) / "provider_shadow_verification.md").write_text(
        "changed after archive\n",
        encoding="utf-8",
    )

    result = save_provider_shadow_run_comparison(
        "odds_api",
        tmp_path / "data" / "outputs",
    )

    assert result["summary"]["verdict"] == "Failed/untrusted"
    assert result["summary"]["latest_run"]["archive_integrity_status"] == "Mismatch"


def test_comparison_reports_warning_and_blocker_changes(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "outputs"
    first_summary = _summary(
        "2026-08-06T12:00:00+00:00",
        warnings=["Old warning"],
    )
    first_paths = _write_source_reports(output_dir, first_summary, marker="first")
    archive_provider_shadow_run(
        first_summary,
        verification_paths=first_paths["verification"],
        provider_report_paths=first_paths["provider"],
        staging_validation_paths=first_paths["staging"],
        output_dir=output_dir,
    )
    second_summary = _summary(
        "2026-08-06T13:00:00+00:00",
        warnings=["New warning"],
        blockers=["New blocker"],
    )
    second_paths = _write_source_reports(output_dir, second_summary, marker="second")
    archive_provider_shadow_run(
        second_summary,
        verification_paths=second_paths["verification"],
        provider_report_paths=second_paths["provider"],
        staging_validation_paths=second_paths["staging"],
        output_dir=output_dir,
    )

    rows = save_provider_shadow_run_comparison("odds_api", output_dir)["comparison"]

    assert "New warning" in rows.loc[
        rows["metric"] == "warnings_added", "latest_value"
    ].iloc[0]
    assert "Old warning" in rows.loc[
        rows["metric"] == "warnings_removed", "previous_value"
    ].iloc[0]
    assert "New blocker" in rows.loc[
        rows["metric"] == "blockers_added", "latest_value"
    ].iloc[0]
