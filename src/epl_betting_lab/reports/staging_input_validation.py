from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, PROJECT_ROOT, STAGING_DIR
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.github_runner_inputs import build_github_runner_input_handoff
from epl_betting_lab.reports.current_odds_completeness import (
    build_current_odds_completeness,
)
from epl_betting_lab.reports.current_odds_validation import (
    build_current_odds_validation,
)


ODDS_STAGING_FILENAME = "current_odds_staging.csv"
FIXTURES_STAGING_FILENAME = "upcoming_fixtures_staging.csv"
VALIDATION_CSV_FILENAME = "staging_input_validation.csv"
VALIDATION_MARKDOWN_FILENAME = "staging_input_validation.md"
VALIDATION_JSON_FILENAME = "staging_input_validation.json"
ODDS_REQUIRED_COLUMNS = (
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "american_odds",
    "book",
)
FIXTURE_REQUIRED_COLUMNS = ("date", "home_team", "away_team")
VERDICTS = (
    "Ready for handoff",
    "Needs fixes",
    "Blocked",
    "Missing staging inputs",
)
VALIDATION_COLUMNS = [
    "severity",
    "category",
    "check",
    "source_file",
    "row_number",
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "details",
]


@dataclass(frozen=True)
class StagingFileInspection:
    label: str
    path: Path
    display_path: str
    path_safe: bool
    exists: bool
    readable: bool
    row_count: int
    checksum_sha256: str
    missing_columns: tuple[str, ...]
    fatal_codes: tuple[str, ...]
    fatal_messages: tuple[str, ...]
    frame: pd.DataFrame | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        return str(path)


def _contains_symlink(path: Path, repository_root: Path) -> bool:
    try:
        relative = path.absolute().relative_to(repository_root)
    except ValueError:
        return False
    current = repository_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _inspect_staging_file(
    requested_path: Path,
    *,
    label: str,
    required_columns: tuple[str, ...],
    repository_root: Path,
    staging_dir: Path,
) -> StagingFileInspection:
    candidate = (
        requested_path
        if requested_path.is_absolute()
        else repository_root / requested_path
    )
    path = candidate.resolve(strict=False)
    display_path = _display_path(path, repository_root)
    fatal_codes: list[str] = []
    fatal_messages: list[str] = []

    try:
        path.relative_to(staging_dir)
    except ValueError:
        fatal_codes.append("unsafe_staging_path")
        fatal_messages.append(
            f"{label} must be a CSV inside "
            f"`{_display_path(staging_dir, repository_root)}`."
        )
    if path.suffix.lower() != ".csv":
        fatal_codes.append("invalid_staging_extension")
        fatal_messages.append(f"{label} must use a `.csv` file path.")
    if _contains_symlink(candidate, repository_root):
        fatal_codes.append("staging_symlink_not_allowed")
        fatal_messages.append(f"{label} cannot use a symbolic link.")

    path_safe = not fatal_codes
    exists = path.exists() if path_safe else False
    readable = False
    frame: pd.DataFrame | None = None
    checksum = ""
    missing_columns: tuple[str, ...] = ()
    if path_safe and exists and not path.is_file():
        fatal_codes.append("staging_path_not_file")
        fatal_messages.append(f"{label} is not a regular file: `{display_path}`.")
    elif path_safe and exists:
        try:
            checksum = _sha256(path)
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as exc:
            fatal_codes.append("unreadable_staging_csv")
            fatal_messages.append(f"{label} could not be read as CSV: {exc}")
        else:
            readable = True
            missing_columns = tuple(
                column for column in required_columns if column not in frame.columns
            )
            if missing_columns:
                fatal_codes.append("missing_required_columns")
                fatal_messages.append(
                    f"{label} is missing required column(s): "
                    f"{', '.join(missing_columns)}."
                )
            if frame.empty:
                fatal_codes.append("empty_staging_csv")
                fatal_messages.append(f"{label} has headers but no data rows.")

    return StagingFileInspection(
        label=label,
        path=path,
        display_path=display_path,
        path_safe=path_safe,
        exists=exists,
        readable=readable,
        row_count=0 if frame is None else int(len(frame)),
        checksum_sha256=checksum,
        missing_columns=missing_columns,
        fatal_codes=tuple(fatal_codes),
        fatal_messages=tuple(fatal_messages),
        frame=frame,
    )


