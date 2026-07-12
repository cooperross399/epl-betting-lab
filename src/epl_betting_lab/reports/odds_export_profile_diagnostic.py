from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import import (
    IMPORT_REQUIRED_COLUMNS,
    _normalize_market,
    _normalize_selection,
)
from epl_betting_lab.reports.odds_export_conversion import (
    build_odds_export_conversion_preview,
    load_odds_import_profiles,
    validate_odds_import_profile,
)


DEFAULT_SOURCE_PATH = MANUAL_DIR / "sportsbook_export.csv"
DEFAULT_PROFILES_PATH = MANUAL_DIR / "odds_import_profiles.json"
DIAGNOSTIC_COLUMNS = [
    "profile_name",
    "profile_description",
    "profile_status",
    "match_percentage",
    "required_mapped_columns",
    "matched_required_mapped_columns",
    "missing_required_mapped_columns",
    "extra_unmapped_columns",
    "profile_configuration_issues",
    "market_normalization_issues",
    "selection_normalization_issues",
    "sample_normalized_preview",
    "is_best_match",
]
SAMPLE_COLUMNS = [
    "profile_name",
    "source_row_number",
    "date",
    "home_team",
    "away_team",
    "source_market",
    "normalized_market",
    "source_selection",
    "normalized_selection",
    "american_odds",
    "book",
    "diagnostic_notes",
]
FATAL_DIAGNOSTIC_STATUSES = {
    "missing_source",
    "empty_source",
    "unreadable_source",
    "missing_profiles",
    "unreadable_profiles",
}


class OddsExportProfileDiagnosticError(RuntimeError):
    """Raised by the dashboard when a diagnostic input cannot be read."""


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _joined(values: list[str] | set[str]) -> str:
    return ", ".join(sorted(value for value in values if value))


