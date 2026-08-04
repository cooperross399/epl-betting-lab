from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.providers.manual_staging_provider import (
    PROVENANCE_FILENAME,
    REPORT_JSON_FILENAME,
    REPORT_MARKDOWN_FILENAME,
    SOURCE_FIXTURES_FILENAME,
    SOURCE_ODDS_FILENAME,
    STAGING_FIXTURES_FILENAME,
    STAGING_ODDS_FILENAME,
    run_manual_staging_provider,
)
from epl_betting_lab.reports.staging_input_validation import (
    build_staging_input_validation,
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


def _write_sources(root: Path) -> dict[str, Path]:
    staging = root / "data" / "staging"
    staging.mkdir(parents=True)
    odds_source = staging / SOURCE_ODDS_FILENAME
    fixtures_source = staging / SOURCE_FIXTURES_FILENAME
    fixture = {
        "date": "2026-08-08",
        "home_team": "Arsenal",
        "away_team": "Coventry",
        "notes": "Prepared fixture source",
    }
    pd.DataFrame([fixture]).to_csv(fixtures_source, index=False)
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
                "notes": "Prepared real-price source",
            }
            for market, selection, odds in MARKETS
        ]
    ).to_csv(odds_source, index=False)
    return {
        "staging": staging,
        "odds_source": odds_source,
        "fixtures_source": fixtures_source,
    }