def _add_check(
    rows: list[dict[str, object]],
    severity: str,
    category: str,
    check: str,
    source_file: str,
    details: str,
    *,
    row: pd.Series | None = None,
    row_number: int | None = None,
) -> None:
    rows.append(
        {
            "severity": severity,
            "category": category,
            "check": check,
            "source_file": source_file,
            "row_number": row_number if row_number is not None else pd.NA,
            "date": row.get("date", "") if row is not None else "",
            "home_team": row.get("home_team", "") if row is not None else "",
            "away_team": row.get("away_team", "") if row is not None else "",
            "market": row.get("market", "") if row is not None else "",
            "selection": row.get("selection", "") if row is not None else "",
            "details": details,
        }
    )


def _append_file_checks(
    rows: list[dict[str, object]],
    inspection: StagingFileInspection,
) -> None:
    if not inspection.path_safe:
        for code, message in zip(
            inspection.fatal_codes,
            inspection.fatal_messages,
            strict=True,
        ):
            _add_check(
                rows,
                "error",
                "File safety",
                code,
                inspection.display_path,
                message,
            )
        return
    _add_check(
        rows,
        "info",
        "File safety",
        "safe_staging_path",
        inspection.display_path,
        "Path is a CSV inside data/staging and does not use a symbolic link.",
    )
    if not inspection.exists:
        _add_check(
            rows,
            "error",
            "File availability",
            "missing_staging_file",
            inspection.display_path,
            f"Missing {inspection.label}: `{inspection.display_path}`.",
        )
        return
    if inspection.readable:
        _add_check(
            rows,
            "info",
            "File availability",
            "readable_staging_csv",
            inspection.display_path,
            f"CSV is readable with {inspection.row_count} row(s).",
        )
    for code, message in zip(
        inspection.fatal_codes,
        inspection.fatal_messages,
        strict=True,
    ):
        _add_check(
            rows,
            "error",
            "File structure",
            code,
            inspection.display_path,
            message,
        )
    if inspection.readable and not inspection.fatal_codes:
        _add_check(
            rows,
            "info",
            "File structure",
            "required_columns_present",
            inspection.display_path,
            "Required columns are present and the file contains data rows.",
        )


def _append_date_checks(
    rows: list[dict[str, object]],
    inspection: StagingFileInspection,
    *,
    today: date,
) -> dict[str, object]:
    result: dict[str, object] = {
        "earliest_date": "",
        "latest_date": "",
        "past_rows": 0,
        "today_or_future_rows": 0,
        "invalid_date_rows": 0,
    }
    frame = inspection.frame
    if frame is None or "date" not in frame.columns:
        return result

    valid_dates: list[date] = []
    for index, row in frame.iterrows():
        value = str(row.get("date", "")).strip()
        row_number = int(index) + 2
        parsed = pd.to_datetime(value, errors="coerce") if value else pd.NaT
        if pd.isna(parsed):
            result["invalid_date_rows"] = int(result["invalid_date_rows"]) + 1
            _add_check(
                rows,
                "error",
                "Date freshness",
                "blank_date" if not value else "invalid_date",
                inspection.display_path,
                "Enter a valid match date such as 2026-08-15.",
                row=row,
                row_number=row_number,
            )
            continue
        parsed_date = parsed.date()
        valid_dates.append(parsed_date)
        if parsed_date < today:
            result["past_rows"] = int(result["past_rows"]) + 1
            _add_check(
                rows,
                "error",
                "Date freshness",
                "past_match_date",
                inspection.display_path,
                "Thursday staging inputs cannot contain past matches.",
                row=row,
                row_number=row_number,
            )
        else:
            result["today_or_future_rows"] = (
                int(result["today_or_future_rows"]) + 1
            )
    if valid_dates:
        result["earliest_date"] = min(valid_dates).isoformat()
        result["latest_date"] = max(valid_dates).isoformat()
    if not result["past_rows"] and not result["invalid_date_rows"]:
        _add_check(
            rows,
            "info",
            "Date freshness",
            "dates_today_or_future",
            inspection.display_path,
            f"All {result['today_or_future_rows']} row(s) are today or future.",
        )
    return result


