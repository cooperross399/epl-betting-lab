from __future__ import annotations

import json

import pandas as pd

from epl_betting_lab.reports.current_odds_import import process_current_odds_import
from epl_betting_lab.reports.current_odds_template import CURRENT_ODDS_COLUMNS
from epl_betting_lab.reports.odds_export_conversion import (
    convert_odds_export,
    load_odds_import_profiles,
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


def _profiles(path) -> None:
    path.write_text(
        json.dumps({"profiles": {"generic": {"column_map": GENERIC_MAP}}}),
        encoding="utf-8",
    )


def _source(path, odds: str = "+125") -> None:
    pd.DataFrame(
        [
            {
                "game_date": "2026-08-21",
                "home": "Arsenal",
                "away": "Coventry",
                "bet_type": "moneyline",
                "pick": "home",
                "odds": odds,
                "sportsbook": "ExampleBook",
            }
        ]
    ).to_csv(path, index=False)


def test_repository_generic_profile_maps_example_export_columns() -> None:
    profile = load_odds_import_profiles()["generic"]

    assert profile["column_map"] == GENERIC_MAP


def test_generic_profile_converts_to_standard_import_and_safe_importer_can_read_it(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    import_path = tmp_path / "current_odds_import.csv"
    output_dir = tmp_path / "outputs"
    _profiles(profiles_path)
    _source(source_path)

    paths = convert_odds_export(
        "generic",
        source_path,
        profiles_path,
        import_path,
        output_dir,
    )

    assert paths["status"] == "converted"
    converted = pd.read_csv(import_path, dtype=str).fillna("")
    assert list(converted.columns) == CURRENT_ODDS_COLUMNS
    assert converted.loc[0, "market"] == "moneyline"
    assert converted.loc[0, "american_odds"] == "+125"

    fixtures = pd.DataFrame(
        [{"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"}]
    )
    import_paths = process_current_odds_import(
        import_path,
        tmp_path / "current_odds.csv",
        tmp_path / "import_outputs",
        fixtures=fixtures,
        matches=pd.DataFrame(),
    )
    import_preview = pd.read_csv(import_paths["csv"], dtype=str).fillna("")
    assert import_preview.loc[0, "import_status"] == "valid"
    assert import_preview.loc[0, "market"] == "1x2"


def test_invalid_odds_are_reported_and_not_written_to_import(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    import_path = tmp_path / "current_odds_import.csv"
    output_dir = tmp_path / "outputs"
    _profiles(profiles_path)
    _source(source_path, odds="2.10")

    paths = convert_odds_export(
        "generic",
        source_path,
        profiles_path,
        import_path,
        output_dir,
    )

    assert paths["status"] == "no_valid_rows"
    assert not import_path.exists()
    preview = pd.read_csv(paths["csv"], dtype=str).fillna("")
    assert preview.loc[0, "conversion_status"] == "invalid"
    assert "use American prices" in preview.loc[0, "conversion_issues"]


def test_existing_import_is_preserved_without_explicit_overwrite(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    import_path = tmp_path / "current_odds_import.csv"
    output_dir = tmp_path / "outputs"
    _profiles(profiles_path)
    _source(source_path)
    import_path.write_text("original\nkeep\n", encoding="utf-8")
    original = import_path.read_text(encoding="utf-8")

    paths = convert_odds_export(
        "generic",
        source_path,
        profiles_path,
        import_path,
        output_dir,
    )

    assert paths["status"] == "blocked_existing_import"
    assert import_path.read_text(encoding="utf-8") == original
    assert "--overwrite-import" in paths["markdown"].read_text(encoding="utf-8")


def test_explicit_overwrite_replaces_only_the_intermediate_import_file(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    import_path = tmp_path / "current_odds_import.csv"
    output_dir = tmp_path / "outputs"
    _profiles(profiles_path)
    _source(source_path)
    import_path.write_text("original\nkeep\n", encoding="utf-8")

    paths = convert_odds_export(
        "generic",
        source_path,
        profiles_path,
        import_path,
        output_dir,
        overwrite_import=True,
    )

    assert paths["status"] == "converted"
    converted = pd.read_csv(import_path, dtype=str).fillna("")
    assert converted.loc[0, "book"] == "ExampleBook"


def test_preview_only_writes_reports_but_not_import_file(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    import_path = tmp_path / "current_odds_import.csv"
    output_dir = tmp_path / "outputs"
    _profiles(profiles_path)
    _source(source_path)

    paths = convert_odds_export(
        "generic",
        source_path,
        profiles_path,
        import_path,
        output_dir,
        write_import=False,
    )

    assert paths["status"] == "preview_only"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert not import_path.exists()


def test_friendly_errors_are_written_for_profile_source_and_column_problems(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    output_dir = tmp_path / "outputs"
    import_path = tmp_path / "current_odds_import.csv"
    _profiles(profiles_path)

    missing_profile = convert_odds_export(
        "",
        tmp_path / "sportsbook_export.csv",
        profiles_path,
        import_path,
        output_dir,
    )
    assert missing_profile["status"] == "missing_profile"

    unknown = convert_odds_export(
        "missing",
        tmp_path / "sportsbook_export.csv",
        profiles_path,
        import_path,
        output_dir,
    )
    assert unknown["status"] == "unknown_profile"

    missing_source = convert_odds_export(
        "generic",
        tmp_path / "sportsbook_export.csv",
        profiles_path,
        import_path,
        output_dir,
    )
    assert missing_source["status"] == "missing_source"

    source_path = tmp_path / "sportsbook_export.csv"
    pd.DataFrame([{"game_date": "2026-08-21"}]).to_csv(source_path, index=False)
    missing_columns = convert_odds_export(
        "generic",
        source_path,
        profiles_path,
        import_path,
        output_dir,
    )
    assert missing_columns["status"] == "missing_mapped_columns"
    report = missing_columns["markdown"].read_text(encoding="utf-8")
    assert "missing mapped columns" in report.lower()

    source_path.write_text("", encoding="utf-8")
    empty_source = convert_odds_export(
        "generic",
        source_path,
        profiles_path,
        import_path,
        output_dir,
    )
    assert empty_source["status"] == "empty_source"


def test_heavy_juice_is_warned_but_not_fabricated_or_rejected(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    import_path = tmp_path / "current_odds_import.csv"
    output_dir = tmp_path / "outputs"
    _profiles(profiles_path)
    _source(source_path, odds="-170")

    paths = convert_odds_export(
        "generic",
        source_path,
        profiles_path,
        import_path,
        output_dir,
    )

    preview = pd.read_csv(paths["csv"], dtype=str).fillna("")
    assert paths["status"] == "converted"
    assert "heavy juice" in preview.loc[0, "conversion_warnings"]
    assert pd.read_csv(import_path, dtype=str).loc[0, "american_odds"] == "-170"
