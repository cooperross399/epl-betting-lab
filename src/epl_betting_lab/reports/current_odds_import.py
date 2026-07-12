from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures
from epl_betting_lab.reports.current_odds_maintenance import (
    backup_current_odds,
    load_existing_current_odds,
)
from epl_betting_lab.reports.current_odds_template import CURRENT_ODDS_COLUMNS


IMPORT_REQUIRED_COLUMNS = [
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "american_odds",
    "book",
]
IMPORT_OPTIONAL_COLUMNS = ["closing_american_odds", "notes"]
IMPORT_PREVIEW_COLUMNS = [
    "source_row_number",
    *CURRENT_ODDS_COLUMNS,
    "import_status",
    "import_action",
    "issues",
    "warnings",
]
MATCH_KEY_COLUMNS = ["date", "home_team", "away_team", "market", "selection", "book"]

MARKET_ALIASES = {
    "1x2": "1x2",
    "moneyline": "1x2",
    "matchresult": "1x2",
    "threeway": "1x2",
    "threewaymoneyline": "1x2",
    "total25": "total_2_5",
    "totals25": "total_2_5",
    "overunder25": "total_2_5",
    "ou25": "total_2_5",
    "btts": "btts",
    "bothteamstoscore": "btts",
}
SELECTION_ALIASES = {
    "1x2": {
        "home": "home",
        "homewin": "home",
        "h": "home",
        "1": "home",
        "draw": "draw",
        "tie": "draw",
        "d": "draw",
        "x": "draw",
        "away": "away",
        "awaywin": "away",
        "a": "away",
        "2": "away",
    },
    "total_2_5": {
        "over": "over",
        "over25": "over",
        "o": "over",
        "under": "under",
        "under25": "under",
        "u": "under",
    },
    "btts": {
        "yes": "yes",
        "bttsyes": "yes",
        "y": "yes",
        "no": "no",
        "bttsno": "no",
        "n": "no",
    },
}
TEAM_EQUIVALENTS = (
    ("manunited", "manchesterunited"),
    ("mancity", "manchestercity"),
    ("nottmforest", "nottinghamforest"),
    ("tottenham", "tottenhamhotspur"),
    ("newcastle", "newcastleunited"),
    ("westham", "westhamunited"),
    ("wolves", "wolverhamptonwanderers"),
    ("brighton", "brightonandhovealbion"),
    ("leeds", "leedsunited"),
    ("ipswich", "ipswichtown"),
    ("hull", "hullcity"),
    ("coventry", "coventrycity"),
)


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _relaxed(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _normalize_date(value: object) -> str:
    text = _clean(value)
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.date().isoformat()


def _team_map(fixtures: pd.DataFrame, matches: pd.DataFrame) -> dict[str, str]:
    teams: dict[str, str] = {}
    for frame in [fixtures, matches]:
        for column in ["home_team", "away_team"]:
            if column not in frame.columns:
                continue
            for value in frame[column].dropna():
                team = _clean(value)
                if team:
                    teams.setdefault(_relaxed(team), team)
    for equivalents in TEAM_EQUIVALENTS:
        canonical = next((teams[key] for key in equivalents if key in teams), None)
        if canonical:
            for key in equivalents:
                teams.setdefault(key, canonical)
    return teams


def _normalize_team(value: object, teams: dict[str, str]) -> tuple[str, bool]:
    text = _clean(value)
    if not text:
        return "", False
    canonical = teams.get(_relaxed(text))
    return (canonical, True) if canonical else (text, False)


def _normalize_market(value: object) -> str:
    return MARKET_ALIASES.get(_relaxed(value), "")


def _normalize_selection(value: object, market: str) -> str:
    return SELECTION_ALIASES.get(market, {}).get(_relaxed(value), "")


def _is_numeric(value: object) -> bool:
    text = _clean(value)
    return bool(text) and not pd.isna(pd.to_numeric(text, errors="coerce"))


def _row_key(row: pd.Series | dict[str, object]) -> tuple[str, ...]:
    return tuple(_clean(row.get(column, "")).lower() for column in MATCH_KEY_COLUMNS)


def _fixture_keys(fixtures: pd.DataFrame, teams: dict[str, str]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for _, row in fixtures.iterrows():
        home, home_known = _normalize_team(row.get("home_team"), teams)
        away, away_known = _normalize_team(row.get("away_team"), teams)
        date = _normalize_date(row.get("date"))
        if date and home_known and away_known:
            keys.add((date, home.lower(), away.lower()))
    return keys


def _existing_key_index(existing: pd.DataFrame, teams: dict[str, str]) -> dict[tuple[str, ...], list[object]]:
    result: dict[tuple[str, ...], list[object]] = {}
    for index, row in existing.iterrows():
        home, _ = _normalize_team(row.get("home_team"), teams)
        away, _ = _normalize_team(row.get("away_team"), teams)
        market = _normalize_market(row.get("market")) or _clean(row.get("market")).lower()
        selection = _normalize_selection(row.get("selection"), market) or _clean(row.get("selection")).lower()
        normalized = {
            "date": _normalize_date(row.get("date")) or _clean(row.get("date")),
            "home_team": home,
            "away_team": away,
            "market": market,
            "selection": selection,
            "book": _clean(row.get("book")),
        }
        result.setdefault(_row_key(normalized), []).append(index)
    return result


def _numeric_equal(left: object, right: object) -> bool:
    if not _is_numeric(left) or not _is_numeric(right):
        return _clean(left) == _clean(right)
    return float(pd.to_numeric(_clean(left))) == float(pd.to_numeric(_clean(right)))


def _would_change(existing: pd.Series, imported: dict[str, object]) -> bool:
    for column in ["date", "home_team", "away_team", "market", "selection"]:
        if _clean(existing.get(column)) != _clean(imported.get(column)):
            return True
    if _clean(existing.get("book")).lower() != _clean(imported.get("book")).lower():
        return True
    if not _numeric_equal(existing.get("american_odds"), imported.get("american_odds")):
        return True
    for column in IMPORT_OPTIONAL_COLUMNS:
        imported_value = _clean(imported.get(column))
        if imported_value and _clean(existing.get(column)) != imported_value:
            return True
    return False


def build_current_odds_import_preview(
    imported: pd.DataFrame,
    existing: pd.DataFrame | None,
    fixtures: pd.DataFrame,
    matches: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Normalize and classify imported rows without editing any files."""
    existing = pd.DataFrame(columns=CURRENT_ODDS_COLUMNS) if existing is None else existing.fillna("")
    matches = pd.DataFrame() if matches is None else matches
    original_columns = set(imported.columns)
    missing_columns = [column for column in IMPORT_REQUIRED_COLUMNS if column not in original_columns]
    extra_columns = [
        column
        for column in imported.columns
        if column not in IMPORT_REQUIRED_COLUMNS + IMPORT_OPTIONAL_COLUMNS
    ]
    work = imported.copy().fillna("")
    for column in IMPORT_REQUIRED_COLUMNS + IMPORT_OPTIONAL_COLUMNS:
        if column not in work.columns:
            work[column] = ""

    teams = _team_map(fixtures, matches)
    fixture_keys = _fixture_keys(fixtures, teams)
    normalized_rows: list[dict[str, object]] = []
    row_issues: list[list[str]] = []
    row_warnings: list[list[str]] = []

    for index, row in work.iterrows():
        issues: list[str] = []
        warnings: list[str] = []
        if missing_columns:
            issues.append(f"missing required columns: {', '.join(missing_columns)}")

        date = _normalize_date(row.get("date"))
        if not _clean(row.get("date")):
            issues.append("missing date")
        elif not date:
            issues.append("invalid date")

        home_team, home_known = _normalize_team(row.get("home_team"), teams)
        away_team, away_known = _normalize_team(row.get("away_team"), teams)
        if not _clean(row.get("home_team")):
            issues.append("missing home_team")
        elif not home_known:
            issues.append("unknown home_team")
        if not _clean(row.get("away_team")):
            issues.append("missing away_team")
        elif not away_known:
            issues.append("unknown away_team")

        market = _normalize_market(row.get("market"))
        if not market:
            issues.append("invalid market")
        selection = _normalize_selection(row.get("selection"), market)
        if not selection:
            issues.append("invalid selection")

        american_odds = _clean(row.get("american_odds"))
        if not american_odds:
            issues.append("missing american_odds")
        elif not _is_numeric(american_odds):
            issues.append("non-numeric american_odds")
        elif float(pd.to_numeric(american_odds)) <= MAX_DEFAULT_JUICE:
            warnings.append(f"heavy juice at or worse than {MAX_DEFAULT_JUICE}")

        closing_odds = _clean(row.get("closing_american_odds"))
        if closing_odds and not _is_numeric(closing_odds):
            issues.append("non-numeric closing_american_odds")

        book = _clean(row.get("book"))
        if not book:
            issues.append("missing book")
        if market == "total_2_5" and selection == "under":
            warnings.append("totals under requires extreme caution")

        if fixture_keys and date and home_known and away_known:
            if (date, home_team.lower(), away_team.lower()) not in fixture_keys:
                issues.append("fixture not found")
        elif not fixture_keys:
            issues.append("upcoming fixture data unavailable")

        normalized_rows.append({
            "source_row_number": int(index) + 2,
            "date": date or _clean(row.get("date")),
            "home_team": home_team,
            "away_team": away_team,
            "market": market or _clean(row.get("market")).lower(),
            "selection": selection or _clean(row.get("selection")).lower(),
            "american_odds": american_odds,
            "closing_american_odds": closing_odds,
            "book": book,
            "notes": _clean(row.get("notes")),
        })
        row_issues.append(issues)
        row_warnings.append(warnings)

    import_keys = [_row_key(row) for row in normalized_rows]
    key_counts = pd.Series(import_keys, dtype=object).value_counts().to_dict() if import_keys else {}
    existing_index = _existing_key_index(existing, teams)

    preview_rows: list[dict[str, object]] = []
    for position, normalized in enumerate(normalized_rows):
        issues = list(row_issues[position])
        key = import_keys[position]
        if key_counts.get(key, 0) > 1:
            issues.append("duplicate import row")

        matches_in_existing = existing_index.get(key, [])
        if len(matches_in_existing) > 1:
            issues.append("multiple matching rows already exist in current_odds.csv")

        if issues:
            action = "skip_invalid"
            status = "invalid"
        elif not matches_in_existing:
            action = "add_new"
            status = "valid"
        else:
            current_row = existing.loc[matches_in_existing[0]]
            action = "update_existing" if _would_change(current_row, normalized) else "no_change"
            status = "valid"

        preview_rows.append({
            **normalized,
            "import_status": status,
            "import_action": action,
            "issues": "; ".join(dict.fromkeys(issues)),
            "warnings": "; ".join(dict.fromkeys(row_warnings[position])),
        })

    preview = pd.DataFrame(preview_rows, columns=IMPORT_PREVIEW_COLUMNS)
    summary = {
        "source_status": "ready",
        "message": "Import rows were normalized and checked.",
        "total_rows": len(preview),
        "valid_rows": int(preview["import_status"].eq("valid").sum()) if not preview.empty else 0,
        "invalid_rows": int(preview["import_status"].eq("invalid").sum()) if not preview.empty else 0,
        "add_rows": int(preview["import_action"].eq("add_new").sum()) if not preview.empty else 0,
        "update_rows": int(preview["import_action"].eq("update_existing").sum()) if not preview.empty else 0,
        "no_change_rows": int(preview["import_action"].eq("no_change").sum()) if not preview.empty else 0,
        "duplicate_rows": (
            int(preview["issues"].str.contains("duplicate import row", na=False).sum())
            if not preview.empty
            else 0
        ),
        "warning_rows": int(preview["warnings"].ne("").sum()) if not preview.empty else 0,
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
    }
    if missing_columns:
        summary["source_status"] = "invalid_columns"
        summary["message"] = f"The import file is missing required columns: {', '.join(missing_columns)}."
    return preview, summary


def _apply_preview(preview: pd.DataFrame, existing: pd.DataFrame, teams: dict[str, str]) -> pd.DataFrame:
    columns = list(existing.columns) if len(existing.columns) else list(CURRENT_ODDS_COLUMNS)
    for column in CURRENT_ODDS_COLUMNS:
        if column not in columns:
            columns.append(column)
    updated = existing.reindex(columns=columns, fill_value="").copy().fillna("")
    existing_index = _existing_key_index(updated, teams)

    changes = preview[preview["import_action"].isin(["add_new", "update_existing"])]
    for _, row in changes.iterrows():
        if row["import_action"] == "update_existing":
            target_index = existing_index[_row_key(row)][0]
            for column in ["date", "home_team", "away_team", "market", "selection", "american_odds", "book"]:
                updated.at[target_index, column] = _clean(row.get(column))
            for column in IMPORT_OPTIONAL_COLUMNS:
                if _clean(row.get(column)):
                    updated.at[target_index, column] = _clean(row.get(column))
            continue

        new_row = {column: "" for column in columns}
        for column in CURRENT_ODDS_COLUMNS:
            new_row[column] = _clean(row.get(column))
        updated = pd.concat([updated, pd.DataFrame([new_row], columns=columns)], ignore_index=True)
    return updated.fillna("")


def render_current_odds_import_report(preview: pd.DataFrame, summary: dict[str, object]) -> str:
    applied = bool(summary.get("applied", False))
    apply_requested = bool(summary.get("apply_requested", False))
    if applied:
        mode = "applied"
    elif apply_requested:
        mode = "apply requested; no valid changes"
    else:
        mode = "preview / dry run"
    lines = [
        "# Current Odds Import",
        "",
        "This workflow only uses odds entered in `data/manual/current_odds_import.csv`. "
        "It does not fetch or fabricate prices, and it does not place bets.",
        "",
        "## Summary",
        "",
        f"- Mode: {mode}",
        f"- Import file status: {summary.get('source_status', 'unknown')}",
        f"- Total import rows: {int(summary.get('total_rows', 0))}",
        f"- Valid rows: {int(summary.get('valid_rows', 0))}",
        f"- Invalid rows skipped: {int(summary.get('invalid_rows', 0))}",
        f"- Rows to add: {int(summary.get('add_rows', 0))}",
        f"- Rows to update: {int(summary.get('update_rows', 0))}",
        f"- Rows already unchanged: {int(summary.get('no_change_rows', 0))}",
        f"- Duplicate import rows: {int(summary.get('duplicate_rows', 0))}",
        f"- Rows with warnings: {int(summary.get('warning_rows', 0))}",
        f"- Message: {summary.get('message', '')}",
    ]
    if summary.get("extra_columns"):
        lines.append(f"- Extra columns ignored: {', '.join(summary['extra_columns'])}")
    if summary.get("backup_path"):
        lines.append(f"- Backup: `{summary['backup_path']}`")
    if applied:
        lines.append(f"- Valid changes applied: {int(summary.get('applied_rows', 0))}")
    elif not apply_requested:
        lines.append(
            "- No odds file was changed. Review this report, then use "
            "`python scripts/import_current_odds.py --apply` from Terminal."
        )
    else:
        lines.append("- No odds file was changed because there were no valid additions or updates to apply.")

    invalid = preview[preview["import_status"] == "invalid"] if not preview.empty else preview
    changes = preview[preview["import_action"].isin(["add_new", "update_existing"])] if not preview.empty else preview
    lines.extend([
        "",
        "## Rows that would change current odds",
        "",
        changes.to_markdown(index=False) if not changes.empty else "No valid additions or updates found.",
        "",
        "## Invalid rows",
        "",
        invalid.to_markdown(index=False) if not invalid.empty else "No invalid rows found.",
    ])
    return "\n".join(lines)


def _save_reports(preview: pd.DataFrame, summary: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "current_odds_import_preview.csv"
    markdown_path = output_dir / "current_odds_import_report.md"
    preview.to_csv(csv_path, index=False)
    markdown_path.write_text(render_current_odds_import_report(preview, summary), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}


def process_current_odds_import(
    import_path: Path | None = None,
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    apply: bool = False,
    fixtures: pd.DataFrame | None = None,
    matches: pd.DataFrame | None = None,
    timestamp: str | None = None,
) -> dict[str, Path]:
    import_path = import_path or MANUAL_DIR / "current_odds_import.csv"
    current_odds_path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    output_dir = output_dir or OUTPUTS_DIR

    if not import_path.exists():
        preview = pd.DataFrame(columns=IMPORT_PREVIEW_COLUMNS)
        summary = {
            "source_status": "missing",
            "message": (
                f"Missing `{import_path}`. Run `cp data/manual/current_odds_import_template.csv "
                "data/manual/current_odds_import.csv`, then enter real sportsbook odds and book names."
            ),
            "applied": False,
            "apply_requested": apply,
        }
        return _save_reports(preview, summary, output_dir)

    try:
        imported = pd.read_csv(import_path, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        imported = pd.DataFrame()
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        preview = pd.DataFrame(columns=IMPORT_PREVIEW_COLUMNS)
        summary = {
            "source_status": "unreadable",
            "message": f"The import file could not be read: {exc}. Copy the template again and check the CSV format.",
            "applied": False,
            "apply_requested": apply,
        }
        return _save_reports(preview, summary, output_dir)
    if imported.empty:
        preview = pd.DataFrame(columns=IMPORT_PREVIEW_COLUMNS)
        summary = {
            "source_status": "empty",
            "message": "The import file exists, but it has no odds rows. Add real sportsbook prices before importing.",
            "applied": False,
            "apply_requested": apply,
        }
        return _save_reports(preview, summary, output_dir)

    if fixtures is None:
        try:
            fixtures = load_upcoming_fixtures()
        except FileNotFoundError:
            fixtures = pd.DataFrame()
    if matches is None:
        try:
            matches = load_matches()
        except FileNotFoundError:
            matches = pd.DataFrame()
    try:
        existing = load_existing_current_odds(current_odds_path)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        preview = pd.DataFrame(columns=IMPORT_PREVIEW_COLUMNS)
        summary = {
            "source_status": "current_odds_unreadable",
            "message": f"The existing current odds file could not be read safely: {exc}. No import was applied.",
            "applied": False,
            "apply_requested": apply,
        }
        return _save_reports(preview, summary, output_dir)
    preview, summary = build_current_odds_import_preview(imported, existing, fixtures, matches)
    summary.update({"applied": False, "apply_requested": apply, "applied_rows": 0})

    backup_path = None
    change_count = int(preview["import_action"].isin(["add_new", "update_existing"]).sum())
    if apply and change_count:
        current_odds_path.parent.mkdir(parents=True, exist_ok=True)
        if current_odds_path.exists():
            backup_path = backup_current_odds(current_odds_path, timestamp=timestamp)
        teams = _team_map(fixtures, matches)
        updated = _apply_preview(preview, existing, teams)
        updated.to_csv(current_odds_path, index=False)
        summary.update({
            "applied": True,
            "applied_rows": change_count,
            "backup_path": str(backup_path) if backup_path else "",
            "message": f"Applied {change_count} valid addition/update row(s). Invalid rows were skipped.",
        })

    paths = _save_reports(preview, summary, output_dir)
    if backup_path is not None:
        paths["backup"] = backup_path
    if apply and change_count:
        paths["current_odds"] = current_odds_path
    return paths
