from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.providers.base import atomic_write_report
from epl_betting_lab.reports.provider_shadow_history import (
    build_provider_shadow_comparison_rows,
    load_provider_shadow_run_history,
)


ACCEPTANCE_JSON_FILENAME = "provider_acceptance_checklist.json"
ACCEPTANCE_MARKDOWN_FILENAME = "provider_acceptance_checklist.md"
ACCEPTANCE_CSV_FILENAME = "provider_acceptance_checklist.csv"
DEFAULT_MINIMUM_LIVE_RUNS = 3
DEFAULT_REVIEW_WINDOW = 5
ACCEPTANCE_VERDICTS = (
    "Ready for human allowlist review",
    "Needs more shadow runs",
    "Needs mapping fixes",
    "Needs market coverage review",
    "Needs quota review",
    "Needs provider policy review",
    "Not trusted",
)
CHECKLIST_COLUMNS = (
    "requirement",
    "status",
    "observed",
    "required",
    "details",
)
CHECKSUM_FIELDS = (
    "provenance_status",
    "source_odds_checksum_status",
    "source_fixtures_checksum_status",
    "staging_odds_checksum_status",
    "staging_fixtures_checksum_status",
    "odds_checksum_pair_status",
    "fixtures_checksum_pair_status",
)


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _as_float(value: object) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    return float(numeric)


def _as_int(value: object) -> int:
    numeric = _as_float(value)
    return int(numeric) if numeric is not None else 0


def _nested(summary: Mapping[str, object], *keys: str, default: object = "") -> object:
    value: object = summary
    for key in keys:
        if not isinstance(value, Mapping):
            return default
        value = value.get(key, default)
    return value


def _summary(record: Mapping[str, object]) -> Mapping[str, object]:
    value = record.get("summary", {})
    return value if isinstance(value, Mapping) else {}


def _is_live(record: Mapping[str, object]) -> bool:
    summary = _summary(record)
    return (
        _clean(summary.get("mode")) or _clean(record.get("mode"))
    ) == "Live shadow run"


def _is_completed(record: Mapping[str, object]) -> bool:
    return _clean(_nested(_summary(record), "provider_run", "status")) == "Completed"


def _add_check(
    rows: list[dict[str, object]],
    requirement: str,
    status: str,
    observed: object,
    required: str,
    details: str,
) -> None:
    if isinstance(observed, (dict, list, tuple, set)):
        observed = json.dumps(observed, sort_keys=True)
    rows.append(
        {
            "requirement": requirement,
            "status": status,
            "observed": observed,
            "required": required,
            "details": details,
        }
    )


def _coverage_check(
    records: Sequence[Mapping[str, object]],
    section: str,
) -> tuple[bool, str]:
    values = [
        _as_float(_nested(_summary(record), section, "coverage_percentage"))
        for record in records
    ]
    statuses = [
        _clean(_nested(_summary(record), section, "status")) for record in records
    ]
    valid_values = [value for value in values if value is not None]
    stable = bool(valid_values) and max(valid_values) - min(valid_values) <= 0.001
    complete = (
        bool(records)
        and len(valid_values) == len(records)
        and all(value >= 0.999 for value in valid_values)
        and all(status == "Verified" for status in statuses)
    )
    display = (
        f"{min(valid_values):.1%} to {max(valid_values):.1%}"
        if valid_values
        else "No completed live-run coverage"
    )
    return complete and stable, display


def _bookmaker_check(
    records: Sequence[Mapping[str, object]],
) -> tuple[bool, str]:
    sets: list[tuple[str, ...]] = []
    for record in records:
        summary = _summary(record)
        raw = _nested(summary, "bookmaker_coverage", "bookmakers", default=[])
        books = tuple(sorted(_clean(item) for item in raw if _clean(item))) if isinstance(
            raw, list
        ) else ()
        status = _clean(_nested(summary, "bookmaker_coverage", "status"))
        if status != "Available" or not books:
            return False, "At least one reviewed run has no usable bookmaker."
        sets.append(books)
    if not sets:
        return False, "No completed live-run bookmaker evidence"
    stable = len(set(sets)) == 1
    observed = "; ".join(", ".join(items) for items in dict.fromkeys(sets))
    return stable, observed


