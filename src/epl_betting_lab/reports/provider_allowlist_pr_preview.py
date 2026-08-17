from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from difflib import unified_diff
import json
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import (
    OUTPUTS_DIR,
    PROJECT_ROOT,
    STAGING_PROVIDER_POLICY_PATH,
)
from epl_betting_lab.providers.base import (
    atomic_write_report,
    file_sha256,
    path_contains_symlink,
)
from epl_betting_lab.providers.provider_registry import create_provider
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    APPROVAL_DECISION,
    READY_VERDICT,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt_verification import (
    VERIFICATION_JSON_FILENAME,
)
from epl_betting_lab.staging_provider_policy import load_staging_provider_policy


PREVIEW_JSON_FILENAME = "provider_allowlist_pr_preview.json"
PREVIEW_MARKDOWN_FILENAME = "provider_allowlist_pr_preview.md"
PREVIEW_CSV_FILENAME = "provider_allowlist_pr_preview.csv"
REQUIRED_VERIFICATION_VERDICT = "Verified for allowlist PR review"
READY_STATUS = "Ready for separate allowlist PR"
BLOCKED_STATUS = "Blocked"
NO_CHANGE_STATUS = "No policy change needed"
PREVIEW_COLUMNS = (
    "category",
    "field",
    "before",
    "after",
    "change",
    "status",
    "details",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MARKET_NAMES = {
    "h2h": "1x2",
    "totals": "total_2_5",
    "btts": "btts",
}


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _slug(value: object) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", _clean(value).casefold()).strip("_")
    return slug or "unknown_provider"


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repository_root).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _resolve_json_path(
    value: Path | str,
    *,
    repository_root: Path,
    label: str,
) -> tuple[Path, str]:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else repository_root / raw
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(repository_root)
    except (OSError, RuntimeError, ValueError):
        return candidate, f"{label} must stay inside the repository."
    if resolved.suffix.lower() != ".json":
        return resolved, f"{label} must be a JSON file."
    if path_contains_symlink(candidate.absolute(), repository_root):
        return resolved, f"{label} cannot use a symbolic link."
    if not resolved.exists():
        return resolved, f"{label} is missing: `{_display_path(resolved, repository_root)}`."
    if not resolved.is_file() or resolved.is_symlink():
        return resolved, f"{label} must be a regular, non-symlinked file."
    return resolved, ""


