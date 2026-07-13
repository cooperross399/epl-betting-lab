from __future__ import annotations

import json

import pandas as pd

from epl_betting_lab.reports.odds_export_profile_suggestion import (
    suggest_odds_export_profile,
)
from epl_betting_lab.reports.odds_export_profile_suggestion_validation import (
    VERDICT_INVALID,
    VERDICT_NEEDS_EDITS,
    VERDICT_READY,
    validate_odds_export_profile_suggestion_file,
)


def _source_rows(odds: str = "+125", market: str = "moneyline", selection: str = "home") -> list[dict[str, str]]:
    return [
        {
            "game_date": "2026-08-21",
            "home": "Arsenal",
            "away": "Coventry",
            "bet_type": market,
            "pick": selection,
            "odds": odds,
            "sportsbook": "ExampleBook",
        }
    ]


def _write_source(path, rows: list[dict[str, str]] | None = None) -> None:
    pd.DataFrame(rows or _source_rows()).to_csv(path, index=False)


def test_valid_draft_converts_in_memory_and_is_ready_for_manual_review(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    suggestion_dir = tmp_path / "suggestion_outputs"
    validation_dir = tmp_path / "validation_outputs"
    _write_source(source_path)
    suggestion_paths = suggest_odds_export_profile(
        source_path,
        "example_book",
        suggestion_dir,
    )

    paths = validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        output_dir=validation_dir,
    )

    assert paths["verdict"] == VERDICT_READY
    assert paths["status"] == "ready"
    preview = pd.read_csv(paths["csv"], dtype=str).fillna("")
    assert preview.loc[0, "validation_status"] == "valid"
    assert preview.loc[0, "market"] == "moneyline"
    assert preview.loc[0, "normalized_market"] == "1x2"
    assert preview.loc[0, "normalized_selection"] == "home"
    report = paths["markdown"].read_text(encoding="utf-8")
    assert "Ready for manual profile review" in report
    assert "does not modify `odds_import_profiles.json`" in report
    assert not (tmp_path / "current_odds_import.csv").exists()
    assert not (tmp_path / "current_odds.csv").exists()


def test_bad_values_and_duplicate_output_rows_need_edits(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    rows = _source_rows(odds="not-odds", market="point spread", selection="favorite")
    _write_source(source_path, rows + rows)
    suggestion_paths = suggest_odds_export_profile(
        source_path,
        "example_book",
        tmp_path / "suggestion_outputs",
    )

    paths = validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        output_dir=tmp_path / "validation_outputs",
    )

    assert paths["verdict"] == VERDICT_NEEDS_EDITS
    preview = pd.read_csv(paths["csv"], dtype=str).fillna("")
    assert preview["validation_status"].eq("invalid").all()
    issues = " ".join(preview["validation_issues"])
    assert "non-numeric american_odds" in issues
    assert "market `point spread` is not recognized" in issues
    assert "selection `favorite` cannot be normalized" in issues
    assert "duplicate converted output row" in issues


def test_review_needed_and_missing_source_columns_need_edits(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    partial = _source_rows()[0]
    partial.pop("sportsbook")
    _write_source(source_path, [partial])
    suggestion_paths = suggest_odds_export_profile(
        source_path,
        "partial",
        tmp_path / "suggestion_outputs",
    )

    paths = validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        output_dir=tmp_path / "validation_outputs",
    )

    assert paths["verdict"] == VERDICT_NEEDS_EDITS
    assert "REVIEW_NEEDED required mappings: book" in paths["message"] or paths["status"] == "needs_edits"
    report = paths["markdown"].read_text(encoding="utf-8")
    assert "REVIEW_NEEDED required mappings: book" in report
    assert "empty required output `book`" in report

    complete_source = tmp_path / "complete.csv"
    _write_source(complete_source)
    suggestion_paths = suggest_odds_export_profile(
        complete_source,
        "missing_column",
        tmp_path / "second_suggestion",
    )
    payload = json.loads(suggestion_paths["json"].read_text(encoding="utf-8"))
    mapping = payload["suggested_profile"]["column_map"]
    mapping["missing_price"] = mapping.pop("odds")
    suggestion_paths["json"].write_text(json.dumps(payload), encoding="utf-8")

    paths = validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        output_dir=tmp_path / "second_validation",
    )
    assert paths["verdict"] == VERDICT_NEEDS_EDITS
    assert "missing_price" in paths["markdown"].read_text(encoding="utf-8")


def test_no_confident_mappings_are_an_invalid_draft(tmp_path) -> None:
    source_path = tmp_path / "unknown.csv"
    pd.DataFrame([{"alpha": "one", "beta": "two"}]).to_csv(source_path, index=False)
    suggestion_paths = suggest_odds_export_profile(
        source_path,
        "unknown",
        tmp_path / "suggestion_outputs",
    )

    paths = validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        output_dir=tmp_path / "validation_outputs",
    )

    assert paths["verdict"] == VERDICT_INVALID
    assert paths["status"] == "no_confident_mappings"
    assert "no confident column mappings" in paths["message"]


def test_validation_has_beginner_friendly_file_fallbacks_and_source_override(tmp_path) -> None:
    output_dir = tmp_path / "validation_outputs"
    suggestion_path = tmp_path / "suggestion.json"

    missing = validate_odds_export_profile_suggestion_file(
        suggestion_path,
        output_dir=output_dir,
    )
    assert missing["status"] == "missing_suggestion"
    assert missing["verdict"] == VERDICT_INVALID

    suggestion_path.write_text("{not-json", encoding="utf-8")
    malformed = validate_odds_export_profile_suggestion_file(
        suggestion_path,
        output_dir=output_dir,
    )
    assert malformed["status"] == "malformed_suggestion"

    source_path = tmp_path / "sportsbook_export.csv"
    _write_source(source_path)
    suggestion_paths = suggest_odds_export_profile(
        source_path,
        "example_book",
        tmp_path / "suggestion_outputs",
    )
    payload = json.loads(suggestion_paths["json"].read_text(encoding="utf-8"))
    payload["source_file"] = str(tmp_path / "missing.csv")
    suggestion_paths["json"].write_text(json.dumps(payload), encoding="utf-8")

    missing_source = validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        output_dir=output_dir,
    )
    assert missing_source["status"] == "missing_source"

    override = validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        source_path,
        output_dir,
    )
    assert override["verdict"] == VERDICT_READY

    source_path.write_text("game_date,home\n", encoding="utf-8")
    empty = validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        source_path,
        output_dir,
    )
    assert empty["status"] == "empty_source"
    assert empty["csv"].exists()
    assert empty["markdown"].exists()


def test_validation_does_not_modify_protected_files(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    profiles_path = tmp_path / "odds_import_profiles.json"
    current_odds_path = tmp_path / "current_odds.csv"
    import_path = tmp_path / "current_odds_import.csv"
    _write_source(source_path)
    profiles_path.write_text('{"profiles":{"keep":{}}}\n', encoding="utf-8")
    current_odds_path.write_text("keep odds\n", encoding="utf-8")
    import_path.write_text("keep import\n", encoding="utf-8")
    originals = {
        path: path.read_text(encoding="utf-8")
        for path in [profiles_path, current_odds_path, import_path]
    }
    suggestion_paths = suggest_odds_export_profile(
        source_path,
        "example_book",
        tmp_path / "suggestion_outputs",
    )

    validate_odds_export_profile_suggestion_file(
        suggestion_paths["json"],
        output_dir=tmp_path / "validation_outputs",
    )

    for path, original in originals.items():
        assert path.read_text(encoding="utf-8") == original
