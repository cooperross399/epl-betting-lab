from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.providers.odds_api_staging_provider import (
    API_KEY_ENV,
    OddsApiStagingProvider,
)
from epl_betting_lab.reports.provider_shadow_verification import (
    SHADOW_VERDICTS,
    save_provider_shadow_verification,
)


RUN_AT = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
SECRET = "shadow-test-secret-never-write"


class MockResponse:
    def __init__(self, payload: object) -> None:
        self.status_code = 200
        self.content = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.headers = {
            "x-requests-remaining": "498",
            "x-requests-used": "2",
            "x-requests-last": "1",
            "authorization": SECRET,
        }

    def json(self) -> object:
        return json.loads(self.content)


def _payload(
    *,
    include_btts: bool = True,
    home_team: str = "Arsenal",
) -> list[dict[str, object]]:
    markets: list[dict[str, object]] = [
        {
            "key": "h2h",
            "outcomes": [
                {"name": home_team, "price": -120},
                {"name": "Draw", "price": 250},
                {"name": "Coventry", "price": 350},
            ],
        },
        {
            "key": "totals",
            "outcomes": [
                {"name": "Over", "price": -105, "point": 2.5},
                {"name": "Under", "price": -115, "point": 2.5},
            ],
        },
    ]
    if include_btts:
        markets.append(
            {
                "key": "btts",
                "outcomes": [
                    {"name": "Yes", "price": 110},
                    {"name": "No", "price": -130},
                ],
            }
        )
    return [
        {
            "id": "shadow-event-1",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-08T14:00:00Z",
            "home_team": home_team,
            "away_team": "Coventry",
            "bookmakers": [
                {
                    "key": "examplebook",
                    "title": "Example Book",
                    "markets": markets,
                }
            ],
        }
    ]


def _provider(payload: object, calls: list[object] | None = None):
    def requester(url: str, **kwargs: object) -> MockResponse:
        if calls is not None:
            calls.append((url, kwargs))
        return MockResponse(payload)

    return OddsApiStagingProvider(
        environment={API_KEY_ENV: SECRET},
        requester=requester,
    )


def _write_reference_data(root: Path) -> Path:
    path = root / "data" / "processed" / "epl_historical_matches.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
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
    ).to_csv(path, index=False)
    return path


def _write_policy(root: Path, *, allow_provider: bool) -> Path:
    path = root / "data" / "manual" / "staging_provider_policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "allowed_provider_names": [
                    "the_odds_api" if allow_provider else "manual_reviewed"
                ],
                "allowed_provider_types": ["manual_upload", "odds_api"],
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
    return path


def _run(
    root: Path,
    *,
    payload: object | None = None,
    dry_run: bool = False,
    allow_provider: bool = True,
    home_team: str = "Arsenal",
    include_btts: bool = True,
) -> dict[str, object]:
    matches = _write_reference_data(root)
    policy = _write_policy(root, allow_provider=allow_provider)
    selected_payload = payload or _payload(
        include_btts=include_btts,
        home_team=home_team,
    )
    return save_provider_shadow_verification(
        "odds_api",
        dry_run=dry_run,
        repository_root=root,
        matches_path=matches,
        provider_policy_path=policy,
        run_at=RUN_AT,
        provider=_provider(selected_payload),
    )


def test_shadow_verdicts_are_explicit_and_conservative() -> None:
    assert SHADOW_VERDICTS == (
        "Shadow ready for review",
        "Needs mapping fixes",
        "Needs market coverage review",
        "Needs provider policy review",
        "Blocked",
        "Failed",
    )


def test_dry_run_never_calls_network_or_writes_staging(tmp_path: Path) -> None:
    calls: list[object] = []
    matches = _write_reference_data(tmp_path)
    policy = _write_policy(tmp_path, allow_provider=False)
    provider = _provider(_payload(), calls)

    result = save_provider_shadow_verification(
        "odds_api",
        dry_run=True,
        repository_root=tmp_path,
        matches_path=matches,
        provider_policy_path=policy,
        run_at=RUN_AT,
        provider=provider,
    )

    summary = result["summary"]
    assert summary["verdict"] == "Blocked"
    assert summary["provider_run"]["status"] == "Dry run ready"
    assert summary["provider_run"]["network_request_made"] is False
    assert summary["staging_validation"]["verdict"] == "Not run"
    assert calls == []
    assert not (tmp_path / "data" / "staging").exists()
    assert Path(result["json"]).is_file()
    assert Path(result["markdown"]).is_file()
    assert Path(result["csv"]).is_file()


