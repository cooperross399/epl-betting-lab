from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.current_odds_completeness import (
    build_current_odds_completeness,
)
from epl_betting_lab.reports.current_odds_validation import (
    build_current_odds_validation,
)
from epl_betting_lab.workflow_status import (
    inspect_current_odds_date_freshness,
    inspect_fixture_date_freshness,
)


HANDOFF_JSON_FILENAME = "github_runner_input_handoff.json"
HANDOFF_MARKDOWN_FILENAME = "github_runner_input_handoff.md"
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class _PathInspection:
    path: Path
    display_path: str
    path_policy_valid: bool
    available: bool
    checksum_sha256: str
    checksum_status: str
    blockers: tuple[str, ...]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        value = path.relative_to(repository_root).as_posix()
    except ValueError:
        value = str(path)
    return "".join(
        character if character.isprintable() and character != "`" else "_"
        for character in value
    )


def _contains_symlink(path: Path, repository_root: Path) -> bool:
    try:
        relative = path.relative_to(repository_root)
    except ValueError:
        return False
    current = repository_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _inspect_repository_csv(
    path: Path,
    *,
    label: str,
    repository_root: Path,
    expected_checksum_sha256: str,
) -> _PathInspection:
    raw_text = str(path).strip()
    candidate = path if path.is_absolute() else repository_root / path
    lexical_path = candidate.absolute()
    resolved = candidate.resolve(strict=False)
    display_path = _display_path(resolved, repository_root)
    blockers: list[str] = []
    path_policy_valid = True

    if not raw_text or raw_text == ".":
        blockers.append(f"{label} path is blank.")
        path_policy_valid = False
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        blockers.append(
            f"{label} must be a repository-relative CSV path inside "
            f"`{repository_root}`."
        )
        path_policy_valid = False
    if resolved.suffix.lower() != ".csv":
        blockers.append(f"{label} must point to a `.csv` file.")
        path_policy_valid = False
    if path_policy_valid and _contains_symlink(lexical_path, repository_root):
        blockers.append(
            f"{label} uses a symbolic link. GitHub runner handoff files must be "
            "regular repository files."
        )
        path_policy_valid = False

    available = False
    checksum = ""
    if path_policy_valid:
        if not resolved.exists():
            blockers.append(f"{label} is missing: `{display_path}`.")
        elif not resolved.is_file():
            blockers.append(f"{label} is not a regular file: `{display_path}`.")
        else:
            try:
                checksum = _sha256(resolved)
            except OSError as exc:
                blockers.append(f"{label} could not be read: {exc}")
            else:
                available = True

    expected = expected_checksum_sha256.strip().lower()
    if expected:
        if not SHA256_PATTERN.fullmatch(expected):
            checksum_status = "Invalid expected checksum"
            blockers.append(
                f"The expected SHA-256 value for {label.lower()} must contain "
                "exactly 64 hexadecimal characters."
            )
        elif not checksum:
            checksum_status = "Not available"
        elif checksum == expected:
            checksum_status = "Verified"
        else:
            checksum_status = "Mismatch"
            blockers.append(
                f"{label} checksum does not match the optional checksum entered "
                "when the workflow was started."
            )
    else:
        checksum_status = "Recorded" if checksum else "Not available"

    return _PathInspection(
        path=resolved,
        display_path=display_path,
        path_policy_valid=path_policy_valid,
        available=available,
        checksum_sha256=checksum,
        checksum_status=checksum_status,
        blockers=tuple(blockers),
    )


def _issue_codes(issues: pd.DataFrame, severity: str) -> list[str]:
    if issues.empty or not {"severity", "issue"}.issubset(issues.columns):
        return []
    selected = issues[
        issues["severity"].fillna("").astype(str).str.lower() == severity
    ]
    return list(dict.fromkeys(selected["issue"].dropna().astype(str).tolist()))


