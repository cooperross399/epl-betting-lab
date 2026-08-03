from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.github_runner_inputs import (
    build_github_runner_input_handoff,
    save_github_runner_input_handoff,
)
from epl_betting_lab.reports.staging_input_validation import (
    save_staging_input_validation,
)


RUN_AT = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
MARKETS = [
    ("1x2", "home", -110),
    ("1x2", "draw", 240),
    ("1x2", "away", 225),
    ("total_2_5", "over", -105),
    ("total_2_5", "under", -115),
    ("btts", "yes", 105),
    ("btts", "no", -125),
]


def _write_inputs(
    root: Path,
    *,
    fixture_dates: tuple[str, ...] = ("2026-08-08",),
    include_markets: tuple[tuple[str, str, int], ...] | None = None,
) -> dict[str, Path]:
    manual = root / "data" / "manual"
    processed = root / "data" / "processed"
    output = root / "data" / "outputs"
    manual.mkdir(parents=True)
    processed.mkdir(parents=True)

    fixtures_rows = []
    odds_rows = []
    markets = list(include_markets) if include_markets is not None else MARKETS
    for index, fixture_date in enumerate(fixture_dates):
        home = f"Home {index + 1}"
        away = f"Away {index + 1}"
        fixtures_rows.append(
            {"date": fixture_date, "home_team": home, "away_team": away}
        )
        for market, selection, american_odds in markets:
            odds_rows.append(
                {
                    "date": fixture_date,
                    "home_team": home,
                    "away_team": away,
                    "market": market,
                    "selection": selection,
                    "american_odds": american_odds,
                    "closing_american_odds": "",
                    "book": "Example Book",
                    "notes": "",
                }
            )

    fixtures = manual / "upcoming_fixtures.csv"
    odds = manual / "current_odds.csv"
    matches = processed / "epl_historical_matches.csv"
    pd.DataFrame(fixtures_rows).to_csv(fixtures, index=False)
    pd.DataFrame(odds_rows).to_csv(odds, index=False)
    pd.DataFrame(
        [
            {
                "date": "2026-05-01",
                "home_team": "Home 1",
                "away_team": "Away 1",
                "home_goals": 1,
                "away_goals": 0,
            }
        ]
    ).to_csv(matches, index=False)
    return {
        "current_odds_path": odds,
        "fixtures_path": fixtures,
        "matches_path": matches,
        "output_dir": output,
    }


def _build(
    root: Path,
    paths: dict[str, Path],
    *,
    run_at: datetime = RUN_AT,
    **kwargs,
) -> dict[str, object]:
    return build_github_runner_input_handoff(
        current_odds_path=paths["current_odds_path"],
        fixtures_path=paths["fixtures_path"],
        matches_path=paths["matches_path"],
        run_at=run_at,
        repository_root=root,
        **kwargs,
    )


def _write_ready_staging_receipt(
    root: Path,
    *,
    receipt_run_at: datetime = RUN_AT,
) -> tuple[dict[str, Path], Path]:
    paths = _write_inputs(root)
    staging = root / "data" / "staging"
    staging.mkdir(parents=True)
    staging_odds = staging / "current_odds_staging.csv"
    staging_fixtures = staging / "upcoming_fixtures_staging.csv"
    staging_odds.write_bytes(paths["current_odds_path"].read_bytes())
    staging_fixtures.write_bytes(paths["fixtures_path"].read_bytes())
    policy_path = root / "data" / "manual" / "staging_provider_policy.json"
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
                "notes": "Ready receipt fixture.",
            }
        ),
        encoding="utf-8",
    )
    paths["current_odds_path"] = staging_odds
    paths["fixtures_path"] = staging_fixtures
    paths["staging_provider_policy_path"] = policy_path
    paths["staging_provenance_path"] = provenance_path
    saved = save_staging_input_validation(
        staging_odds,
        staging_fixtures,
        matches_path=paths["matches_path"],
        output_dir=paths["output_dir"],
        repository_root=root,
        staging_dir=staging,
        run_at=receipt_run_at,
    )
    return paths, Path(saved["json"])