def _run(root: Path, **kwargs: object) -> dict[str, object]:
    return run_manual_staging_provider(
        repository_root=root,
        run_at=RUN_AT,
        generated_by="test suite",
        notes="Fixed-time provider adapter test.",
        **kwargs,
    )


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_provider_writes_only_staging_bundle_and_reports(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    original_odds = paths["odds_source"].read_bytes()
    original_fixtures = paths["fixtures_source"].read_bytes()

    result = _run(tmp_path)

    summary = result["summary"]
    assert summary["status"] == "Completed"
    assert Path(result["staging_odds"]).read_bytes() == original_odds
    assert Path(result["staging_fixtures"]).read_bytes() == original_fixtures
    provenance = json.loads(Path(result["provenance"]).read_text(encoding="utf-8"))
    assert provenance["provider_name"] == "manual_reviewed"
    assert provenance["provider_type"] == "manual_upload"
    assert provenance["generated_by"] == "test suite"
    assert provenance["generated_at"] == RUN_AT.isoformat(timespec="seconds")
    assert provenance["source_files"]["current_odds"]["checksum_sha256"] == _sha256(
        paths["odds_source"]
    )
    assert provenance["source_files"]["upcoming_fixtures"][
        "checksum_sha256"
    ] == _sha256(paths["fixtures_source"])
    assert provenance["staging_files"]["current_odds"]["checksum_sha256"] == _sha256(
        Path(result["staging_odds"])
    )
    assert provenance["staging_files"]["upcoming_fixtures"][
        "checksum_sha256"
    ] == _sha256(Path(result["staging_fixtures"]))
    assert (tmp_path / "data" / "outputs" / REPORT_JSON_FILENAME).is_file()
    assert (tmp_path / "data" / "outputs" / REPORT_MARKDOWN_FILENAME).is_file()
    assert not (tmp_path / "data" / "manual" / "current_odds.csv").exists()
    assert summary["manual_files_edited"] is False
    assert summary["staging_validation_run"] is False
    assert summary["cron_enabled"] is False
    assert summary["bets_placed"] is False


def test_existing_output_blocks_entire_bundle_without_overwrite(
    tmp_path: Path,
) -> None:
    paths = _write_sources(tmp_path)
    existing_odds = paths["staging"] / STAGING_ODDS_FILENAME
    existing_odds.write_bytes(b"existing odds stay unchanged\n")

    result = _run(tmp_path)

    summary = result["summary"]
    assert summary["status"] == "Blocked"
    assert summary["files_written"] == []
    assert existing_odds.read_bytes() == b"existing odds stay unchanged\n"
    assert not (paths["staging"] / STAGING_FIXTURES_FILENAME).exists()
    assert not (paths["staging"] / PROVENANCE_FILENAME).exists()
    assert any("--overwrite-staging" in item for item in summary["blockers"])


def test_explicit_overwrite_replaces_all_staging_outputs(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    for filename in (
        STAGING_ODDS_FILENAME,
        STAGING_FIXTURES_FILENAME,
        PROVENANCE_FILENAME,
    ):
        (paths["staging"] / filename).write_text("old content\n", encoding="utf-8")

    result = _run(tmp_path, overwrite_staging=True)

    assert result["summary"]["status"] == "Completed"
    assert Path(result["staging_odds"]).read_bytes() == paths[
        "odds_source"
    ].read_bytes()
    assert Path(result["staging_fixtures"]).read_bytes() == paths[
        "fixtures_source"
    ].read_bytes()
    assert len(result["summary"]["files_written"]) == 3


def test_missing_or_empty_source_blocks_without_staging_writes(tmp_path: Path) -> None:
    staging = tmp_path / "data" / "staging"
    staging.mkdir(parents=True)
    (staging / SOURCE_ODDS_FILENAME).write_bytes(b"")

    result = _run(tmp_path)

    assert result["summary"]["status"] == "Blocked"
    assert result["summary"]["files_written"] == []
    assert any("is empty" in item for item in result["summary"]["blockers"])
    assert any("is missing" in item for item in result["summary"]["blockers"])
    assert not (staging / STAGING_ODDS_FILENAME).exists()


def test_source_outside_staging_is_blocked_without_editing_it(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    protected = tmp_path / "data" / "manual" / "current_odds.csv"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(paths["odds_source"].read_bytes())
    original = protected.read_bytes()

    result = _run(tmp_path, odds_source_path=protected)

    assert result["summary"]["status"] == "Blocked"
    assert protected.read_bytes() == original
    assert any(
        "must stay inside `data/staging`" in item
        for item in result["summary"]["blockers"]
    )
    assert not (paths["staging"] / STAGING_ODDS_FILENAME).exists()


def test_source_path_with_traversal_is_blocked(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)

    result = _run(
        tmp_path,
        odds_source_path=Path(
            "data/staging/../staging/source_current_odds.csv"
        ),
    )

    assert result["summary"]["status"] == "Blocked"
    assert any("path traversal" in item for item in result["summary"]["blockers"])
    assert not (paths["staging"] / STAGING_ODDS_FILENAME).exists()


def test_symlink_source_is_blocked(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    real_odds = paths["staging"] / "real_source_odds.csv"
    paths["odds_source"].replace(real_odds)
    paths["odds_source"].symlink_to(real_odds)

    result = _run(tmp_path)

    assert result["summary"]["status"] == "Blocked"
    assert any("symbolic link" in item for item in result["summary"]["blockers"])
    assert not (paths["staging"] / STAGING_ODDS_FILENAME).exists()


def test_provider_output_can_pass_the_separate_staging_gate(tmp_path: Path) -> None:
    paths = _write_sources(tmp_path)
    manual = tmp_path / "data" / "manual"
    processed = tmp_path / "data" / "processed"
    manual.mkdir(parents=True)
    processed.mkdir(parents=True)
    policy_path = manual / "staging_provider_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "allowed_provider_names": ["manual_reviewed"],
                "allowed_provider_types": ["manual_upload"],
                "allow_unknown_providers": False,
                "allow_missing_provenance": False,
                "max_receipt_age_hours": 12,
                "timezone": "America/New_York",
                "thursday_cutoff_time": "10:00",
            }
        ),
        encoding="utf-8",
    )
    matches_path = processed / "epl_historical_matches.csv"
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
    provider_result = _run(tmp_path)

    _, validation = build_staging_input_validation(
        Path(provider_result["staging_odds"]),
        Path(provider_result["staging_fixtures"]),
        matches_path=matches_path,
        repository_root=tmp_path,
        staging_dir=paths["staging"],
        provenance_path=Path(provider_result["provenance"]),
        provider_policy_path=policy_path,
        run_at=RUN_AT,
    )

    assert provider_result["summary"]["staging_validation_run"] is False
    assert validation["verdict"] == "Ready for handoff"
    assert validation["handoff_eligible"] is True
    assert validation["provider_name"] == "manual_reviewed"
    assert validation["provider_type"] == "manual_upload"
    assert validation["provenance_status"] == "Verified"
    assert validation["source_odds_checksum_status"] == "Verified"
    assert validation["source_fixtures_checksum_status"] == "Verified"
    assert validation["staging_odds_checksum_status"] == "Verified"
    assert validation["staging_fixtures_checksum_status"] == "Verified"
    assert validation["source_file_path"] == (
        f"data/staging/{SOURCE_ODDS_FILENAME}"
    )
