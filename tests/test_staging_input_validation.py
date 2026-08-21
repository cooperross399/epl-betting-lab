from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.reports.staging_input_validation import (
    build_staging_input_validation,
    save_staging_input_validation,
)


RUN_AT = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
MARKETS = (
    ("1x2", "home", -110),
    ("1x2", "draw", 240),
    ("1x2", "away", 225),
    ("total_2_5", "over", -105),
    ("total_2_5", "under", -115),
    ("btts", "yes", 105),
    ("btts", "no", -125),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _refresh_provider_provenance(paths: dict[str, Path]) -> None:
    paths["source_odds_path"].write_bytes(paths["odds_path"].read_bytes())
    paths["source_fixtures_path"].write_bytes(paths["fixtures_path"].read_bytes())
    paths["provenance_path"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider_name": "manual_reviewed",
                "provider_type": "manual_upload",
                "source_file_path": "data/staging/source_current_odds.csv",
                "source_checksum_sha256": _sha256(paths["source_odds_path"]),
                "source_files": {
                    "current_odds": {
                        "path": "data/staging/source_current_odds.csv",
                        "checksum_sha256": _sha256(paths["source_odds_path"]),
                        "row_count": len(pd.read_csv(paths["source_odds_path"])),
                    },
                    "upcoming_fixtures": {
                        "path": "data/staging/source_upcoming_fixtures.csv",
                        "checksum_sha256": _sha256(paths["source_fixtures_path"]),
                        "row_count": len(pd.read_csv(paths["source_fixtures_path"])),
                    },
                },
                "staging_files": {
                    "current_odds": {
                        "path": "data/staging/current_odds_staging.csv",
                        "checksum_sha256": _sha256(paths["odds_path"]),
                        "row_count": len(pd.read_csv(paths["odds_path"])),
                    },
                    "upcoming_fixtures": {
                        "path": "data/staging/upcoming_fixtures_staging.csv",
                        "checksum_sha256": _sha256(paths["fixtures_path"]),
                        "row_count": len(pd.read_csv(paths["fixtures_path"])),
                    },
                },
                "generated_by": "test suite",
                "generated_at": RUN_AT.isoformat(timespec="seconds"),
                "notes": "Fixed-time staging fixture.",
            }
        ),
        encoding="utf-8",
    )


def _set_provider_timestamp(paths: dict[str, Path], timestamp: str | None) -> None:
    provenance = json.loads(paths["provenance_path"].read_text(encoding="utf-8"))
    if timestamp is None:
        provenance.pop("generated_at", None)
    else:
        provenance["generated_at"] = timestamp
    paths["provenance_path"].write_text(json.dumps(provenance), encoding="utf-8")


def _write_ready_inputs(root: Path) -> dict[str, Path]:
    staging = root / "data" / "staging"
    manual = root / "data" / "manual"
    processed = root / "data" / "processed"
    staging.mkdir(parents=True)
    manual.mkdir(parents=True)
    processed.mkdir(parents=True)
    fixture = {
        "date": "2026-08-08",
        "home_team": "Arsenal",
        "away_team": "Coventry",
        "notes": "",
    }
    fixtures_path = staging / "upcoming_fixtures_staging.csv"
    odds_path = staging / "current_odds_staging.csv"
    source_odds_path = staging / "source_current_odds.csv"
    source_fixtures_path = staging / "source_upcoming_fixtures.csv"
    matches_path = processed / "epl_historical_matches.csv"
    pd.DataFrame([fixture]).to_csv(fixtures_path, index=False)
    pd.DataFrame(
        [
            {
                "date": fixture["date"],
                "home_team": fixture["home_team"],
                "away_team": fixture["away_team"],
                "market": market,
                "selection": selection,
                "american_odds": odds,
                "closing_american_odds": "",
                "book": "Example Book",
                "notes": "",
            }
            for market, selection, odds in MARKETS
        ]
    ).to_csv(odds_path, index=False)
    pd.DataFrame(
        [
            {
                "date": "2026-05-01",
                "home_team": "Arsenal",
                "away_team": "Coventry",
                "home_goals": 2,
                "away_goals": 0,
            }
        ]
    ).to_csv(matches_path, index=False)
    policy_path = manual / "staging_provider_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "allowed_provider_names": ["manual_reviewed"],
                "allowed_provider_types": ["manual_upload"],
                "allow_unknown_providers": False,
                "allow_missing_provenance": False,
                "max_receipt_age_hours": 12,
                "max_provider_run_age_hours": 12,
                "timezone": "America/New_York",
                "thursday_cutoff_time": "10:00",
            }
        ),
        encoding="utf-8",
    )
    paths = {
        "staging_dir": staging,
        "odds_path": odds_path,
        "fixtures_path": fixtures_path,
        "source_odds_path": source_odds_path,
        "source_fixtures_path": source_fixtures_path,
        "matches_path": matches_path,
        "policy_path": policy_path,
        "provenance_path": staging / "staging_provenance.json",
    }
    _refresh_provider_provenance(paths)
    return paths


