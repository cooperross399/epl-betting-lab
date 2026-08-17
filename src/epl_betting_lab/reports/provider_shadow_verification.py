from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.providers.base import (
    BaseStagingProvider,
    ProviderRunRequest,
    atomic_write_report,
    file_sha256,
)
from epl_betting_lab.providers.provider_registry import create_provider
from epl_betting_lab.providers.team_names import (
    normalize_team_name,
    unmapped_team_names,
)
from epl_betting_lab.market_eligibility import evaluate_market_eligibility
from epl_betting_lab.reports.current_odds_template import SUPPORTED_MARKETS
from epl_betting_lab.selected_slate import (
    SELECTED_WEEK1_LABEL,
    filter_to_selected_window,
)
from epl_betting_lab.reports.provider_shadow_history import (
    archive_provider_shadow_run,
)
from epl_betting_lab.reports.staging_input_validation import (
    save_staging_input_validation,
)


SHADOW_JSON_FILENAME = "provider_shadow_verification.json"
SHADOW_MARKDOWN_FILENAME = "provider_shadow_verification.md"
SHADOW_CSV_FILENAME = "provider_shadow_verification.csv"
SHADOW_VERDICTS = (
    "Shadow ready for review",
    "Needs mapping fixes",
    "Needs market coverage review",
    "Needs provider policy review",
    "Blocked",
    "Failed",
)
SHADOW_COLUMNS = ("category", "check", "status", "value", "details")
CHECKSUM_FIELDS = (
    "source_odds_checksum_status",
    "source_fixtures_checksum_status",
    "staging_odds_checksum_status",
    "staging_fixtures_checksum_status",
    "odds_checksum_pair_status",
    "fixtures_checksum_pair_status",
)


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _key(value: object) -> str:
    return _clean(value).casefold()


