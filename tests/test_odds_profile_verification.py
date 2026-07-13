from __future__ import annotations

import json

import pandas as pd

from epl_betting_lab.reports.odds_profile_verification import (
    verify_installed_odds_profile,
)


PROFILE = {
    "description": "Installed test profile",
    "column_map": {
        "game_date": "date",
        "home": "home_team",
        "away": "away_team",
        "bet_type": "market",
        "pick": "selection",
        "odds": "american_odds",
        "sportsbook": "book",
    },
}


def _registry(path, profiles=None) -> None:
    path.write_text(json.dumps({"profiles": profiles or {"example": PROFILE}}), encoding="utf-8")


def _source(path, rows=None) -> None:
    rows = rows or [
        {
            "game_date": "2026-08-21",
            "home": "Arsenal",
            "away": "Coventry",
            "bet_type": "moneyline",
            "pick": "home",
            "odds": "+125",
            "sportsbook": "ExampleBook",
        }
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_installed_profile_verifies_in_memory_without_writing_odds_files(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    _registry(registry_path)
    _source(source_path)

    paths = verify_installed_odds_profile(
        "example",
        source_path,
        registry_path,
        output_dir,
    )

    assert paths["status"] == "verified"
    assert paths["verdict"] == "Installed profile verified"
    preview = pd.read_csv(paths["csv"], dtype=str).fillna("")
    assert preview.loc[0, "validation_status"] == "valid"
    assert preview.loc[0, "normalized_market"] == "1x2"
    assert preview.loc[0, "normalized_selection"] == "home"
    assert "Sample converted rows" in paths["markdown"].read_text(encoding="utf-8")
    assert not (tmp_path / "current_odds.csv").exists()
    assert not (tmp_path / "current_odds_import.csv").exists()


def test_installed_profile_flags_bad_odds_normalization_and_duplicates(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    _registry(registry_path)
    bad_row = {
        "game_date": "2026-08-21",
        "home": "Arsenal",
        "away": "Coventry",
        "bet_type": "point spread",
        "pick": "favorite",
        "odds": "not-odds",
        "sportsbook": "ExampleBook",
    }
    _source(source_path, [bad_row, bad_row])

    paths = verify_installed_odds_profile(
        "example",
        source_path,
        registry_path,
        output_dir,
    )

    assert paths["status"] == "needs_attention"
    preview = pd.read_csv(paths["csv"], dtype=str).fillna("")
    issues = " ".join(preview["validation_issues"])
    assert "non-numeric american_odds" in issues
    assert "market `point spread` is not recognized" in issues
    assert "selection `favorite` cannot be normalized" in issues
    assert "duplicate converted output row" in issues


def test_installed_profile_verification_has_beginner_friendly_fallbacks(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"

    missing_registry = verify_installed_odds_profile(
        "example",
        source_path,
        registry_path,
        output_dir,
    )
    assert missing_registry["status"] == "missing_registry"

    _registry(registry_path)
    missing_profile = verify_installed_odds_profile(
        "not_installed",
        source_path,
        registry_path,
        output_dir,
    )
    assert missing_profile["status"] == "missing_profile"
    assert "Available profiles: example" in missing_profile["message"]

    missing_source = verify_installed_odds_profile(
        "example",
        source_path,
        registry_path,
        output_dir,
    )
    assert missing_source["status"] == "missing_source"

    source_path.write_text("game_date,home\n", encoding="utf-8")
    empty_source = verify_installed_odds_profile(
        "example",
        source_path,
        registry_path,
        output_dir,
    )
    assert empty_source["status"] == "empty_source"

    registry_path.write_text("{bad-json", encoding="utf-8")
    malformed = verify_installed_odds_profile(
        "example",
        source_path,
        registry_path,
        output_dir,
    )
    assert malformed["status"] == "malformed_registry"
    assert malformed["csv"].exists()
    assert malformed["markdown"].exists()
