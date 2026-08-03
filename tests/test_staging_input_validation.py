from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

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
                "max_receipt_age_hours": 12,
                "timezone": "America/New_York",
                "thursday_cutoff_time": "10:00",
            }
        ),
        encoding="utf-8",
    )
    provenance_path = staging / "staging_provenance.json"
    provenance_path.write_text(
        json.dumps(
            {
                "provider_name": "manual_reviewed",
                "provider_type": "manual_upload",
                "source_file_path": "data/staging/current_odds_staging.csv",
                "source_checksum_sha256": "",
                "generated_by": "test suite",
                "notes": "Fixed-time staging fixture.",
            }
        ),
        encoding="utf-8",
    )
    return {
        "staging_dir": staging,
        "odds_path": odds_path,
        "fixtures_path": fixtures_path,
        "matches_path": matches_path,
        "policy_path": policy_path,
        "provenance_path": provenance_path,
    }


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
    assert summary["provider_policy"]["provider_policy_status"] == "Provider allowed"
    assert summary["provider_policy"]["receipt_age_status"] == "Within age limit"
    assert summary["provider_policy"]["cutoff_policy_status"] == "Before cutoff"
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


def test_missing_provider_policy_blocks_validation(tmp_path: Path) -> None:
    paths = _write_ready_inputs(tmp_path)
    paths["policy_path"].unlink()

    checks, summary = _build(tmp_path, paths)

    assert summary["verdict"] == "Blocked"
    assert summary["handoff_eligible"] is False
    assert summary["provider_policy"]["load_status"] == "Policy missing"
    assert "provider_policy_invalid" in set(checks["check"])


def test_staging_validation_after_thursday_cutoff_needs_fixes(
    tmp_path: Path,
) -> None:
    paths = _write_ready_inputs(tmp_path)
    after_cutoff = datetime(2026, 8, 6, 14, 1, tzinfo=timezone.utc)

    _, summary = _build(tmp_path, paths, run_at=after_cutoff)

    assert summary["verdict"] == "Needs fixes"
    assert summary["provider_policy"]["cutoff_policy_status"] == "After cutoff"
    assert summary["handoff_eligible"] is False


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
    assert payload["generated_by"] == "test suite"
    assert len(payload["provider_policy"]["checksum_sha256"]) == 64
    assert payload["provider_policy"]["allowed"] is True
    assert payload["current_odds_staging"]["row_count"] == len(MARKETS)
    assert payload["upcoming_fixtures_staging"]["row_count"] == 1
    assert len(payload["current_odds_staging"]["checksum_sha256"]) == 64
    assert len(payload["upcoming_fixtures_staging"]["checksum_sha256"]) == 64
    assert payload["files_promoted_or_copied"] is False
    assert payload["cron_enabled"] is False
    assert paths["odds_path"].read_bytes() == original_odds
    assert paths["fixtures_path"].read_bytes() == original_fixtures