def _build(
    root: Path,
    paths: dict[str, Path],
    *,
    run_at: datetime = RUN_AT,
):
    return build_staging_input_validation(
        paths["odds_path"],
        paths["fixtures_path"],
        matches_path=paths["matches_path"],
        repository_root=root,
        staging_dir=paths["staging_dir"],
        run_at=run_at,
    )


def test_ready_staging_inputs_pass_existing_handoff_gate(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Ready for handoff"
    assert summary["handoff_eligible"] is True
    assert summary["current_odds_validation"]["status"] == "Ready"
    assert summary["odds_completeness"]["status"] == "Complete"
    assert summary["odds_completeness"]["completion_percentage"] == 1.0
    assert summary["handoff_gate"]["card_generation_allowed"] is True
    assert summary["provider_name"] == "manual_reviewed"
    assert summary["provider_type"] == "manual_upload"
    assert summary["provider_generated_at"] == RUN_AT.isoformat(timespec="seconds")
    assert summary["provider_run_age_minutes"] == 0.0
    assert summary["provider_age_status"] == "Fresh"
    assert summary["provider_policy"]["provider_policy_status"] == "Provider allowed"
    assert summary["provider_policy"]["receipt_age_status"] == "Within age limit"
    assert summary["provider_policy"]["cutoff_policy_status"] == "Before cutoff"
    assert summary["provenance_status"] == "Verified"
    assert summary["source_odds_checksum_status"] == "Verified"
    assert summary["source_fixtures_checksum_status"] == "Verified"
    assert summary["staging_odds_checksum_status"] == "Verified"
    assert summary["staging_fixtures_checksum_status"] == "Verified"
    assert summary["odds_checksum_pair_status"] == "Verified"
    assert summary["fixtures_checksum_pair_status"] == "Verified"
    assert "existing_handoff_gate" in set(checks["check"])


def test_disallowed_provider_needs_fixes(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    provenance = json.loads(paths["provenance_path"].read_text(encoding="utf-8"))
    provenance["provider_name"] = "unapproved_feed"
    paths["provenance_path"].write_text(json.dumps(provenance), encoding="utf-8")

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Needs fixes"
    assert summary["handoff_eligible"] is False
    assert summary["provider_policy"]["provider_policy_status"] == "Provider not allowed"
    assert "provider_allowed" in set(checks["check"])


def test_changed_source_odds_blocks_handoff_with_clear_reason(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths["source_odds_path"].write_bytes(
        paths["source_odds_path"].read_bytes() + b"\n"
    )

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["handoff_eligible"] is False
    assert summary["source_odds_checksum_status"] == "Mismatch"
    assert summary["odds_checksum_pair_status"] == "Mismatch"
    assert "Provider ran, but source odds changed afterward" in summary[
        "provenance_note"
    ]
    assert "source_odds_checksum_status" in set(checks["check"])


def test_changed_staging_odds_blocks_handoff_with_clear_reason(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths["odds_path"].write_bytes(paths["odds_path"].read_bytes() + b"\n")

    _, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["staging_odds_checksum_status"] == "Mismatch"
    assert summary["odds_checksum_pair_status"] == "Mismatch"
    assert "Provider ran, but staging odds changed afterward" in summary[
        "provenance_note"
    ]


@pytest.mark.parametrize(
    ("path_key", "summary_key", "expected_note"),
    (
        (
            "source_fixtures_path",
            "source_fixtures_checksum_status",
            "source fixtures changed afterward",
        ),
        (
            "fixtures_path",
            "staging_fixtures_checksum_status",
            "staging fixtures changed afterward",
        ),
    ),
)
def test_changed_fixture_files_block_handoff(
    tmp_path: Path,
    path_key: str,
    summary_key: str,
    expected_note: str,
) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths[path_key].write_bytes(paths[path_key].read_bytes() + b"\n")

    _, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary[summary_key] == "Mismatch"
    assert summary["fixtures_checksum_pair_status"] == "Mismatch"
    assert expected_note in summary["provenance_note"]


def test_different_verified_source_and_staging_files_fail_pair_check(
    tmp_path: Path,
) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths["source_odds_path"].write_bytes(
        paths["source_odds_path"].read_bytes() + b"\n"
    )
    provenance = json.loads(paths["provenance_path"].read_text(encoding="utf-8"))
    provenance["source_files"]["current_odds"]["checksum_sha256"] = _sha256(
        paths["source_odds_path"]
    )
    paths["provenance_path"].write_text(json.dumps(provenance), encoding="utf-8")

    _, summary = _build(tmp_path, paths)

    assert summary["source_odds_checksum_status"] == "Verified"
    assert summary["staging_odds_checksum_status"] == "Verified"
    assert summary["odds_checksum_pair_status"] == "Mismatch"
    assert summary["verdict"] == "Blocked"


def test_missing_provenance_fails_closed_by_default(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths["provenance_path"].unlink()

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Needs fixes"
    assert summary["handoff_eligible"] is False
    assert summary["provenance_status"] == "Missing"
    assert summary["source_odds_checksum_status"] == "Not available"
    assert "No provenance receipt found" in summary["provenance_note"]
    assert "provider_policy_blocker" in set(checks["check"])


def test_policy_can_explicitly_allow_missing_provenance(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    policy = json.loads(paths["policy_path"].read_text(encoding="utf-8"))
    policy["allow_missing_provenance"] = True
    paths["policy_path"].write_text(json.dumps(policy), encoding="utf-8")
    paths["provenance_path"].unlink()

    _, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Needs fixes"
    assert summary["handoff_eligible"] is False
    assert summary["provider_age_status"] == "Missing"
    assert summary["provider_policy"]["allow_missing_provenance"] is True
    assert (
        summary["provider_policy"]["provider_policy_status"]
        == "Missing provenance allowed"
    )


def test_old_provider_run_blocks_ready_handoff(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    _set_provider_timestamp(paths, "2026-08-05T23:59:00+00:00")

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Needs fixes"
    assert summary["handoff_eligible"] is False
    assert summary["provider_age_status"] == "Too old"
    assert summary["provider_run_age_minutes"] == 721.0
    assert (
        summary["provider_age_note"]
        == "Provider run is too old. Rerun the staging provider before validation."
    )
    assert "provider_age_status" in set(checks["check"])


def test_provider_timestamp_in_future_blocks_ready_handoff(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    _set_provider_timestamp(paths, "2026-08-06T12:01:00+00:00")

    _, summary = _build(tmp_path, paths)

    assert summary["provider_age_status"] == "Future timestamp"
    assert summary["handoff_eligible"] is False
    assert summary["provider_age_note"] == (
        "Provider timestamp is in the future. Check the system clock or "
        "provenance file."
    )


def test_missing_or_invalid_provider_timestamp_blocks_ready_handoff(
    tmp_path: Path,
) -> None:
    for index, (timestamp, expected_status) in enumerate((
        (None, "Missing"),
        ("not-a-timestamp", "Invalid"),
        ("2026-08-06T11:00:00", "Invalid"),
    )):
        paths = _write_ready_inputs(tmp_path / f"case_{index}")
        _set_provider_timestamp(paths, timestamp)

        _, summary = _build(paths["staging_dir"].parents[1], paths)

        assert summary["provider_age_status"] == expected_status
        assert summary["handoff_eligible"] is False


def test_provider_timestamp_at_policy_limit_is_still_fresh(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    _set_provider_timestamp(paths, "2026-08-06T00:00:00+00:00")

    _, summary = _build(tmp_path, paths)

    assert summary["provider_run_age_minutes"] == 720.0
    assert summary["provider_age_status"] == "Fresh"
    assert summary["verdict"] == "Ready for handoff"


def test_missing_recorded_checksum_blocks_handoff(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    provenance = json.loads(paths["provenance_path"].read_text(encoding="utf-8"))
    provenance["source_files"]["upcoming_fixtures"]["checksum_sha256"] = ""
    paths["provenance_path"].write_text(json.dumps(provenance), encoding="utf-8")

    _, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["source_fixtures_checksum_status"] == "Not available"
    assert "valid SHA-256 checksum for source fixtures" in summary[
        "provenance_note"
    ]


def test_missing_recorded_source_file_blocks_handoff(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths["source_fixtures_path"].unlink()

    _, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["source_fixtures_checksum_status"] == "Missing file"
    assert "source fixtures is missing" in summary["provenance_note"]


def test_unreadable_provenance_file_is_reported(tmp_path: Path, monkeypatch) -> None:
    paths = _write_ready_inputs(tmp_path)
    from epl_betting_lab import staging_provider_policy

    real_sha256 = staging_provider_policy.file_sha256

    def fail_source_fixtures(path: Path) -> str:
        if path.name == "source_upcoming_fixtures.csv":
            raise OSError("test read failure")
        return real_sha256(path)

    monkeypatch.setattr(staging_provider_policy, "file_sha256", fail_source_fixtures)

    _, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["source_fixtures_checksum_status"] == "Unreadable file"
    assert "test read failure" in summary["provenance_note"]


def test_missing_provider_policy_blocks_validation(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths["policy_path"].unlink()

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["handoff_eligible"] is False
    assert summary["provider_policy"]["load_status"] == "Policy missing"
    assert "provider_policy_invalid" in set(checks["check"])


def test_staging_validation_after_thursday_cutoff_needs_fixes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    paths = _write_ready_inputs(tmp_path)
    after_cutoff = datetime(2026, 8, 6, 14, 1, tzinfo=timezone.utc)

    _, summary = _build(tmp_path, paths, run_at=after_cutoff)

    assert summary["verdict"] == "Needs fixes"
    assert summary["provider_policy"]["cutoff_policy_status"] == "After cutoff"
    assert summary["handoff_eligible"] is False


def test_manual_run_after_thursday_cutoff_is_handoff_eligible(
    tmp_path: Path, monkeypatch
) -> None:
    """The cutoff is an automation deadline; a workflow_dispatch run passes it."""
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    paths = _write_ready_inputs(tmp_path)
    after_cutoff = datetime(2026, 8, 6, 14, 1, tzinfo=timezone.utc)

    checks, summary = _build(tmp_path, paths, run_at=after_cutoff)

    assert summary["provider_policy"]["cutoff_policy_status"] == "Manual run"
    cutoff_rows = checks[checks["check"] == "thursday_cutoff"]
    assert set(cutoff_rows["severity"]) == {"info"}
    assert summary["verdict"] == "Ready for handoff"
    assert summary["handoff_eligible"] is True


def test_non_thursday_receipt_is_still_handoff_eligible(tmp_path: Path) -> None:
    """The Thursday cutoff only applies on Thursdays.

    The card runs Friday through Monday as well; a receipt generated on those
    days reports "Not a Thursday" and must pass, not fail, the cutoff check.
    """
    paths = _write_ready_inputs(tmp_path)
    friday = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    _set_provider_timestamp(paths, friday.isoformat(timespec="seconds"))

    checks, summary = _build(tmp_path, paths, run_at=friday)

    assert summary["provider_policy"]["cutoff_policy_status"] == "Not a Thursday"
    cutoff_rows = checks[checks["check"] == "thursday_cutoff"]
    assert set(cutoff_rows["severity"]) == {"info"}
    assert summary["verdict"] == "Ready for handoff"
    assert summary["handoff_eligible"] is True


def test_missing_staging_inputs_get_missing_verdict(tmp_path: Path) -> None:
    staging = tmp_path / "data" / "staging"
    staging.mkdir(parents=True)

    _, summary = build_staging_input_validation(
        repository_root=tmp_path,
        staging_dir=staging,
        matches_path=tmp_path / "data" / "processed" / "matches.csv",
        run_at=RUN_AT,
    )

    assert summary["verdict"] == "Missing staging inputs"
    assert summary["handoff_eligible"] is False


def test_past_staging_dates_need_fixes(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    fixtures = pd.read_csv(paths["fixtures_path"])
    odds = pd.read_csv(paths["odds_path"])
    fixtures["date"] = "2026-08-01"
    odds["date"] = "2026-08-01"
    fixtures.to_csv(paths["fixtures_path"], index=False)
    odds.to_csv(paths["odds_path"], index=False)
    _refresh_provider_provenance(paths)

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Needs fixes"
    assert summary["handoff_eligible"] is False
    assert summary["current_odds_date_freshness"]["past_rows"] == len(odds)
    assert summary["fixture_date_freshness"]["past_rows"] == 1
    assert "past_match_date" in set(checks["check"])


def test_incomplete_market_rows_need_fixes(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    odds = pd.read_csv(paths["odds_path"]).iloc[:-1]
    odds.to_csv(paths["odds_path"], index=False)
    _refresh_provider_provenance(paths)

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Needs fixes"
    assert summary["odds_completeness"]["completion_percentage"] < 1.0
    assert "missing_expected_market_row" in set(checks["check"])


def test_invalid_selection_and_duplicate_odds_are_flagged(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    odds = pd.read_csv(paths["odds_path"])
    odds.loc[0, "selection"] = "team-a"
    odds = pd.concat([odds, odds.iloc[[1]]], ignore_index=True)
    odds.to_csv(paths["odds_path"], index=False)
    _refresh_provider_provenance(paths)

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Needs fixes"
    assert "invalid_selection" in set(checks["check"])
    assert "duplicate_row" in set(checks["check"])


def test_non_numeric_odds_and_fixture_mismatch_need_fixes(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    odds = pd.read_csv(paths["odds_path"])
    odds["american_odds"] = odds["american_odds"].astype(str)
    odds.loc[0, "american_odds"] = "not-a-price"
    odds.loc[1, "away_team"] = "Wrong Team"
    odds.to_csv(paths["odds_path"], index=False)
    _refresh_provider_provenance(paths)

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Needs fixes"
    assert "non_numeric_american_odds" in set(checks["check"])
    assert "fixture_not_found" in set(checks["check"])


def test_unreadable_staging_csv_blocks_validation(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths["odds_path"].write_bytes(b"\xff\xfe\x00\x00")

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert "unreadable_staging_csv" in set(checks["check"])


def test_missing_required_columns_block_validation(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    pd.DataFrame([{"date": "2026-08-08", "home_team": "Arsenal"}]).to_csv(
        paths["odds_path"],
        index=False,
    )

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["handoff_eligible"] is False
    assert "missing_required_columns" in set(checks["check"])


def test_path_outside_staging_is_blocked_without_reading_it(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    outside = tmp_path / "data" / "manual" / "current_odds.csv"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("not,a,staging,file\n", encoding="utf-8")
    paths["odds_path"] = outside

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["current_odds_staging"]["readable"] is False
    assert summary["current_odds_staging"]["checksum_sha256"] == ""
    assert "unsafe_staging_path" in set(checks["check"])


def test_save_writes_reports_without_changing_staging_files(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    output_dir = tmp_path / "data" / "outputs"
    original_odds = paths["odds_path"].read_bytes()
    original_fixtures = paths["fixtures_path"].read_bytes()

    result = save_staging_input_validation(
        paths["odds_path"],
        paths["fixtures_path"],
        matches_path=paths["matches_path"],
        output_dir=output_dir,
        repository_root=tmp_path,
        staging_dir=paths["staging_dir"],
        run_at=RUN_AT,
    )

    assert result["verdict"] == "Ready for handoff"
    assert Path(result["csv"]).exists()
    assert Path(result["markdown"]).exists()
    payload = json.loads(Path(result["json"]).read_text(encoding="utf-8"))
    assert payload["generated_at"] == RUN_AT.isoformat(timespec="seconds")
    assert payload["provider_name"] == "manual_reviewed"
    assert payload["provider_type"] == "manual_upload"
    assert payload["provider_age_status"] == "Fresh"
    assert payload["provider_run_age_minutes"] == 0.0
    assert payload["generated_by"] == "test suite"
    assert len(payload["provider_policy"]["checksum_sha256"]) == 64
    assert payload["provider_policy"]["allowed"] is True
    assert payload["provenance_status"] == "Verified"
    assert payload["source_odds_checksum_status"] == "Verified"
    assert payload["source_fixtures_checksum_status"] == "Verified"
    assert payload["staging_odds_checksum_status"] == "Verified"
    assert payload["staging_fixtures_checksum_status"] == "Verified"
    assert "source_odds_checksum_status" in set(
        pd.read_csv(result["csv"])["check"]
    )
    assert "provider_age_status" in set(pd.read_csv(result["csv"])["check"])
    assert "Source-to-staging checksum proof" in Path(result["markdown"]).read_text(
        encoding="utf-8"
    )
    assert payload["current_odds_staging"]["row_count"] == len(MARKETS)
    assert payload["upcoming_fixtures_staging"]["row_count"] == 1
    assert len(payload["current_odds_staging"]["checksum_sha256"]) == 64
    assert len(payload["upcoming_fixtures_staging"]["checksum_sha256"]) == 64
    assert payload["files_promoted_or_copied"] is False
    assert payload["cron_enabled"] is False
    assert paths["odds_path"].read_bytes() == original_odds
    assert paths["fixtures_path"].read_bytes() == original_fixtures
