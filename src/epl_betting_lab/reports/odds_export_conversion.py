from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_import import IMPORT_REQUIRED_COLUMNS
from epl_betting_lab.reports.current_odds_template import CURRENT_ODDS_COLUMNS


DEFAULT_PROFILES_PATH = MANUAL_DIR / "odds_import_profiles.json"
DEFAULT_SOURCE_PATH = MANUAL_DIR / "sportsbook_export.csv"
DEFAULT_IMPORT_PATH = MANUAL_DIR / "current_odds_import.csv"
CONVERSION_PREVIEW_COLUMNS = [
    "source_row_number",
    *CURRENT_ODDS_COLUMNS,
    "conversion_status",
    "conversion_issues",
    "conversion_warnings",
]


class OddsExportConversionError(RuntimeError):
    """Raised by UI helpers when an export cannot be previewed safely."""


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _valid_american_odds(value: object) -> bool:
    text = _clean(value)
    if not text:
        return False
    numeric = pd.to_numeric(text, errors="coerce")
    return not pd.isna(numeric) and abs(float(numeric)) >= 100


def load_odds_import_profiles(path: Path | None = None) -> dict[str, dict[str, object]]:
    path = path or DEFAULT_PROFILES_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Missing mapping profile file `{path}`. Restore `data/manual/odds_import_profiles.json`."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Mapping profile file `{path}` could not be read: {exc}") from exc
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError(f"Mapping profile file `{path}` must contain a non-empty `profiles` object.")
    return profiles


def validate_odds_import_profile(
    profile_name: str,
    profile: dict[str, object],
) -> tuple[dict[str, str], list[str]]:
    column_map = profile.get("column_map")
    if not isinstance(column_map, dict) or not column_map:
        return {}, [f"Profile `{profile_name}` must define a non-empty `column_map` object."]
    mapping = {
        str(source).strip(): str(target).strip()
        for source, target in column_map.items()
        if str(source).strip() and str(target).strip()
    }
    issues: list[str] = []
    unsupported_targets = sorted(set(mapping.values()) - set(CURRENT_ODDS_COLUMNS))
    if unsupported_targets:
        issues.append(f"Profile maps unsupported target columns: {', '.join(unsupported_targets)}.")
    duplicate_targets = sorted({
        target
        for target in mapping.values()
        if list(mapping.values()).count(target) > 1
    })
    if duplicate_targets:
        issues.append(f"Profile maps more than one source column to: {', '.join(duplicate_targets)}.")
    missing_targets = [column for column in IMPORT_REQUIRED_COLUMNS if column not in mapping.values()]
    if missing_targets:
        issues.append(f"Profile does not map required standard columns: {', '.join(missing_targets)}.")
    return mapping, issues


def map_odds_export_columns(
    source: pd.DataFrame,
    column_map: dict[str, str],
) -> pd.DataFrame:
    """Map source columns in memory without writing or applying an import."""
    converted = pd.DataFrame("", index=source.index, columns=CURRENT_ODDS_COLUMNS)
    for source_column, target_column in column_map.items():
        if source_column in source.columns and target_column in CURRENT_ODDS_COLUMNS:
            converted[target_column] = source[source_column].fillna("").astype(str).str.strip()
    return converted


