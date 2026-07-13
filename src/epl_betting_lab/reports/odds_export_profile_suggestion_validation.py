from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import import (
    IMPORT_REQUIRED_COLUMNS,
    _normalize_market,
    _normalize_selection,
)
from epl_betting_lab.reports.current_odds_template import CURRENT_ODDS_COLUMNS
from epl_betting_lab.reports.odds_export_conversion import (
    map_odds_export_columns,
    validate_odds_import_profile,
)
from epl_betting_lab.reports.odds_export_profile_diagnostic import (
    read_odds_export_source,
)


DEFAULT_SUGGESTION_PATH = OUTPUTS_DIR / "odds_export_profile_suggestion.json"
VALIDATION_COLUMNS = [
    "source_row_number",
    *CURRENT_ODDS_COLUMNS,
    "normalized_market",
    "normalized_selection",
    "validation_status",
    "validation_issues",
]
FATAL_VALIDATION_STATUSES = {
    "missing_suggestion",
    "malformed_suggestion",
    "missing_source",
    "empty_source",
    "unreadable_source",
}
VERDICT_READY = "Ready for manual profile review"
VERDICT_NEEDS_EDITS = "Needs edits before profile review"
VERDICT_INVALID = "Invalid draft suggestion"


class OddsExportProfileSuggestionValidationError(RuntimeError):
    """Raised by the dashboard when suggestion validation cannot run."""


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _required_review_fields(suggestion: dict[str, object]) -> list[str]:
    fields: set[str] = set()
    for value in suggestion.get("missing_required_fields", []):
        field = _clean(value)
        if field in IMPORT_REQUIRED_COLUMNS:
            fields.add(field)
    for key in ["field_suggestions", "review_needed"]:
        items = suggestion.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not bool(item.get("required")):
                continue
            field = _clean(item.get("standard_field"))
            source_column = _clean(item.get("suggested_source_column"))
            if bool(item.get("review_needed")) or source_column == "REVIEW_NEEDED":
                if field in IMPORT_REQUIRED_COLUMNS:
                    fields.add(field)
    return sorted(fields)


def _duplicate_mask(converted: pd.DataFrame) -> pd.Series:
    basis = converted[IMPORT_REQUIRED_COLUMNS].copy().fillna("")
    for column in basis.columns:
        basis[column] = basis[column].astype(str).str.strip().str.lower()
    return basis.duplicated(keep=False)