def _market_check(
    records: Sequence[Mapping[str, object]],
    *,
    market: str,
    selections_per_fixture: int,
) -> tuple[bool, str]:
    observations: list[str] = []
    passing = True
    for record in records:
        summary = _summary(record)
        fixture_count = _as_int(_nested(summary, "provider_run", "fixture_count"))
        row_count = _as_int(
            _nested(summary, "market_coverage", "market_counts", market)
        )
        expected = fixture_count * selections_per_fixture
        run_ok = row_count >= expected if expected else row_count > 0
        passing = passing and run_ok
        observations.append(f"{row_count}/{expected or 'unknown'}")
    if not records:
        return False, "No completed live-run market evidence"
    return passing, ", ".join(observations)


def _btts_reporting_check(
    records: Sequence[Mapping[str, object]],
) -> tuple[bool, str]:
    availability: list[str] = []
    for record in records:
        coverage = _nested(_summary(record), "market_coverage", default={})
        if not isinstance(coverage, Mapping):
            return False, "BTTS coverage is not structured in at least one run."
        counts = coverage.get("market_counts", {})
        missing = coverage.get("missing_markets", [])
        if not isinstance(counts, Mapping) or "btts" not in counts or not isinstance(
            missing, list
        ):
            return False, "BTTS availability is not explicitly reported."
        count = _as_int(counts.get("btts"))
        availability.append("Available" if count > 0 else "Unavailable")
    if not records:
        return False, "No completed live-run BTTS evidence"
    return True, ", ".join(availability)


def _technical_staging_success(summary: Mapping[str, object]) -> bool:
    staging_verdict = _clean(_nested(summary, "staging_validation", "verdict"))
    if staging_verdict == "Ready for handoff":
        return True
    shadow_verdict = _clean(summary.get("verdict"))
    if shadow_verdict != "Needs provider policy review":
        return False
    checksums = _nested(summary, "checksums", default={})
    checksum_ok = isinstance(checksums, Mapping) and all(
        _clean(checksums.get(field)) == "Verified" for field in CHECKSUM_FIELDS
    )
    # Market coverage is judged market-aware, matching staging validation: a
    # market the card excludes (today `total_2_5`, priced at 3.0/3.5 for two
    # fixtures) must not fail an otherwise-clean run. At least one market must
    # still be eligible, and completeness for the eligible scope must be full.
    # Records written before market eligibility existed fall back to the
    # original all-markets requirement.
    eligibility = _nested(summary, "market_eligibility", default=None)
    if isinstance(eligibility, Mapping):
        coverage_ok = bool(eligibility.get("any_market_eligible", False))
    else:
        coverage_ok = _clean(_nested(summary, "market_coverage", "status")) == "Complete"

    return bool(
        checksum_ok
        and _clean(_nested(summary, "raw_evidence", "checksum_status"))
        == "Verified"
        and _clean(_nested(summary, "provider_age", "status")) == "Fresh"
        and _clean(_nested(summary, "team_mapping", "status")) == "Verified"
        and _clean(_nested(summary, "fixture_matching", "status")) == "Verified"
        and coverage_ok
        and (_as_float(_nested(summary, "odds_completeness", "completion_percentage")) or 0.0)
        >= 0.999
    )


def _checksum_check(
    records: Sequence[Mapping[str, object]],
) -> tuple[bool, str]:
    failures: list[str] = []
    for record in records:
        summary = _summary(record)
        label = _clean(record.get("generated_at")) or _clean(record.get("archive_path"))
        statuses = [
            _clean(record.get("archive_integrity_status")),
            _clean(_nested(summary, "raw_evidence", "checksum_status")),
            *[
                _clean(_nested(summary, "checksums", field))
                for field in CHECKSUM_FIELDS
            ],
        ]
        if any(status != "Verified" for status in statuses):
            failures.append(label or "unknown run")
    return not failures and bool(records), (
        "All archive, raw, source, staging, and provenance checksums verified."
        if records and not failures
        else f"Unverified runs: {failures or 'no completed live runs'}"
    )