def _append_fixture_checks(
    rows: list[dict[str, object]],
    inspection: StagingFileInspection,
) -> None:
    frame = inspection.frame
    if frame is None or not set(FIXTURE_REQUIRED_COLUMNS).issubset(frame.columns):
        return
    keys = frame[list(FIXTURE_REQUIRED_COLUMNS)].fillna("").astype(str)
    keys = keys.apply(lambda column: column.str.strip().str.casefold())
    duplicate_mask = keys.duplicated(keep=False)
    for index, row in frame.iterrows():
        row_number = int(index) + 2
        home = str(row.get("home_team", "")).strip()
        away = str(row.get("away_team", "")).strip()
        if not home or not away:
            _add_check(
                rows,
                "error",
                "Fixture quality",
                "missing_fixture_team",
                inspection.display_path,
                "Both home_team and away_team are required.",
                row=row,
                row_number=row_number,
            )
        elif home.casefold() == away.casefold():
            _add_check(
                rows,
                "error",
                "Fixture quality",
                "same_home_and_away_team",
                inspection.display_path,
                "A fixture cannot use the same team as home and away.",
                row=row,
                row_number=row_number,
            )
        if bool(duplicate_mask.loc[index]):
            _add_check(
                rows,
                "error",
                "Fixture quality",
                "duplicate_fixture_row",
                inspection.display_path,
                "This date/home/away fixture appears more than once.",
                row=row,
                row_number=row_number,
            )


def _append_existing_report(
    rows: list[dict[str, object]],
    report: pd.DataFrame,
    *,
    category: str,
    source_file: str,
) -> None:
    for _, report_row in report.iterrows():
        row_number = report_row.get("row_number", pd.NA)
        _add_check(
            rows,
            str(report_row.get("severity", "error")).lower(),
            category,
            str(report_row.get("issue", "validation_issue")),
            source_file,
            str(report_row.get("details", "")),
            row=report_row,
            row_number=None if pd.isna(row_number) else int(row_number),
        )


def _file_summary(inspection: StagingFileInspection) -> dict[str, object]:
    return {
        "path": inspection.display_path,
        "path_safe": inspection.path_safe,
        "exists": inspection.exists,
        "readable": inspection.readable,
        "row_count": inspection.row_count,
        "checksum_sha256": inspection.checksum_sha256,
        "missing_columns": list(inspection.missing_columns),
        "fatal_codes": list(inspection.fatal_codes),
    }


def _next_step(verdict: str) -> str:
    return {
        "Ready for handoff": (
            "Review warnings and checksums. These files are eligible for handoff, "
            "but this report did not copy or promote them."
        ),
        "Needs fixes": (
            "Fix the listed data, freshness, validation, or completeness issues, "
            "then run `python scripts/validate_staging_inputs.py` again."
        ),
        "Blocked": (
            "Fix unsafe paths, unreadable CSVs, empty files, or missing required "
            "columns before attempting a handoff."
        ),
        "Missing staging inputs": (
            "Create both staging files from the templates, add real provider odds "
            "and current fixtures, then rerun validation."
        ),
    }[verdict]