def build_odds_export_profile_suggestion_validation(
    suggestion: dict[str, object],
    source: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    profile_name = _clean(suggestion.get("profile_name")) or "draft_profile"
    suggested_profile = suggestion.get("suggested_profile")
    if not isinstance(suggested_profile, dict):
        return pd.DataFrame(columns=VALIDATION_COLUMNS), {
            "status": "invalid_draft",
            "verdict": VERDICT_INVALID,
            "message": "The suggestion is missing a valid `suggested_profile` object.",
            "profile_name": profile_name,
            "draft_issues": ["missing suggested_profile object"],
        }
    raw_map = suggested_profile.get("column_map")
    if not isinstance(raw_map, dict) or not raw_map:
        return pd.DataFrame(columns=VALIDATION_COLUMNS), {
            "status": "no_confident_mappings",
            "verdict": VERDICT_INVALID,
            "message": "The draft has no confident column mappings to validate.",
            "profile_name": profile_name,
            "draft_issues": ["no confident mappings"],
        }

    column_map, profile_issues = validate_odds_import_profile(profile_name, suggested_profile)
    review_fields = _required_review_fields(suggestion)
    missing_source_columns = sorted(
        source_column
        for source_column in column_map
        if source_column not in source.columns
    )
    draft_issues = list(profile_issues)
    if review_fields:
        draft_issues.append(
            f"REVIEW_NEEDED required mappings: {', '.join(review_fields)}"
        )
    if missing_source_columns:
        draft_issues.append(
            f"Mapped source columns are missing from the export: {', '.join(missing_source_columns)}"
        )

    converted = map_odds_export_columns(source, column_map)
    duplicate_mask = _duplicate_mask(converted)
    validation_rows: list[dict[str, object]] = []
    for position, ((_, row), duplicate) in enumerate(
        zip(converted.iterrows(), duplicate_mask, strict=False),
        start=2,
    ):
        issues: list[str] = []
        for column in IMPORT_REQUIRED_COLUMNS:
            if not _clean(row.get(column)):
                issues.append(f"empty required output `{column}`")

        american_odds = _clean(row.get("american_odds"))
        numeric_odds = pd.to_numeric(american_odds, errors="coerce")
        if american_odds and pd.isna(numeric_odds):
            issues.append("non-numeric american_odds")
        elif american_odds and abs(float(numeric_odds)) < 100:
            issues.append("invalid American odds; expected a price such as -110 or +125")

        market = _clean(row.get("market"))
        normalized_market = _normalize_market(market)
        if market and not normalized_market:
            issues.append(f"market `{market}` is not recognized")
        selection = _clean(row.get("selection"))
        normalized_selection = _normalize_selection(selection, normalized_market)
        if selection and normalized_market and not normalized_selection:
            issues.append(
                f"selection `{selection}` is not recognized for `{normalized_market}`"
            )
        elif selection and not normalized_market:
            issues.append(
                f"selection `{selection}` cannot be normalized until the market is fixed"
            )
        if bool(duplicate):
            issues.append("duplicate converted output row")

        validation_rows.append(
            {
                "source_row_number": position,
                **{column: _clean(row.get(column)) for column in CURRENT_ODDS_COLUMNS},
                "normalized_market": normalized_market or "not recognized",
                "normalized_selection": normalized_selection or "not recognized",
                "validation_status": "invalid" if issues else "valid",
                "validation_issues": "; ".join(issues),
            }
        )

    preview = pd.DataFrame(validation_rows, columns=VALIDATION_COLUMNS)
    invalid_rows = int(preview["validation_status"].eq("invalid").sum())
    duplicate_rows = int(preview["validation_issues"].str.contains("duplicate", na=False).sum())
    if draft_issues or invalid_rows:
        status = "needs_edits"
        verdict = VERDICT_NEEDS_EDITS
        message = (
            f"The draft needs edits: {len(draft_issues)} draft issue(s) and "
            f"{invalid_rows} invalid converted row(s) were found."
        )
    else:
        status = "ready"
        verdict = VERDICT_READY
        message = (
            "The draft produced every required standard field with no row-level validation problems. "
            "Manual profile review is still required."
        )
    return preview, {
        "status": status,
        "verdict": verdict,
        "message": message,
        "profile_name": profile_name,
        "row_count": len(preview),
        "valid_rows": len(preview) - invalid_rows,
        "invalid_rows": invalid_rows,
        "duplicate_rows": duplicate_rows,
        "review_needed_fields": review_fields,
        "missing_source_columns": missing_source_columns,
        "draft_issues": draft_issues,
    }


def render_odds_export_profile_suggestion_validation(
    preview: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    draft_issues = summary.get("draft_issues", [])
    lines = [
        "# Draft Odds Export Profile Validation",
        "",
        "This validation runs only in memory and writes report files. It does not modify "
        "`odds_import_profiles.json`, `current_odds_import.csv`, `current_odds.csv`, the ledger, or the model.",
        "",
        f"## Verdict: {summary.get('verdict', VERDICT_INVALID)}",
        "",
        f"- Status: {summary.get('status', 'unknown')}",
        f"- Profile name: {summary.get('profile_name', 'unknown')}",
        f"- Suggestion file: `{summary.get('suggestion_path', '')}`",
        f"- Source file: `{summary.get('source_path', '')}`",
        f"- Converted rows: {int(summary.get('row_count', 0))}",
        f"- Valid rows: {int(summary.get('valid_rows', 0))}",
        f"- Invalid rows: {int(summary.get('invalid_rows', 0))}",
        f"- Duplicate rows: {int(summary.get('duplicate_rows', 0))}",
        f"- Message: {summary.get('message', '')}",
        "",
        "## Draft issues",
        "",
        "\n".join(f"- {issue}" for issue in draft_issues)
        if draft_issues
        else "No draft-level issues found.",
        "",
        "## Sample converted rows",
        "",
        preview.head(10).to_markdown(index=False)
        if not preview.empty
        else "No converted preview rows are available.",
        "",
        "## Next step",
        "",
    ]
    verdict = summary.get("verdict")
    if verdict == VERDICT_READY:
        lines.append(
            "Review every mapping manually. Only then add the approved profile to "
            "`data/manual/odds_import_profiles.json` and rerun the profile diagnostic."
        )
    elif verdict == VERDICT_NEEDS_EDITS:
        lines.append(
            "Fix the draft mapping or source values shown above, then rerun this validation. "
            "Do not add the draft to the profile registry yet."
        )
    else:
        lines.append(
            "Regenerate or repair the draft suggestion, then run validation again. No profile or odds file was changed."
        )
    return "\n".join(lines)


def _save_validation(
    preview: pd.DataFrame,
    summary: dict[str, object],
    output_dir: Path,
) -> dict[str, Path | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "odds_export_profile_suggestion_validation.csv"
    markdown_path = output_dir / "odds_export_profile_suggestion_validation.md"
    preview.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_odds_export_profile_suggestion_validation(preview, summary),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "status": str(summary.get("status", "unknown")),
        "verdict": str(summary.get("verdict", VERDICT_INVALID)),
        "message": str(summary.get("message", "")),
    }


def _error_summary(
    status: str,
    message: str,
    suggestion_path: Path,
    source_path: Path | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "verdict": VERDICT_INVALID,
        "message": message,
        "profile_name": "unknown",
        "suggestion_path": str(suggestion_path),
        "source_path": str(source_path) if source_path else "not available",
        "row_count": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "duplicate_rows": 0,
        "draft_issues": [message],
    }


def validate_odds_export_profile_suggestion_file(
    suggestion_path: Path | None = None,
    source_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    suggestion_path = suggestion_path or DEFAULT_SUGGESTION_PATH
    output_dir = output_dir or OUTPUTS_DIR
    empty = pd.DataFrame(columns=VALIDATION_COLUMNS)

    if not suggestion_path.exists():
        summary = _error_summary(
            "missing_suggestion",
            f"Missing draft suggestion `{suggestion_path}`. Generate a suggestion first.",
            suggestion_path,
            source_path,
        )
        return _save_validation(empty, summary, output_dir)
    try:
        suggestion = json.loads(suggestion_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        summary = _error_summary(
            "malformed_suggestion",
            f"The draft suggestion JSON could not be read: {exc}",
            suggestion_path,
            source_path,
        )
        return _save_validation(empty, summary, output_dir)
    if not isinstance(suggestion, dict):
        summary = _error_summary(
            "malformed_suggestion",
            "The draft suggestion JSON must contain one object.",
            suggestion_path,
            source_path,
        )
        return _save_validation(empty, summary, output_dir)

    if source_path is None:
        stored_source = _clean(suggestion.get("source_file"))
        if not stored_source:
            summary = _error_summary(
                "missing_source",
                "The draft does not store a source file path. Run again with `--source SOURCE.csv`.",
                suggestion_path,
            )
            return _save_validation(empty, summary, output_dir)
        source_path = Path(stored_source)

    source, source_status, source_message = read_odds_export_source(source_path)
    if source is None or source_status != "ready":
        summary = _error_summary(
            source_status,
            source_message,
            suggestion_path,
            source_path,
        )
        return _save_validation(empty, summary, output_dir)

    preview, summary = build_odds_export_profile_suggestion_validation(suggestion, source)
    summary.update(
        {
            "suggestion_path": str(suggestion_path),
            "source_path": str(source_path),
        }
    )
    return _save_validation(preview, summary, output_dir)