def _quota_check(
    records: Sequence[Mapping[str, object]],
) -> tuple[bool, str, int]:
    available = 0
    issues: list[str] = []
    for record in records:
        summary = _summary(record)
        quota = _nested(summary, "api_quota", default={})
        if not isinstance(quota, Mapping):
            issues.append("Malformed quota summary")
            continue
        if _clean(quota.get("status")) != "Available":
            continue
        available += 1
        observed_value = False
        for field in ("requests_remaining", "requests_used", "requests_last"):
            value = _clean(quota.get(field))
            if not value:
                continue
            observed_value = True
            numeric = _as_float(value)
            if numeric is None or numeric < 0:
                issues.append(f"{field}={value or 'blank'}")
        if not observed_value:
            issues.append("Quota marked available without a numeric value")
    if issues:
        return False, "; ".join(issues), available
    if available:
        return True, f"Safe non-negative quota headers in {available} run(s).", available
    return True, "Quota headers were explicitly not available.", 0


def _policy_check(
    records: Sequence[Mapping[str, object]],
) -> tuple[bool, bool, str]:
    statuses = [
        _clean(_nested(_summary(record), "provider_policy", "provider_policy_status"))
        for record in records
    ]
    valid = bool(statuses) and all(
        status in {"Provider allowed", "Provider not allowed"} for status in statuses
    )
    stable = len(set(statuses)) == 1 if statuses else False
    latest_allowed = bool(
        records
        and _nested(_summary(records[0]), "provider_policy", "provider_allowed")
        is True
    )
    observed = ", ".join(statuses) if statuses else "No completed live-run policy evidence"
    return valid and stable, latest_allowed, observed


def _unresolved_blockers(
    records: Sequence[Mapping[str, object]],
) -> list[str]:
    unresolved: list[str] = []
    for record in records:
        summary = _summary(record)
        verdict = _clean(summary.get("verdict"))
        if verdict == "Needs provider policy review":
            continue
        blockers = summary.get("blockers", [])
        if isinstance(blockers, list):
            unresolved.extend(_clean(item) for item in blockers if _clean(item))
    return list(dict.fromkeys(unresolved))


def _next_step(verdict: str) -> str:
    return {
        "Ready for human allowlist review": (
            "A person may now review the evidence and policy change separately. "
            "This report does not approve or edit the allowlist."
        ),
        "Needs more shadow runs": "Complete more controlled live shadow runs, then regenerate this checklist.",
        "Needs mapping fixes": "Fix and retest explicit team or fixture mappings before policy review.",
        "Needs market coverage review": "Review bookmaker and 1X2/totals/BTTS coverage without inventing missing odds.",
        "Needs quota review": "Review provider quota headers and request-cost behavior before further automation work.",
        "Needs provider policy review": "Resolve missing, malformed, or changing policy evidence manually.",
        "Not trusted": "Resolve checksum, age, staging, archive-integrity, or blocker failures first.",
    }[verdict]


