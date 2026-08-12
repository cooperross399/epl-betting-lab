from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
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
from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    PREVIEW_JSON_FILENAME,
    READY_STATUS,
)


CONFORMANCE_JSON_FILENAME = "provider_allowlist_pr_conformance.json"
CONFORMANCE_MARKDOWN_FILENAME = "provider_allowlist_pr_conformance.md"
CONFORMANCE_CSV_FILENAME = "provider_allowlist_pr_conformance.csv"

CONFORMS_VERDICT = "Conforms to preview"
DOES_NOT_CONFORM_VERDICT = "Does not conform"
MISSING_PREVIEW_VERDICT = "Missing preview evidence"
MALFORMED_POLICY_VERDICT = "Malformed policy"
UNSAFE_AUTOMATION_VERDICT = "Unsafe automation change detected"

MATCH_STATUS = "Match"
MISSING_FIELD_STATUS = "Missing field"
VALUE_MISMATCH_STATUS = "Value mismatch"
UNEXPECTED_EDIT_STATUS = "Unexpected policy edit"
PREVIEW_NOT_VERIFIED_STATUS = "Preview not verified"
MISSING_PREVIEW_STATUS = "Missing preview"
MALFORMED_POLICY_STATUS = "Malformed policy"
UNSAFE_AUTOMATION_STATUS = "Unsafe automation change"

