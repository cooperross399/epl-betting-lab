from __future__ import annotations

import json

import pandas as pd

from epl_betting_lab.reports.odds_export_profile_diagnostic import (
    build_odds_export_profile_diagnostic,
    diagnose_odds_export_profiles,
)


GENERIC_MAP = {
    "game_date": "date",
    "home": "home_team",
    "away": "away_team",
    "bet_type": "market",
    "pick": "selection",
    "odds": "american_odds",
    "sportsbook": "book",
}


def _profiles(path, profiles: dict[str, object] | None = None) -> None:
    payload = profiles or {
        "generic": {
            "description": "Generic export",
            "column_map": GENERIC_MAP,
        }
    }
    path.write_text(json.dumps({"profiles": payload}), encoding="utf-8")


def _source(path, market: str = "moneyline", selection: str = "home") -> None:
    pd.DataFrame(
        [
            {
                "game_date": "2026-08-21",
                "home": "Arsenal",
                "away": "Coventry",
                "bet_type": market,
                "pick": selection,
                "odds": "+125",
                "sportsbook": "ExampleBook",
                "provider_event_id": "abc-123",
            }
        ]
    ).to_csv(path, index=False)


def test_diagnostic_finds_best_profile_and_builds_normalized_sample(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    _profiles(profiles_path)
    _source(source_path)

    paths = diagnose_odds_export_profiles(source_path, profiles_path, output_dir)

    assert paths["status"] == "match_found"
    diagnostic = pd.read_csv(paths["csv"], dtype=str).fillna("")
    assert diagnostic.loc[0, "profile_name"] == "generic"
    assert diagnostic.loc[0, "match_percentage"] == "100.0"
    assert diagnostic.loc[0, "extra_unmapped_columns"] == "provider_event_id"
    assert "moneyline/home -> 1x2/home" in diagnostic.loc[0, "sample_normalized_preview"]
    report = paths["markdown"].read_text(encoding="utf-8")
    assert "Best matching profile: generic" in report
    assert "not write `current_odds_import.csv`" in report


def test_diagnostic_flags_likely_market_and_selection_normalization_issues() -> None:
    source = pd.DataFrame(
        [
            {
                "game_date": "2026-08-21",
                "home": "Arsenal",
                "away": "Coventry",
                "bet_type": "point spread",
                "pick": "favorite",
                "odds": "+125",
                "sportsbook": "ExampleBook",
            }
        ]
    )
    profiles = {"generic": {"column_map": GENERIC_MAP}}

    diagnostic, sample, summary = build_odds_export_profile_diagnostic(source, profiles)

    assert summary["status"] == "match_found"
    assert "unsupported market `point spread`" in diagnostic.loc[0, "market_normalization_issues"]
    assert "could not be checked" in diagnostic.loc[0, "selection_normalization_issues"]
    assert sample.loc[0, "normalized_market"] == "not recognized"
    assert sample.loc[0, "normalized_selection"] == "not recognized"


def test_diagnostic_reports_no_match_and_missing_columns(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    _profiles(profiles_path)
    pd.DataFrame(
        [
            {
                "date": "2026-08-21",
                "home_team": "Arsenal",
                "away_team": "Coventry",
            }
        ]
    ).to_csv(source_path, index=False)

    paths = diagnose_odds_export_profiles(source_path, profiles_path, output_dir)

    assert paths["status"] == "no_matching_profile"
    diagnostic = pd.read_csv(paths["csv"], dtype=str).fillna("")
    assert diagnostic.loc[0, "profile_status"] == "Missing columns"
    assert "game_date" in diagnostic.loc[0, "missing_required_mapped_columns"]
    assert "No profile contains every required source column" in paths["message"]


def test_diagnostic_reports_multiple_possible_profiles() -> None:
    source = pd.DataFrame(
        [
            {
                "game_date": "2026-08-21",
                "home": "Arsenal",
                "away": "Coventry",
                "bet_type": "1x2",
                "pick": "home",
                "odds": "+125",
                "sportsbook": "ExampleBook",
            }
        ]
    )
    profiles = {
        "generic": {"column_map": GENERIC_MAP},
        "generic_copy": {"column_map": GENERIC_MAP},
    }

    diagnostic, sample, summary = build_odds_export_profile_diagnostic(source, profiles)

    assert summary["status"] == "multiple_matches"
    assert summary["possible_matching_profiles"] == "generic, generic_copy"
    assert diagnostic["profile_status"].eq("Possible match").all()
    assert len(sample) == 1


def test_diagnostic_writes_beginner_friendly_reports_for_file_problems(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    _profiles(profiles_path)

    missing = diagnose_odds_export_profiles(source_path, profiles_path, output_dir)
    assert missing["status"] == "missing_source"
    assert "Missing source export" in missing["message"]

    source_path.write_text("game_date,home\n", encoding="utf-8")
    empty = diagnose_odds_export_profiles(source_path, profiles_path, output_dir)
    assert empty["status"] == "empty_source"

    source_path.write_bytes(b"\xff\xfe\x00")
    unreadable = diagnose_odds_export_profiles(source_path, profiles_path, output_dir)
    assert unreadable["status"] == "unreadable_source"

    _source(source_path)
    missing_profiles = diagnose_odds_export_profiles(
        source_path,
        tmp_path / "missing_profiles.json",
        output_dir,
    )
    assert missing_profiles["status"] == "missing_profiles"
    assert missing_profiles["csv"].exists()
    assert missing_profiles["markdown"].exists()
    assert not (tmp_path / "current_odds_import.csv").exists()
    assert not (tmp_path / "current_odds.csv").exists()