def _date_key(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return _key(value)
    return parsed.strftime("%Y-%m-%d")


def _fixture_key(row: pd.Series) -> tuple[str, str, str] | None:
    date_value = _date_key(row.get("date", ""))
    home = _key(row.get("home_team", ""))
    away = _key(row.get("away_team", ""))
    if not date_value or not home or not away:
        return None
    return date_value, home, away


def _fixture_keys(frame: pd.DataFrame) -> set[tuple[str, str, str]]:
    return {
        key
        for _, row in frame.iterrows()
        if (key := _fixture_key(row)) is not None
    }


def _format_fixture(key: tuple[str, str, str]) -> str:
    return f"{key[0]}: {key[1]} vs {key[2]}"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("")


def _reference_teams(
    repository_root: Path,
    matches_path: Path,
) -> tuple[set[str], list[str], list[str]]:
    reference_paths = (
        matches_path,
        repository_root / "data" / "manual" / "upcoming_fixtures.csv",
    )
    teams: set[str] = set()
    sources: list[str] = []
    warnings: list[str] = []
    for path in reference_paths:
        if not path.exists():
            continue
        try:
            frame = _read_csv(path)
        except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
            warnings.append(f"Team reference could not be read: `{path}`.")
            continue
        if not {"home_team", "away_team"}.issubset(frame.columns):
            warnings.append(f"Team reference is missing team columns: `{path}`.")
            continue
        for column in ("home_team", "away_team"):
            teams.update(_key(value) for value in frame[column] if _key(value))
        try:
            sources.append(path.relative_to(repository_root).as_posix())
        except ValueError:
            sources.append(str(path))
    return teams, sources, warnings


def _team_mapping_metrics(
    odds: pd.DataFrame,
    fixtures: pd.DataFrame,
    *,
    repository_root: Path,
    matches_path: Path,
) -> dict[str, object]:
    provider_names: dict[str, str] = {}
    for frame in (odds, fixtures):
        for column in ("home_team", "away_team"):
            if column not in frame.columns:
                continue
            for value in frame[column]:
                name = _clean(value)
                if name:
                    provider_names.setdefault(name.casefold(), name)
    references, sources, warnings = _reference_teams(repository_root, matches_path)
    # A name counts as mapped when it already matches a project reference or
    # when a reviewed alias resolves it onto one. Unknown names stay unmapped.
    unmapped = sorted(
        name
        for key, name in provider_names.items()
        if key not in references
        and normalize_team_name(name).casefold() not in references
    )
    unreviewed = unmapped_team_names(provider_names.values())
    total = len(provider_names)
    mapped = total - len(unmapped) if references else 0
    if not provider_names or not references:
        status = "Not checked"
        percentage: float | None = None
    elif unmapped:
        status = "Needs review"
        percentage = mapped / total
    else:
        status = "Verified"
        percentage = 1.0
    return {
        "status": status,
        "provider_team_count": total,
        "mapped_team_count": mapped,
        "unmapped_team_count": len(unmapped),
        "coverage_percentage": percentage,
        "unmapped_teams": unmapped,
        "names_without_reviewed_alias": unreviewed,
        "reference_sources": sources,
        "warnings": warnings,
    }


def _fixture_matching_metrics(
    odds: pd.DataFrame,
    fixtures: pd.DataFrame,
) -> dict[str, object]:
    odds_keys = _fixture_keys(odds)
    fixture_keys = _fixture_keys(fixtures)
    matched = odds_keys & fixture_keys
    unmatched_odds = sorted(odds_keys - fixture_keys)
    fixtures_without_odds = sorted(fixture_keys - odds_keys)
    union = odds_keys | fixture_keys
    percentage = len(matched) / len(union) if union else 0.0
    status = "Verified" if union and odds_keys == fixture_keys else "Needs review"
    return {
        "status": status,
        "odds_fixture_count": len(odds_keys),
        "staging_fixture_count": len(fixture_keys),
        "matched_fixture_count": len(matched),
        "coverage_percentage": percentage,
        "unmatched_odds_fixtures": [_format_fixture(item) for item in unmatched_odds],
        "fixtures_without_odds": [
            _format_fixture(item) for item in fixtures_without_odds
        ],
    }


def _slate_coverage_metrics(
    odds: pd.DataFrame,
    fixtures: pd.DataFrame,
    *,
    repository_root: Path,
) -> dict[str, object]:
    """Report fixture coverage against three explicitly different denominators.

    A single "fixture matching" percentage is misleading: 10 of 10
    provider-returned events is 100% against the provider's own list while
    covering only half of `upcoming_fixtures.csv`. Each scope below names its
    denominator so the number cannot be read as broader than it is.
    """
    odds_keys = _fixture_keys(odds)
    staging_keys = _fixture_keys(fixtures)

    upcoming_path = repository_root / "data" / "manual" / "upcoming_fixtures.csv"
    upcoming = pd.DataFrame()
    upcoming_error = ""
    if upcoming_path.is_file():
        try:
            upcoming = _read_csv(upcoming_path)
        except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
            upcoming_error = f"Upcoming fixtures could not be read: `{upcoming_path}`."

    upcoming_keys = _fixture_keys(upcoming) if not upcoming.empty else set()
    selected = (
        filter_to_selected_window(upcoming) if not upcoming.empty else pd.DataFrame()
    )
    selected_keys = _fixture_keys(selected) if not selected.empty else set()

    def _scope(
        label: str,
        description: str,
        expected: set[tuple[str, str, str]],
    ) -> dict[str, object]:
        covered = expected & odds_keys
        missing = sorted(expected - odds_keys)
        percentage = len(covered) / len(expected) if expected else None
        if not expected:
            status = "Not checked"
        elif missing:
            status = "Incomplete"
        else:
            status = "Complete"
        return {
            "scope": label,
            "denominator": description,
            "status": status,
            "expected_fixture_count": len(expected),
            "covered_fixture_count": len(covered),
            "coverage_percentage": percentage,
            "missing_fixtures": [_format_fixture(item) for item in missing],
        }

    provider_scope = _scope(
        "provider_returned",
        "fixtures the provider actually returned in this run",
        staging_keys,
    )
    selected_scope = _scope(
        "selected_week1_window",
        f"fixtures inside the selected Week 1 window ({SELECTED_WEEK1_LABEL})",
        selected_keys,
    )
    full_scope = _scope(
        "full_upcoming_fixtures",
        "every fixture in data/manual/upcoming_fixtures.csv",
        upcoming_keys,
    )

    warnings: list[str] = []
    if upcoming_error:
        warnings.append(upcoming_error)
    if provider_scope["status"] == "Complete" and selected_scope["status"] not in {
        "Complete",
        "Not checked",
    }:
        warnings.append(
            "Provider-returned coverage is complete, but the selected Week 1 "
            "window is not fully covered. Do not read provider coverage as slate "
            "coverage."
        )
    if (
        full_scope["expected_fixture_count"]
        and selected_scope["expected_fixture_count"]
        and full_scope["expected_fixture_count"]
        > selected_scope["expected_fixture_count"]
    ):
        warnings.append(
            f"`upcoming_fixtures.csv` holds "
            f"{full_scope['expected_fixture_count']} fixtures but the selected "
            f"Week 1 window holds only "
            f"{selected_scope['expected_fixture_count']}. Coverage percentages "
            "differ by scope."
        )

    return {
        "selected_window": SELECTED_WEEK1_LABEL,
        "provider_returned": provider_scope,
        "selected_week1_window": selected_scope,
        "full_upcoming_fixtures": full_scope,
        "warnings": warnings,
    }


def _btts_availability_metrics(
    odds: pd.DataFrame,
    market_coverage: Mapping[str, object],
) -> dict[str, object]:
    """Report BTTS separately from 1X2/totals.

    A provider that returns no BTTS rows is not a provider with bad BTTS prices;
    it is a provider with no BTTS feed. That distinction has to survive into the
    report so nobody fabricates the missing side.
    """
    counts = market_coverage.get("market_counts", {})
    counts = counts if isinstance(counts, Mapping) else {}
    btts_rows = int(counts.get("btts", 0) or 0)
    core_rows = int(counts.get("1x2", 0) or 0) + int(counts.get("total_2_5", 0) or 0)

    books: set[str] = set()
    if btts_rows and "book" in odds.columns and "market" in odds.columns:
        for _, row in odds.iterrows():
            if _key(row.get("market", "")) == "btts" and _clean(row.get("book", "")):
                books.add(_clean(row.get("book", "")))

    if btts_rows:
        status = "Available"
        recommendation = ""
    elif core_rows:
        status = "Unavailable"
        recommendation = (
            "The provider returned 1X2 and/or totals but no BTTS rows. Either "
            "enter real BTTS prices manually, request a provider/market "
            "configuration that includes BTTS, or run the card on markets that "
            "do not require BTTS. Never fabricate a BTTS price."
        )
    else:
        status = "Not checked"
        recommendation = ""

    return {
        "status": status,
        "btts_row_count": btts_rows,
        "core_market_row_count": core_rows,
        "bookmakers_with_btts": sorted(books),
        "trusted": False,
        "fabricated": False,
        "recommended_action": recommendation,
    }


def _core_market_coverage_metrics(
    market_coverage: Mapping[str, object],
) -> dict[str, object]:
    """1X2 + totals coverage reported independently of BTTS availability."""
    missing = market_coverage.get("missing_fixture_selections", [])
    missing = missing if isinstance(missing, list) else []
    core_missing = [
        str(item) for item in missing if "| btts " not in str(item)
    ]
    counts = market_coverage.get("market_counts", {})
    counts = counts if isinstance(counts, Mapping) else {}
    return {
        "status": "Complete" if not core_missing else "Incomplete",
        "markets": ["1x2", "total_2_5"],
        "row_count": int(counts.get("1x2", 0) or 0)
        + int(counts.get("total_2_5", 0) or 0),
        "missing_fixture_selections": core_missing,
        "note": (
            "1X2 and totals coverage only. BTTS availability is reported "
            "separately and is never inferred from these markets."
        ),
    }


def _market_coverage_metrics(
    odds: pd.DataFrame,
    fixtures: pd.DataFrame,
) -> dict[str, object]:
    fixture_keys = _fixture_keys(fixtures)
    expected = {
        (*fixture, market, selection)
        for fixture in fixture_keys
        for market, selection in SUPPORTED_MARKETS
    }
    present: set[tuple[str, str, str, str, str]] = set()
    market_counts = {"1x2": 0, "total_2_5": 0, "btts": 0}
    selection_counts: dict[str, int] = {}
    for _, row in odds.iterrows():
        fixture = _fixture_key(row)
        market = _key(row.get("market", ""))
        selection = _key(row.get("selection", ""))
        if market in market_counts:
            market_counts[market] += 1
            selection_counts[f"{market}:{selection}"] = (
                selection_counts.get(f"{market}:{selection}", 0) + 1
            )
        if fixture is not None and market and selection:
            present.add((*fixture, market, selection))
    missing = sorted(expected - present)
    covered = len(expected & present)
    percentage = covered / len(expected) if expected else 0.0
    missing_markets = sorted({item[3] for item in missing})
    missing_rows = [
        f"{item[0]}: {item[1]} vs {item[2]} | {item[3]} {item[4]}"
        for item in missing
    ]
    return {
        "status": "Complete" if expected and not missing else "Incomplete",
        "market_counts": market_counts,
        "selection_counts": dict(sorted(selection_counts.items())),
        "expected_fixture_selection_count": len(expected),
        "covered_fixture_selection_count": covered,
        "coverage_percentage": percentage,
        "missing_markets": missing_markets,
        "missing_fixture_selections": missing_rows,
    }


def _bookmaker_coverage_metrics(odds: pd.DataFrame) -> dict[str, object]:
    rows_by_book: dict[str, int] = {}
    fixtures_by_book: dict[str, set[tuple[str, str, str]]] = {}
    if "book" in odds.columns:
        for _, row in odds.iterrows():
            book = _clean(row.get("book", ""))
            if not book:
                continue
            rows_by_book[book] = rows_by_book.get(book, 0) + 1
            fixture = _fixture_key(row)
            if fixture is not None:
                fixtures_by_book.setdefault(book, set()).add(fixture)
    return {
        "status": "Available" if rows_by_book else "Missing",
        "bookmaker_count": len(rows_by_book),
        "bookmakers": sorted(rows_by_book),
        "rows_by_bookmaker": dict(sorted(rows_by_book.items())),
        "fixtures_by_bookmaker": {
            book: len(fixtures_by_book.get(book, set()))
            for book in sorted(rows_by_book)
        },
    }


def _raw_evidence_files(
    provider_summary: Mapping[str, object],
    repository_root: Path,
) -> dict[str, object]:
    declared: list[str] = []
    raw_path = _clean(provider_summary.get("raw_source_path", ""))
    if raw_path:
        declared.append(raw_path)
    files_written = provider_summary.get("files_written", [])
    if isinstance(files_written, list):
        declared.extend(
            str(item)
            for item in files_written
            if "/raw/" in str(item).replace("\\", "/")
        )
    declared = list(dict.fromkeys(declared))
    found = []
    current_checksums: dict[str, str] = {}
    for value in declared:
        candidate = Path(value)
        path = candidate if candidate.is_absolute() else repository_root / candidate
        if path.is_file():
            found.append(value)
            try:
                current_checksums[value] = file_sha256(path)
            except OSError:
                current_checksums[value] = ""
    recorded_checksum = _clean(
        provider_summary.get("raw_source_checksum_sha256", "")
    )
    if not declared or len(found) != len(declared):
        checksum_status = "Missing"
    elif not recorded_checksum or not all(current_checksums.values()):
        checksum_status = "Not available"
    elif all(value == recorded_checksum for value in current_checksums.values()):
        checksum_status = "Verified"
    else:
        checksum_status = "Mismatch"
    return {
        "status": "Created" if declared and len(found) == len(declared) else "Missing",
        "declared_files": declared,
        "found_files": found,
        "raw_source_checksum_sha256": recorded_checksum,
        "current_checksums_sha256": current_checksums,
        "checksum_status": checksum_status,
    }


def _quota_metrics(provider_summary: Mapping[str, object]) -> dict[str, object]:
    headers = provider_summary.get("provider_response_headers", {})
    safe_headers = headers if isinstance(headers, dict) else {}
    values = {
        "requests_remaining": _clean(safe_headers.get("x-requests-remaining", "")),
        "requests_used": _clean(safe_headers.get("x-requests-used", "")),
        "requests_last": _clean(safe_headers.get("x-requests-last", "")),
    }
    return {
        "status": "Available" if any(values.values()) else "Not available",
        **values,
    }


def _empty_validation_summary() -> dict[str, object]:
    return {
        "verdict": "Not run",
        "handoff_eligible": False,
        "provider_age_status": "Not checked",
        "provenance_status": "Not checked",
        **{field: "Not checked" for field in CHECKSUM_FIELDS},
        "odds_completeness": {
            "status": "Not checked",
            "completion_percentage": 0.0,
            "matches_incomplete": 0,
        },
        "provider_policy": {
            "provider_policy_status": "Not checked",
            "provider_allowed": False,
            "allowed": False,
            "blockers": [],
            "warnings": [],
        },
        "handoff_gate": {"blockers": [], "warnings": []},
    }


def _choose_verdict(
    *,
    dry_run: bool,
    provider_status: str,
    validation_error: str,
    validation: Mapping[str, object],
    raw_evidence: Mapping[str, object],
    team_mapping: Mapping[str, object],
    fixture_matching: Mapping[str, object],
    market_coverage: Mapping[str, object],
    bookmaker_coverage: Mapping[str, object],
    eligibility: Mapping[str, object] | None = None,
) -> tuple[str, str]:
    if provider_status == "Failed":
        return "Failed", "The provider adapter encountered a file/runtime failure."
    if dry_run:
        return (
            "Blocked",
            "Dry-run made no network request or staging bundle, so usability is not proven.",
        )
    if provider_status != "Completed":
        return "Blocked", "The live provider run did not complete safely."
    if validation_error:
        return "Failed", f"Staging validation could not finish: {validation_error}"
    if (
        raw_evidence.get("status") != "Created"
        or raw_evidence.get("checksum_status") != "Verified"
    ):
        return "Blocked", "Raw provider evidence is missing or failed SHA-256 verification."

    checksum_statuses = [str(validation.get(field, "Not checked")) for field in CHECKSUM_FIELDS]
    if (
        str(validation.get("provenance_status")) != "Verified"
        or str(validation.get("provider_age_status")) != "Fresh"
        or any(status != "Verified" for status in checksum_statuses)
    ):
        return (
            "Blocked",
            "Provider provenance, age, or source/staging checksum proof did not pass.",
        )
    if team_mapping.get("status") != "Verified":
        return (
            "Needs mapping fixes",
            "One or more provider team names lack an exact reviewed project mapping.",
        )
    if fixture_matching.get("status") != "Verified":
        return (
            "Needs mapping fixes",
            "Provider odds and fixture identities do not match completely.",
        )

    completeness = validation.get("odds_completeness", {})
    completion_percentage = (
        float(completeness.get("completion_percentage", 0.0))
        if isinstance(completeness, dict)
        else 0.0
    )
    # Market-aware coverage: judge the markets the card will actually use.
    # An excluded market is excluded, not an outstanding gap.
    eligible = list((eligibility or {}).get("eligible_markets", []) or [])
    excluded = list((eligibility or {}).get("excluded_markets", []) or [])
    if eligibility is None:
        coverage_ok = market_coverage.get("status") == "Complete"
        coverage_reason = (
            "At least one required 1X2, totals, or BTTS selection is missing."
        )
    elif not eligible:
        coverage_ok = False
        coverage_reason = (
            "No market is complete enough to be eligible for an automated card."
        )
    else:
        coverage_ok = True
        coverage_reason = ""
    if not coverage_ok or completion_percentage < 1.0:
        return (
            "Needs market coverage review",
            coverage_reason
            or (
                "Eligible markets "
                f"{eligible} are complete, but odds completeness for them is "
                f"{completion_percentage:.1%}."
            ),
        )
    if bookmaker_coverage.get("status") != "Available":
        return (
            "Needs market coverage review",
            "No usable bookmaker identity was returned with the prices.",
        )

    policy = validation.get("provider_policy", {})
    if not isinstance(policy, dict):
        return "Blocked", "The provider policy result is unavailable."
    if not bool(policy.get("provider_allowed")):
        return (
            "Needs provider policy review",
            "The data checks passed, but the reviewed policy does not allow this provider.",
        )
    if not bool(policy.get("allowed")):
        return "Blocked", "Receipt age, cutoff, or another provider policy gate blocked handoff."
    if validation.get("verdict") != "Ready for handoff" or not bool(
        validation.get("handoff_eligible")
    ):
        return "Blocked", "An existing staging or GitHub handoff gate still blocks the bundle."
    return (
        "Shadow ready for review",
        "The live bundle passed current technical gates; manual review is still required.",
    )


def _next_step(verdict: str) -> str:
    return {
        "Shadow ready for review": (
            "Review raw evidence and repeat several manual shadow runs before any "
            "provider allowlist or scheduling decision."
        ),
        "Needs mapping fixes": (
            "Review the listed provider team/fixture names and add only deliberate, "
            "tested normalization support."
        ),
        "Needs market coverage review": (
            "Review provider market availability, especially BTTS. Leave unavailable "
            "prices missing rather than inventing them."
        ),
        "Needs provider policy review": (
            "Review repeated shadow evidence manually before deciding whether to edit "
            "the provider allowlist. This report does not edit policy."
        ),
        "Blocked": (
            "Fix the reported credentials, staging collision, provenance, age, data, "
            "or validation blocker, then rerun the shadow verifier."
        ),
        "Failed": "Inspect the failure details, fix the runtime issue, and rerun dry-run.",
    }[verdict]


def _add_check(
    rows: list[dict[str, object]],
    category: str,
    check: str,
    status: object,
    value: object,
    details: str,
) -> None:
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, sort_keys=True)
    rows.append(
        {
            "category": category,
            "check": check,
            "status": status,
            "value": value,
            "details": details,
        }
    )


