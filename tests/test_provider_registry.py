from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.providers.base import ProviderRunRequest, UnknownProviderError
from epl_betting_lab.providers.provider_registry import (
    available_provider_names,
    create_provider,
)


RUN_AT = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def test_registry_lists_manual_and_odds_api() -> None:
    assert available_provider_names() == ("manual", "odds_api")
    assert create_provider("manual").provider_type == "manual_upload"
    assert create_provider("odds-api").provider_type == "odds_api"


def test_registry_rejects_unknown_provider_with_available_names() -> None:
    with pytest.raises(UnknownProviderError) as exc:
        create_provider("made_up_book")

    message = str(exc.value)
    assert "Unknown provider" in message
    assert "manual" in message
    assert "odds_api" in message


def test_manual_registry_adapter_supports_read_only_dry_run(tmp_path: Path) -> None:
    staging = tmp_path / "data" / "staging"
    staging.mkdir(parents=True)
    odds_source = staging / "source_current_odds.csv"
    fixtures_source = staging / "source_upcoming_fixtures.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-08-08",
                "home_team": "Arsenal",
                "away_team": "Coventry",
                "market": "1x2",
                "selection": "home",
                "american_odds": -120,
                "book": "Example Book",
            }
        ]
    ).to_csv(odds_source, index=False)
    pd.DataFrame(
        [
            {
                "date": "2026-08-08",
                "home_team": "Arsenal",
                "away_team": "Coventry",
            }
        ]
    ).to_csv(fixtures_source, index=False)
    provider = create_provider(
        "manual",
        odds_source_path=odds_source,
        fixtures_source_path=fixtures_source,
    )

    result = provider.run(
        ProviderRunRequest(
            dry_run=True,
            repository_root=tmp_path,
            run_at=RUN_AT,
            generated_by="test suite",
        )
    )

    assert result["summary"]["status"] == "Dry run ready"
    assert result["summary"]["files_written"] == []
    assert not (staging / "current_odds_staging.csv").exists()
    assert not (staging / "upcoming_fixtures_staging.csv").exists()
    assert not (staging / "staging_provenance.json").exists()
    assert Path(result["report_markdown"]).exists()