def build_staging_input_validation(
    odds_path: Path | None = None,
    fixtures_path: Path | None = None,
    *,
    matches_path: Path | None = None,
    repository_root: Path | None = None,
    staging_dir: Path | None = None,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Validate staging inputs without copying or changing any input file."""
    root = (repository_root or PROJECT_ROOT).resolve()
    staging = (staging_dir or root / "data" / "staging").resolve()
    run_at = run_at or datetime.now().astimezone()
    selected_matches = matches_path or root / "data" / "processed" / "epl_historical_matches.csv"
    odds = _inspect_staging_file(
        odds_path or staging / ODDS_STAGING_FILENAME,
        label="Current odds staging file",
        required_columns=ODDS_REQUIRED_COLUMNS,
        repository_root=root,
        staging_dir=staging,
    )
    fixtures = _inspect_staging_file(
        fixtures_path or staging / FIXTURES_STAGING_FILENAME,
        label="Upcoming fixtures staging file",
        required_columns=FIXTURE_REQUIRED_COLUMNS,
        repository_root=root,
        staging_dir=staging,
    )

    rows: list[dict[str, object]] = []
    _append_file_checks(rows, odds)
    _append_file_checks(rows, fixtures)
    odds_dates = _append_date_checks(rows, odds, today=run_at.date())
    fixture_dates = _append_date_checks(rows, fixtures, today=run_at.date())
    _append_fixture_checks(rows, fixtures)

    missing_inputs = any(
        item.path_safe and not item.exists for item in (odds, fixtures)
    )
    structural_block = any(item.fatal_codes for item in (odds, fixtures))
    processing_block = False
    handoff: dict[str, object] | None = None
    if not missing_inputs and not structural_block:
        matches = pd.DataFrame()
        try:
            matches = load_matches(Path(selected_matches))
        except (
            FileNotFoundError,
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as exc:
            _add_check(
                rows,
                "warning",
                "Reference data",
                "historical_matches_unavailable",
                _display_path(Path(selected_matches).resolve(strict=False), root),
                f"Historical matches were unavailable: {exc}",
            )
        try:
            validation = build_current_odds_validation(
                odds.path,
                matches=matches,
                fixtures=fixtures.frame,
            )
            completeness, _ = build_current_odds_completeness(
                odds.path,
                fixtures=fixtures.frame,
            )
            _append_existing_report(
                rows,
                validation,
                category="Current odds validation",
                source_file=odds.display_path,
            )
            _append_existing_report(
                rows,
                completeness,
                category="Odds completeness",
                source_file=odds.display_path,
            )
            handoff = build_github_runner_input_handoff(
                current_odds_path=odds.path,
                fixtures_path=fixtures.path,
                matches_path=Path(selected_matches),
                run_at=run_at,
                repository_root=root,
            )
        except (
            OSError,
            UnicodeError,
            ValueError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as exc:
            processing_block = True
            _add_check(
                rows,
                "error",
                "Validation engine",
                "staging_validation_failed",
                "data/staging",
                f"Existing validation gates could not run: {exc}",
            )
        else:
            allowed = bool(handoff["card_generation_allowed"])
            blockers = [str(item) for item in handoff.get("blockers", [])]
            _add_check(
                rows,
                "info" if allowed else "error",
                "GitHub handoff gate",
                "existing_handoff_gate",
                "data/staging",
                (
                    "Existing handoff validation passed."
                    if allowed
                    else "Existing handoff validation blocked these files: "
                    + " ".join(blockers)
                ),
            )
            for warning in handoff.get("warnings", []):
                _add_check(
                    rows,
                    "warning",
                    "GitHub handoff gate",
                    "handoff_warning",
                    "data/staging",
                    str(warning),
                )

    checks = pd.DataFrame(rows, columns=VALIDATION_COLUMNS)
    error_count = int((checks["severity"] == "error").sum())
    warning_count = int((checks["severity"] == "warning").sum())
    handoff_allowed = bool(handoff and handoff.get("card_generation_allowed"))
    if structural_block or processing_block:
        verdict = "Blocked"
    elif missing_inputs:
        verdict = "Missing staging inputs"
    elif error_count or not handoff_allowed:
        verdict = "Needs fixes"
    else:
        verdict = "Ready for handoff"
    if verdict not in VERDICTS:
        raise ValueError(f"Unexpected staging validation verdict: {verdict}")

    summary = {
        "validated_at": run_at.isoformat(timespec="seconds"),
        "verdict": verdict,
        "handoff_eligible": verdict == "Ready for handoff" and handoff_allowed,
        "next_step": _next_step(verdict),
        "current_odds_staging": _file_summary(odds),
        "upcoming_fixtures_staging": _file_summary(fixtures),
        "current_odds_date_freshness": odds_dates,
        "fixture_date_freshness": fixture_dates,
        "current_odds_validation": {
            "status": str(handoff.get("validation_status", "Not checked"))
            if handoff
            else "Not checked",
            "serious_issue_count": int(
                handoff.get("validation_serious_issue_count", 0)
            )
            if handoff
            else 0,
            "warning_count": int(handoff.get("validation_warning_count", 0))
            if handoff
            else 0,
        },
        "odds_completeness": {
            "status": str(handoff.get("completeness_status", "Not checked"))
            if handoff
            else "Not checked",
            "completion_percentage": float(
                handoff.get("completion_percentage", 0.0)
            )
            if handoff
            else 0.0,
            "matches_incomplete": int(handoff.get("incomplete_match_count", 0))
            if handoff
            else 0,
        },
        "handoff_gate": {
            "status": str(handoff.get("status", "Not checked"))
            if handoff
            else "Not checked",
            "card_generation_allowed": handoff_allowed,
            "blockers": [str(item) for item in handoff.get("blockers", [])]
            if handoff
            else [],
            "warnings": [str(item) for item in handoff.get("warnings", [])]
            if handoff
            else [],
        },
        "serious_issue_count": error_count,
        "warning_count": warning_count,
        "cron_enabled": False,
        "files_promoted_or_copied": False,
    }
    return checks, summary


def render_staging_input_validation(
    checks: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    serious = checks[checks["severity"] == "error"]
    warnings = checks[checks["severity"] == "warning"]
    passed = checks[checks["severity"] == "info"]
    odds = summary["current_odds_staging"]
    fixtures = summary["upcoming_fixtures_staging"]
    odds_dates = summary["current_odds_date_freshness"]
    fixture_dates = summary["fixture_date_freshness"]
    validation = summary["current_odds_validation"]
    completeness = summary["odds_completeness"]
    handoff = summary["handoff_gate"]
    lines = [
        "# Staging Odds and Fixtures Validation",
        "",
        (
            "This read-only report checks provider staging inputs before they are "
            "considered for the GitHub runner handoff. It does not copy or promote "
            "files, edit manual data, fabricate odds, enable cron, or place bets."
        ),
        "",
        "## Verdict",
        "",
        f"- **{summary['verdict']}**",
        f"- Eligible for handoff: **{'Yes' if summary['handoff_eligible'] else 'No'}**",
        f"- Serious issues: {summary['serious_issue_count']}",
        f"- Warnings: {summary['warning_count']}",
        f"- Next step: {summary['next_step']}",
        "",
        "## Staging files",
        "",
        (
            f"- Odds: `{odds['path']}` | {odds['row_count']} row(s) | "
            f"SHA-256 `{odds['checksum_sha256'] or 'not available'}`"
        ),
        (
            f"- Fixtures: `{fixtures['path']}` | {fixtures['row_count']} row(s) | "
            f"SHA-256 `{fixtures['checksum_sha256'] or 'not available'}`"
        ),
        "",
        "## Freshness and existing gates",
        "",
        (
            "- Odds dates: "
            f"{odds_dates['earliest_date'] or 'not available'} to "
            f"{odds_dates['latest_date'] or 'not available'}; "
            f"{odds_dates['past_rows']} past, "
            f"{odds_dates['today_or_future_rows']} today/future, "
            f"{odds_dates['invalid_date_rows']} invalid"
        ),
        (
            "- Fixture dates: "
            f"{fixture_dates['earliest_date'] or 'not available'} to "
            f"{fixture_dates['latest_date'] or 'not available'}; "
            f"{fixture_dates['past_rows']} past, "
            f"{fixture_dates['today_or_future_rows']} today/future, "
            f"{fixture_dates['invalid_date_rows']} invalid"
        ),
        f"- Current odds validation: **{validation['status']}**",
        (
            f"- Odds completeness: **{completeness['status']}** "
            f"({float(completeness['completion_percentage']):.1%})"
        ),
        f"- Existing GitHub handoff gate: **{handoff['status']}**",
        "",
        "## Serious issues",
        "",
        serious.to_markdown(index=False) if not serious.empty else "No serious issues found.",
        "",
        "## Warnings",
        "",
        warnings.to_markdown(index=False) if not warnings.empty else "No warnings found.",
        "",
        "## Passed checks",
        "",
        passed.to_markdown(index=False) if not passed.empty else "No checks passed yet.",
        "",
        "## Automation safety",
        "",
        (
            "Cron remains disabled. A future provider may write real odds and fixtures "
            "to these staging paths, but a separate, explicitly reviewed promotion or "
            "handoff step is still required. This validator never changes production files."
        ),
    ]
    return "\n".join(lines)


def save_staging_input_validation(
    odds_path: Path | None = None,
    fixtures_path: Path | None = None,
    *,
    matches_path: Path | None = None,
    output_dir: Path | None = None,
    repository_root: Path | None = None,
    staging_dir: Path | None = None,
    run_at: datetime | None = None,
) -> dict[str, object]:
    outputs = output_dir or OUTPUTS_DIR
    checks, summary = build_staging_input_validation(
        odds_path,
        fixtures_path,
        matches_path=matches_path or PROCESSED_DIR / "epl_historical_matches.csv",
        repository_root=repository_root,
        staging_dir=staging_dir or STAGING_DIR,
        run_at=run_at,
    )
    outputs.mkdir(parents=True, exist_ok=True)
    csv_path = outputs / VALIDATION_CSV_FILENAME
    markdown_path = outputs / VALIDATION_MARKDOWN_FILENAME
    json_path = outputs / VALIDATION_JSON_FILENAME
    checks.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_staging_input_validation(checks, summary),
        encoding="utf-8",
    )
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "json": json_path,
        "verdict": summary["verdict"],
        "handoff_eligible": summary["handoff_eligible"],
        "next_step": summary["next_step"],
    }