def build_github_runner_input_handoff(
    *,
    current_odds_path: Path,
    fixtures_path: Path,
    matches_path: Path,
    run_at: datetime,
    repository_root: Path | None = None,
    expected_current_odds_sha256: str = "",
    expected_fixtures_sha256: str = "",
    github_repository: str | None = None,
    github_ref: str | None = None,
    github_sha: str | None = None,
    github_run_id: str | None = None,
) -> dict[str, object]:
    """Inspect committed runner inputs without changing either input file."""
    root = (repository_root or PROJECT_ROOT).resolve()
    odds = _inspect_repository_csv(
        current_odds_path,
        label="Current odds input",
        repository_root=root,
        expected_checksum_sha256=expected_current_odds_sha256,
    )
    fixtures = _inspect_repository_csv(
        fixtures_path,
        label="Upcoming fixtures input",
        repository_root=root,
        expected_checksum_sha256=expected_fixtures_sha256,
    )
    blockers = list(odds.blockers) + list(fixtures.blockers)
    warnings: list[str] = []

    odds_freshness = None
    if odds.available:
        odds_freshness = inspect_current_odds_date_freshness(
            odds.path,
            today=run_at.date(),
        )
        if odds_freshness.status != "Fresh":
            blockers.append(f"Current odds freshness: {odds_freshness.note}")
        if (odds_freshness.past_rows or 0) > 0:
            blockers.append(
                f"Current odds contain {odds_freshness.past_rows} row(s) tied "
                "to past matches. Remove or archive them before the GitHub run."
            )
        if (odds_freshness.today_or_future_rows or 0) == 0:
            blockers.append(
                "Current odds do not contain any rows for today or a future match."
            )
        if (odds_freshness.invalid_date_rows or 0) > 0:
            blockers.append(
                f"Current odds contain {odds_freshness.invalid_date_rows} blank "
                "or malformed date row(s)."
            )

    fixture_freshness = None
    if fixtures.available:
        fixture_freshness = inspect_fixture_date_freshness(
            fixtures.path,
            today=run_at.date(),
        )
        if fixture_freshness.status != "Fresh":
            blockers.append(f"Fixture freshness: {fixture_freshness.note}")
        if (fixture_freshness.past_fixtures or 0) > 0:
            blockers.append(
                f"Upcoming fixtures contain {fixture_freshness.past_fixtures} "
                "past match row(s). Use a clean upcoming slate for the GitHub run."
            )
        if (fixture_freshness.today_or_future_fixtures or 0) == 0:
            blockers.append(
                "Upcoming fixtures do not contain any match today or in the future."
            )
        if (fixture_freshness.invalid_fixture_dates or 0) > 0:
            blockers.append(
                f"Upcoming fixtures contain "
                f"{fixture_freshness.invalid_fixture_dates} blank or malformed "
                "date row(s)."
            )

    fixture_rows = pd.DataFrame()
    fixture_read_error = ""
    if fixtures.available:
        try:
            fixture_rows = pd.read_csv(fixtures.path, dtype=str)
        except (
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as exc:
            fixture_read_error = str(exc)
            blockers.append(f"Upcoming fixtures CSV could not be read: {exc}")

    matches = pd.DataFrame()
    try:
        matches = load_matches(matches_path)
    except (FileNotFoundError, OSError, UnicodeError, pd.errors.ParserError) as exc:
        warnings.append(
            f"Historical results were unavailable during input handoff validation: {exc}"
        )

    validation_status = "Not checked"
    validation_serious_count = 0
    validation_warning_count = 0
    validation_issue_codes: list[str] = []
    if odds.available and fixtures.available and not fixture_read_error:
        try:
            validation_issues = build_current_odds_validation(
                odds.path,
                matches=matches,
                fixtures=fixture_rows,
            )
        except (
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
            ValueError,
        ) as exc:
            validation_status = "Blocked"
            blockers.append(f"Current odds validation could not run: {exc}")
        else:
            validation_warning_count = int(
                (
                    validation_issues["severity"]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                    == "warning"
                ).sum()
            ) if not validation_issues.empty else 0
            serious_rows = int(
                (
                    validation_issues["severity"]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                    == "error"
                ).sum()
            ) if not validation_issues.empty else 0
            validation_serious_count = serious_rows
            validation_issue_codes = _issue_codes(validation_issues, "error")
            validation_status = "Blocked" if serious_rows else "Ready"
            if serious_rows:
                blockers.append(
                    f"Current odds validation found {serious_rows} serious "
                    f"issue(s): {', '.join(validation_issue_codes)}."
                )
            if validation_warning_count:
                warnings.append(
                    f"Current odds validation found {validation_warning_count} "
                    "warning(s). Review them before trusting the card."
                )

    completeness_status = "Not checked"
    completion_percentage = 0.0
    incomplete_matches = 0
    completeness_error_count = 0
    completeness_warning_count = 0
    completeness_issue_codes: list[str] = []
    if odds.available and fixtures.available and not fixture_read_error:
        try:
            completeness_issues, completeness_summary = (
                build_current_odds_completeness(
                    odds.path,
                    fixtures=fixture_rows,
                )
            )
        except (
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
            ValueError,
        ) as exc:
            completeness_status = "Blocked"
            blockers.append(f"Odds completeness could not be checked: {exc}")
        else:
            completion_percentage = float(
                completeness_summary.get("completion_percentage", 0.0)
            )
            incomplete_matches = int(
                completeness_summary.get("matches_incomplete", 0)
            )
            if completeness_issues.empty:
                error_mask = pd.Series(dtype=bool)
                warning_mask = pd.Series(dtype=bool)
            else:
                severities = (
                    completeness_issues["severity"]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                )
                error_mask = severities == "error"
                warning_mask = severities == "warning"
            completeness_error_count = int(error_mask.sum())
            completeness_warning_count = int(warning_mask.sum())
            completeness_issue_codes = _issue_codes(completeness_issues, "error")
            complete = (
                completeness_error_count == 0
                and completion_percentage >= 1.0
                and incomplete_matches == 0
            )
            completeness_status = "Complete" if complete else "Blocked"
            if not complete:
                blockers.append(
                    "Odds entry is incomplete: "
                    f"{completion_percentage:.1%} complete, "
                    f"{incomplete_matches} incomplete match(es), and "
                    f"{completeness_error_count} serious completeness issue(s)."
                )
            if completeness_warning_count:
                warnings.append(
                    f"Odds completeness found {completeness_warning_count} "
                    "warning(s)."
                )

    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    card_generation_allowed = not blockers
    if blockers:
        status = "Blocked"
    elif warnings:
        status = "Warnings only"
    else:
        status = "Ready"

    return {
        "run_timestamp": run_at.isoformat(timespec="seconds"),
        "status": status,
        "source_mode": "workflow_dispatch repository files",
        "repository_root": str(root),
        "github_repository": github_repository
        if github_repository is not None
        else os.getenv("GITHUB_REPOSITORY", ""),
        "github_ref": github_ref if github_ref is not None else os.getenv("GITHUB_REF", ""),
        "github_sha": github_sha if github_sha is not None else os.getenv("GITHUB_SHA", ""),
        "github_run_id": github_run_id
        if github_run_id is not None
        else os.getenv("GITHUB_RUN_ID", ""),
        "current_odds_path": odds.display_path,
        "current_odds_checksum_sha256": odds.checksum_sha256,
        "current_odds_expected_checksum_sha256": (
            expected_current_odds_sha256.strip().lower()
        ),
        "current_odds_checksum_status": odds.checksum_status,
        "current_odds_path_policy_valid": odds.path_policy_valid,
        "current_odds_freshness_status": (
            odds_freshness.status if odds_freshness is not None else "Not checked"
        ),
        "current_odds_freshness_note": (
            odds_freshness.note if odds_freshness is not None else ""
        ),
        "current_odds_earliest_date": (
            odds_freshness.earliest_date if odds_freshness is not None else ""
        ),
        "current_odds_latest_date": (
            odds_freshness.latest_date if odds_freshness is not None else ""
        ),
        "current_odds_past_rows": (
            odds_freshness.past_rows if odds_freshness is not None else None
        ),
        "current_odds_today_or_future_rows": (
            odds_freshness.today_or_future_rows
            if odds_freshness is not None
            else None
        ),
        "current_odds_invalid_date_rows": (
            odds_freshness.invalid_date_rows if odds_freshness is not None else None
        ),
        "fixtures_path": fixtures.display_path,
        "fixtures_checksum_sha256": fixtures.checksum_sha256,
        "fixtures_expected_checksum_sha256": expected_fixtures_sha256.strip().lower(),
        "fixtures_checksum_status": fixtures.checksum_status,
        "fixtures_path_policy_valid": fixtures.path_policy_valid,
        "fixtures_freshness_status": (
            fixture_freshness.status
            if fixture_freshness is not None
            else "Not checked"
        ),
        "fixtures_freshness_note": (
            fixture_freshness.note if fixture_freshness is not None else ""
        ),
        "fixtures_earliest_date": (
            fixture_freshness.earliest_date
            if fixture_freshness is not None
            else ""
        ),
        "fixtures_latest_date": (
            fixture_freshness.latest_date if fixture_freshness is not None else ""
        ),
        "fixtures_past_rows": (
            fixture_freshness.past_fixtures
            if fixture_freshness is not None
            else None
        ),
        "fixtures_today_or_future_rows": (
            fixture_freshness.today_or_future_fixtures
            if fixture_freshness is not None
            else None
        ),
        "fixtures_invalid_date_rows": (
            fixture_freshness.invalid_fixture_dates
            if fixture_freshness is not None
            else None
        ),
        "validation_status": validation_status,
        "validation_serious_issue_count": validation_serious_count,
        "validation_warning_count": validation_warning_count,
        "validation_issue_codes": validation_issue_codes,
        "completeness_status": completeness_status,
        "completion_percentage": completion_percentage,
        "incomplete_match_count": incomplete_matches,
        "completeness_error_count": completeness_error_count,
        "completeness_warning_count": completeness_warning_count,
        "completeness_issue_codes": completeness_issue_codes,
        "card_generation_allowed": card_generation_allowed,
        "blockers": blockers,
        "warnings": warnings,
    }


def render_github_runner_input_handoff(summary: dict[str, object]) -> str:
    allowed = "Yes" if summary["card_generation_allowed"] else "No"
    lines = [
        "# GitHub Runner Odds and Fixtures Handoff",
        "",
        (
            "This receipt proves which committed repository files the manual GitHub "
            "runner inspected. It reads inputs and writes reports only; it does not "
            "create sportsbook prices, edit manual files, or place bets."
        ),
        "",
        "## Gate result",
        "",
        f"- Status: **{summary['status']}**",
        f"- Thursday card generation allowed: **{allowed}**",
        f"- Run timestamp: {summary['run_timestamp']}",
        f"- Input method: {summary['source_mode']}",
        f"- GitHub ref: `{summary['github_ref'] or 'not available'}`",
        f"- GitHub commit: `{summary['github_sha'] or 'not available'}`",
        "",
        "## Input proof",
        "",
        "| Input | Repository path | SHA-256 | Checksum status | Date freshness |",
        "|---|---|---|---|---|",
        (
            f"| Current odds | `{summary['current_odds_path']}` | "
            f"`{summary['current_odds_checksum_sha256'] or 'not available'}` | "
            f"{summary['current_odds_checksum_status']} | "
            f"{summary['current_odds_freshness_status']} |"
        ),
        (
            f"| Upcoming fixtures | `{summary['fixtures_path']}` | "
            f"`{summary['fixtures_checksum_sha256'] or 'not available'}` | "
            f"{summary['fixtures_checksum_status']} | "
            f"{summary['fixtures_freshness_status']} |"
        ),
        "",
        "## Validation gates",
        "",
        f"- Current odds validation: **{summary['validation_status']}**",
        (
            "- Serious validation issues: "
            f"{summary['validation_serious_issue_count']}"
        ),
        f"- Validation warnings: {summary['validation_warning_count']}",
        f"- Odds completeness: **{summary['completeness_status']}**",
        f"- Completion percentage: {float(summary['completion_percentage']):.1%}",
        f"- Incomplete matches: {summary['incomplete_match_count']}",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary["blockers"])
    lines.extend([f"- {item}" for item in blockers] or ["- None."])
    lines.extend(["", "## Warnings", ""])
    warnings = list(summary["warnings"])
    lines.extend([f"- {item}" for item in warnings] or ["- None."])
    lines.extend(
        [
            "",
            "## Beginner next step",
            "",
            (
                "If this receipt is Blocked, update the committed odds or fixture "
                "input on the selected branch, run local validation, and start the "
                "manual Action again. Never fill missing odds with guesses."
                if blockers
                else (
                    "The input handoff passed. Review any warnings and the generated "
                    "Thursday reports manually before considering a bet."
                )
            ),
        ]
    )
    return "\n".join(lines)


def save_github_runner_input_handoff(
    *,
    output_dir: Path,
    current_odds_path: Path,
    fixtures_path: Path,
    matches_path: Path,
    run_at: datetime,
    repository_root: Path | None = None,
    expected_current_odds_sha256: str = "",
    expected_fixtures_sha256: str = "",
) -> dict[str, object]:
    summary = build_github_runner_input_handoff(
        current_odds_path=current_odds_path,
        fixtures_path=fixtures_path,
        matches_path=matches_path,
        run_at=run_at,
        repository_root=repository_root,
        expected_current_odds_sha256=expected_current_odds_sha256,
        expected_fixtures_sha256=expected_fixtures_sha256,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / HANDOFF_JSON_FILENAME
    markdown_path = output_dir / HANDOFF_MARKDOWN_FILENAME
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_github_runner_input_handoff(summary),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "json": json_path,
        "markdown": markdown_path,
    }