def test_live_shadow_blocks_without_environment_credential(tmp_path: Path) -> None:
    calls: list[object] = []
    matches = _write_reference_data(tmp_path)
    policy = _write_policy(tmp_path, allow_provider=False)
    provider = OddsApiStagingProvider(
        environment={},
        requester=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = save_provider_shadow_verification(
        "odds_api",
        dry_run=False,
        repository_root=tmp_path,
        matches_path=matches,
        provider_policy_path=policy,
        run_at=RUN_AT,
        provider=provider,
    )

    assert result["summary"]["verdict"] == "Blocked"
    assert result["summary"]["provider_run"]["status"] == "Blocked"
    assert calls == []
    assert not (tmp_path / "data" / "staging").exists()


def test_complete_live_shadow_is_ready_for_manual_review(tmp_path: Path) -> None:
    result = _run(tmp_path)
    summary = result["summary"]

    assert summary["verdict"] == "Shadow ready for review"
    assert summary["provider_run"]["status"] == "Completed"
    assert summary["raw_evidence"]["status"] == "Created"
    assert summary["raw_evidence"]["checksum_status"] == "Verified"
    assert summary["checksums"]["provenance_status"] == "Verified"
    assert all(
        summary["checksums"][field] == "Verified"
        for field in (
            "source_odds_checksum_status",
            "source_fixtures_checksum_status",
            "staging_odds_checksum_status",
            "staging_fixtures_checksum_status",
            "odds_checksum_pair_status",
            "fixtures_checksum_pair_status",
        )
    )
    assert summary["provider_age"]["status"] == "Fresh"
    assert summary["team_mapping"]["coverage_percentage"] == 1.0
    assert summary["fixture_matching"]["coverage_percentage"] == 1.0
    assert summary["market_coverage"]["market_counts"] == {
        "1x2": 3,
        "total_2_5": 2,
        "btts": 2,
    }
    assert summary["odds_completeness"]["completion_percentage"] == 1.0
    assert summary["staging_validation"]["verdict"] == "Ready for handoff"
    assert summary["provider_policy"]["provider_allowed"] is True
    assert summary["safety"]["trusted_picks_generated"] is False
    assert summary["safety"]["cron_enabled"] is False
    assert summary["safety"]["bets_placed"] is False


def test_missing_btts_is_reported_without_fabrication(tmp_path: Path) -> None:
    result = _run(tmp_path, include_btts=False)
    summary = result["summary"]

    assert summary["verdict"] == "Needs market coverage review"
    assert summary["market_coverage"]["market_counts"]["btts"] == 0
    assert summary["market_coverage"]["missing_markets"] == ["btts"]
    odds = pd.read_csv(tmp_path / "data" / "staging" / "current_odds_staging.csv")
    assert "btts" not in set(odds["market"])
    assert any("No odds were fabricated" in item for item in summary["warnings"])


def test_unknown_provider_team_name_needs_mapping_fixes(tmp_path: Path) -> None:
    result = _run(tmp_path, home_team="Provider Arsenal Alias")
    summary = result["summary"]

    assert summary["verdict"] == "Needs mapping fixes"
    assert summary["team_mapping"]["status"] == "Needs review"
    assert summary["team_mapping"]["unmapped_teams"] == [
        "Provider Arsenal Alias"
    ]


def test_complete_data_with_disallowed_provider_needs_policy_review(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, allow_provider=False)
    summary = result["summary"]

    assert summary["verdict"] == "Needs provider policy review"
    assert summary["provider_policy"]["provider_allowed"] is False
    policy = json.loads(
        (tmp_path / "data" / "manual" / "staging_provider_policy.json").read_text(
            encoding="utf-8"
        )
    )
    assert "the_odds_api" not in policy["allowed_provider_names"]


def test_shadow_reports_safe_quota_and_bookmaker_coverage_without_secret(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path)
    summary = result["summary"]

    assert summary["bookmaker_coverage"]["bookmakers"] == ["Example Book"]
    assert summary["bookmaker_coverage"]["rows_by_bookmaker"] == {
        "Example Book": 7
    }
    assert summary["api_quota"] == {
        "status": "Available",
        "requests_remaining": "498",
        "requests_used": "2",
        "requests_last": "1",
    }
    for path in (result["json"], result["markdown"], result["csv"]):
        assert SECRET not in Path(path).read_text(encoding="utf-8")
    assert "authorization" not in Path(result["json"]).read_text(encoding="utf-8")


def test_shadow_outputs_do_not_touch_protected_manual_files(tmp_path: Path) -> None:
    protected = {
        "current_odds.csv": b"keep current odds\n",
        "current_odds_import.csv": b"keep import\n",
        "bet_ledger.csv": b"keep ledger\n",
        "odds_import_profiles.json": b"{}\n",
    }
    manual = tmp_path / "data" / "manual"
    manual.mkdir(parents=True)
    for filename, content in protected.items():
        (manual / filename).write_bytes(content)

    _run(tmp_path)

    for filename, content in protected.items():
        assert (manual / filename).read_bytes() == content