def read_odds_export_source(
    source_path: Path,
) -> tuple[pd.DataFrame | None, str, str]:
    """Read an export without changing it and return a beginner-friendly status."""
    if not source_path.exists():
        return None, "missing_source", f"Missing source export `{source_path}`. Save the CSV there and run again."
    try:
        source = pd.read_csv(source_path, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        source = pd.DataFrame()
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        return None, "unreadable_source", f"The source export could not be read as CSV: {exc}"
    if source.empty:
        return source, "empty_source", "The source export exists, but it has no odds rows to inspect."
    return source, "ready", "The source export was read successfully."


def _normalization_details(
    profile_name: str,
    preview: pd.DataFrame,
    sample_limit: int,
) -> tuple[pd.DataFrame, str, str, str]:
    sample_rows: list[dict[str, object]] = []
    market_issues: set[str] = set()
    selection_issues: set[str] = set()
    preview_labels: list[str] = []

    for _, row in preview.iterrows():
        source_market = _clean(row.get("market"))
        normalized_market = _normalize_market(source_market)
        source_selection = _clean(row.get("selection"))
        normalized_selection = _normalize_selection(source_selection, normalized_market)

        if not source_market:
            market_issues.add("blank market value")
        elif not normalized_market:
            market_issues.add(f"unsupported market `{source_market}`")
        if not source_selection:
            selection_issues.add("blank selection value")
        elif normalized_market and not normalized_selection:
            selection_issues.add(
                f"unsupported selection `{source_selection}` for `{normalized_market}`"
            )
        elif not normalized_market:
            selection_issues.add(
                f"selection `{source_selection}` could not be checked because its market is unsupported"
            )

        notes = [
            value
            for value in [
                _clean(row.get("conversion_issues")),
                _clean(row.get("conversion_warnings")),
            ]
            if value
        ]
        if len(sample_rows) < sample_limit:
            sample_rows.append(
                {
                    "profile_name": profile_name,
                    "source_row_number": row.get("source_row_number", ""),
                    "date": _clean(row.get("date")),
                    "home_team": _clean(row.get("home_team")),
                    "away_team": _clean(row.get("away_team")),
                    "source_market": source_market,
                    "normalized_market": normalized_market or "not recognized",
                    "source_selection": source_selection,
                    "normalized_selection": normalized_selection or "not recognized",
                    "american_odds": _clean(row.get("american_odds")),
                    "book": _clean(row.get("book")),
                    "diagnostic_notes": "; ".join(notes),
                }
            )
            preview_labels.append(
                f"{source_market or 'blank'}/{source_selection or 'blank'} -> "
                f"{normalized_market or 'not recognized'}/{normalized_selection or 'not recognized'}"
            )

    return (
        pd.DataFrame(sample_rows, columns=SAMPLE_COLUMNS),
        _joined(market_issues),
        _joined(selection_issues),
        " | ".join(preview_labels),
    )


def _diagnose_profile(
    source: pd.DataFrame,
    profile_name: str,
    profile: object,
    sample_limit: int,
) -> tuple[dict[str, object], pd.DataFrame]:
    if not isinstance(profile, dict):
        row = {
            "profile_name": profile_name,
            "profile_description": "",
            "profile_status": "Invalid profile",
            "match_percentage": 0.0,
            "required_mapped_columns": "",
            "matched_required_mapped_columns": "",
            "missing_required_mapped_columns": "",
            "extra_unmapped_columns": _joined(set(source.columns)),
            "profile_configuration_issues": "Profile must be a JSON object.",
            "market_normalization_issues": "not checked",
            "selection_normalization_issues": "not checked",
            "sample_normalized_preview": "",
            "is_best_match": False,
        }
        return row, pd.DataFrame(columns=SAMPLE_COLUMNS)

    column_map, profile_issues = validate_odds_import_profile(profile_name, profile)
    required_sources = [
        source_column
        for source_column, standard_column in column_map.items()
        if standard_column in IMPORT_REQUIRED_COLUMNS
    ]
    matched = [column for column in required_sources if column in source.columns]
    missing = [column for column in required_sources if column not in source.columns]
    extra = set(source.columns) - set(column_map)
    denominator = len(required_sources)
    match_percentage = 100.0 * len(matched) / denominator if denominator else 0.0

    sample = pd.DataFrame(columns=SAMPLE_COLUMNS)
    market_issues = "not checked"
    selection_issues = "not checked"
    sample_preview = ""
    if not profile_issues and not missing:
        preview, _ = build_odds_export_conversion_preview(source, column_map)
        sample, market_issues, selection_issues, sample_preview = _normalization_details(
            profile_name,
            preview,
            sample_limit,
        )

    if profile_issues:
        profile_status = "Invalid profile"
    elif missing:
        profile_status = "Missing columns"
    else:
        profile_status = "Possible match"

    return (
        {
            "profile_name": profile_name,
            "profile_description": _clean(profile.get("description")),
            "profile_status": profile_status,
            "match_percentage": round(match_percentage, 1),
            "required_mapped_columns": _joined(required_sources),
            "matched_required_mapped_columns": _joined(matched),
            "missing_required_mapped_columns": _joined(missing),
            "extra_unmapped_columns": _joined(extra),
            "profile_configuration_issues": " ".join(profile_issues),
            "market_normalization_issues": market_issues,
            "selection_normalization_issues": selection_issues,
            "sample_normalized_preview": sample_preview,
            "is_best_match": False,
        },
        sample,
    )


def build_odds_export_profile_diagnostic(
    source: pd.DataFrame,
    profiles: dict[str, object],
    *,
    sample_limit: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    rows: list[dict[str, object]] = []
    samples: dict[str, pd.DataFrame] = {}
    for profile_name in sorted(profiles):
        row, sample = _diagnose_profile(
            source,
            profile_name,
            profiles[profile_name],
            sample_limit,
        )
        rows.append(row)
        samples[profile_name] = sample

    diagnostics = pd.DataFrame(rows, columns=DIAGNOSTIC_COLUMNS)
    diagnostics = diagnostics.sort_values(
        ["match_percentage", "profile_name"],
        ascending=[False, True],
    ).reset_index(drop=True)
    eligible = diagnostics[diagnostics["profile_status"] != "Invalid profile"]
    best_profile = _clean(eligible.iloc[0]["profile_name"]) if not eligible.empty else ""
    possible = diagnostics[diagnostics["profile_status"] == "Possible match"]

    if len(possible) > 1:
        status = "multiple_matches"
        message = (
            "More than one profile contains every required source column. Review the profile comparison "
            "and normalized samples before choosing one."
        )
        best_profile = _clean(possible.iloc[0]["profile_name"])
    elif len(possible) == 1:
        status = "match_found"
        best_profile = _clean(possible.iloc[0]["profile_name"])
        message = f"Profile `{best_profile}` contains every required source column."
    elif best_profile:
        status = "no_matching_profile"
        best_score = float(eligible.iloc[0]["match_percentage"])
        message = (
            f"No profile contains every required source column. `{best_profile}` is closest at "
            f"{best_score:.1f}% coverage."
        )
    else:
        status = "no_matching_profile"
        message = "No usable mapping profile was found. Fix the profile configuration and run the diagnostic again."

    if best_profile:
        diagnostics.loc[diagnostics["profile_name"] == best_profile, "is_best_match"] = True
    sample = samples.get(best_profile, pd.DataFrame(columns=SAMPLE_COLUMNS))
    summary = {
        "status": status,
        "message": message,
        "detected_columns": _joined(set(source.columns)),
        "row_count": len(source),
        "profiles_checked": _joined(set(profiles)),
        "profile_count": len(profiles),
        "best_matching_profile": best_profile or "none",
        "possible_matching_profiles": _joined(set(possible["profile_name"].astype(str))),
    }
    return diagnostics, sample, summary


def render_odds_export_profile_diagnostic(
    diagnostics: pd.DataFrame,
    sample: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    lines = [
        "# Odds Export Profile Diagnostic",
        "",
        "This report only reads a supplied export and mapping profiles. It does not write "
        "`current_odds_import.csv`, edit `current_odds.csv`, apply imports, fabricate odds, or place bets.",
        "",
        "## Summary",
        "",
        f"- Source file: `{summary.get('source_path', '')}`",
        f"- Status: {summary.get('status', 'unknown')}",
        f"- Detected columns: {summary.get('detected_columns', 'none') or 'none'}",
        f"- Row count: {int(summary.get('row_count', 0))}",
        f"- Profiles checked: {summary.get('profiles_checked', 'none') or 'none'}",
        f"- Best matching profile: {summary.get('best_matching_profile', 'none')}",
        f"- Message: {summary.get('message', '')}",
        "",
        "## Profile comparison",
        "",
        diagnostics.to_markdown(index=False) if not diagnostics.empty else "No profiles could be compared.",
        "",
        "## Sample mapped and normalized rows",
        "",
        sample.to_markdown(index=False)
        if not sample.empty
        else "No normalized sample is available until a profile contains all required source columns.",
        "",
        "## Beginner notes",
        "",
        "- Missing required mapped columns prevent that profile from converting the export.",
        "- Extra/unmapped columns are informational; they are ignored unless you add them to a profile.",
        "- Market or selection warnings mean the safe importer may reject those values after conversion.",
    ]

    status = summary.get("status")
    best_profile = _clean(summary.get("best_matching_profile"))
    lines.extend(["", "## Next step", ""])
    if status == "match_found":
        lines.append(
            f"Preview conversion with `python scripts/convert_odds_export.py --profile {best_profile} "
            f"--source {summary.get('source_path', '')}`."
        )
    elif status == "multiple_matches":
        lines.append(
            "Review the normalized sample and profile descriptions, then explicitly choose the profile "
            "that matches the export provider."
        )
    elif status == "no_matching_profile":
        lines.append(
            "Update `data/manual/odds_import_profiles.json` with the missing source-column mappings, "
            "then run this diagnostic again. No import file was created."
        )
    else:
        lines.append("Fix the input problem shown above, then run the diagnostic again.")
    return "\n".join(lines)


def _save_diagnostic(
    diagnostics: pd.DataFrame,
    sample: pd.DataFrame,
    summary: dict[str, object],
    output_dir: Path,
) -> dict[str, Path | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "odds_export_profile_diagnostic.csv"
    markdown_path = output_dir / "odds_export_profile_diagnostic.md"
    diagnostics.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_odds_export_profile_diagnostic(diagnostics, sample, summary),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "status": str(summary.get("status", "unknown")),
        "message": str(summary.get("message", "")),
    }


def diagnose_odds_export_profiles(
    source_path: Path | None = None,
    profiles_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    source_path = source_path or DEFAULT_SOURCE_PATH
    profiles_path = profiles_path or DEFAULT_PROFILES_PATH
    output_dir = output_dir or OUTPUTS_DIR
    empty = pd.DataFrame(columns=DIAGNOSTIC_COLUMNS)
    empty_sample = pd.DataFrame(columns=SAMPLE_COLUMNS)
    summary: dict[str, object] = {
        "source_path": str(source_path),
        "detected_columns": "",
        "row_count": 0,
        "profiles_checked": "",
        "profile_count": 0,
        "best_matching_profile": "none",
        "possible_matching_profiles": "",
    }

    source, source_status, source_message = read_odds_export_source(source_path)
    if source is None or source_status != "ready":
        if source is not None:
            summary["detected_columns"] = _joined(set(source.columns))
        summary.update({"status": source_status, "message": source_message})
        return _save_diagnostic(empty, empty_sample, summary, output_dir)

    summary["detected_columns"] = _joined(set(source.columns))

    try:
        profiles = load_odds_import_profiles(profiles_path)
    except FileNotFoundError as exc:
        summary.update({"status": "missing_profiles", "message": str(exc)})
        return _save_diagnostic(empty, empty_sample, summary, output_dir)
    except ValueError as exc:
        summary.update({"status": "unreadable_profiles", "message": str(exc)})
        return _save_diagnostic(empty, empty_sample, summary, output_dir)

    diagnostics, sample, built_summary = build_odds_export_profile_diagnostic(source, profiles)
    summary.update(built_summary)
    return _save_diagnostic(diagnostics, sample, summary, output_dir)