def _read_json_object(path: Path, label: str) -> tuple[dict[str, object] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{label} is unreadable or malformed: {exc}"
    if not isinstance(payload, dict):
        return None, f"{label} must contain one JSON object."
    return payload, ""


def _parse_timestamp(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _find_verification_check(
    verification: Mapping[str, object],
    check_name: str,
) -> Mapping[str, object] | None:
    checks = verification.get("checks", [])
    if not isinstance(checks, list):
        return None
    for item in checks:
        if isinstance(item, Mapping) and _clean(item.get("check")) == check_name:
            return item
    return None


def _eligible_markets_from_evidence(output_dir: Path | None = None) -> list[str]:
    """Markets the reviewed evidence found eligible, if any.

    The adapter's `featured_markets_requested` describes what the *bulk*
    endpoint asks for, which is not the same as what the card may use: BTTS now
    arrives from the per-event endpoint, and totals is excluded while it covers
    only 8 of 10 fixtures. Allowlisting the adapter's request list would grant
    totals and omit BTTS - the opposite of what was reviewed.
    """
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    path = outputs / "automated_card_input.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(payload, Mapping):
        return []
    eligibility = payload.get("eligibility")
    if not isinstance(eligibility, Mapping):
        return []
    markets = eligibility.get("eligible_markets")
    if not isinstance(markets, list):
        return []
    return [str(item).strip().lower() for item in markets if str(item).strip()]


def _provider_markets_and_limitations(
    provider: object,
    output_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    eligible = _eligible_markets_from_evidence(output_dir)
    if eligible:
        limitations: list[str] = []
        for market in ("1x2", "total_2_5", "btts"):
            if market not in eligible:
                limitations.append(
                    f"`{market}` is not allowlisted: the reviewed evidence did "
                    "not find it eligible. Its prices remain unavailable or "
                    "incomplete and must never be fabricated."
                )
        limitations.append(
            "Allowlisting does not bypass staging validation, freshness, "
            "completeness, checksum, receipt, or Thursday cutoff gates."
        )
        return list(dict.fromkeys(eligible)), limitations

    configuration = provider.public_configuration()
    featured = configuration.get("featured_markets_requested", [])
    if isinstance(featured, list):
        markets = [
            MARKET_NAMES[item]
            for item in featured
            if isinstance(item, str) and item in MARKET_NAMES
        ]
    else:
        markets = []
    if not markets:
        markets = ["1x2", "total_2_5", "btts"]
    markets = list(dict.fromkeys(markets))
    limitations: list[str] = []
    if "btts" not in markets:
        limitations.append(
            "BTTS is not requested by the current provider adapter. Missing BTTS "
            "prices remain unavailable and must never be fabricated."
        )
    limitations.append(
        "Allowlisting does not bypass staging validation, freshness, completeness, "
        "checksum, receipt, or Thursday cutoff gates."
    )
    return markets, limitations


def _value(value: object) -> str:
    if isinstance(value, (dict, list, tuple, bool)) or value is None:
        return json.dumps(value, sort_keys=True)
    return str(value)


def _add_row(
    rows: list[dict[str, object]],
    *,
    category: str,
    field: str,
    before: object = "",
    after: object = "",
    change: str,
    status: str,
    details: str,
) -> None:
    rows.append(
        {
            "category": category,
            "field": field,
            "before": _value(before),
            "after": _value(after),
            "change": change,
            "status": status,
            "details": details,
        }
    )


def _policy_diff(before: Mapping[str, object], after: Mapping[str, object]) -> str:
    before_lines = json.dumps(before, indent=2, sort_keys=True).splitlines()
    after_lines = json.dumps(after, indent=2, sort_keys=True).splitlines()
    return "\n".join(
        unified_diff(
            before_lines,
            after_lines,
            fromfile="data/manual/staging_provider_policy.json (current)",
            tofile="data/manual/staging_provider_policy.json (proposed)",
            lineterm="",
        )
    )


def _recommended_pr(
    provider_name: str,
    provider_type: str,
    receipt_id: str,
    required_markets: list[str],
    limitations: list[str],
) -> tuple[str, str]:
    title = f"Allowlist {provider_name} staging provider"
    market_text = ", ".join(required_markets)
    limitation_text = " ".join(limitations)
    description = (
        f"Adds `{provider_name}` (`{provider_type}`) to the reviewed staging "
        f"provider allowlist for {market_text}. Binds the policy entry to human "
        f"acceptance receipt `{receipt_id}` and its verified evidence. "
        f"Known limitations: {limitation_text} This policy-only proposal does not "
        "promote staging, run a provider, generate picks, place bets, or enable cron."
    )
    return title, description


def build_provider_allowlist_pr_preview(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    verification_path: Path | None = None,
    policy_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    root = (repository_root or PROJECT_ROOT).resolve()
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    selected_verification = verification_path or outputs / VERIFICATION_JSON_FILENAME
    selected_policy = policy_path or STAGING_PROVIDER_POLICY_PATH
    provider = create_provider(provider_name)
    provider_key = provider.provider_key
    canonical_name = provider.provider_name
    provider_type = provider.provider_type
    required_markets, limitations = _provider_markets_and_limitations(
        provider, output_dir
    )
    blockers: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, object]] = []

    verification_file, path_error = _resolve_json_path(
        selected_verification,
        repository_root=root,
        label="Receipt verification report",
    )
    verification: dict[str, object] | None = None
    verification_checksum = ""
    if path_error:
        blockers.append(path_error)
    else:
        verification, read_error = _read_json_object(
            verification_file,
            "Receipt verification report",
        )
        if read_error:
            blockers.append(read_error)
        else:
            try:
                verification_checksum = file_sha256(verification_file)
            except OSError as exc:
                blockers.append(f"Receipt verification report could not be hashed: {exc}")

    verification_verdict = _clean(
        verification.get("verdict") if verification else ""
    )
    if verification_verdict != REQUIRED_VERIFICATION_VERDICT:
        blockers.append(
            "Receipt verification must be `Verified for allowlist PR review`; "
            f"current verdict is `{verification_verdict or 'missing'}`."
        )
    verification_provider = _clean(
        verification.get("provider_key") if verification else ""
    )
    if verification and _slug(verification_provider) != _slug(provider_key):
        blockers.append(
            f"Receipt verification belongs to `{verification_provider or 'unknown'}`, "
            f"not `{provider_key}`."
        )
    checks = verification.get("checks", []) if verification else []
    if not isinstance(checks, list) or not checks:
        blockers.append("Receipt verification has no structured verification checks.")
    elif any(
        not isinstance(item, Mapping) or _clean(item.get("status")) != "Verified"
        for item in checks
    ):
        blockers.append("Receipt verification contains one or more non-Verified checks.")

    receipt_id = _clean(verification.get("receipt_id") if verification else "")
    reviewer_name = _clean(
        verification.get("reviewer_name") if verification else ""
    )
    decision = _clean(verification.get("decision") if verification else "")
    approved_at = _clean(
        verification.get("receipt_created_at") if verification else ""
    )
    reviewed_at = _clean(verification.get("generated_at") if verification else "")
    if not receipt_id:
        blockers.append("Receipt verification is missing the evidence receipt ID.")
    if not reviewer_name:
        blockers.append("Receipt verification is missing the reviewer name.")
    if decision != APPROVAL_DECISION:
        blockers.append("The bound human receipt decision is not approval.")
    if _clean(verification.get("checklist_verdict") if verification else "") != READY_VERDICT:
        blockers.append("The bound provider acceptance checklist was not ready.")
    if _parse_timestamp(approved_at) is None:
        blockers.append("The receipt approval timestamp is missing or invalid.")
    if _parse_timestamp(reviewed_at) is None:
        blockers.append("The verification review timestamp is missing or invalid.")

    receipt: dict[str, object] | None = None
    receipt_file: Path | None = None
    expected_receipt_checksum = _clean(
        verification.get("receipt_checksum_sha256") if verification else ""
    )
    receipt_reference = _clean(
        verification.get("receipt_path") if verification else ""
    )
    if not receipt_reference or not SHA256_PATTERN.fullmatch(expected_receipt_checksum):
        blockers.append("Receipt verification does not contain a bound receipt path and SHA-256.")
    else:
        receipt_file, receipt_path_error = _resolve_json_path(
            receipt_reference,
            repository_root=root,
            label="Human acceptance receipt",
        )
        if receipt_path_error:
            blockers.append(receipt_path_error)
        else:
            receipt, receipt_error = _read_json_object(
                receipt_file,
                "Human acceptance receipt",
            )
            if receipt_error:
                blockers.append(receipt_error)
            else:
                try:
                    current_receipt_checksum = file_sha256(receipt_file)
                except OSError as exc:
                    blockers.append(f"Human acceptance receipt could not be hashed: {exc}")
                    current_receipt_checksum = ""
                if (
                    current_receipt_checksum
                    and current_receipt_checksum != expected_receipt_checksum
                ):
                    blockers.append(
                        "The human acceptance receipt changed after verification. "
                        "Rerun receipt verification before creating this preview."
                    )

    if receipt:
        if _clean(receipt.get("receipt_id")) != receipt_id:
            blockers.append("Receipt ID does not match the verification report.")
        if _clean(receipt.get("reviewer_name")) != reviewer_name:
            blockers.append("Receipt reviewer does not match the verification report.")
        if _clean(receipt.get("decision")) != APPROVAL_DECISION:
            blockers.append("The current receipt does not approve an allowlist PR.")
        if _clean(receipt.get("created_at")) != approved_at:
            blockers.append("Receipt approval time does not match the verification report.")
        gate = receipt.get("approval_gate", {})
        if not isinstance(gate, Mapping) or _clean(gate.get("status")) != "Passed":
            blockers.append("The receipt approval gate did not pass without override.")
        elif gate.get("override_used") is True:
            blockers.append("An overridden approval receipt cannot support this preview.")

    policy_request = Path(selected_policy)
    policy_file = (
        policy_request
        if policy_request.is_absolute()
        else root / policy_request
    ).resolve(strict=False)
    policy_status = load_staging_provider_policy(
        policy_file,
        repository_root=root,
    )
    blockers.extend(str(item) for item in policy_status.get("blockers", []))
    before_policy: dict[str, object] = {}
    if policy_status.get("valid") is True:
        before_policy, policy_read_error = _read_json_object(
            policy_file,
            "Staging provider policy",
        )
        if policy_read_error:
            blockers.append(policy_read_error)
            before_policy = {}

    current_policy_checksum = _clean(policy_status.get("checksum_sha256"))
    policy_evidence: Mapping[str, object] = {}
    if receipt:
        evidence = receipt.get("evidence", {})
        if isinstance(evidence, Mapping):
            candidate = evidence.get("provider_policy", {})
            if isinstance(candidate, Mapping):
                policy_evidence = candidate
    if _clean(policy_evidence.get("status")) != "Bound":
        blockers.append("The human receipt did not bind the provider policy.")
    else:
        bound_policy_checksum = _clean(policy_evidence.get("checksum_sha256"))
        bound_policy_reference = _clean(policy_evidence.get("path"))
        if bound_policy_checksum != current_policy_checksum:
            blockers.append(
                "The provider policy changed after human approval. Rerun the "
                "checklist, receipt, and receipt verification."
            )
        bound_policy_file, bound_path_error = _resolve_json_path(
            bound_policy_reference,
            repository_root=root,
            label="Receipt-bound provider policy",
        )
        if bound_path_error:
            blockers.append(bound_path_error)
        elif bound_policy_file != policy_file:
            blockers.append("The selected policy path differs from the receipt-bound policy.")

    policy_check = (
        _find_verification_check(verification, "Provider policy checksum")
        if verification
        else None
    )
    if policy_check is None:
        blockers.append("Receipt verification did not check the provider policy checksum.")
    elif (
        _clean(policy_check.get("status")) != "Verified"
        or _clean(policy_check.get("observed")) != current_policy_checksum
        or _clean(policy_check.get("expected")) != current_policy_checksum
    ):
        blockers.append(
            "The current provider policy does not match the checksum verified by "
            "the receipt verification report."
        )

    allowed_names = [
        _clean(item) for item in policy_status.get("allowed_provider_names", [])
    ]
    already_allowed = canonical_name.casefold() in {
        item.casefold() for item in allowed_names
    }
    entries_present = "provider_allowlist_entries" in before_policy
    existing_entries = before_policy.get("provider_allowlist_entries", {})
    if entries_present and not isinstance(existing_entries, dict):
        blockers.append("`provider_allowlist_entries` must be a JSON object.")
        existing_entries = {}
    existing_entry = (
        existing_entries.get(canonical_name)
        if isinstance(existing_entries, dict)
        else None
    )
    if existing_entry is not None and not already_allowed:
        blockers.append(
            "Provider policy already has conflicting metadata for this provider; "
            "review it manually before proposing an allowlist change."
        )

    blockers = list(dict.fromkeys(item for item in blockers if item))
    generated_at = (run_at or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    proposed_entry: dict[str, object] = {}
    after_policy = deepcopy(before_policy)
    recommended_title = ""
    recommended_description = ""
    if already_allowed and not blockers:
        status = NO_CHANGE_STATUS
        warnings.append(
            f"`{canonical_name}` is already in `allowed_provider_names`; no new "
            "allowlist PR should be opened from this preview."
        )
    elif blockers:
        status = BLOCKED_STATUS
        after_policy = deepcopy(before_policy)
    else:
        status = READY_STATUS
        proposed_entry = {
            "provider_key": provider_key,
            "provider_name": canonical_name,
            "provider_type": provider_type,
            "allowlist_status": "allowed",
            "max_provider_run_age_hours": policy_status.get(
                "max_provider_run_age_hours"
            ),
            "cutoff_policy": {
                "day": "Thursday",
                "time": policy_status.get("thursday_cutoff_time"),
                "timezone": policy_status.get("timezone"),
            },
            "required_markets": required_markets,
            "known_limitations": limitations,
            "evidence_receipt_id": receipt_id,
            "verification_report_path": _display_path(verification_file, root),
            "verification_report_checksum_sha256": verification_checksum,
            "reviewer_name": reviewer_name,
            "reviewed_at": reviewed_at,
            "approved_at": approved_at,
        }
        proposed_names = list(allowed_names)
        proposed_names.append(canonical_name)
        after_policy["allowed_provider_names"] = proposed_names
        allowed_types = [
            _clean(item) for item in policy_status.get("allowed_provider_types", [])
        ]
        if provider_type not in allowed_types:
            allowed_types.append(provider_type)
        after_policy["allowed_provider_types"] = allowed_types
        proposed_entries = dict(existing_entries)
        proposed_entries[canonical_name] = proposed_entry
        after_policy["provider_allowlist_entries"] = proposed_entries
        recommended_title, recommended_description = _recommended_pr(
            canonical_name,
            provider_type,
            receipt_id,
            required_markets,
            limitations,
        )

    _add_row(
        rows,
        category="Evidence",
        field="receipt_verification_verdict",
        before=verification_verdict or "Missing",
        after=REQUIRED_VERIFICATION_VERDICT,
        change="Required gate",
        status="Verified" if verification_verdict == REQUIRED_VERIFICATION_VERDICT else "Blocked",
        details="An existing verified receipt report is required; this preview does not rerun it.",
    )
    _add_row(
        rows,
        category="Evidence",
        field="verification_report_checksum_sha256",
        before=verification_checksum or "Missing",
        after=verification_checksum or "Missing",
        change="Bound evidence",
        status="Verified" if verification_checksum else "Blocked",
        details="The proposed policy entry binds the exact verification report bytes.",
    )
    _add_row(
        rows,
        category="Policy",
        field="allowed_provider_names",
        before=before_policy.get("allowed_provider_names", []),
        after=after_policy.get("allowed_provider_names", []),
        change="Add provider name" if status == READY_STATUS else "No applied change",
        status=status,
        details=f"Proposed canonical provider name: `{canonical_name}`.",
    )
    _add_row(
        rows,
        category="Policy",
        field="allowed_provider_types",
        before=before_policy.get("allowed_provider_types", []),
        after=after_policy.get("allowed_provider_types", []),
        change=(
            "Ensure provider type is allowed"
            if status == READY_STATUS
            else "No applied change"
        ),
        status=status,
        details=f"Provider type: `{provider_type}`.",
    )
    for field, value in proposed_entry.items():
        _add_row(
            rows,
            category="Provider controls",
            field=f"provider_allowlist_entries.{canonical_name}.{field}",
            before="Not present",
            after=value,
            change="Add reviewed provider control",
            status=status,
            details="This field is proposed only and was not written to policy.",
        )

    policy_diff = (
        _policy_diff(before_policy, after_policy) if status == READY_STATUS else ""
    )
    summary: dict[str, object] = {
        "schema_version": 1,
        "generated_at": generated_at,
        "status": status,
        "provider_key": provider_key,
        "provider_name": canonical_name,
        "provider_type": provider_type,
        "current_allowlist_status": "Allowed" if already_allowed else "Not allowed",
        "proposed_allowlist_status": "Allowed" if status == READY_STATUS else "Not proposed",
        "verification": {
            "path": _display_path(verification_file, root),
            "checksum_sha256": verification_checksum,
            "verdict": verification_verdict or "Missing",
            "receipt_path": (
                _display_path(receipt_file, root) if receipt_file else receipt_reference
            ),
            "receipt_checksum_sha256": expected_receipt_checksum,
            "receipt_id": receipt_id,
            "reviewer_name": reviewer_name,
            "reviewed_at": reviewed_at,
            "approved_at": approved_at,
        },
        "policy": {
            "path": _display_path(policy_file, root),
            "checksum_sha256": current_policy_checksum,
            "max_provider_run_age_hours": policy_status.get(
                "max_provider_run_age_hours"
            ),
            "cutoff_policy": {
                "day": "Thursday",
                "time": policy_status.get("thursday_cutoff_time"),
                "timezone": policy_status.get("timezone"),
            },
        },
        "proposed_provider_entry": proposed_entry,
        "before_policy": before_policy,
        "after_policy": after_policy,
        "policy_diff": policy_diff,
        "blockers": blockers,
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_pr_title": recommended_title,
        "recommended_pr_description": recommended_description,
        "rows": rows,
        "safety": {
            "preview_only": True,
            "provider_policy_edited": False,
            "provider_allowlisted": False,
            "receipt_created": False,
            "receipt_verified_by_side_effect": False,
            "staging_promoted": False,
            "provider_run": False,
            "cron_enabled": False,
            "protected_files_edited": False,
            "picks_generated": False,
            "bets_placed": False,
        },
    }
    return pd.DataFrame(rows, columns=PREVIEW_COLUMNS), summary


def render_provider_allowlist_pr_preview(
    changes: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    blockers = summary.get("blockers", [])
    warnings = summary.get("warnings", [])
    verification = summary.get("verification", {})
    policy = summary.get("policy", {})
    proposed = summary.get("proposed_provider_entry", {})
    lines = [
        "# Provider Allowlist PR Readiness Preview",
        "",
        "**Preview only: nothing was applied.** This report does not edit "
        "`staging_provider_policy.json`, allowlist a provider, promote staging, "
        "run a provider, generate picks, place bets, or enable cron.",
        "",
        "## Status",
        "",
        f"- **{summary.get('status', BLOCKED_STATUS)}**",
        f"- Provider: `{summary.get('provider_name', '')}` "
        f"(`{summary.get('provider_type', '')}`)",
        f"- Current allowlist status: **{summary.get('current_allowlist_status', '')}**",
        f"- Proposed allowlist status: **{summary.get('proposed_allowlist_status', '')}**",
        "",
        "## Evidence used",
        "",
        f"- Verification verdict: **{verification.get('verdict', 'Missing')}**",
        f"- Verification report: `{verification.get('path', '')}`",
        f"- Verification SHA-256: `{verification.get('checksum_sha256', '') or 'Missing'}`",
        f"- Human receipt ID: `{verification.get('receipt_id', '') or 'Missing'}`",
        f"- Reviewer: **{verification.get('reviewer_name', '') or 'Missing'}**",
        f"- Reviewed at: {verification.get('reviewed_at', '') or 'Missing'}",
        f"- Approved at: {verification.get('approved_at', '') or 'Missing'}",
        f"- Current policy: `{policy.get('path', '')}`",
        f"- Current policy SHA-256: `{policy.get('checksum_sha256', '') or 'Missing'}`",
        "",
        "## Blockers",
        "",
        *(f"- {item}" for item in blockers),
    ]
    if not blockers:
        lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in warnings)
    if not warnings:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Exact proposed provider fields",
            "",
            "```json",
            json.dumps(proposed, indent=2, sort_keys=True),
            "```",
            "",
            "## Change table",
            "",
            changes.to_markdown(index=False),
            "",
            "## Current policy",
            "",
            "```json",
            json.dumps(summary.get("before_policy", {}), indent=2, sort_keys=True),
            "```",
            "",
            "## Proposed policy",
            "",
            "```json",
            json.dumps(summary.get("after_policy", {}), indent=2, sort_keys=True),
            "```",
            "",
            "## Diff preview",
            "",
            "```diff",
            _clean(summary.get("policy_diff")) or "No policy diff is available.",
            "```",
            "",
            "## Recommended separate PR",
            "",
            f"- Title: {summary.get('recommended_pr_title', '') or 'Not available while blocked'}",
            "- Description:",
            "",
            _clean(summary.get("recommended_pr_description"))
            or "Fix the blockers and regenerate this preview before opening a PR.",
            "",
            "## Decision boundary",
            "",
            "A Ready preview is evidence for a separate human-reviewed policy PR. "
            "It is not an apply command and does not make the provider eligible by "
            "itself. Cron remains disabled and requires another separate decision.",
        ]
    )
    return "\n".join(lines)


def save_provider_allowlist_pr_preview(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    verification_path: Path | None = None,
    policy_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    changes, summary = build_provider_allowlist_pr_preview(
        provider_name,
        outputs,
        verification_path=verification_path,
        policy_path=policy_path,
        repository_root=repository_root,
        run_at=run_at,
    )
    json_path = outputs / PREVIEW_JSON_FILENAME
    markdown_path = outputs / PREVIEW_MARKDOWN_FILENAME
    csv_path = outputs / PREVIEW_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        render_provider_allowlist_pr_preview(changes, summary).encode("utf-8"),
    )
    atomic_write_report(
        csv_path,
        changes.to_csv(index=False, lineterminator="\n").encode("utf-8"),
    )
    return {
        "summary": summary,
        "changes": changes,
        "status": summary["status"],
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
    }