def build_provider_acceptance_checklist(
    records: Sequence[Mapping[str, object]],
    *,
    provider_name: str,
    minimum_live_runs: int = DEFAULT_MINIMUM_LIVE_RUNS,
    review_window: int = DEFAULT_REVIEW_WINDOW,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if minimum_live_runs < 1:
        raise ValueError("minimum_live_runs must be at least 1.")
    if review_window < minimum_live_runs:
        raise ValueError("review_window must be at least minimum_live_runs.")

    live_records = [record for record in records if _is_live(record)]
    reviewed = live_records[:review_window]
    completed = [record for record in reviewed if _is_completed(record)]
    rows: list[dict[str, object]] = []

    enough_runs = len(completed) >= minimum_live_runs
    _add_check(
        rows,
        "Completed live shadow runs",
        "Pass" if enough_runs else "Fail",
        f"{len(completed)} completed in {len(reviewed)} reviewed live run(s)",
        f"At least {minimum_live_runs}",
        "Dry runs do not count toward provider acceptance evidence.",
    )

    untrusted_runs = [
        _clean(record.get("generated_at")) or _clean(record.get("archive_path"))
        for record in reviewed
        if not bool(record.get("readable"))
        or _clean(record.get("archive_integrity_status")) != "Verified"
        or _clean(_summary(record).get("verdict")) in {"Failed", "Blocked"}
    ]
    trusted_verdicts = not untrusted_runs
    _add_check(
        rows,
        "No failed or untrusted runs",
        "Pass" if trusted_verdicts else "Fail",
        untrusted_runs or "None",
        "No Failed, Blocked, unreadable, or checksum-mismatched live runs",
        "The reviewed live-run window fails closed on untrusted archives.",
    )

    team_ok, team_observed = _coverage_check(completed, "team_mapping")
    _add_check(
        rows,
        "Stable team-name mapping",
        "Pass" if team_ok else "Fail",
        team_observed,
        "Verified and at least 99.9% in every completed run",
        "Coverage must stay complete across the reviewed window.",
    )
    fixture_ok, fixture_observed = _coverage_check(completed, "fixture_matching")
    _add_check(
        rows,
        "Stable fixture matching",
        "Pass" if fixture_ok else "Fail",
        fixture_observed,
        "Verified and at least 99.9% in every completed run",
        "Provider odds and fixtures must continue to identify the same matches.",
    )

    bookmaker_ok, bookmaker_observed = _bookmaker_check(completed)
    _add_check(
        rows,
        "Stable bookmaker coverage",
        "Pass" if bookmaker_ok else "Fail",
        bookmaker_observed,
        "At least one consistent bookmaker set",
        "Bookmaker disappearance or churn requires manual review.",
    )
    one_x_two_ok, one_x_two_observed = _market_check(
        completed,
        market="1x2",
        selections_per_fixture=3,
    )
    _add_check(
        rows,
        "Acceptable 1X2 coverage",
        "Pass" if one_x_two_ok else "Fail",
        one_x_two_observed,
        "Home, draw, and away for each returned fixture",
        "Counts may exceed the minimum when multiple books are returned.",
    )
    totals_ok, totals_observed = _market_check(
        completed,
        market="total_2_5",
        selections_per_fixture=2,
    )
    _add_check(
        rows,
        "Acceptable totals coverage",
        "Pass" if totals_ok else "Fail",
        totals_observed,
        "Over and under 2.5 for each returned fixture",
        "Missing totals are never filled with guessed prices.",
    )
    btts_reported, btts_observed = _btts_reporting_check(completed)
    _add_check(
        rows,
        "BTTS availability explicitly reported",
        "Pass" if btts_reported else "Fail",
        btts_observed,
        "Each run says Available or Unavailable",
        "Unavailable BTTS remains missing; the checklist never fabricates it.",
    )

    staging_successes = sum(
        _technical_staging_success(_summary(record)) for record in completed
    )
    staging_rate = staging_successes / len(completed) if completed else 0.0
    staging_ok = bool(completed) and staging_rate >= 0.999
    _add_check(
        rows,
        "Staging validation success rate",
        "Pass" if staging_ok else "Fail",
        f"{staging_successes}/{len(completed)} ({staging_rate:.1%})",
        "100% technical success",
        "A policy-only block may count as technically successful, but it remains unapproved.",
    )

    fresh_count = sum(
        _clean(_nested(_summary(record), "provider_age", "status")) == "Fresh"
        for record in completed
    )
    age_ok = bool(completed) and fresh_count == len(completed)
    _add_check(
        rows,
        "Provider age and freshness",
        "Pass" if age_ok else "Fail",
        f"{fresh_count}/{len(completed)} Fresh",
        "Fresh in every completed run",
        "Old or future-dated provider evidence is not acceptance evidence.",
    )

    checksum_ok, checksum_observed = _checksum_check(completed)
    _add_check(
        rows,
        "Checksum and provenance proof",
        "Pass" if checksum_ok else "Fail",
        checksum_observed,
        "All archive/raw/source/staging/provenance checks Verified",
        "A mismatch or unavailable checksum fails closed.",
    )

    quota_ok, quota_observed, quota_available_count = _quota_check(completed)
    _add_check(
        rows,
        "Quota and safe header behavior",
        "Pass" if quota_ok else "Needs review",
        quota_observed,
        "Available quota values are numeric and non-negative",
        "Missing optional quota headers are reported, not guessed.",
    )

    policy_ok, latest_allowed, policy_observed = _policy_check(completed)
    policy_status = "Pass" if policy_ok and latest_allowed else (
        "Pending human review" if policy_ok else "Needs review"
    )
    _add_check(
        rows,
        "Provider policy state",
        policy_status,
        policy_observed,
        "Stable, readable policy evidence",
        "Provider not allowed is expected before human review and is never changed here.",
    )

    unresolved = _unresolved_blockers(completed)
    blocker_ok = not unresolved
    _add_check(
        rows,
        "No unresolved blockers",
        "Pass" if blocker_ok else "Fail",
        unresolved or "None",
        "No non-policy blockers",
        "Policy-only pending blockers are separated from technical blockers.",
    )

    latest_pair_changes: list[str] = []
    if len(completed) >= 2:
        pair_rows = build_provider_shadow_comparison_rows(completed[1], completed[0])
        latest_pair_changes = pair_rows.loc[
            pair_rows["change_status"] == "Changed", "metric"
        ].astype(str).tolist()

    critical_trust_failure = not trusted_verdicts or (
        bool(completed) and (not checksum_ok or not age_ok)
    )
    market_failure = not all(
        (bookmaker_ok, one_x_two_ok, totals_ok, btts_reported)
    ) or any(
        _clean(_summary(record).get("verdict"))
        == "Needs market coverage review"
        for record in completed
    )
    if critical_trust_failure:
        verdict = "Not trusted"
    elif not enough_runs:
        verdict = "Needs more shadow runs"
    elif not team_ok or not fixture_ok:
        verdict = "Needs mapping fixes"
    elif market_failure:
        verdict = "Needs market coverage review"
    elif not quota_ok:
        verdict = "Needs quota review"
    elif not policy_ok:
        verdict = "Needs provider policy review"
    elif not staging_ok or not blocker_ok:
        verdict = "Not trusted"
    else:
        verdict = "Ready for human allowlist review"
    if verdict not in ACCEPTANCE_VERDICTS:
        raise ValueError(f"Unexpected provider acceptance verdict: {verdict}")

    provider_display = _clean(
        _summary(completed[0]).get("provider_name") if completed else ""
    ) or provider_name
    checks = pd.DataFrame(rows, columns=CHECKLIST_COLUMNS)
    summary: dict[str, object] = {
        "generated_at": (run_at or datetime.now().astimezone()).isoformat(
            timespec="seconds"
        ),
        "provider_key": _clean(
            _summary(completed[0]).get("provider_key") if completed else ""
        )
        or provider_name,
        "provider_name": provider_display,
        "verdict": verdict,
        "next_step": _next_step(verdict),
        "minimum_live_runs": minimum_live_runs,
        "review_window": review_window,
        "archived_run_count": len(records),
        "live_run_count": len(live_records),
        "reviewed_live_run_count": len(reviewed),
        "completed_live_run_count": len(completed),
        "quota_header_run_count": quota_available_count,
        "provider_currently_allowed": latest_allowed,
        "latest_pair_changed_metrics": latest_pair_changes,
        "reviewed_runs": [
            {
                "generated_at": _clean(record.get("generated_at")),
                "archive_path": _clean(record.get("archive_path")),
                "archive_integrity_status": _clean(
                    record.get("archive_integrity_status")
                ),
                "provider_run_status": _clean(
                    _nested(_summary(record), "provider_run", "status")
                ),
                "shadow_verdict": _clean(_summary(record).get("verdict")),
                "staging_verdict": _clean(
                    _nested(_summary(record), "staging_validation", "verdict")
                ),
            }
            for record in reviewed
        ],
        "checklist": checks.to_dict(orient="records"),
        "safety": {
            "read_only": True,
            "provider_policy_edited": False,
            "provider_allowlisted": False,
            "staging_promoted": False,
            "cron_enabled": False,
            "bets_placed": False,
        },
    }
    return checks, summary


def render_provider_acceptance_checklist(
    checks: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    reviewed = summary.get("reviewed_runs", [])
    reviewed_frame = pd.DataFrame(reviewed)
    reviewed_table = (
        reviewed_frame.to_markdown(index=False)
        if not reviewed_frame.empty
        else "No live shadow runs are archived yet."
    )
    lines = [
        "# Provider Acceptance Checklist",
        "",
        "This is a read-only evidence checklist. It does not allowlist a "
        "provider, edit policy, promote staging, enable cron, generate trusted "
        "picks, or place bets.",
        "",
        "## Verdict",
        "",
        f"- **{summary['verdict']}**",
        f"- Provider: **{summary['provider_name']}** (`{summary['provider_key']}`)",
        f"- Next step: {summary['next_step']}",
        f"- Completed live runs: **{summary['completed_live_run_count']}** (minimum {summary['minimum_live_runs']})",
        f"- Review window: latest **{summary['review_window']}** live runs",
        f"- Provider currently allowed: **{'Yes' if summary['provider_currently_allowed'] else 'No'}**",
        "",
        "## Checklist",
        "",
        checks.to_markdown(index=False),
        "",
        "## Reviewed live runs",
        "",
        reviewed_table,
        "",
        "## Human decision boundary",
        "",
        "- `Ready for human allowlist review` means the evidence can be reviewed by a person; it is not approval.",
        "- Any allowlist edit remains a separate, explicit manual change to staging_provider_policy.json.",
        "- Cron remains disabled until provider ownership, failure handling, "
        "credentials, and repeated live evidence are approved separately.",
        "- Missing BTTS or any other market remains missing. No odds are fabricated.",
        "",
        "## Verdict meanings",
        "",
        "- **Ready for human allowlist review:** minimum evidence and technical stability requirements passed.",
        "- **Needs more shadow runs:** too few completed live runs exist.",
        "- **Needs mapping fixes:** team or fixture matching is incomplete or unstable.",
        "- **Needs market coverage review:** bookmaker, 1X2, totals, BTTS reporting, or coverage needs review.",
        "- **Needs quota review:** available safe quota headers are malformed or unacceptable.",
        "- **Needs provider policy review:** policy evidence is missing, malformed, or changed.",
        "- **Not trusted:** archive, checksum, age, staging, or unresolved blocker evidence failed.",
        "",
        "No provider was allowlisted and cron remains disabled.",
    ]
    return "\n".join(lines)


def save_provider_acceptance_checklist(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    minimum_live_runs: int = DEFAULT_MINIMUM_LIVE_RUNS,
    review_window: int = DEFAULT_REVIEW_WINDOW,
    run_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    records = load_provider_shadow_run_history(
        outputs,
        provider_name=provider_name,
    )
    checks, summary = build_provider_acceptance_checklist(
        records,
        provider_name=provider_name,
        minimum_live_runs=minimum_live_runs,
        review_window=review_window,
        run_at=run_at,
    )
    json_path = outputs / ACCEPTANCE_JSON_FILENAME
    markdown_path = outputs / ACCEPTANCE_MARKDOWN_FILENAME
    csv_path = outputs / ACCEPTANCE_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        render_provider_acceptance_checklist(checks, summary).encode("utf-8"),
    )
    atomic_write_report(
        csv_path,
        checks.to_csv(index=False, lineterminator="\n").encode("utf-8"),
    )
    return {
        "summary": summary,
        "checklist": checks,
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
    }
