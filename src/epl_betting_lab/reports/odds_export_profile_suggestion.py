from __future__ import annotations

import json
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import import (
    IMPORT_OPTIONAL_COLUMNS,
    IMPORT_REQUIRED_COLUMNS,
)
from epl_betting_lab.reports.odds_export_profile_diagnostic import (
    read_odds_export_source,
)


DEFAULT_SOURCE_PATH = MANUAL_DIR / "sportsbook_export.csv"
STANDARD_FIELDS = [*IMPORT_REQUIRED_COLUMNS, *IMPORT_OPTIONAL_COLUMNS]
FIELD_ALIASES = {
    "date": [
        "date",
        "game_date",
        "event_date",
        "start_time",
        "start_date",
        "commence_time",
        "kickoff",
        "kickoff_time",
    ],
    "home_team": ["home", "home_team", "home_side", "home_name", "team_home"],
    "away_team": ["away", "away_team", "away_side", "away_name", "team_away"],
    "market": ["market", "bet_type", "wager_type", "market_type"],
    "selection": ["pick", "selection", "outcome", "wager", "side"],
    "american_odds": [
        "odds",
        "american_odds",
        "price",
        "american_price",
        "moneyline_odds",
    ],
    "book": ["book", "sportsbook", "provider", "bookmaker"],
    "closing_american_odds": [
        "closing_american_odds",
        "closing_odds",
        "close_odds",
        "closing_price",
    ],
    "notes": ["notes", "note", "comments", "comment"],
}
FATAL_SUGGESTION_STATUSES = {
    "missing_profile_name",
    "missing_source",
    "empty_source",
    "unreadable_source",
}


class OddsExportProfileSuggestionError(RuntimeError):
    """Raised by the dashboard when a draft suggestion cannot be created."""


def _normalized_column(value: object) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower())
    return text.strip("_")


def _compact(value: object) -> str:
    return _normalized_column(value).replace("_", "")


def _field_suggestion(
    standard_field: str,
    source_columns: list[str],
) -> dict[str, object]:
    aliases = FIELD_ALIASES[standard_field]
    normalized_aliases = set(aliases)
    exact = [
        column
        for column in source_columns
        if _normalized_column(column) in normalized_aliases
    ]
    if len(exact) == 1:
        return {
            "standard_field": standard_field,
            "required": standard_field in IMPORT_REQUIRED_COLUMNS,
            "suggested_source_column": exact[0],
            "confidence": "high",
            "confidence_note": (
                f"`{exact[0]}` exactly matches a known alias for `{standard_field}` after basic cleanup."
            ),
            "review_needed": False,
        }
    if len(exact) > 1:
        return {
            "standard_field": standard_field,
            "required": standard_field in IMPORT_REQUIRED_COLUMNS,
            "suggested_source_column": "REVIEW_NEEDED",
            "confidence": "review_needed",
            "confidence_note": (
                f"Multiple known aliases could map this field: {', '.join(exact)}. Choose one manually."
            ),
            "review_needed": True,
        }

    compact_aliases = {_compact(alias) for alias in aliases}
    compact_matches = [
        column
        for column in source_columns
        if _compact(column) in compact_aliases
    ]
    if len(compact_matches) == 1:
        return {
            "standard_field": standard_field,
            "required": standard_field in IMPORT_REQUIRED_COLUMNS,
            "suggested_source_column": compact_matches[0],
            "confidence": "medium",
            "confidence_note": (
                f"`{compact_matches[0]}` matches a known alias after removing spaces and separators. "
                "Review the provider documentation before use."
            ),
            "review_needed": False,
        }
    if len(compact_matches) > 1:
        return {
            "standard_field": standard_field,
            "required": standard_field in IMPORT_REQUIRED_COLUMNS,
            "suggested_source_column": "REVIEW_NEEDED",
            "confidence": "review_needed",
            "confidence_note": (
                f"Multiple compact-name matches were found: {', '.join(compact_matches)}. Choose one manually."
            ),
            "review_needed": True,
        }

    required = standard_field in IMPORT_REQUIRED_COLUMNS
    return {
        "standard_field": standard_field,
        "required": required,
        "suggested_source_column": "REVIEW_NEEDED" if required else "",
        "confidence": "review_needed" if required else "optional_not_found",
        "confidence_note": (
            "No known alias was found. This required field must be mapped manually."
            if required
            else "No known alias was found. This optional field may remain unmapped."
        ),
        "review_needed": required,
    }


def build_odds_export_profile_suggestion(
    source: pd.DataFrame,
    profile_name: str,
    source_path: Path,
) -> dict[str, object]:
    source_columns = [str(column) for column in source.columns]
    suggestions = [
        _field_suggestion(standard_field, source_columns)
        for standard_field in STANDARD_FIELDS
    ]
    confident = [
        item
        for item in suggestions
        if item["confidence"] in {"high", "medium"}
    ]
    column_map = {
        str(item["suggested_source_column"]): str(item["standard_field"])
        for item in confident
    }
    review_needed = [item for item in suggestions if bool(item["review_needed"])]
    mapped_sources = set(column_map)
    unmapped_source_columns = [
        column for column in source_columns if column not in mapped_sources
    ]
    mapped_required = {
        str(item["standard_field"])
        for item in confident
        if bool(item["required"])
    }
    missing_required = [
        field for field in IMPORT_REQUIRED_COLUMNS if field not in mapped_required
    ]

    if not column_map:
        status = "no_confident_mappings"
        message = (
            "No source columns matched the conservative alias list. Every required field needs manual review."
        )
    elif missing_required:
        status = "review_required"
        message = (
            "A partial draft was created. Required fields still needing review: "
            f"{', '.join(missing_required)}."
        )
    else:
        status = "draft_ready_for_review"
        message = (
            "All required fields received conservative suggestions, but the draft must still be reviewed manually."
        )

    suggested_profile = {
        "description": (
            f"DRAFT mapping for {source_path.name}. Manually review every field before use."
        ),
        "column_map": column_map,
    }
    return {
        "draft": True,
        "manual_review_required": True,
        "status": status,
        "message": message,
        "profile_name": profile_name,
        "source_file": str(source_path),
        "row_count": len(source),
        "detected_columns": source_columns,
        "suggested_profile": suggested_profile,
        "profile_registry_snippet": {profile_name: suggested_profile},
        "field_suggestions": suggestions,
        "review_needed": review_needed,
        "missing_required_fields": missing_required,
        "unmapped_source_columns": unmapped_source_columns,
        "safety_notes": [
            "This draft was not added to odds_import_profiles.json.",
            "No current odds or import file was created or edited.",
            "Run the profile diagnostic again after manual review.",
        ],
    }