def test_runner_handoff_records_valid_committed_inputs_and_allows_card(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(tmp_path)

    result = _build(
        tmp_path,
        paths,
        github_ref="refs/heads/weekly-odds",
        github_sha="abc123",
    )

    assert result["status"] == "Warnings only"
    assert result["card_generation_allowed"] is True
    assert result["current_odds_path"] == "data/manual/current_odds.csv"
    assert result["fixtures_path"] == "data/manual/upcoming_fixtures.csv"
    assert len(str(result["current_odds_checksum_sha256"])) == 64
    assert result["current_odds_checksum_status"] == "Recorded"
    assert result["current_odds_freshness_status"] == "Fresh"
    assert result["fixtures_freshness_status"] == "Fresh"
    assert result["validation_status"] == "Ready"
    assert result["validation_serious_issue_count"] == 0
    assert result["completeness_status"] == "Complete"
    assert result["completion_percentage"] == 1.0
    assert result["github_ref"] == "refs/heads/weekly-odds"
    assert result["github_sha"] == "abc123"


def test_runner_handoff_blocks_any_odds_rows_tied_to_past_matches(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(
        tmp_path,
        fixture_dates=("2026-08-05", "2026-08-08"),
    )

    result = _build(tmp_path, paths)

    assert result["status"] == "Blocked"
    assert result["card_generation_allowed"] is False
    assert result["current_odds_past_rows"] == 7
    assert result["current_odds_today_or_future_rows"] == 7
    assert any("tied to past matches" in item for item in result["blockers"])


def test_runner_handoff_blocks_past_fixture_rows(tmp_path: Path) -> None:
    paths = _write_inputs(
        tmp_path,
        fixture_dates=("2026-08-05", "2026-08-08"),
    )

    result = _build(tmp_path, paths)

    assert result["fixtures_past_rows"] == 1
    assert result["card_generation_allowed"] is False
    assert any("past match row" in item for item in result["blockers"])


def test_runner_handoff_blocks_incomplete_expected_market_rows(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(
        tmp_path,
        include_markets=tuple(MARKETS[:3]),
    )

    result = _build(tmp_path, paths)

    assert result["status"] == "Blocked"
    assert result["completeness_status"] == "Blocked"
    assert result["completion_percentage"] < 1.0
    assert result["incomplete_match_count"] == 1
    assert result["card_generation_allowed"] is False


def test_runner_handoff_blocks_missing_current_odds_file(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    paths["current_odds_path"].unlink()

    result = _build(tmp_path, paths)

    assert result["status"] == "Blocked"
    assert result["current_odds_checksum_status"] == "Not available"
    assert result["validation_status"] == "Not checked"
    assert result["card_generation_allowed"] is False
    assert any("is missing" in item for item in result["blockers"])


def test_runner_handoff_blocks_malformed_odds_dates(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    odds = pd.read_csv(paths["current_odds_path"])
    odds["date"] = "2026-99-99"
    odds.to_csv(paths["current_odds_path"], index=False)

    with pytest.warns(UserWarning, match="Could not infer format"):
        result = _build(tmp_path, paths)

    assert result["current_odds_freshness_status"] == "Not checked"
    assert result["current_odds_invalid_date_rows"] == 7
    assert result["card_generation_allowed"] is False
    assert any("malformed" in item for item in result["blockers"])


def test_runner_handoff_blocks_paths_outside_repository(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    paths = _write_inputs(root)
    outside = tmp_path / "outside_current_odds.csv"
    outside.write_text(
        paths["current_odds_path"].read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paths["current_odds_path"] = outside

    result = _build(root, paths)

    assert result["current_odds_path_policy_valid"] is False
    assert result["card_generation_allowed"] is False
    assert any("inside" in item for item in result["blockers"])


def test_runner_handoff_blocks_symbolic_link_inputs(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    link = paths["current_odds_path"].with_name("linked_current_odds.csv")
    link.symlink_to(paths["current_odds_path"])
    paths["current_odds_path"] = link

    result = _build(tmp_path, paths)

    assert result["current_odds_path_policy_valid"] is False
    assert result["card_generation_allowed"] is False
    assert any("symbolic link" in item for item in result["blockers"])


def test_runner_handoff_blocks_optional_checksum_mismatch(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)

    result = _build(
        tmp_path,
        paths,
        expected_current_odds_sha256="0" * 64,
    )

    assert result["current_odds_checksum_status"] == "Mismatch"
    assert result["card_generation_allowed"] is False
    assert any("checksum does not match" in item for item in result["blockers"])


def test_runner_handoff_verifies_matching_optional_checksums(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    odds_checksum = hashlib.sha256(paths["current_odds_path"].read_bytes()).hexdigest()
    fixtures_checksum = hashlib.sha256(paths["fixtures_path"].read_bytes()).hexdigest()

    result = _build(
        tmp_path,
        paths,
        expected_current_odds_sha256=odds_checksum,
        expected_fixtures_sha256=fixtures_checksum,
    )

    assert result["current_odds_checksum_status"] == "Verified"
    assert result["fixtures_checksum_status"] == "Verified"
    assert result["card_generation_allowed"] is True


def test_runner_handoff_binds_exact_ready_staging_receipt(tmp_path: Path) -> None:
    paths, receipt_path = _write_ready_staging_receipt(tmp_path)

    result = _build(
        tmp_path,
        paths,
        staging_receipt_path=receipt_path,
        require_staging_receipt=True,
    )

    assert result["status"] == "Warnings only"
    assert result["staging_receipt_required"] is True
    assert result["staging_receipt_verdict"] == "Ready for handoff"
    assert result["staging_receipt_binding_status"] == "Verified"
    assert result["staging_receipt_path_match_status"] == "Verified"
    assert result["staging_receipt_input_checksum_status"] == "Verified"
    assert result["staging_receipt_row_count_status"] == "Verified"
    assert result["staging_receipt_provider_name"] == "manual_reviewed"
    assert result["staging_provider_policy_match_status"] == "Verified"
    assert result["staging_provider_policy_status"] == "Provider allowed"
    assert result["staging_receipt_age_status"] == "Within age limit"
    assert result["staging_cutoff_policy_status"] == "Before cutoff"
    assert result["card_generation_allowed"] is True


def test_runner_handoff_blocks_receipt_older_than_policy_limit(
    tmp_path: Path,
) -> None:
    paths, receipt_path = _write_ready_staging_receipt(tmp_path)

    result = _build(
        tmp_path,
        paths,
        run_at=datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc),
        staging_receipt_path=receipt_path,
        require_staging_receipt=True,
    )

    assert result["staging_receipt_age_status"] == "Receipt too old"
    assert result["card_generation_allowed"] is False
    assert any("at most 12 hours" in item for item in result["blockers"])


def test_runner_handoff_blocks_provider_not_allowed_by_current_policy(
    tmp_path: Path,
) -> None:
    paths, receipt_path = _write_ready_staging_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["provider_name"] = "unapproved_feed"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    result = _build(
        tmp_path,
        paths,
        staging_receipt_path=receipt_path,
        require_staging_receipt=True,
    )

    assert result["staging_provider_policy_status"] == "Provider not allowed"
    assert result["card_generation_allowed"] is False


def test_runner_handoff_blocks_when_provider_policy_changed_after_receipt(
    tmp_path: Path,
) -> None:
    paths, receipt_path = _write_ready_staging_receipt(tmp_path)
    policy = json.loads(
        paths["staging_provider_policy_path"].read_text(encoding="utf-8")
    )
    policy["max_receipt_age_hours"] = 6
    paths["staging_provider_policy_path"].write_text(
        json.dumps(policy),
        encoding="utf-8",
    )

    result = _build(
        tmp_path,
        paths,
        staging_receipt_path=receipt_path,
        require_staging_receipt=True,
    )

    assert result["staging_provider_policy_match_status"] == "Mismatch"
    assert result["card_generation_allowed"] is False
    assert any("Validate staging again" in item for item in result["blockers"])


def test_runner_handoff_blocks_missing_required_staging_receipt(
    tmp_path: Path,
) -> None:
    paths, _ = _write_ready_staging_receipt(tmp_path)

    result = _build(
        tmp_path,
        paths,
        staging_receipt_path=tmp_path / "data" / "outputs" / "missing.json",
        require_staging_receipt=True,
    )

    assert result["staging_receipt_binding_status"] == "Missing"
    assert result["card_generation_allowed"] is False
    assert any("receipt is missing" in item for item in result["blockers"])


def test_runner_handoff_blocks_changed_staging_file_after_receipt(
    tmp_path: Path,
) -> None:
    paths, receipt_path = _write_ready_staging_receipt(tmp_path)
    odds = pd.read_csv(paths["current_odds_path"])
    odds.loc[0, "american_odds"] = -109
    odds.to_csv(paths["current_odds_path"], index=False)

    result = _build(
        tmp_path,
        paths,
        staging_receipt_path=receipt_path,
        require_staging_receipt=True,
    )

    assert result["staging_receipt_current_odds_checksum_status"] == "Mismatch"
    assert result["staging_receipt_input_checksum_status"] == "Mismatch"
    assert result["card_generation_allowed"] is False
    assert any("changed after validation" in item for item in result["blockers"])


def test_runner_handoff_blocks_receipt_path_or_verdict_mismatch(
    tmp_path: Path,
) -> None:
    paths, receipt_path = _write_ready_staging_receipt(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["verdict"] = "Needs fixes"
    receipt["current_odds_staging"]["path"] = "data/staging/different.csv"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    result = _build(
        tmp_path,
        paths,
        staging_receipt_path=receipt_path,
        require_staging_receipt=True,
    )

    assert result["staging_receipt_verdict"] == "Needs fixes"
    assert result["staging_receipt_path_match_status"] == "Mismatch"
    assert result["staging_receipt_binding_status"] == "Blocked"
    assert result["card_generation_allowed"] is False


def test_runner_handoff_rejects_non_staging_paths_for_required_receipt(
    tmp_path: Path,
) -> None:
    staging_paths, receipt_path = _write_ready_staging_receipt(tmp_path)
    manual_paths = _write_inputs(tmp_path / "other")

    result = build_github_runner_input_handoff(
        current_odds_path=manual_paths["current_odds_path"],
        fixtures_path=manual_paths["fixtures_path"],
        matches_path=staging_paths["matches_path"],
        run_at=RUN_AT,
        repository_root=tmp_path,
        staging_receipt_path=receipt_path,
        require_staging_receipt=True,
    )

    assert result["staging_receipt_path_match_status"] == "Mismatch"
    assert result["card_generation_allowed"] is False
    assert any("inside `data/staging`" in item for item in result["blockers"])


def test_runner_handoff_writes_json_and_beginner_markdown(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)

    saved = save_github_runner_input_handoff(
        output_dir=paths["output_dir"],
        current_odds_path=paths["current_odds_path"],
        fixtures_path=paths["fixtures_path"],
        matches_path=paths["matches_path"],
        run_at=RUN_AT,
        repository_root=tmp_path,
    )

    payload = json.loads(Path(saved["json"]).read_text(encoding="utf-8"))
    markdown = Path(saved["markdown"]).read_text(encoding="utf-8")
    assert payload["current_odds_path"] == "data/manual/current_odds.csv"
    assert payload["card_generation_allowed"] is True
    assert "Input proof" in markdown
    assert "SHA-256" in markdown
    assert "Never fill missing odds with guesses" not in markdown
    assert "does not create sportsbook prices" in markdown
