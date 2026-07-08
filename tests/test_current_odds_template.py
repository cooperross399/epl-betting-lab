from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.reports.current_odds_template import (
    CURRENT_ODDS_COLUMNS,
    build_current_odds_template,
    create_current_odds_template,
)


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry", "matchweek": 1},
        {"date": "2026-08-22", "home_team": "Chelsea", "away_team": "Fulham", "matchweek": 2},
    ])


def test_build_current_odds_template_creates_supported_market_rows() -> None:
    template = build_current_odds_template(_fixtures(), book="ExampleBook")

    assert list(template.columns) == CURRENT_ODDS_COLUMNS
    assert len(template) == 14
    assert set(template["market"]) == {"1x2", "total_2_5", "btts"}
    assert set(template["selection"]) == {"home", "draw", "away", "over", "under", "yes", "no"}
    assert template["american_odds"].fillna("").eq("").all()
    assert template["closing_american_odds"].fillna("").eq("").all()
    assert template["book"].eq("ExampleBook").all()
    assert "High caution" in template[(template["market"] == "total_2_5") & (template["selection"] == "under")]["notes"].iloc[0]


def test_build_current_odds_template_filters_matchweek_when_available() -> None:
    template = build_current_odds_template(_fixtures(), week=2)

    assert len(template) == 7
    assert set(template["home_team"]) == {"Chelsea"}


def test_create_current_odds_template_writes_file_and_protects_existing_file(tmp_path) -> None:
    output_path = tmp_path / "current_odds.csv"

    path, template, message = create_current_odds_template(_fixtures(), output_path)

    assert path == output_path
    assert output_path.exists()
    assert len(template) == 14
    assert "validate_current_odds.py" in message
    original = output_path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        create_current_odds_template(_fixtures(), output_path)

    assert output_path.read_text(encoding="utf-8") == original


def test_create_current_odds_template_overwrite_replaces_existing_file(tmp_path) -> None:
    output_path = tmp_path / "current_odds.csv"
    output_path.write_text("old\n", encoding="utf-8")

    _, template, _ = create_current_odds_template(_fixtures(), output_path, overwrite=True, week=1)

    assert len(template) == 7
    assert "Arsenal" in output_path.read_text(encoding="utf-8")
