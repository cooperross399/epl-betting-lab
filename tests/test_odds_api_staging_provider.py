from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import requests

from epl_betting_lab.providers.base import ProviderRunRequest
from epl_betting_lab.providers.odds_api_staging_provider import (
    API_KEY_ENV,
    OddsApiStagingProvider,
)
from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
from epl_betting_lab.reports.staging_input_validation import (
    build_staging_input_validation,
)


RUN_AT = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)
SECRET = "test-secret-that-must-not-be-written"


def _provider_payload() -> list[dict[str, object]]:
    return [
        {
            "id": "event-123",
            "sport_key": "soccer_epl",
            "commence_time": "2026-08-08T14:00:00Z",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "bookmakers": [
                {
                    "key": "examplebook",
                    "title": "Example Book",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Arsenal", "price": -120},
                                {"name": "Draw", "price": 250},
                                {"name": "Coventry", "price": 350},
                            ],
                        },
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": -105, "point": 2.5},
                                {"name": "Under", "price": -115, "point": 2.5},
                                {"name": "Over", "price": 145, "point": 3.5},
                                {"name": "Under", "price": -175, "point": 3.5},
                            ],
                        },
                        {
                            "key": "btts",
                            "outcomes": [
                                {"name": "Yes", "price": 110},
                                {"name": "No", "price": -130},
                            ],
                        },
                    ],
                }
            ],
        }
    ]


class MockResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.content = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.headers = {
            "x-requests-remaining": "499",
            "x-requests-used": "1",
            "authorization": SECRET,
        }

    def json(self) -> object:
        return self.payload