def _empty_suggestion(
    source_path: Path,
    profile_name: str,
    status: str,
    message: str,
) -> dict[str, object]:
    return {
        "draft": True,
        "manual_review_required": True,
        "status": status,
        "message": message,
        "profile_name": profile_name,
        "source_file": str(source_path),
        "row_count": 0,
        "detected_columns": [],
        "suggested_profile": {"description": "DRAFT - REVIEW NEEDED", "column_map": {}},
        "profile_registry_snippet": {},
        "field_suggestions": [],
        "review_needed": [],
        "missing_required_fields": list(IMPORT_REQUIRED_COLUMNS),
        "unmapped_source_columns": [],
        "safety_notes": [
            "No profile registry or odds file was changed.",
            "Fix the input problem before reviewing a mapping draft.",
        ],
    }


def render_odds_export_profile_suggestion(suggestion: dict[str, object]) -> str:
    field_suggestions = pd.DataFrame(suggestion.get("field_suggestions", []))
    review_needed = pd.DataFrame(suggestion.get("review_needed", []))
    unmapped = suggestion.get("unmapped_source_columns", [])
    snippet = suggestion.get("profile_registry_snippet", {})
    lines = [
        "# DRAFT Odds Export Profile Suggestion",
        "",
        "**Manual review is required. Do not add this draft to "
        "`odds_import_profiles.json` until every mapping has been checked.**",
        "",
        "This workflow does not edit the profile registry, `current_odds.csv`, or "
        "`current_odds_import.csv`. It does not apply imports, fabricate odds, or place bets.",
        "",
        "## Summary",
        "",
        f"- Status: {suggestion.get('status', 'unknown')}",
        f"- Profile name: {suggestion.get('profile_name', '') or 'missing'}",
        f"- Source file: `{suggestion.get('source_file', '')}`",
        f"- Source rows: {int(suggestion.get('row_count', 0))}",
        f"- Detected columns: {', '.join(suggestion.get('detected_columns', [])) or 'none'}",
        f"- Message: {suggestion.get('message', '')}",
        "",
        "## Field suggestions",
        "",
        field_suggestions.to_markdown(index=False)
        if not field_suggestions.empty
        else "No field suggestions are available.",
        "",
        "## Required manual review",
        "",
        review_needed.to_markdown(index=False)
        if not review_needed.empty
        else "No required field is currently unresolved. Review every suggested mapping anyway.",
        "",
        "## Unmapped source columns",
        "",
        ", ".join(str(value) for value in unmapped) if unmapped else "None.",
        "",
        "## Draft registry snippet",
        "",
        "```json",
        json.dumps(snippet, indent=2),
        "```",
        "",
        "## Next steps",
        "",
        "1. Check each source column against the export provider's documentation.",
        "2. Resolve every `REVIEW_NEEDED` required field.",
        "3. Manually add only the reviewed profile object to `data/manual/odds_import_profiles.json`.",
        "4. Run `python scripts/diagnose_odds_export.py --source SOURCE.csv` again.",
        "5. Convert only after the diagnostic confirms the reviewed profile matches.",
    ]
    return "\n".join(lines)


def _save_suggestion(
    suggestion: dict[str, object],
    output_dir: Path,
) -> dict[str, Path | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "odds_export_profile_suggestion.json"
    markdown_path = output_dir / "odds_export_profile_suggestion.md"
    json_path.write_text(json.dumps(suggestion, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_odds_export_profile_suggestion(suggestion),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "markdown": markdown_path,
        "status": str(suggestion.get("status", "unknown")),
        "message": str(suggestion.get("message", "")),
    }


def suggest_odds_export_profile(
    source_path: Path | None = None,
    profile_name: str = "",
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    source_path = source_path or DEFAULT_SOURCE_PATH
    output_dir = output_dir or OUTPUTS_DIR
    profile_name = profile_name.strip()

    if not profile_name:
        suggestion = _empty_suggestion(
            source_path,
            "",
            "missing_profile_name",
            "A draft profile name is required. Use `--profile-name some_name` and run again.",
        )
        return _save_suggestion(suggestion, output_dir)

    source, source_status, source_message = read_odds_export_source(source_path)
    if source is None or source_status != "ready":
        suggestion = _empty_suggestion(
            source_path,
            profile_name,
            source_status,
            source_message,
        )
        if source is not None:
            suggestion["detected_columns"] = [str(column) for column in source.columns]
        return _save_suggestion(suggestion, output_dir)

    suggestion = build_odds_export_profile_suggestion(source, profile_name, source_path)
    return _save_suggestion(suggestion, output_dir)
