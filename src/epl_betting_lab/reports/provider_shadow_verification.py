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
from epl_betting_lab.reports.current_odds_template import SUPPORTED_MARKETS
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
    unmapped = sorted(
        name for key, name in provider_names.items() if key not in references
    )
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
    if market_coverage.get("status") != "Complete" or completion_percentage < 1.0:
        return (
            "Needs market coverage review",
            "At least one required 1X2, totals, or BTTS selection is missing.",
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
            f"- Odds completeness: {summary['odds_completeness']['completion_percentage']:.1%}"
        ),
        (
            f"- Bookmakers ({summary['bookmaker_coverage']['bookmaker_count']}): "
            f"{summary['bookmaker_coverage']['bookmakers'] or 'none'}"
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
    if market_coverage["missing_markets"]:
        warnings.append(
            "Missing market coverage: "
            + ", ".join(str(item) for item in market_coverage["missing_markets"])
            + ". No odds were fabricated."
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
        "bookmaker_coverage": bookmaker_coverage,
        "market_coverage": market_coverage,
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
    return {
        "summary": summary,
        "checks": checks,
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
    }
