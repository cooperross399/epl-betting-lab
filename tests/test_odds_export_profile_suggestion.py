from __future__ import annotations

import json

import pandas as pd

from epl_betting_lab.reports.odds_export_profile_suggestion import (
    build_odds_export_profile_suggestion,
    suggest_odds_export_profile,
)


def _complete_source() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_date": "2026-08-21",
                "home": "Arsenal",
                "away": "Coventry",
                "bet_type": "moneyline",
                "pick": "home",
                "odds": "+125",
                "sportsbook": "ExampleBook",
                "closing_odds": "+120",
                "comments": "manual export",
                "event_id": "abc-123",
            }
        ]
    )


def test_suggestion_maps_known_aliases_with_confidence_notes(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    source = _complete_source()

    suggestion = build_odds_export_profile_suggestion(
        source,
        "example_book",
        source_path,
    )

    assert suggestion["status"] == "draft_ready_for_review"
    assert suggestion["manual_review_required"] is True
    mapping = suggestion["suggested_profile"]["column_map"]
    assert mapping["game_date"] == "date"
    assert mapping["home"] == "home_team"
    assert mapping["closing_odds"] == "closing_american_odds"
    assert mapping["comments"] == "notes"
    assert suggestion["unmapped_source_columns"] == ["event_id"]
    date_note = next(
        item for item in suggestion["field_suggestions"] if item["standard_field"] == "date"
    )
    assert date_note["confidence"] == "high"
    assert "known alias" in date_note["confidence_note"]


def test_compact_names_are_medium_confidence_and_ambiguous_fields_need_review(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    source = _complete_source().rename(columns={"game_date": "GameDate"})

    suggestion = build_odds_export_profile_suggestion(source, "compact", source_path)

    date_item = next(
        item for item in suggestion["field_suggestions"] if item["standard_field"] == "date"
    )
    assert date_item["confidence"] == "medium"
    assert suggestion["suggested_profile"]["column_map"]["GameDate"] == "date"

    ambiguous = source.rename(columns={"GameDate": "date"}).copy()
    ambiguous["game_date"] = "2026-08-21"
    suggestion = build_odds_export_profile_suggestion(ambiguous, "ambiguous", source_path)
    date_item = next(
        item for item in suggestion["field_suggestions"] if item["standard_field"] == "date"
    )
    assert suggestion["status"] == "review_required"
    assert date_item["suggested_source_column"] == "REVIEW_NEEDED"
    assert "date" not in suggestion["suggested_profile"]["column_map"].values()


def test_no_confident_mappings_are_left_for_manual_review(tmp_path) -> None:
    source = pd.DataFrame([{"alpha": "one", "beta": "two"}])

    suggestion = build_odds_export_profile_suggestion(
        source,
        "unknown_export",
        tmp_path / "unknown.csv",
    )

    assert suggestion["status"] == "no_confident_mappings"
    assert suggestion["suggested_profile"]["column_map"] == {}
    assert suggestion["missing_required_fields"] == [
        "date",
        "home_team",
        "away_team",
        "market",
        "selection",
        "american_odds",
        "book",
    ]
    assert all(item["suggested_source_column"] == "REVIEW_NEEDED" for item in suggestion["review_needed"])


def test_suggestion_outputs_are_drafts_and_protected_files_are_unchanged(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    profiles_path = tmp_path / "odds_import_profiles.json"
    current_odds_path = tmp_path / "current_odds.csv"
    import_path = tmp_path / "current_odds_import.csv"
    _complete_source().to_csv(source_path, index=False)
    profiles_path.write_text('{"profiles":{"keep":{}}}\n', encoding="utf-8")
    current_odds_path.write_text("keep current odds\n", encoding="utf-8")
    import_path.write_text("keep import\n", encoding="utf-8")
    originals = {
        path: path.read_text(encoding="utf-8")
        for path in [profiles_path, current_odds_path, import_path]
    }

    paths = suggest_odds_export_profile(source_path, "example_book", output_dir)

    assert paths["status"] == "draft_ready_for_review"
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["draft"] is True
    assert payload["profile_registry_snippet"]["example_book"]["column_map"]["odds"] == "american_odds"
    report = paths["markdown"].read_text(encoding="utf-8")
    assert "Manual review is required" in report
    assert "does not edit the profile registry" in report
    for path, original in originals.items():
        assert path.read_text(encoding="utf-8") == original


def test_suggestion_writes_beginner_friendly_fallbacks(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"

    missing_name = suggest_odds_export_profile(source_path, "", output_dir)
    assert missing_name["status"] == "missing_profile_name"
    assert "--profile-name" in missing_name["message"]

    missing_source = suggest_odds_export_profile(source_path, "draft", output_dir)
    assert missing_source["status"] == "missing_source"

    source_path.write_text("date,home\n", encoding="utf-8")
    empty = suggest_odds_export_profile(source_path, "draft", output_dir)
    assert empty["status"] == "empty_source"

    source_path.write_bytes(b"\xff\xfe\x00")
    unreadable = suggest_odds_export_profile(source_path, "draft", output_dir)
    assert unreadable["status"] == "unreadable_source"
    assert unreadable["json"].exists()
    assert unreadable["markdown"].exists()