CHECK_COLUMNS = (
    "category",
    "field",
    "baseline",
    "expected",
    "actual",
    "status",
    "details",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MISSING = object()
REQUIRED_PROPOSED_FIELD_PATHS = (
    ("provider_key",),
    ("provider_name",),
    ("provider_type",),
    ("allowlist_status",),
    ("max_provider_run_age_hours",),
    ("cutoff_policy", "day"),
    ("cutoff_policy", "time"),
    ("cutoff_policy", "timezone"),
    ("required_markets",),
    ("known_limitations",),
    ("evidence_receipt_id",),
    ("verification_report_path",),
    ("verification_report_checksum_sha256",),
    ("reviewer_name",),
    ("reviewed_at",),
    ("approved_at",),
)
_DISABLED_AUTOMATION_VALUES = {
    "",
    "0",
    "disabled",
    "false",
    "manual",
    "manual_only",
    "no",
    "none",
    "not_enabled",
    "null",
    "off",
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


def _value(value: object) -> str:
    if value is _MISSING:
        return "Missing"
    if isinstance(value, (dict, list, tuple, bool)) or value is None:
        return json.dumps(value, sort_keys=True)
    return str(value)


def _add_check(
    rows: list[dict[str, object]],
    *,
    category: str,
    field: str,
    baseline: object = "",
    expected: object = "",
    actual: object = "",
    status: str,
    details: str,
) -> None:
    rows.append(
        {
            "category": category,
            "field": field,
            "baseline": _value(baseline),
            "expected": _value(expected),
            "actual": _value(actual),
            "status": status,
            "details": details,
        }
    )


def _lookup_path(payload: object, path: tuple[str, ...]) -> object:
    current = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _leaf_paths(value: object, prefix: tuple[str, ...]) -> set[tuple[str, ...]]:
    if isinstance(value, Mapping) and value:
        paths: set[tuple[str, ...]] = set()
        for key, child in value.items():
            paths.update(_leaf_paths(child, (*prefix, str(key))))
        return paths
    return {prefix}


def _different_leaf_paths(
    expected: object,
    actual: object,
    prefix: tuple[str, ...] = (),
) -> set[tuple[str, ...]]:
    if expected is _MISSING:
        return _leaf_paths(actual, prefix)
    if actual is _MISSING:
        return _leaf_paths(expected, prefix)
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        paths: set[tuple[str, ...]] = set()
        for key in set(expected) | set(actual):
            paths.update(
                _different_leaf_paths(
                    expected.get(key, _MISSING),
                    actual.get(key, _MISSING),
                    (*prefix, str(key)),
                )
            )
        return paths
    return set() if expected == actual else {prefix}


def _path_is_expected_change(
    path: tuple[str, ...],
    expected_changes: set[tuple[str, ...]],
) -> bool:
    return any(
        path == changed
        or path[: len(changed)] == changed
        or changed[: len(path)] == path
        for changed in expected_changes
    )


def _policy_diff(
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    *,
    expected_label: str,
    actual_label: str,
) -> str:
    expected_lines = json.dumps(expected, indent=2, sort_keys=True).splitlines()
    actual_lines = json.dumps(actual, indent=2, sort_keys=True).splitlines()
    return "\n".join(
        unified_diff(
            expected_lines,
            actual_lines,
            fromfile=expected_label,
            tofile=actual_label,
            lineterm="",
        )
    )


def _is_automation_path(path: tuple[str, ...]) -> bool:
    tokens = [
        token
        for part in path
        for token in re.split(r"[^a-z0-9]+", part.casefold())
        if token
    ]
    return any(
        token.startswith("cron")
        or token.startswith("automat")
        or token.startswith("schedul")
        for token in tokens
    )


def _looks_enabled(value: object) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().casefold() not in _DISABLED_AUTOMATION_VALUES
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _format_path(path: tuple[str, ...]) -> str:
    return ".".join(path) or "policy"


def build_provider_allowlist_pr_conformance(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    preview_path: Path | None = None,
    policy_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    root = (repository_root or PROJECT_ROOT).resolve()
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    selected_preview = preview_path or outputs / PREVIEW_JSON_FILENAME
    selected_policy = policy_path or STAGING_PROVIDER_POLICY_PATH
    provider = create_provider(provider_name)
    provider_key = provider.provider_key
    canonical_name = provider.provider_name
    provider_type = provider.provider_type
    rows: list[dict[str, object]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    preview_missing = False
    policy_malformed = False

    preview_file, preview_path_error = _resolve_json_path(
        selected_preview,
        repository_root=root,
        label="Allowlist PR preview",
    )
    preview: dict[str, object] | None = None
    preview_checksum = ""
    if preview_path_error:
        preview_missing = True
        blockers.append(preview_path_error)
        _add_check(
            rows,
            category="Preview evidence",
            field="preview_file",
            expected="Readable preview JSON",
            actual=preview_path_error,
            status=MISSING_PREVIEW_STATUS,
            details="Generate the allowlist PR preview before checking conformance.",
        )
    else:
        preview, preview_read_error = _read_json_object(
            preview_file,
            "Allowlist PR preview",
        )
        if preview_read_error:
            preview_missing = True
            blockers.append(preview_read_error)
            _add_check(
                rows,
                category="Preview evidence",
                field="preview_file",
                expected="Readable preview JSON",
                actual=preview_read_error,
                status=MISSING_PREVIEW_STATUS,
                details="The preview cannot be trusted until it is regenerated.",
            )
        else:
            try:
                preview_checksum = file_sha256(preview_file)
            except OSError as exc:
                preview_missing = True
                blockers.append(f"Allowlist PR preview could not be hashed: {exc}")
            _add_check(
                rows,
                category="Preview evidence",
                field="preview_file",
                expected="Readable preview JSON",
                actual=_display_path(preview_file, root),
                status=MATCH_STATUS if preview_checksum else MISSING_PREVIEW_STATUS,
                details="The checker reads the existing preview and does not regenerate it.",
            )

    preview_status = _clean(preview.get("status") if preview else "")
    proposed_status = _clean(
        preview.get("proposed_allowlist_status") if preview else ""
    )
    preview_ready = preview_status == READY_STATUS and proposed_status == "Allowed"
    if preview and not preview_ready:
        blockers.append(
            "The preview was not ready for a separate allowlist PR. Regenerate "
            "a verified Ready preview before checking policy conformance."
        )
    if preview:
        _add_check(
            rows,
            category="Preview evidence",
            field="preview_status",
            expected=f"{READY_STATUS}; proposed allowlist status Allowed",
            actual=f"{preview_status or 'Missing'}; {proposed_status or 'Missing'}",
            status=MATCH_STATUS if preview_ready else PREVIEW_NOT_VERIFIED_STATUS,
            details="Only a Ready, verified preview can define the expected policy change.",
        )

    identity_fields = {
        "provider_key": provider_key,
        "provider_name": canonical_name,
        "provider_type": provider_type,
    }
    if preview:
        for field, expected_value in identity_fields.items():
            actual_value = _clean(preview.get(field))
            matches = (
                _slug(actual_value) == _slug(expected_value)
                if field != "provider_type"
                else actual_value == expected_value
            )
            if not matches:
                blockers.append(
                    f"Preview {field} `{actual_value or 'Missing'}` does not match "
                    f"requested provider `{expected_value}`."
                )
            _add_check(
                rows,
                category="Provider identity",
                field=field,
                expected=expected_value,
                actual=actual_value or "Missing",
                status=MATCH_STATUS if matches else VALUE_MISMATCH_STATUS,
                details="The requested provider must match the preview exactly.",
            )

    verification_expected_checksum = ""
    verification_current_checksum = ""
    verification_reference = ""
    verification_status = PREVIEW_NOT_VERIFIED_STATUS
    verification = preview.get("verification", {}) if preview else {}
    if isinstance(verification, Mapping):
        verification_expected_checksum = _clean(verification.get("checksum_sha256"))
        verification_reference = _clean(verification.get("path"))
    if preview and (
        not verification_reference
        or not SHA256_PATTERN.fullmatch(verification_expected_checksum)
    ):
        blockers.append(
            "The preview does not bind a valid receipt verification path and SHA-256."
        )
    elif preview:
        verification_file, verification_path_error = _resolve_json_path(
            verification_reference,
            repository_root=root,
            label="Receipt verification report",
        )
        if verification_path_error:
            blockers.append(verification_path_error)
        else:
            try:
                verification_current_checksum = file_sha256(verification_file)
            except OSError as exc:
                blockers.append(f"Receipt verification report could not be hashed: {exc}")
            if verification_current_checksum == verification_expected_checksum:
                verification_status = MATCH_STATUS
            else:
                blockers.append(
                    "The receipt verification report changed after the allowlist PR "
                    "preview was generated. Regenerate the preview before review."
                )
    if preview:
        _add_check(
            rows,
            category="Preview evidence",
            field="verification_report_checksum_sha256",
            expected=verification_expected_checksum or "Missing",
            actual=verification_current_checksum or "Missing",
            status=verification_status,
            details="The checker re-hashes the verification report bound by the preview.",
        )

    before_policy_value = preview.get("before_policy") if preview else None
    expected_policy_value = preview.get("after_policy") if preview else None
    proposed_entry_value = preview.get("proposed_provider_entry") if preview else None
    before_policy = (
        dict(before_policy_value) if isinstance(before_policy_value, Mapping) else {}
    )
    expected_policy = (
        dict(expected_policy_value) if isinstance(expected_policy_value, Mapping) else {}
    )
    proposed_entry = (
        dict(proposed_entry_value) if isinstance(proposed_entry_value, Mapping) else {}
    )
    if preview and not before_policy:
        blockers.append("The preview is missing its comparable baseline policy.")
    if preview and not expected_policy:
        blockers.append("The preview is missing its exact proposed policy.")
    if preview and not proposed_entry:
        blockers.append("The preview is missing its proposed provider fields.")

    policy_file, policy_path_error = _resolve_json_path(
        selected_policy,
        repository_root=root,
        label="Staging provider policy",
    )
    actual_policy: dict[str, object] = {}
    policy_checksum = ""
    if policy_path_error:
        policy_malformed = True
        blockers.append(policy_path_error)
        _add_check(
            rows,
            category="Policy",
            field="policy_file",
            expected="Readable policy JSON",
            actual=policy_path_error,
            status=MALFORMED_POLICY_STATUS,
            details="The current or selected policy must be readable before comparison.",
        )
    else:
        loaded_policy, policy_read_error = _read_json_object(
            policy_file,
            "Staging provider policy",
        )
        if policy_read_error:
            policy_malformed = True
            blockers.append(policy_read_error)
            _add_check(
                rows,
                category="Policy",
                field="policy_file",
                expected="Readable policy JSON",
                actual=policy_read_error,
                status=MALFORMED_POLICY_STATUS,
                details="Fix the policy JSON before checking the proposed PR.",
            )
        else:
            actual_policy = loaded_policy or {}
            try:
                policy_checksum = file_sha256(policy_file)
            except OSError as exc:
                policy_malformed = True
                blockers.append(f"Staging provider policy could not be hashed: {exc}")
            _add_check(
                rows,
                category="Policy",
                field="policy_file",
                expected=_display_path(policy_file, root),
                actual=_display_path(policy_file, root),
                status=MATCH_STATUS if policy_checksum else MALFORMED_POLICY_STATUS,
                details="The policy is read and hashed; it is never edited by this checker.",
            )

    entry_root = ("provider_allowlist_entries", canonical_name)
    proposed_relative_paths = set(REQUIRED_PROPOSED_FIELD_PATHS)
    if proposed_entry:
        proposed_relative_paths.update(_leaf_paths(proposed_entry, ()))
    proposed_paths = {
        (*entry_root, *relative_path) for relative_path in proposed_relative_paths
    }
    for relative_path in sorted(proposed_relative_paths):
        path = (*entry_root, *relative_path)
        preview_value = _lookup_path(proposed_entry, relative_path)
        expected_value = _lookup_path(expected_policy, path)
        actual_value = _lookup_path(actual_policy, path)
        if preview_value is _MISSING:
            status = PREVIEW_NOT_VERIFIED_STATUS
            blockers.append(
                f"Required proposed field `{_format_path(path)}` is missing "
                "from the preview evidence."
            )
        elif expected_value is _MISSING or expected_value != preview_value:
            status = PREVIEW_NOT_VERIFIED_STATUS
            blockers.append(
                f"Proposed field `{_format_path(path)}` does not match the "
                "previewed after-policy."
            )
        elif actual_value is _MISSING:
            status = MISSING_FIELD_STATUS
        elif actual_value != expected_value:
            status = VALUE_MISMATCH_STATUS
        else:
            status = MATCH_STATUS
        _add_check(
            rows,
            category="Proposed provider fields",
            field=_format_path(path),
            baseline=_lookup_path(before_policy, path),
            expected=preview_value,
            actual=actual_value,
            status=status,
            details="Required provider fields must match the preview exactly.",
        )

    if proposed_entry:
        proposed_verification_path = _clean(
            proposed_entry.get("verification_report_path")
        )
        proposed_verification_checksum = _clean(
            proposed_entry.get("verification_report_checksum_sha256")
        )
        if (
            proposed_verification_path != verification_reference
            or proposed_verification_checksum != verification_expected_checksum
        ):
            blockers.append(
                "The proposed provider entry does not bind the same verification "
                "path and checksum recorded by the preview evidence."
            )

    expected_change_paths = (
        _different_leaf_paths(before_policy, expected_policy)
        if before_policy and expected_policy
        else set()
    )
    reported_paths = set(proposed_paths)
    for path in sorted(expected_change_paths):
        if path in reported_paths:
            continue
        expected_value = _lookup_path(expected_policy, path)
        actual_value = _lookup_path(actual_policy, path)
        if actual_value is _MISSING:
            status = MISSING_FIELD_STATUS
        elif actual_value != expected_value:
            status = VALUE_MISMATCH_STATUS
        else:
            status = MATCH_STATUS
        _add_check(
            rows,
            category="Expected policy changes",
            field=_format_path(path),
            baseline=_lookup_path(before_policy, path),
            expected=expected_value,
            actual=actual_value,
            status=status,
            details="This is an intended policy change recorded by the preview.",
        )
        reported_paths.add(path)

    actual_difference_paths = (
        _different_leaf_paths(expected_policy, actual_policy)
        if expected_policy
        else set()
    )
    unexpected_count = 0
    for path in sorted(actual_difference_paths):
        if path in reported_paths:
            continue
        baseline_value = _lookup_path(before_policy, path)
        expected_value = _lookup_path(expected_policy, path)
        actual_value = _lookup_path(actual_policy, path)
        if actual_value is _MISSING:
            status = MISSING_FIELD_STATUS
        elif expected_value is _MISSING:
            status = UNEXPECTED_EDIT_STATUS
        elif _path_is_expected_change(path, expected_change_paths):
            status = VALUE_MISMATCH_STATUS
        else:
            status = UNEXPECTED_EDIT_STATUS
        if status == UNEXPECTED_EDIT_STATUS:
            unexpected_count += 1
        _add_check(
            rows,
            category="Policy comparison",
            field=_format_path(path),
            baseline=baseline_value,
            expected=expected_value,
            actual=actual_value,
            status=status,
            details=(
                "This difference was not part of the reviewed preview."
                if status == UNEXPECTED_EDIT_STATUS
                else "The policy does not contain the exact previewed value."
            ),
        )
    if actual_difference_paths:
        blockers.append(
            "The current policy differs from the exact previewed policy in "
            f"{len(actual_difference_paths)} field(s)."
        )
    if unexpected_count:
        blockers.append(
            f"The current policy contains {unexpected_count} unrelated or hidden "
            "edit(s) that were not approved in the preview."
        )

    automation_changes: list[tuple[str, object, object]] = []
    if before_policy:
        for path in sorted(_different_leaf_paths(before_policy, actual_policy)):
            baseline_value = _lookup_path(before_policy, path)
            actual_value = _lookup_path(actual_policy, path)
            if _is_automation_path(path) and _looks_enabled(actual_value):
                automation_changes.append(
                    (_format_path(path), baseline_value, actual_value)
                )
    if automation_changes:
        for field, baseline_value, actual_value in automation_changes:
            _add_check(
                rows,
                category="Safety",
                field=field,
                baseline=baseline_value,
                expected="No newly enabled cron or automation setting",
                actual=actual_value,
                status=UNSAFE_AUTOMATION_STATUS,
                details="Automation enablement requires a separate decision and is unsafe here.",
            )
        blockers.append(
            "A cron, schedule, or automation-related setting appears to have been "
            "enabled outside the reviewed provider allowlist change."
        )
    else:
        _add_check(
            rows,
            category="Safety",
            field="cron_or_automation_enablement",
            baseline="No newly enabled setting",
            expected="No newly enabled setting",
            actual="No newly enabled setting detected",
            status=MATCH_STATUS,
            details="Allowlisting and cron remain separate decisions.",
        )

    blockers = list(dict.fromkeys(item for item in blockers if item))
    if policy_malformed:
        verdict = MALFORMED_POLICY_VERDICT
    elif preview_missing:
        verdict = MISSING_PREVIEW_VERDICT
    elif automation_changes:
        verdict = UNSAFE_AUTOMATION_VERDICT
    elif (
        blockers
        or actual_difference_paths
        or not preview_ready
        or any(_clean(row.get("status")) != MATCH_STATUS for row in rows)
    ):
        verdict = DOES_NOT_CONFORM_VERDICT
    else:
        verdict = CONFORMS_VERDICT

    status_counts = Counter(_clean(row.get("status")) for row in rows)
    generated_at = (run_at or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    expected_actual_diff = (
        _policy_diff(
            expected_policy,
            actual_policy,
            expected_label="previewed staging_provider_policy.json",
            actual_label="current staging_provider_policy.json",
        )
        if expected_policy
        else ""
    )
    baseline_actual_diff = (
        _policy_diff(
            before_policy,
            actual_policy,
            expected_label="preview baseline staging_provider_policy.json",
            actual_label="current staging_provider_policy.json",
        )
        if before_policy
        else ""
    )
    summary: dict[str, object] = {
        "schema_version": 1,
        "generated_at": generated_at,
        "verdict": verdict,
        "provider_key": provider_key,
        "provider_name": canonical_name,
        "provider_type": provider_type,
        "preview": {
            "path": _display_path(preview_file, root),
            "checksum_sha256": preview_checksum,
            "status": preview_status or "Missing",
            "proposed_allowlist_status": proposed_status or "Missing",
            "verification_report_path": verification_reference,
            "expected_verification_checksum_sha256": verification_expected_checksum,
            "current_verification_checksum_sha256": verification_current_checksum,
            "verification_checksum_status": verification_status,
        },
        "policy": {
            "path": _display_path(policy_file, root),
            "checksum_sha256": policy_checksum,
        },
        "baseline_policy": before_policy,
        "expected_policy": expected_policy,
        "actual_policy": actual_policy,
        "expected_actual_diff": expected_actual_diff,
        "baseline_actual_diff": baseline_actual_diff,
        "status_counts": dict(sorted(status_counts.items())),
        "blockers": blockers,
        "warnings": list(dict.fromkeys(warnings)),
        "checks": rows,
        "safety": {
            "read_only": True,
            "provider_policy_edited": False,
            "preview_created": False,
            "receipt_verified_by_side_effect": False,
            "provider_allowlisted": False,
            "staging_promoted": False,
            "provider_run": False,
            "cron_enabled": False,
            "protected_files_edited": False,
            "picks_generated": False,
            "bets_placed": False,
        },
    }
    return pd.DataFrame(rows, columns=CHECK_COLUMNS), summary


def render_provider_allowlist_pr_conformance(
    checks: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    preview = summary.get("preview", {})
    policy = summary.get("policy", {})
    blockers = summary.get("blockers", [])
    warnings = summary.get("warnings", [])
    status_counts = summary.get("status_counts", {})
    lines = [
        "# Provider Allowlist PR Conformance Check",
        "",
        "**Read-only check: nothing was applied.** This report compares the "
        "current provider policy with an existing reviewed preview. It does not "
        "edit policy, allowlist a provider, promote staging, run providers, "
        "generate picks, place bets, or enable cron.",
        "",
        "## Verdict",
        "",
        f"- **{summary.get('verdict', DOES_NOT_CONFORM_VERDICT)}**",
        f"- Provider: `{summary.get('provider_name', '')}` "
        f"(`{summary.get('provider_type', '')}`)",
        f"- Preview: `{preview.get('path', '')}`",
        f"- Preview status: **{preview.get('status', 'Missing')}**",
        f"- Policy checked: `{policy.get('path', '')}`",
        "",
        "## Evidence checks",
        "",
        f"- Preview SHA-256: `{preview.get('checksum_sha256', '') or 'Missing'}`",
        "- Bound verification SHA-256: "
        f"`{preview.get('expected_verification_checksum_sha256', '') or 'Missing'}`",
        "- Current verification SHA-256: "
        f"`{preview.get('current_verification_checksum_sha256', '') or 'Missing'}`",
        "- Verification checksum status: "
        f"**{preview.get('verification_checksum_status', PREVIEW_NOT_VERIFIED_STATUS)}**",
        f"- Current policy SHA-256: `{policy.get('checksum_sha256', '') or 'Missing'}`",
        "",
        "## Check totals",
        "",
    ]
    if isinstance(status_counts, Mapping) and status_counts:
        lines.extend(f"- {status}: {count}" for status, count in status_counts.items())
    else:
        lines.append("- No checks were available.")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {item}" for item in blockers)
    if not blockers:
        lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in warnings)
    if not warnings:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Expected vs actual checks",
            "",
            checks.to_markdown(index=False),
            "",
            "## Expected policy",
            "",
            "```json",
            json.dumps(summary.get("expected_policy", {}), indent=2, sort_keys=True),
            "```",
            "",
            "## Actual policy",
            "",
            "```json",
            json.dumps(summary.get("actual_policy", {}), indent=2, sort_keys=True),
            "```",
            "",
            "## Expected/actual diff",
            "",
            "```diff",
            _clean(summary.get("expected_actual_diff"))
            or "No differences. The current policy matches the previewed policy.",
            "```",
            "",
            "## Baseline/current diff",
            "",
            "```diff",
            _clean(summary.get("baseline_actual_diff"))
            or "No baseline/current diff is available.",
            "```",
            "",
            "## What the verdict means",
            "",
            "`Conforms to preview` means the complete policy document matches the "
            "reviewed after-policy exactly and no automation change was detected. "
            "Any missing field, changed value, extra policy edit, stale verification "
            "evidence, or automation enablement must be resolved before merge.",
            "",
            "Allowlisting and cron remain separate decisions. Passing this checker "
            "does not enable a provider for scheduled runs and does not authorize "
            "any automated betting action.",
        ]
    )
    return "\n".join(lines)


def save_provider_allowlist_pr_conformance(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    preview_path: Path | None = None,
    policy_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    checks, summary = build_provider_allowlist_pr_conformance(
        provider_name,
        outputs,
        preview_path=preview_path,
        policy_path=policy_path,
        repository_root=repository_root,
        run_at=run_at,
    )
    json_path = outputs / CONFORMANCE_JSON_FILENAME
    markdown_path = outputs / CONFORMANCE_MARKDOWN_FILENAME
    csv_path = outputs / CONFORMANCE_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        render_provider_allowlist_pr_conformance(checks, summary).encode("utf-8"),
    )
    atomic_write_report(
        csv_path,
        checks.to_csv(index=False, lineterminator="\n").encode("utf-8"),
    )
    return {
        "summary": summary,
        "checks": checks,
        "verdict": summary["verdict"],
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
    }