def build_odds_export_conversion_preview(
    source: pd.DataFrame,
    column_map: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, object]]:
    missing_source_columns = [
        source_column
        for source_column, target_column in column_map.items()
        if target_column in IMPORT_REQUIRED_COLUMNS and source_column not in source.columns
    ]
    if missing_source_columns:
        return pd.DataFrame(columns=CONVERSION_PREVIEW_COLUMNS), {
            "source_status": "missing_mapped_columns",
            "message": f"Source export is missing mapped columns: {', '.join(missing_source_columns)}.",
            "total_rows": len(source),
            "valid_rows": 0,
            "invalid_rows": len(source),
            "missing_source_columns": missing_source_columns,
        }

    converted = map_odds_export_columns(source, column_map)

    preview_rows: list[dict[str, object]] = []
    for position, (_, row) in enumerate(converted.iterrows(), start=2):
        issues: list[str] = []
        warnings: list[str] = []
        for column in IMPORT_REQUIRED_COLUMNS:
            if not _clean(row.get(column)):
                issues.append(f"missing {column}")

        american_odds = _clean(row.get("american_odds"))
        if american_odds and not _valid_american_odds(american_odds):
            issues.append("unsupported/invalid american_odds; use American prices like -110 or +125")
        elif american_odds and float(pd.to_numeric(american_odds)) <= MAX_DEFAULT_JUICE:
            warnings.append(f"heavy juice at or worse than {MAX_DEFAULT_JUICE}")

        closing_odds = _clean(row.get("closing_american_odds"))
        if closing_odds and not _valid_american_odds(closing_odds):
            issues.append("unsupported/invalid closing_american_odds")

        preview_rows.append(
            {
                "source_row_number": position,
                **{column: _clean(row.get(column)) for column in CURRENT_ODDS_COLUMNS},
                "conversion_status": "invalid" if issues else "valid",
                "conversion_issues": "; ".join(issues),
                "conversion_warnings": "; ".join(warnings),
            }
        )

    preview = pd.DataFrame(preview_rows, columns=CONVERSION_PREVIEW_COLUMNS)
    valid_rows = int(preview["conversion_status"].eq("valid").sum()) if not preview.empty else 0
    return preview, {
        "source_status": "ready",
        "message": "Source columns were mapped to the standard current-odds import format.",
        "total_rows": len(preview),
        "valid_rows": valid_rows,
        "invalid_rows": len(preview) - valid_rows,
        "warning_rows": int(preview["conversion_warnings"].ne("").sum()) if not preview.empty else 0,
        "missing_source_columns": [],
    }


def render_odds_export_conversion_report(
    preview: pd.DataFrame,
    summary: dict[str, object],
    column_map: dict[str, str] | None = None,
) -> str:
    lines = [
        "# Odds Export Conversion",
        "",
        "This converter only rearranges values from a supplied CSV export. It does not fetch or fabricate odds, "
        "edit `current_odds.csv`, apply imports, or place bets.",
        "",
        "## Summary",
        "",
        f"- Profile: {summary.get('profile_name', 'not available')}",
        f"- Source: `{summary.get('source_path', '')}`",
        f"- Status: {summary.get('source_status', 'unknown')}",
        f"- Total source rows: {int(summary.get('total_rows', 0))}",
        f"- Conversion-valid rows: {int(summary.get('valid_rows', 0))}",
        f"- Invalid rows excluded from the import file: {int(summary.get('invalid_rows', 0))}",
        f"- Warning rows: {int(summary.get('warning_rows', 0))}",
        f"- Message: {summary.get('message', '')}",
    ]
    if summary.get("import_written"):
        lines.append(f"- Standard import file written to: `{summary.get('import_path', '')}`")
    elif summary.get("source_status") == "blocked_existing_import":
        lines.append("- Existing current_odds_import.csv was preserved. Use `--overwrite-import` only intentionally.")
    else:
        lines.append("- No current_odds_import.csv file was written.")

    if column_map:
        mapping = pd.DataFrame([
            {"source_column": source, "standard_column": target}
            for source, target in column_map.items()
        ])
        lines.extend(["", "## Column mapping", "", mapping.to_markdown(index=False)])

    invalid = preview[preview["conversion_status"] == "invalid"] if not preview.empty else preview
    lines.extend([
        "",
        "## Conversion preview",
        "",
        preview.to_markdown(index=False) if not preview.empty else "No source rows were available to preview.",
        "",
        "## Invalid rows",
        "",
        invalid.to_markdown(index=False) if not invalid.empty else "No conversion-invalid rows found.",
        "",
        "## Next step",
        "",
        "After a successful conversion, run `python scripts/import_current_odds.py` to use the existing safe "
        "preview, validation, duplicate, backup, apply, and audit gates.",
    ])
    return "\n".join(lines)


def _save_conversion_reports(
    preview: pd.DataFrame,
    summary: dict[str, object],
    column_map: dict[str, str] | None,
    output_dir: Path,
) -> dict[str, Path | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "odds_export_conversion_preview.csv"
    markdown_path = output_dir / "odds_export_conversion_report.md"
    preview.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_odds_export_conversion_report(preview, summary, column_map),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "status": str(summary.get("source_status", "unknown")),
        "message": str(summary.get("message", "")),
    }