def _request(dry_run: bool, root: Path) -> ProviderRunRequest:
    return ProviderRunRequest(
        dry_run=dry_run,
        repository_root=root,
        run_at=RUN_AT,
        generated_by="test suite",
        notes="Mocked provider response test.",
    )


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_dry_run_never_calls_provider_or_writes_staging(tmp_path: Path) -> None:
    calls = []

    def requester(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("Dry-run must not call the provider")

    provider = OddsApiStagingProvider(
        environment={API_KEY_ENV: SECRET},
        requester=requester,
    )

    result = provider.run(_request(True, tmp_path))

    assert result["summary"]["status"] == "Dry run ready"
    assert result["summary"]["network_request_made"] is False
    assert result["summary"]["files_written"] == []
    assert calls == []
    assert not (tmp_path / "data" / "staging").exists()
    report = Path(result["report_markdown"]).read_text(encoding="utf-8")
    report_json = Path(result["report_json"]).read_text(encoding="utf-8")
    assert SECRET not in report
    assert SECRET not in report_json


def test_live_mode_blocks_missing_credentials_without_network(tmp_path: Path) -> None:
    calls = []

    def requester(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("Missing credentials must block before a request")

    provider = OddsApiStagingProvider(environment={}, requester=requester)

    result = provider.run(_request(False, tmp_path))

    assert result["summary"]["status"] == "Blocked"
    assert API_KEY_ENV in result["summary"]["blockers"][0]
    assert result["summary"]["files_written"] == []
    assert calls == []
    assert not Path(result["staging_odds"]).exists()


def test_unapproved_api_host_blocks_before_secret_can_be_sent(tmp_path: Path) -> None:
    calls = []

    def requester(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("An unapproved host must never receive the API key")

    provider = OddsApiStagingProvider(
        environment={
            API_KEY_ENV: SECRET,
            "EPL_ODDS_API_BASE_URL": "https://untrusted.example",
        },
        requester=requester,
    )

    result = provider.run(_request(False, tmp_path))

    assert result["summary"]["status"] == "Blocked"
    assert "approved The Odds API HTTPS host" in result["summary"]["blockers"][0]
    assert calls == []
    assert SECRET not in Path(result["report_json"]).read_text(encoding="utf-8")


def test_secret_accidentally_placed_in_notes_is_blocked_and_not_written(
    tmp_path: Path,
) -> None:
    provider = OddsApiStagingProvider(environment={API_KEY_ENV: SECRET})
    request = ProviderRunRequest(
        dry_run=True,
        repository_root=tmp_path,
        run_at=RUN_AT,
        generated_by="test suite",
        notes=f"do not save {SECRET}",
    )

    result = provider.run(request)

    assert result["summary"]["status"] == "Blocked"
    report_json = Path(result["report_json"]).read_text(encoding="utf-8")
    assert SECRET not in report_json


def test_live_mocked_response_writes_only_staging_evidence_and_reports(
    tmp_path: Path,
) -> None:
    calls = []
    response = MockResponse(_provider_payload())

    def requester(url: str, **kwargs: object) -> object:
        calls.append((url, kwargs))
        return response

    provider = OddsApiStagingProvider(
        environment={API_KEY_ENV: SECRET},
        requester=requester,
    )

    result = provider.run(_request(False, tmp_path))
    summary = result["summary"]

    assert summary["status"] == "Completed"
    assert summary["fixture_count"] == 1
    assert summary["odds_row_count"] == 7
    # Counts for the markets this fixture prices, without pinning the full set:
    # a hardcoded dict here is what let a new market raise a KeyError in the
    # provider itself and take the whole refresh down.
    assert summary["market_counts"]["1x2"] == 3
    assert summary["market_counts"]["total_2_5"] == 2
    assert summary["market_counts"]["btts"] == 2
    assert set(summary["market_counts"]) == set(MARKET_SELECTIONS)
    assert summary["network_request_made"] is True
    assert len(calls) == 1
    assert calls[0][1]["params"]["apiKey"] == SECRET
    assert calls[0][1]["params"]["oddsFormat"] == "american"
    assert "authorization" not in summary["provider_response_headers"]

    staging_odds = Path(result["staging_odds"])
    staging_fixtures = Path(result["staging_fixtures"])
    source_odds = tmp_path / "data" / "staging" / "source_current_odds.csv"
    source_fixtures = (
        tmp_path / "data" / "staging" / "source_upcoming_fixtures.csv"
    )
    assert staging_odds.read_bytes() == source_odds.read_bytes()
    assert staging_fixtures.read_bytes() == source_fixtures.read_bytes()
    assert len(pd.read_csv(staging_odds)) == 7
    assert len(pd.read_csv(staging_fixtures)) == 1

    raw_path = tmp_path / summary["raw_source_path"]
    assert raw_path.read_bytes() == response.content
    assert summary["raw_source_checksum_sha256"] == _sha256(raw_path)
    provenance = json.loads(Path(result["provenance"]).read_text(encoding="utf-8"))
    assert provenance["provider_name"] == "the_odds_api"
    assert provenance["provider_type"] == "odds_api"
    assert provenance["generated_at"] == RUN_AT.isoformat(timespec="seconds")
    assert provenance["raw_source_files"]["odds_api_response"][
        "checksum_sha256"
    ] == _sha256(raw_path)
    assert provenance["source_files"]["current_odds"][
        "checksum_sha256"
    ] == _sha256(source_odds)
    assert provenance["staging_files"]["current_odds"][
        "checksum_sha256"
    ] == _sha256(staging_odds)
    assert SECRET not in Path(result["report_markdown"]).read_text(encoding="utf-8")
    assert SECRET not in Path(result["report_json"]).read_text(encoding="utf-8")
    assert SECRET not in Path(result["provenance"]).read_text(encoding="utf-8")
    assert not (tmp_path / "data" / "manual" / "current_odds.csv").exists()
    assert summary["staging_validation_run"] is False
    assert summary["manual_files_edited"] is False
    assert summary["staging_promoted"] is False
    assert summary["cron_enabled"] is False
    assert summary["bets_placed"] is False


def test_existing_staging_output_blocks_before_provider_request(tmp_path: Path) -> None:
    staging = tmp_path / "data" / "staging"
    staging.mkdir(parents=True)
    existing = staging / "current_odds_staging.csv"
    existing.write_text("keep this file\n", encoding="utf-8")
    calls = []

    def requester(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return MockResponse(_provider_payload())

    provider = OddsApiStagingProvider(
        environment={API_KEY_ENV: SECRET},
        requester=requester,
    )

    result = provider.run(_request(False, tmp_path))

    assert result["summary"]["status"] == "Blocked"
    assert "--overwrite-staging" in " ".join(result["summary"]["blockers"])
    assert calls == []
    assert existing.read_text(encoding="utf-8") == "keep this file\n"


def test_malformed_or_empty_provider_response_never_writes_staging(
    tmp_path: Path,
) -> None:
    for index, payload in enumerate(({"unexpected": "object"}, [])):
        root = tmp_path / f"case-{index}"
        provider = OddsApiStagingProvider(
            environment={API_KEY_ENV: SECRET},
            requester=lambda *args, payload=payload, **kwargs: MockResponse(payload),
        )

        result = provider.run(_request(False, root))

        assert result["summary"]["status"] == "Blocked"
        assert result["summary"]["files_written"] == []
        assert not Path(result["staging_odds"]).exists()
        assert not Path(result["provenance"]).exists()


def test_provider_unavailable_message_does_not_leak_secret(tmp_path: Path) -> None:
    def unavailable(*args: object, **kwargs: object) -> object:
        raise requests.ConnectionError(f"failed with key {SECRET}")

    provider = OddsApiStagingProvider(
        environment={API_KEY_ENV: SECRET},
        requester=unavailable,
    )

    result = provider.run(_request(False, tmp_path))

    blocker = result["summary"]["blockers"][0]
    assert result["summary"]["status"] == "Blocked"
    assert "ConnectionError" in blocker
    assert SECRET not in blocker
    assert SECRET not in Path(result["report_json"]).read_text(encoding="utf-8")


def test_provider_response_that_echoes_secret_is_not_archived(tmp_path: Path) -> None:
    payload = _provider_payload()
    payload[0]["home_team"] = f"Arsenal {SECRET}"
    provider = OddsApiStagingProvider(
        environment={API_KEY_ENV: SECRET},
        requester=lambda *args, **kwargs: MockResponse(payload),
    )

    result = provider.run(_request(False, tmp_path))

    assert result["summary"]["status"] == "Blocked"
    assert "echo the API credential" in result["summary"]["blockers"][0]
    assert not (tmp_path / "data" / "staging" / "raw").exists()
    assert not Path(result["staging_odds"]).exists()
    assert SECRET not in Path(result["report_json"]).read_text(encoding="utf-8")


def test_raw_evidence_and_normalized_payload_must_be_the_same_json(
    tmp_path: Path,
) -> None:
    response = MockResponse(_provider_payload())
    response.content = b'{"different": "raw evidence"}\n'
    provider = OddsApiStagingProvider(
        environment={API_KEY_ENV: SECRET},
        requester=lambda *args, **kwargs: response,
    )

    result = provider.run(_request(False, tmp_path))

    assert result["summary"]["status"] == "Blocked"
    assert "JSON root is not an event list" in result["summary"]["blockers"][0]
    assert not Path(result["staging_odds"]).exists()


def test_completed_provider_bundle_can_pass_separate_staging_validation(
    tmp_path: Path,
) -> None:
    provider = OddsApiStagingProvider(
        environment={API_KEY_ENV: SECRET},
        requester=lambda *args, **kwargs: MockResponse(_provider_payload()),
    )
    result = provider.run(_request(False, tmp_path))
    manual = tmp_path / "data" / "manual"
    processed = tmp_path / "data" / "processed"
    manual.mkdir(parents=True)
    processed.mkdir(parents=True)
    policy_path = manual / "staging_provider_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "allowed_provider_names": ["the_odds_api"],
                "allowed_provider_types": ["odds_api"],
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

    _, validation = build_staging_input_validation(
        Path(result["staging_odds"]),
        Path(result["staging_fixtures"]),
        matches_path=matches_path,
        repository_root=tmp_path,
        staging_dir=tmp_path / "data" / "staging",
        provenance_path=Path(result["provenance"]),
        provider_policy_path=policy_path,
        run_at=RUN_AT,
    )

    assert validation["verdict"] == "Ready for handoff"
    assert validation["handoff_eligible"] is True
    assert validation["provider_name"] == "the_odds_api"
    assert validation["provider_type"] == "odds_api"
    assert validation["provider_age_status"] == "Fresh"
    assert validation["provenance_status"] == "Verified"