def build_shadow_checks(summary: Mapping[str, object]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    _add_check(
        rows,
        "Shadow run",
        "shadow_verdict",
        summary["verdict"],
        summary["mode"],
        str(summary["verdict_reason"]),
    )
    provider = summary["provider_run"]
    _add_check(
        rows,
        "Provider",
        "provider_run_status",
        provider["status"],
        provider["network_request_made"],
        "Network request made is reported without exposing credentials.",
    )
    raw = summary["raw_evidence"]
    _add_check(
        rows,
        "Evidence",
        "raw_evidence",
        raw["status"],
        raw["found_files"],
        f"Raw evidence checksum: {raw['checksum_status']}.",
    )
    checksums = summary["checksums"]
    for field in CHECKSUM_FIELDS:
        _add_check(
            rows,
            "Evidence",
            field,
            checksums[field],
            checksums[field],
            "Status comes from the existing staging provenance verifier.",
        )
    age = summary["provider_age"]
    _add_check(
        rows,
        "Provider",
        "provider_age",
        age["status"],
        age["age_minutes"],
        age["note"],
    )
    mapping = summary["team_mapping"]
    _add_check(
        rows,
        "Coverage",
        "team_name_mapping",
        mapping["status"],
        mapping["coverage_percentage"],
        f"Unmapped teams: {mapping['unmapped_teams'] or 'none'}.",
    )
    fixtures = summary["fixture_matching"]
    _add_check(
        rows,
        "Coverage",
        "fixture_matching",
        fixtures["status"],
        fixtures["coverage_percentage"],
        (
            f"Unmatched odds: {fixtures['unmatched_odds_fixtures'] or 'none'}; "
            f"fixtures without odds: {fixtures['fixtures_without_odds'] or 'none'}."
        ),
    )
    slate = summary["slate_coverage"]
    for scope_key in (
        "provider_returned",
        "selected_week1_window",
        "full_upcoming_fixtures",
    ):
        scope = slate[scope_key]
        _add_check(
            rows,
            "Coverage",
            f"slate_{scope_key}",
            scope["status"],
            scope["coverage_percentage"],
            (
                f"Denominator: {scope['denominator']}; covered "
                f"{scope['covered_fixture_count']}/{scope['expected_fixture_count']}; "
                f"missing: {scope['missing_fixtures'] or 'none'}."
            ),
        )
    btts = summary["btts_availability"]
    _add_check(
        rows,
        "Coverage",
        "btts_availability",
        btts["status"],
        btts["btts_row_count"],
        (
            f"Trusted: {btts['trusted']}; fabricated: {btts['fabricated']}. "
            f"{btts['recommended_action'] or 'BTTS rows were returned.'}"
        ),
    )
    core = summary["core_market_coverage"]
    _add_check(
        rows,
        "Coverage",
        "core_market_coverage",
        core["status"],
        core["row_count"],
        core["note"],
    )
    markets = summary["market_coverage"]
    for market in ("1x2", "total_2_5", "btts"):
        count = markets["market_counts"][market]
        _add_check(
            rows,
            "Coverage",
            f"market_{market}",
            "Returned" if count else "Missing",
            count,
            "No missing price is inferred or fabricated.",
        )
    books = summary["bookmaker_coverage"]
    _add_check(
        rows,
        "Coverage",
        "bookmaker_coverage",
        books["status"],
        books["bookmakers"],
        f"Rows by bookmaker: {books['rows_by_bookmaker']}.",
    )
    completeness = summary["odds_completeness"]
    _add_check(
        rows,
        "Validation",
        "odds_completeness",
        completeness["status"],
        completeness["completion_percentage"],
        f"Incomplete matches: {completeness['matches_incomplete']}.",
    )
    validation = summary["staging_validation"]
    _add_check(
        rows,
        "Validation",
        "staging_validation_verdict",
        validation["verdict"],
        validation["handoff_eligible"],
        "The existing staging and GitHub handoff gates remain authoritative.",
    )
    policy = summary["provider_policy"]
    _add_check(
        rows,
        "Policy",
        "provider_allowed",
        "Allowed" if policy["provider_allowed"] else "Not allowed",
        policy["provider_policy_status"],
        "The shadow verifier never changes the provider policy.",
    )
    quota = summary["api_quota"]
    _add_check(
        rows,
        "Provider",
        "api_quota",
        quota["status"],
        quota,
        "Only the provider's safe request-usage headers are included.",
    )
    return pd.DataFrame(rows, columns=SHADOW_COLUMNS)


def render_provider_shadow_verification(
    checks: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    markets = summary["market_coverage"]
    mapping = summary["team_mapping"]
    fixtures = summary["fixture_matching"]
    slate = summary["slate_coverage"]
    btts = summary["btts_availability"]
    core = summary["core_market_coverage"]
    policy = summary["provider_policy"]
    quota = summary["api_quota"]
    raw = summary["raw_evidence"]
    blockers = [f"- {item}" for item in summary["blockers"]] or ["- None."]
    warnings = [f"- {item}" for item in summary["warnings"]] or ["- None."]
    lines = [
        "# Provider Shadow Verification",
        "",
        (
            "A shadow run evaluates provider staging evidence without generating "
            "trusted picks, promoting files, changing policy, enabling cron, or "
            "placing bets."
        ),
        "",
        "## Verdict",
        "",
        f"- **{summary['verdict']}**",
        f"- Mode: **{summary['mode']}**",
        f"- Reason: {summary['verdict_reason']}",
        f"- Next step: {summary['next_step']}",
        "",
        "## Provider and evidence",
        "",
        f"- Provider: **{summary['provider_name']}** ({summary['provider_type']})",
        f"- Provider run status: **{summary['provider_run']['status']}**",
        (
            "- Network request made: **"
            f"{'Yes' if summary['provider_run']['network_request_made'] else 'No'}**"
        ),
        f"- Raw evidence: **{raw['status']}** | {raw['found_files'] or 'none'}",
        f"- Raw evidence checksum: **{raw['checksum_status']}**",
        f"- Provider age: **{summary['provider_age']['status']}**",
        f"- Provenance: **{summary['checksums']['provenance_status']}**",
        "",
        "## Coverage",
        "",
        (
            f"- Team mapping: **{mapping['status']}** | "
            f"{mapping['mapped_team_count']}/{mapping['provider_team_count']} mapped"
        ),
        f"- Unmapped teams: {mapping['unmapped_teams'] or 'none'}",
        (
            f"- Fixture matching: **{fixtures['status']}** | "
            f"{fixtures['matched_fixture_count']}/"
            f"{max(fixtures['odds_fixture_count'], fixtures['staging_fixture_count'])} "
            "matched"
        ),
        (
            f"- Markets: 1X2 {markets['market_counts']['1x2']} rows; "
            f"totals {markets['market_counts']['total_2_5']} rows; "
            f"BTTS {markets['market_counts']['btts']} rows"
        ),
        f"- Missing market coverage: {markets['missing_markets'] or 'none'}",
        (
            f"- Core markets (1X2 + totals): **{core['status']}** | "
            f"{core['row_count']} rows"
        ),
        (
            f"- BTTS availability: **{btts['status']}** | "
            f"{btts['btts_row_count']} rows | trusted: "
            f"{'Yes' if btts['trusted'] else 'No'}"
        ),
        (
            f"- Odds completeness: {summary['odds_completeness']['completion_percentage']:.1%}"
        ),
        (
            f"- Bookmakers ({summary['bookmaker_coverage']['bookmaker_count']}): "
            f"{summary['bookmaker_coverage']['bookmakers'] or 'none'}"
        ),
        "",
        "## Fixture coverage by scope",
        "",
        (
            "Each row uses a different denominator. A high percentage against "
            "provider-returned fixtures does **not** mean the slate is covered."
        ),
        "",
        "| Scope | Denominator | Status | Covered | Coverage |",
        "|:------|:------------|:-------|:--------|:---------|",
        *[
            (
                f"| `{scope['scope']}` | {scope['denominator']} | "
                f"**{scope['status']}** | "
                f"{scope['covered_fixture_count']}/{scope['expected_fixture_count']} | "
                + (
                    f"{scope['coverage_percentage']:.1%}"
                    if scope["coverage_percentage"] is not None
                    else "n/a"
                )
                + " |"
            )
            for scope in (
                slate["provider_returned"],
                slate["selected_week1_window"],
                slate["full_upcoming_fixtures"],
            )
        ],
        "",
        f"- Selected Week 1 window: **{slate['selected_window']}**",
        (
            "- Fixtures in the selected window without provider odds: "
            f"{slate['selected_week1_window']['missing_fixtures'] or 'none'}"
        ),
        "",
        "## BTTS availability",
        "",
        f"- Status: **{btts['status']}** ({btts['btts_row_count']} rows)",
        f"- Treated as trusted: **{'Yes' if btts['trusted'] else 'No'}**",
        f"- Any price fabricated: **{'Yes' if btts['fabricated'] else 'No'}**",
        (
            f"- Recommended action: {btts['recommended_action']}"
            if btts["recommended_action"]
            else "- Recommended action: none; BTTS rows were returned."
        ),
        (
            f"- Core 1X2/totals coverage is reported separately: "
            f"**{core['status']}** ({core['row_count']} rows)"
        ),
        "",
        "## Existing gates",
        "",
        f"- Staging validation: **{summary['staging_validation']['verdict']}**",
        (
            "- Handoff eligible: **"
            f"{'Yes' if summary['staging_validation']['handoff_eligible'] else 'No'}**"
        ),
        f"- Provider policy: **{policy['provider_policy_status']}**",
        f"- Provider currently allowed: **{'Yes' if policy['provider_allowed'] else 'No'}**",
        "- This report never edits the allowlist.",
        "",
        "## Safe API usage",
        "",
        f"- Quota status: **{quota['status']}**",
        f"- Requests remaining: {quota['requests_remaining'] or 'not available'}",
        f"- Requests used: {quota['requests_used'] or 'not available'}",
        f"- Last request cost: {quota['requests_last'] or 'not available'}",
        "- Credentials are never included in this report.",
        "",
        "## Blockers",
        "",
        *blockers,
        "",
        "## Warnings",
        "",
        *warnings,
        "",
        "## Check table",
        "",
        checks.to_markdown(index=False),
        "",
        "## Verdict meanings",
        "",
        "- **Shadow ready for review:** technical checks passed; manual review still comes first.",
        "- **Needs mapping fixes:** provider team or fixture identities need reviewed mappings.",
        (
            "- **Needs market coverage review:** required prices, including BTTS "
            "when absent, remain incomplete."
        ),
        "- **Needs provider policy review:** data passed, but the provider is not allowlisted.",
        "- **Blocked:** a safety, evidence, age, validation, or credential gate stopped the run.",
        "- **Failed:** a runtime/reporting failure prevented verification.",
        "",
        "Cron remains disabled, and this report cannot generate or approve a bet.",
    ]
    return "\n".join(lines)


def _eligible_markets_for_validation(
    odds: pd.DataFrame,
    fixtures: pd.DataFrame,
) -> list[str] | None:
    """Markets complete enough across the selected window to be validated.

    Validation should judge the bundle on the markets the card will actually
    use. A market the provider prices at a different line for some fixtures
    (today `total_2_5`) is excluded rather than treated as an outstanding gap.
    """
    # Scope is judged across the whole staged bundle, not the Week 1 window:
    # validation must describe the bundle it was handed. Windowing here would
    # silently empty the scope for any bundle outside those dates.
    report = evaluate_market_eligibility(
        odds,
        fixtures,
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
        window_label=SELECTED_WEEK1_LABEL,
        restrict_to_window=False,
    )
    eligible = list(report.eligible_markets)
    # No eligible market means there is nothing narrower to validate. Fall back
    # to the historical all-markets gate rather than validating an empty scope,
    # which would vacuously "pass".
    return eligible or None


def save_provider_shadow_verification(
    provider_name: str,
    *,
    dry_run: bool = True,
    overwrite_staging: bool = False,
    repository_root: Path | None = None,
    matches_path: Path | None = None,
    provider_policy_path: Path | None = None,
    run_at: datetime | None = None,
    provider: BaseStagingProvider | None = None,
) -> dict[str, object]:
    root = (repository_root or PROJECT_ROOT).resolve()
    outputs = root / "data" / "outputs"
    staging = root / "data" / "staging"
    selected_matches = matches_path or root / "data" / "processed" / "epl_historical_matches.csv"
    selected_policy = (
        provider_policy_path
        or root / "data" / "manual" / "staging_provider_policy.json"
    )
    generated_at = run_at or datetime.now().astimezone()
    adapter = provider or create_provider(provider_name)
    provider_result = adapter.run(
        ProviderRunRequest(
            dry_run=dry_run,
            overwrite_staging=overwrite_staging,
            repository_root=root,
            run_at=generated_at,
            generated_by="scripts/run_provider_shadow_verification.py",
            notes="Controlled provider shadow verification run.",
        )
    )
    provider_summary = provider_result.get("summary", {})
    if not isinstance(provider_summary, dict):
        provider_summary = {}
    provider_status = _clean(provider_summary.get("status", "Failed")) or "Failed"

    validation = _empty_validation_summary()
    validation_outputs: dict[str, str] = {}
    validation_error = ""
    odds = pd.DataFrame()
    fixtures = pd.DataFrame()
    if not dry_run and provider_status == "Completed":
        try:
            staged_odds = _read_csv(Path(provider_result["staging_odds"]))
            staged_fixtures = _read_csv(Path(provider_result["staging_fixtures"]))
            eligible_markets = _eligible_markets_for_validation(
                staged_odds, staged_fixtures
            )
            validation_result = save_staging_input_validation(
                Path(provider_result["staging_odds"]),
                Path(provider_result["staging_fixtures"]),
                matches_path=selected_matches,
                output_dir=outputs,
                repository_root=root,
                staging_dir=staging,
                provenance_path=Path(provider_result["provenance"]),
                provider_policy_path=selected_policy,
                run_at=generated_at,
                eligible_markets=eligible_markets,
            )
            validation = json.loads(
                Path(validation_result["json"]).read_text(encoding="utf-8")
            )
            validation_outputs = {
                name: str(validation_result[name])
                for name in ("csv", "markdown", "json")
            }
            odds = _read_csv(Path(provider_result["staging_odds"]))
            fixtures = _read_csv(Path(provider_result["staging_fixtures"]))
        except (
            KeyError,
            OSError,
            UnicodeError,
            ValueError,
            json.JSONDecodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as exc:
            validation_error = f"{type(exc).__name__}: {exc}"

    team_mapping = _team_mapping_metrics(
        odds,
        fixtures,
        repository_root=root,
        matches_path=Path(selected_matches),
    )
    fixture_matching = _fixture_matching_metrics(odds, fixtures)
    market_coverage = _market_coverage_metrics(odds, fixtures)
    slate_coverage = _slate_coverage_metrics(odds, fixtures, repository_root=root)
    _eligibility_report = evaluate_market_eligibility(
        odds,
        fixtures,
        mapping_verified=team_mapping.get("status") == "Verified",
        validation_passed=not validation_error,
        freshness_passed=True,
        window_label=SELECTED_WEEK1_LABEL,
        # Bundle-scoped, not window-scoped: this verdict describes the staged
        # bundle it was handed. Week 1 windowing lives in slate_coverage and in
        # the card-input builder.
        restrict_to_window=False,
    )
    market_eligibility = _eligibility_report.as_dict()
    btts_availability = _btts_availability_metrics(odds, market_coverage)
    core_market_coverage = _core_market_coverage_metrics(market_coverage)
    bookmaker_coverage = _bookmaker_coverage_metrics(odds)
    raw_evidence = _raw_evidence_files(provider_summary, root)
    api_quota = _quota_metrics(provider_summary)
    policy = validation.get("provider_policy", {})
    if not isinstance(policy, dict):
        policy = {}
    completeness = validation.get("odds_completeness", {})
    if not isinstance(completeness, dict):
        completeness = {}
    verdict, verdict_reason = _choose_verdict(
        dry_run=dry_run,
        provider_status=provider_status,
        validation_error=validation_error,
        validation=validation,
        raw_evidence=raw_evidence,
        team_mapping=team_mapping,
        fixture_matching=fixture_matching,
        market_coverage=market_coverage,
        bookmaker_coverage=bookmaker_coverage,
        eligibility=market_eligibility,
    )
    if verdict not in SHADOW_VERDICTS:
        raise ValueError(f"Unexpected shadow verification verdict: {verdict}")

    provider_blockers = provider_summary.get("blockers", [])
    provider_warnings = provider_summary.get("warnings", [])
    handoff = validation.get("handoff_gate", {})
    handoff_blockers = handoff.get("blockers", []) if isinstance(handoff, dict) else []
    handoff_warnings = handoff.get("warnings", []) if isinstance(handoff, dict) else []
    warnings = [str(item) for item in provider_warnings if str(item).strip()]
    warnings.extend(str(item) for item in team_mapping["warnings"])
    warnings.extend(str(item) for item in handoff_warnings if str(item).strip())
    warnings.extend(str(item) for item in slate_coverage["warnings"])
    if market_coverage["missing_markets"]:
        warnings.append(
            "Missing market coverage: "
            + ", ".join(str(item) for item in market_coverage["missing_markets"])
            + ". No odds were fabricated."
        )
    if btts_availability["status"] == "Unavailable":
        warnings.append(
            "BTTS is unavailable from this provider run (0 rows). It is reported "
            "as unavailable, never as trusted, and no BTTS price was invented. "
            "1X2/totals coverage is reported separately under "
            "`core_market_coverage`."
        )
    blockers = [str(item) for item in provider_blockers if str(item).strip()]
    blockers.extend(str(item) for item in handoff_blockers if str(item).strip())
    if validation_error:
        blockers.append(validation_error)

    checksums = {
        "provenance_status": _clean(validation.get("provenance_status", "Not checked")),
        **{
            field: _clean(validation.get(field, "Not checked")) or "Not checked"
            for field in CHECKSUM_FIELDS
        },
    }
    summary: dict[str, object] = {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "provider_key": adapter.provider_key,
        "provider_name": adapter.provider_name,
        "provider_type": adapter.provider_type,
        "mode": "Dry run" if dry_run else "Live shadow run",
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "next_step": _next_step(verdict),
        "provider_run": {
            "status": provider_status,
            "network_request_made": bool(
                provider_summary.get("network_request_made", False)
            ),
            "fixture_count": int(provider_summary.get("fixture_count", 0) or 0),
            "odds_row_count": int(provider_summary.get("odds_row_count", 0) or 0),
            "provider_report_json": str(provider_result.get("report_json", "")),
            "provider_report_markdown": str(
                provider_result.get("report_markdown", "")
            ),
        },
        "raw_evidence": raw_evidence,
        "checksums": checksums,
        "provider_age": {
            "status": _clean(validation.get("provider_age_status", "Not checked"))
            or "Not checked",
            "age_minutes": validation.get("provider_run_age_minutes"),
            "note": _clean(validation.get("provider_age_note", "")),
        },
        "team_mapping": team_mapping,
        "fixture_matching": fixture_matching,
        "slate_coverage": slate_coverage,
        "market_eligibility": market_eligibility,
        "bookmaker_coverage": bookmaker_coverage,
        "market_coverage": market_coverage,
        "core_market_coverage": core_market_coverage,
        "btts_availability": btts_availability,
        "odds_completeness": {
            "status": _clean(completeness.get("status", "Not checked"))
            or "Not checked",
            "completion_percentage": float(
                completeness.get("completion_percentage", 0.0) or 0.0
            ),
            "matches_incomplete": int(
                completeness.get("matches_incomplete", 0) or 0
            ),
        },
        "staging_validation": {
            "verdict": _clean(validation.get("verdict", "Not run")) or "Not run",
            "handoff_eligible": bool(validation.get("handoff_eligible", False)),
            "outputs": validation_outputs,
            "error": validation_error,
        },
        "provider_policy": {
            "provider_policy_status": _clean(
                policy.get("provider_policy_status", "Not checked")
            )
            or "Not checked",
            "provider_allowed": bool(policy.get("provider_allowed", False)),
            "all_policy_gates_allowed": bool(policy.get("allowed", False)),
            "policy_path": _clean(policy.get("path", str(selected_policy))),
        },
        "api_quota": api_quota,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "safety": {
            "trusted_picks_generated": False,
            "manual_or_production_files_edited": False,
            "staging_promoted": False,
            "provider_policy_edited": False,
            "cron_enabled": False,
            "bets_placed": False,
            "secrets_written_or_printed": False,
        },
    }
    checks = build_shadow_checks(summary)
    json_path = outputs / SHADOW_JSON_FILENAME
    markdown_path = outputs / SHADOW_MARKDOWN_FILENAME
    csv_path = outputs / SHADOW_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        render_provider_shadow_verification(checks, summary).encode("utf-8"),
    )
    atomic_write_report(
        csv_path,
        checks.to_csv(index=False, lineterminator="\n").encode("utf-8"),
    )
    archive = archive_provider_shadow_run(
        summary,
        verification_paths={
            "json": json_path,
            "markdown": markdown_path,
            "csv": csv_path,
        },
        provider_report_paths={
            "json": provider_result.get("report_json"),
            "markdown": provider_result.get("report_markdown"),
        },
        staging_validation_paths=validation_outputs,
        output_dir=outputs,
        archived_at=generated_at,
    )
    return {
        "summary": summary,
        "checks": checks,
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
        "archive": archive,
    }