def convert_odds_export(
    profile_name: str,
    source_path: Path | None = None,
    profiles_path: Path | None = None,
    import_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    overwrite_import: bool = False,
    write_import: bool = True,
) -> dict[str, Path | str]:
    source_path = source_path or DEFAULT_SOURCE_PATH
    profiles_path = profiles_path or DEFAULT_PROFILES_PATH
    import_path = import_path or DEFAULT_IMPORT_PATH
    output_dir = output_dir or OUTPUTS_DIR
    empty_preview = pd.DataFrame(columns=CONVERSION_PREVIEW_COLUMNS)
    base_summary: dict[str, object] = {
        "profile_name": profile_name or "not provided",
        "source_path": str(source_path),
        "total_rows": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "warning_rows": 0,
        "import_written": False,
        "import_path": str(import_path),
    }

    if not profile_name.strip():
        summary = {**base_summary, "source_status": "missing_profile", "message": "A profile name is required."}
        return _save_conversion_reports(empty_preview, summary, None, output_dir)
    try:
        profiles = load_odds_import_profiles(profiles_path)
    except (FileNotFoundError, ValueError) as exc:
        summary = {**base_summary, "source_status": "profile_error", "message": str(exc)}
        return _save_conversion_reports(empty_preview, summary, None, output_dir)
    if profile_name not in profiles:
        available = ", ".join(sorted(profiles))
        summary = {
            **base_summary,
            "source_status": "unknown_profile",
            "message": f"Unknown profile `{profile_name}`. Available profiles: {available}.",
        }
        return _save_conversion_reports(empty_preview, summary, None, output_dir)

    profile = profiles[profile_name]
    if not isinstance(profile, dict):
        summary = {
            **base_summary,
            "source_status": "profile_error",
            "message": f"Profile `{profile_name}` must be a JSON object.",
        }
        return _save_conversion_reports(empty_preview, summary, None, output_dir)
    column_map, profile_issues = validate_odds_import_profile(profile_name, profile)
    if profile_issues:
        summary = {**base_summary, "source_status": "profile_error", "message": " ".join(profile_issues)}
        return _save_conversion_reports(empty_preview, summary, column_map, output_dir)

    if not source_path.exists():
        summary = {
            **base_summary,
            "source_status": "missing_source",
            "message": f"Missing source export `{source_path}`. Save the sportsbook/odds-site CSV there first.",
        }
        return _save_conversion_reports(empty_preview, summary, column_map, output_dir)
    try:
        source = pd.read_csv(source_path, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        source = pd.DataFrame()
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        summary = {
            **base_summary,
            "source_status": "unreadable_source",
            "message": f"Source export could not be read: {exc}",
        }
        return _save_conversion_reports(empty_preview, summary, column_map, output_dir)
    if source.empty:
        summary = {
            **base_summary,
            "source_status": "empty_source",
            "message": "The source export exists, but it has no odds rows.",
        }
        return _save_conversion_reports(empty_preview, summary, column_map, output_dir)

    preview, summary = build_odds_export_conversion_preview(source, column_map)
    summary.update(base_summary)
    summary.update(
        {
            "profile_name": profile_name,
            "source_path": str(source_path),
            "total_rows": len(preview) if not preview.empty else len(source),
            "valid_rows": (
                int(preview["conversion_status"].eq("valid").sum())
                if not preview.empty
                else 0
            ),
            "invalid_rows": (
                int(preview["conversion_status"].eq("invalid").sum())
                if not preview.empty
                else len(source)
            ),
            "warning_rows": (
                int(preview["conversion_warnings"].ne("").sum())
                if not preview.empty
                else 0
            ),
            "import_written": False,
            "import_path": str(import_path),
        }
    )
    if summary.get("source_status") != "ready":
        return _save_conversion_reports(preview, summary, column_map, output_dir)
    valid_import = preview[preview["conversion_status"] == "valid"][CURRENT_ODDS_COLUMNS]

    if write_import and import_path.exists() and not overwrite_import:
        summary.update({
            "source_status": "blocked_existing_import",
            "message": f"`{import_path}` already exists and was not overwritten.",
        })
    elif write_import and valid_import.empty:
        summary.update({
            "source_status": "no_valid_rows",
            "message": "No conversion-valid rows were available, so no import file was written.",
        })
    elif write_import:
        import_path.parent.mkdir(parents=True, exist_ok=True)
        valid_import.to_csv(import_path, index=False)
        summary.update({
            "source_status": "converted",
            "message": "Conversion completed. Run the safe current odds importer next.",
            "import_written": True,
        })
    else:
        summary.update({
            "source_status": "preview_only",
            "message": "Dashboard preview completed. No current_odds_import.csv file was written.",
        })

    paths = _save_conversion_reports(preview, summary, column_map, output_dir)
    if summary["import_written"]:
        paths["import"] = import_path
    return paths
