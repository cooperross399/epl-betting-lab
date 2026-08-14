from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import (
    atomic_write_report,
    file_sha256,
    path_contains_symlink,
)
from epl_betting_lab.providers.provider_registry import create_provider
from epl_betting_lab.reports.provider_policy_pr_gate import (
    BOUND_STATUS,
    GATE_JSON_FILENAME,
    NOT_APPLICABLE_VERDICT as GATE_NOT_APPLICABLE_VERDICT,
    PASSED_VERDICT as GATE_PASSED_VERDICT,
    POLICY_RELATIVE_PATH,
    calculate_provider_policy_gate_receipt_identity,
)


VERIFICATION_JSON_FILENAME = "provider_policy_pr_gate_receipt_verification.json"
VERIFICATION_MARKDOWN_FILENAME = "provider_policy_pr_gate_receipt_verification.md"
VERIFICATION_CSV_FILENAME = "provider_policy_pr_gate_receipt_verification.csv"

VERIFIED_STATUS = "Verified"
MISSING_GATE_REPORT_STATUS = "Missing gate report"
MALFORMED_GATE_REPORT_STATUS = "Malformed gate report"
GIT_CONTEXT_CHANGED_STATUS = "Git context changed"
CHANGED_FILES_CHANGED_STATUS = "Changed files changed"
POLICY_CHECKSUM_MISMATCH_STATUS = "Policy checksum mismatch"
EVIDENCE_CHECKSUM_MISMATCH_STATUS = "Evidence checksum mismatch"
RECEIPT_ID_MISMATCH_STATUS = "Receipt ID mismatch"
GATE_NOT_PASSED_STATUS = "Gate was not passed"
NOT_APPLICABLE_STATUS = "Not applicable"

VERIFICATION_STATUSES = (
    VERIFIED_STATUS,
    MISSING_GATE_REPORT_STATUS,
    MALFORMED_GATE_REPORT_STATUS,
    GIT_CONTEXT_CHANGED_STATUS,
    CHANGED_FILES_CHANGED_STATUS,
    POLICY_CHECKSUM_MISMATCH_STATUS,
    EVIDENCE_CHECKSUM_MISMATCH_STATUS,
    RECEIPT_ID_MISMATCH_STATUS,
    GATE_NOT_PASSED_STATUS,
    NOT_APPLICABLE_STATUS,
)

VERIFIED_VERDICT = "Gate receipt verified for PR approval"
NOT_APPLICABLE_VERDICT = "Gate receipt not applicable"
CHANGED_VERDICT = "Gate receipt changed"
MISSING_EVIDENCE_VERDICT = "Gate receipt missing evidence"
MALFORMED_VERDICT = "Gate receipt malformed"
NOT_APPROVED_VERDICT = "Gate receipt not approved"

VERIFICATION_VERDICTS = (
    VERIFIED_VERDICT,
    NOT_APPLICABLE_VERDICT,
    CHANGED_VERDICT,
    MISSING_EVIDENCE_VERDICT,
    MALFORMED_VERDICT,
    NOT_APPROVED_VERDICT,
)

VERIFICATION_COLUMNS = (
    "category",
    "check",
    "evidence_path",
    "expected",
    "observed",
    "status",
    "details",
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_REQUIRED_EVIDENCE_FIELDS = {
    "evidence_bundle_verification_checksum_sha256",
    "conformance_report_checksum_sha256",
    "preview_report_checksum_sha256",
    "receipt_verification_report_checksum_sha256",
}
_EXPECTED_EVIDENCE_FILENAMES = {
    "evidence_bundle_verification_checksum_sha256": (
        "provider_allowlist_evidence_bundle_verification.json"
    ),
    "conformance_report_checksum_sha256": (
        "provider_allowlist_pr_conformance.json"
    ),
    "preview_report_checksum_sha256": "provider_allowlist_pr_preview.json",
    "receipt_verification_report_checksum_sha256": (
        "provider_human_acceptance_receipt_verification.json"
    ),
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


def _canonical_sha256(payload: object) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalize_path(value: object) -> str:
    normalized = _clean(value).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repository_root).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _valid_repo_path(value: str) -> bool:
    path = Path(value)
    return (
        bool(value)
        and not path.is_absolute()
        and ".." not in path.parts
        and (not path.parts or path.parts[0] != ".git")
    )


def _safe_repo_file(
    path: Path,
    *,
    repository_root: Path,
    required_suffix: str | None = None,
) -> tuple[Path, str]:
    candidate = path if path.is_absolute() else repository_root / path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(repository_root)
    except (OSError, RuntimeError, ValueError):
        return candidate, "Path must stay inside the repository."
    if required_suffix and resolved.suffix.casefold() != required_suffix.casefold():
        return resolved, f"Path must be a {required_suffix} file."
    if path_contains_symlink(candidate.absolute(), repository_root):
        return resolved, "Symbolic links are not accepted."
    if not resolved.exists():
        return resolved, "File is missing."
    if not resolved.is_file() or resolved.is_symlink():
        return resolved, "Path must be a regular, non-symlinked file."
    return resolved, ""


def _read_json_object(path: Path) -> tuple[dict[str, object] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"JSON is unreadable or malformed: {exc}"
    if not isinstance(payload, dict):
        return None, "JSON must contain one object."
    return payload, ""


def _file_checksum(
    path: Path,
    *,
    repository_root: Path,
) -> tuple[str, str]:
    resolved, error = _safe_repo_file(path, repository_root=repository_root)
    if error:
        return "", error
    try:
        return file_sha256(resolved), ""
    except OSError as exc:
        return "", f"File could not be hashed: {exc}"


def _git(
    repository_root: Path,
    args: Sequence[str],
    *,
    binary: bool = False,
) -> tuple[bytes | str, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=not binary,
        )
    except OSError as exc:
        return (b"" if binary else ""), f"Git could not run: {exc}"
    if completed.returncode != 0:
        stdout = completed.stdout
        stderr = completed.stderr
        if binary:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        else:
            detail = (stderr or stdout).strip()
        return (b"" if binary else ""), (
            f"Git command failed: {detail or 'unknown error'}"
        )
    return completed.stdout, ""


def _resolve_commit(repository_root: Path, value: str) -> tuple[str, str]:
    if not _GIT_COMMIT_PATTERN.fullmatch(value.casefold()):
        return "", "Recorded commit SHA is missing or malformed."
    output, error = _git(
        repository_root,
        ["rev-parse", "--verify", f"{value}^{{commit}}"],
    )
    resolved = _clean(output).splitlines()[0] if output else ""
    if error:
        return "", error
    if resolved.casefold() != value.casefold():
        return resolved, "Recorded commit SHA resolved to a different commit."
    return resolved.casefold(), ""


def _git_changed_files(
    repository_root: Path,
    *,
    base_sha: str,
    head_sha: str,
) -> tuple[list[str], str]:
    output, error = _git(
        repository_root,
        ["diff", "--no-renames", "--name-only", base_sha, head_sha, "--"],
    )
    if error:
        return [], error
    return sorted(
        {
            normalized
            for line in _clean(output).splitlines()
            if (normalized := _normalize_path(line))
        }
    ), ""


def _working_tree_changed_files(repository_root: Path) -> tuple[list[str], str]:
    output, error = _git(
        repository_root,
        ["diff", "--no-renames", "--name-only", "HEAD", "--"],
    )
    if error:
        return [], error
    return sorted(
        {
            normalized
            for line in _clean(output).splitlines()
            if (normalized := _normalize_path(line))
        }
    ), ""


def _git_file_checksum(
    repository_root: Path,
    *,
    commit_sha: str,
    relative_path: str,
) -> tuple[str, str]:
    if not _GIT_COMMIT_PATTERN.fullmatch(commit_sha.casefold()):
        return "", "Git commit SHA is missing or malformed."
    if not _valid_repo_path(relative_path):
        return "", f"Unsafe repository path: `{relative_path}`."
    content, error = _git(
        repository_root,
        ["show", f"{commit_sha}:{relative_path}"],
        binary=True,
    )
    return (sha256(content).hexdigest() if not error else ""), error


def _deleted_path_checksum(relative_path: str) -> str:
    return _canonical_sha256(
        {"path": relative_path, "state": "deleted_from_head_or_worktree"}
    )


def _current_changed_file_checksum(
    relative_path: str,
    *,
    repository_root: Path,
    comparison_start: str,
    head_sha: str,
) -> tuple[str, str]:
    if not _valid_repo_path(relative_path):
        return "", f"Unsafe repository path: `{relative_path}`."
    current_path = repository_root / relative_path
    checksum, error = _file_checksum(current_path, repository_root=repository_root)
    if not error:
        return checksum.casefold(), ""
    if "missing" not in error.casefold():
        return "", error
    head_checksum, head_error = _git_file_checksum(
        repository_root,
        commit_sha=head_sha,
        relative_path=relative_path,
    )
    before_checksum, before_error = _git_file_checksum(
        repository_root,
        commit_sha=comparison_start,
        relative_path=relative_path,
    )
    if head_checksum or before_checksum:
        return _deleted_path_checksum(relative_path), ""
    return "", head_error or before_error or error


def _add_check(
    rows: list[dict[str, object]],
    *,
    category: str,
    check: str,
    status: str,
    details: str,
    evidence_path: object = "",
    expected: object = "",
    observed: object = "",
) -> None:
    if status not in VERIFICATION_STATUSES:
        raise ValueError(f"Unexpected gate receipt verification status: {status}")
    rows.append(
        {
            "category": category,
            "check": check,
            "evidence_path": _clean(evidence_path),
            "expected": _clean(expected),
            "observed": _clean(observed),
            "status": status,
            "details": details,
        }
    )


def _empty_summary(
    *,
    provider_key: str,
    provider_name: str,
    gate_path: Path,
    generated_at: str,
    diagnostic_mode: bool,
    verdict: str,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "provider_key": provider_key,
        "provider_name": provider_name,
        "gate_report_path": str(gate_path),
        "diagnostic_mode": diagnostic_mode,
        "original_gate_verdict": "",
        "verdict": verdict,
        "original_gate_receipt_id": "",
        "recalculated_gate_receipt_id": "",
        "original_gate_receipt_checksum_sha256": "",
        "recalculated_gate_receipt_checksum_sha256": "",
        "base_sha": "",
        "head_sha": "",
        "merge_base_sha": "",
        "gate_mode": "",
        "expected_changed_files": [],
        "current_changed_files": [],
        "expected_changed_files_digest": "",
        "current_changed_files_digest": "",
        "expected_evidence_digest": "",
        "current_evidence_digest": "",
        "expected_policy_change_digest": "",
        "current_policy_change_digest": "",
        "expected_policy_checksum_sha256": "",
        "current_policy_checksum_sha256": "",
        "comparison_context_status": "Unavailable",
        "receipt_binding_status": "Unverified",
        "mismatches": [row["details"] for row in rows],
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "checks": rows,
        "safety": {
            "read_only": True,
            "policy_edited": False,
            "provider_allowlisted": False,
            "cron_enabled": False,
        },
    }


def _required_gate_fields_missing(payload: Mapping[str, object]) -> list[str]:
    required = (
        "provider_key",
        "policy_path",
        "policy_changed",
        "base_sha",
        "head_sha",
        "merge_base_sha",
        "gate_mode",
        "changed_files",
        "changed_file_digests",
        "changed_files_digest",
        "policy_checksum_before_sha256",
        "policy_checksum_after_sha256",
        "policy_change_digest",
        "evidence_reports",
        "evidence_digest",
        "comparison_context_status",
        "receipt_binding_status",
        "gate_receipt_checksum_sha256",
        "gate_receipt_id",
        "verdict",
    )
    return [field for field in required if field not in payload]


def _valid_checksum(value: object) -> bool:
    return bool(_SHA256_PATTERN.fullmatch(_clean(value).casefold()))


def build_provider_policy_pr_gate_receipt_verification(
    provider_name: str,
    *,
    gate_report_path: Path | None = None,
    repository_root: Path | None = None,
    diagnostic_mode: bool = False,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Verify that a saved gate receipt still binds the exact reviewed state."""
    root = (repository_root or PROJECT_ROOT).resolve()
    provider = create_provider(provider_name)
    provider_key = provider.provider_key
    generated_at = (run_at or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    selected_gate = gate_report_path or (
        root / "data" / "outputs" / GATE_JSON_FILENAME
    )
    gate_path, gate_path_error = _safe_repo_file(
        selected_gate,
        repository_root=root,
        required_suffix=".json",
    )
    rows: list[dict[str, object]] = []
    if gate_path_error:
        _add_check(
            rows,
            category="Gate report",
            check="Gate report is available",
            status=MISSING_GATE_REPORT_STATUS,
            evidence_path=_display_path(gate_path, root),
            expected="Readable gate JSON inside the repository",
            observed=gate_path_error,
            details=(
                "Run the Provider Policy PR Gate first, then verify its saved receipt."
            ),
        )
        summary = _empty_summary(
            provider_key=provider_key,
            provider_name=provider.provider_name,
            gate_path=gate_path,
            generated_at=generated_at,
            diagnostic_mode=diagnostic_mode,
            verdict=MISSING_EVIDENCE_VERDICT,
            rows=rows,
        )
        return pd.DataFrame(rows, columns=VERIFICATION_COLUMNS), summary

    gate, read_error = _read_json_object(gate_path)
    if read_error or gate is None:
        _add_check(
            rows,
            category="Gate report",
            check="Gate report is well formed",
            status=MALFORMED_GATE_REPORT_STATUS,
            evidence_path=_display_path(gate_path, root),
            expected="One valid JSON object",
            observed=read_error,
            details="The gate report cannot be trusted until it is regenerated.",
        )
        summary = _empty_summary(
            provider_key=provider_key,
            provider_name=provider.provider_name,
            gate_path=gate_path,
            generated_at=generated_at,
            diagnostic_mode=diagnostic_mode,
            verdict=MALFORMED_VERDICT,
            rows=rows,
        )
        return pd.DataFrame(rows, columns=VERIFICATION_COLUMNS), summary

    missing_fields = _required_gate_fields_missing(gate)
    gate_provider = _slug(gate.get("provider_key") or gate.get("provider_name"))
    malformed = bool(missing_fields) or gate_provider != _slug(provider_key)
    _add_check(
        rows,
        category="Gate report",
        check="Gate report schema and provider",
        status=MALFORMED_GATE_REPORT_STATUS if malformed else VERIFIED_STATUS,
        evidence_path=_display_path(gate_path, root),
        expected=provider_key,
        observed=gate_provider,
        details=(
            "Missing required fields: " + ", ".join(missing_fields)
            if missing_fields
            else (
                "The gate report provider does not match the requested provider."
                if malformed
                else "The gate report has the required receipt fields and provider."
            )
        ),
    )

    original_gate_verdict = _clean(gate.get("verdict"))
    policy_changed = gate.get("policy_changed") is True
    gate_not_applicable = (
        original_gate_verdict == GATE_NOT_APPLICABLE_VERDICT and not policy_changed
    )
    gate_passed = original_gate_verdict == GATE_PASSED_VERDICT
    _add_check(
        rows,
        category="Gate decision",
        check="Original gate approved this policy comparison",
        status=(
            VERIFIED_STATUS
            if gate_passed
            else NOT_APPLICABLE_STATUS
            if gate_not_applicable
            else GATE_NOT_PASSED_STATUS
        ),
        expected=GATE_PASSED_VERDICT,
        observed=original_gate_verdict or "Missing",
        details=(
            "The original gate passed."
            if gate_passed
            else "No provider-policy change was detected by the original gate."
            if gate_not_applicable
            else "A blocked or failed gate receipt cannot approve a policy PR."
        ),
    )

    base_sha = _clean(gate.get("base_sha")).casefold()
    head_sha = _clean(gate.get("head_sha")).casefold()
    merge_base_sha = _clean(gate.get("merge_base_sha")).casefold()
    gate_mode = _clean(gate.get("gate_mode"))
    saved_changed_files = sorted(
        {
            path
            for value in gate.get("changed_files", [])
            if (path := _normalize_path(value))
        }
    ) if isinstance(gate.get("changed_files"), list) else []

    resolved_base, base_error = _resolve_commit(root, base_sha)
    resolved_head, head_error = _resolve_commit(root, head_sha)
    current_head_output, current_head_error = _git(root, ["rev-parse", "HEAD"])
    current_head = _clean(current_head_output).casefold()
    merge_output, merge_error = _git(root, ["merge-base", base_sha, head_sha])
    current_merge_base = _clean(merge_output).casefold()
    git_error = base_error or head_error or current_head_error or merge_error
    git_context_matches = (
        not git_error
        and resolved_base == base_sha
        and resolved_head == head_sha
        and current_head == head_sha
        and current_merge_base == merge_base_sha
    )
    _add_check(
        rows,
        category="Git context",
        check="Exact base, head, and merge-base context",
        status=VERIFIED_STATUS if git_context_matches else GIT_CONTEXT_CHANGED_STATUS,
        expected=(
            f"base={base_sha}; head={head_sha}; merge_base={merge_base_sha}"
        ),
        observed=(
            f"base={resolved_base or 'Missing'}; head={current_head or 'Missing'}; "
            f"merge_base={current_merge_base or 'Missing'}"
        ),
        details=(
            "The recorded Git comparison is still checked out and reproducible."
            if git_context_matches
            else (
                f"Exact Git context is unavailable or changed: {git_error or 'SHA mismatch'}. "
                + (
                    "Diagnostic mode can write this report, but cannot approve the receipt."
                    if diagnostic_mode
                    else "Fetch/check out the recorded PR commits before verifying."
                )
            )
        ),
    )

    actual_changed_files: list[str] = []
    changed_list_error = git_error
    if not git_error:
        actual_changed_files, changed_list_error = _git_changed_files(
            root,
            base_sha=base_sha,
            head_sha=head_sha,
        )
        source = _clean(
            (gate.get("change_detection") or {}).get("source")
            if isinstance(gate.get("change_detection"), Mapping)
            else ""
        )
        if not changed_list_error and source == "Local Git diff against default branch":
            committed_files, committed_error = _git_changed_files(
                root,
                base_sha=merge_base_sha,
                head_sha=head_sha,
            )
            working_files, working_error = _working_tree_changed_files(root)
            changed_list_error = committed_error or working_error
            actual_changed_files = sorted(set(committed_files) | set(working_files))
    changed_list_matches = not changed_list_error and actual_changed_files == saved_changed_files
    _add_check(
        rows,
        category="Changed files",
        check="PR changed-file list",
        status=(
            VERIFIED_STATUS if changed_list_matches else CHANGED_FILES_CHANGED_STATUS
        ),
        expected=", ".join(saved_changed_files) or "No changed files",
        observed=(
            ", ".join(actual_changed_files)
            if not changed_list_error
            else changed_list_error
        ),
        details=(
            "The current Git comparison has the same normalized changed-file list."
            if changed_list_matches
            else "The recorded and current PR changed-file lists differ."
        ),
    )

    saved_changed_records = gate.get("changed_file_digests")
    malformed_changed_records = not isinstance(saved_changed_records, list)
    current_changed_records: list[dict[str, str]] = []
    changed_content_mismatches: list[str] = []
    comparison_start = merge_base_sha or base_sha
    if isinstance(saved_changed_records, list):
        record_by_path = {
            _normalize_path(record.get("path")): record
            for record in saved_changed_records
            if isinstance(record, Mapping) and _normalize_path(record.get("path"))
        }
        if set(record_by_path) != set(saved_changed_files):
            malformed_changed_records = True
        for relative_path in actual_changed_files:
            checksum, checksum_error = _current_changed_file_checksum(
                relative_path,
                repository_root=root,
                comparison_start=comparison_start,
                head_sha=head_sha,
            )
            current_changed_records.append(
                {"path": relative_path, "checksum_sha256": checksum.casefold()}
            )
            expected_checksum = _clean(
                (record_by_path.get(relative_path) or {}).get("checksum_sha256")
            ).casefold()
            if checksum_error or checksum.casefold() != expected_checksum:
                changed_content_mismatches.append(
                    f"{relative_path}: {checksum_error or 'checksum changed'}"
                )
    current_changed_digest = (
        _canonical_sha256(current_changed_records)
        if current_changed_records
        and all(_valid_checksum(item["checksum_sha256"]) for item in current_changed_records)
        else _canonical_sha256([])
        if not actual_changed_files and not changed_list_error
        else ""
    )
    expected_changed_digest = _clean(gate.get("changed_files_digest")).casefold()
    changed_digest_matches = (
        not malformed_changed_records
        and not changed_content_mismatches
        and current_changed_digest == expected_changed_digest
        and _valid_checksum(expected_changed_digest)
    )
    _add_check(
        rows,
        category="Changed files",
        check="Changed-file contents and aggregate digest",
        status=VERIFIED_STATUS if changed_digest_matches else CHANGED_FILES_CHANGED_STATUS,
        expected=expected_changed_digest or "Missing",
        observed=current_changed_digest or "Unavailable",
        details=(
            "Every changed file still matches the hash bound by the gate."
            if changed_digest_matches
            else "Changed-file binding failed. "
            + ("; ".join(changed_content_mismatches) or "Digest records are malformed.")
        ),
    )

    policy_path_value = _normalize_path(gate.get("policy_path"))
    policy_path_valid = policy_path_value == POLICY_RELATIVE_PATH
    current_policy_checksum, policy_error = _file_checksum(
        root / policy_path_value,
        repository_root=root,
    ) if _valid_repo_path(policy_path_value) else ("", "Unsafe policy path.")
    expected_policy_checksum = _clean(
        gate.get("policy_checksum_after_sha256")
    ).casefold()
    policy_checksum_matches = (
        policy_path_valid
        and not policy_error
        and _valid_checksum(expected_policy_checksum)
        and current_policy_checksum.casefold() == expected_policy_checksum
    )
    _add_check(
        rows,
        category="Provider policy",
        check="Current provider-policy checksum",
        status=(
            VERIFIED_STATUS if policy_checksum_matches else POLICY_CHECKSUM_MISMATCH_STATUS
        ),
        evidence_path=policy_path_value,
        expected=expected_policy_checksum or "Missing",
        observed=current_policy_checksum or policy_error,
        details=(
            "The current provider policy exactly matches the gate receipt."
            if policy_checksum_matches
            else "The provider policy path or contents changed after the gate ran."
        ),
    )
    policy_before_checksum, before_error = _git_file_checksum(
        root,
        commit_sha=comparison_start,
        relative_path=policy_path_value,
    ) if _valid_repo_path(policy_path_value) else ("", "Unsafe policy path.")
    expected_before_checksum = _clean(
        gate.get("policy_checksum_before_sha256")
    ).casefold()
    current_policy_change_digest = (
        _canonical_sha256(
            {
                "path": policy_path_value,
                "before_checksum_sha256": policy_before_checksum.casefold(),
                "after_checksum_sha256": current_policy_checksum.casefold(),
            }
        )
        if not before_error and _valid_checksum(current_policy_checksum)
        else ""
    )
    expected_policy_change_digest = _clean(gate.get("policy_change_digest")).casefold()
    policy_change_matches = (
        policy_before_checksum.casefold() == expected_before_checksum
        and current_policy_change_digest == expected_policy_change_digest
        and _valid_checksum(expected_policy_change_digest)
    )
    _add_check(
        rows,
        category="Provider policy",
        check="Provider-policy before/after digest",
        status=(
            VERIFIED_STATUS if policy_change_matches else POLICY_CHECKSUM_MISMATCH_STATUS
        ),
        expected=expected_policy_change_digest or "Missing",
        observed=current_policy_change_digest or before_error or "Unavailable",
        details=(
            "The policy before/after pair still matches the reviewed comparison."
            if policy_change_matches
            else "The policy baseline, current checksum, or policy-change digest differs."
        ),
    )

    saved_evidence_records = gate.get("evidence_reports")
    current_evidence_records: list[dict[str, str]] = []
    evidence_mismatches: list[str] = []
    evidence_missing = False
    if isinstance(saved_evidence_records, list):
        mapping_records = [
            item for item in saved_evidence_records if isinstance(item, Mapping)
        ]
        if len(mapping_records) != len(saved_evidence_records):
            evidence_mismatches.append(
                "One or more evidence records are not JSON objects."
            )
        recorded_fields = [_clean(item.get("field")) for item in mapping_records]
        if policy_changed and set(recorded_fields) != _REQUIRED_EVIDENCE_FIELDS:
            evidence_mismatches.append(
                "The passing policy gate does not contain the exact required "
                "evidence field set."
            )
        if len(recorded_fields) != len(set(recorded_fields)):
            evidence_mismatches.append("Evidence field names are duplicated.")
        for record in sorted(
            mapping_records,
            key=lambda item: (_clean(item.get("field")), _normalize_path(item.get("path"))),
        ):
            field = _clean(record.get("field"))
            relative_path = _normalize_path(record.get("path"))
            expected_checksum = _clean(record.get("checksum_sha256")).casefold()
            expected_filename = _EXPECTED_EVIDENCE_FILENAMES.get(field, "")
            if expected_filename and Path(relative_path).name != expected_filename:
                evidence_mismatches.append(
                    f"{field}: expected `{expected_filename}`, not "
                    f"`{Path(relative_path).name}`"
                )
            if _clean(gate.get(field)).casefold() != expected_checksum:
                evidence_mismatches.append(
                    f"{field}: top-level and manifest checksums differ"
                )
            if not field or not _valid_repo_path(relative_path):
                evidence_mismatches.append(f"Malformed evidence record: {field or 'missing field'}")
                continue
            checksum, checksum_error = _file_checksum(
                root / relative_path,
                repository_root=root,
            )
            if checksum_error:
                evidence_missing = evidence_missing or (
                    "missing" in checksum_error.casefold()
                )
            current_evidence_records.append(
                {
                    "field": field,
                    "path": relative_path,
                    "checksum_sha256": checksum.casefold(),
                }
            )
            if checksum_error or checksum.casefold() != expected_checksum:
                evidence_mismatches.append(
                    f"{relative_path}: {checksum_error or 'checksum changed'}"
                )
    else:
        evidence_mismatches.append("Evidence records are missing or malformed.")
    valid_current_evidence = [
        item
        for item in current_evidence_records
        if _valid_checksum(item["checksum_sha256"])
    ]
    current_evidence_digest = _canonical_sha256(valid_current_evidence)
    expected_evidence_digest = _clean(gate.get("evidence_digest")).casefold()
    evidence_matches = (
        not evidence_mismatches
        and current_evidence_digest == expected_evidence_digest
        and _valid_checksum(expected_evidence_digest)
    )
    _add_check(
        rows,
        category="Approval evidence",
        check="Evidence files and aggregate digest",
        status=(
            VERIFIED_STATUS if evidence_matches else EVIDENCE_CHECKSUM_MISMATCH_STATUS
        ),
        expected=expected_evidence_digest or "Missing",
        observed=current_evidence_digest or "Unavailable",
        details=(
            "Every evidence report still matches its recorded checksum."
            if evidence_matches
            else "Evidence binding failed. " + "; ".join(evidence_mismatches)
        ),
    )

    original_receipt_id = _clean(gate.get("gate_receipt_id"))
    original_receipt_checksum = _clean(
        gate.get("gate_receipt_checksum_sha256")
    ).casefold()
    receipt_format_valid = (
        _valid_checksum(original_receipt_checksum)
        and original_receipt_id
        == f"{_slug(provider_key)}-provider-policy-gate-{original_receipt_checksum}"
    )
    recalculated_receipt_checksum, recalculated_receipt_id = (
        calculate_provider_policy_gate_receipt_identity(
            provider_key=provider_key,
            base_sha=base_sha,
            head_sha=head_sha,
            changed_file_digests=current_changed_records,
            changed_files_digest=current_changed_digest,
            policy_checksum_after_sha256=current_policy_checksum,
            evidence_checksums=current_evidence_records,
            evidence_digest=current_evidence_digest,
            final_verdict=original_gate_verdict,
        )
    )
    receipt_matches = (
        receipt_format_valid
        and original_receipt_checksum == recalculated_receipt_checksum
        and original_receipt_id == recalculated_receipt_id
    )
    _add_check(
        rows,
        category="Gate receipt",
        check="Deterministic gate receipt ID",
        status=VERIFIED_STATUS if receipt_matches else RECEIPT_ID_MISMATCH_STATUS,
        expected=original_receipt_id or "Missing",
        observed=recalculated_receipt_id,
        details=(
            "The receipt ID was reproduced from the current bound inputs."
            if receipt_matches
            else "The saved receipt ID is malformed or cannot be reproduced."
        ),
    )
    binding_matches = _clean(gate.get("receipt_binding_status")) == BOUND_STATUS
    _add_check(
        rows,
        category="Gate receipt",
        check="Original receipt binding status",
        status=(
            VERIFIED_STATUS
            if binding_matches
            else NOT_APPLICABLE_STATUS
            if gate_not_applicable
            else GATE_NOT_PASSED_STATUS
        ),
        expected=BOUND_STATUS,
        observed=_clean(gate.get("receipt_binding_status")) or "Missing",
        details=(
            "The original passing gate issued a bound receipt."
            if binding_matches
            else "The original report did not issue an approval-bound receipt."
        ),
    )

    statuses = {row["status"] for row in rows}
    if malformed or not receipt_format_valid:
        verdict = MALFORMED_VERDICT
    elif gate_not_applicable:
        verdict = NOT_APPLICABLE_VERDICT
    elif not gate_passed or not binding_matches:
        verdict = NOT_APPROVED_VERDICT
    elif evidence_missing or GIT_CONTEXT_CHANGED_STATUS in statuses:
        verdict = MISSING_EVIDENCE_VERDICT
    elif statuses == {VERIFIED_STATUS}:
        verdict = VERIFIED_VERDICT
    else:
        verdict = CHANGED_VERDICT
    if diagnostic_mode and verdict == VERIFIED_VERDICT:
        # Diagnostic mode is intentionally non-approving even if all checks pass.
        verdict = NOT_APPROVED_VERDICT
        _add_check(
            rows,
            category="Execution mode",
            check="Approval-capable verification mode",
            status=GATE_NOT_PASSED_STATUS,
            expected="Normal verification mode",
            observed="Diagnostic mode",
            details="Diagnostic mode can inspect a receipt but cannot approve it.",
        )

    mismatches = [
        row["details"]
        for row in rows
        if row["status"] not in {VERIFIED_STATUS, NOT_APPLICABLE_STATUS}
    ]
    summary = {
        "schema_version": 1,
        "generated_at": generated_at,
        "provider_key": provider_key,
        "provider_name": provider.provider_name,
        "gate_report_path": _display_path(gate_path, root),
        "diagnostic_mode": diagnostic_mode,
        "original_gate_verdict": original_gate_verdict,
        "verdict": verdict,
        "original_gate_receipt_id": original_receipt_id,
        "recalculated_gate_receipt_id": recalculated_receipt_id,
        "original_gate_receipt_checksum_sha256": original_receipt_checksum,
        "recalculated_gate_receipt_checksum_sha256": recalculated_receipt_checksum,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "merge_base_sha": merge_base_sha,
        "current_head_sha": current_head,
        "current_merge_base_sha": current_merge_base,
        "gate_mode": gate_mode,
        "expected_changed_files": saved_changed_files,
        "current_changed_files": actual_changed_files,
        "expected_changed_files_digest": expected_changed_digest,
        "current_changed_files_digest": current_changed_digest,
        "expected_evidence_digest": expected_evidence_digest,
        "current_evidence_digest": current_evidence_digest,
        "expected_policy_change_digest": expected_policy_change_digest,
        "current_policy_change_digest": current_policy_change_digest,
        "expected_policy_checksum_sha256": expected_policy_checksum,
        "current_policy_checksum_sha256": current_policy_checksum,
        "comparison_context_status": (
            VERIFIED_STATUS if git_context_matches else GIT_CONTEXT_CHANGED_STATUS
        ),
        "receipt_binding_status": (
            VERIFIED_STATUS if receipt_matches else RECEIPT_ID_MISMATCH_STATUS
        ),
        "mismatches": mismatches,
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "checks": rows,
        "safety": {
            "read_only": True,
            "policy_edited": False,
            "provider_allowlisted": False,
            "cron_enabled": False,
            "live_provider_run": False,
        },
    }
    return pd.DataFrame(rows, columns=VERIFICATION_COLUMNS), summary


def render_provider_policy_pr_gate_receipt_verification(
    checks: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    mismatches = summary.get("mismatches")
    mismatch_items = mismatches if isinstance(mismatches, list) else []
    lines = [
        "# Provider Policy PR Gate Receipt Verification",
        "",
        "- Provider: **"
        f"{summary.get('provider_name') or summary.get('provider_key') or 'Unknown'}"
        "**",
        f"- Final verdict: **{summary.get('verdict') or 'Unknown'}**",
        f"- Gate report: `{summary.get('gate_report_path') or 'Missing'}`",
        f"- Original receipt ID: `{summary.get('original_gate_receipt_id') or 'Missing'}`",
        "- Recalculated receipt ID: `"
        f"{summary.get('recalculated_gate_receipt_id') or 'Unavailable'}`",
        f"- Base SHA: `{summary.get('base_sha') or 'Missing'}`",
        f"- Head SHA: `{summary.get('head_sha') or 'Missing'}`",
        f"- Merge-base SHA: `{summary.get('merge_base_sha') or 'Missing'}`",
        f"- Changed-files digest: `{summary.get('current_changed_files_digest') or 'Unavailable'}`",
        f"- Evidence digest: `{summary.get('current_evidence_digest') or 'Unavailable'}`",
        f"- Policy-change digest: `{summary.get('current_policy_change_digest') or 'Unavailable'}`",
        "",
        "## Verification checks",
        "",
    ]
    if checks.empty:
        lines.append("No verification checks were available.")
    else:
        lines.append(
            checks.loc[
                :, ["category", "check", "status", "expected", "observed"]
            ].to_markdown(index=False)
        )
    lines.extend(["", "## Mismatches and blockers", ""])
    blocker_checks = checks.loc[
        ~checks["status"].isin({VERIFIED_STATUS, NOT_APPLICABLE_STATUS})
    ] if not checks.empty else checks
    if not blocker_checks.empty:
        lines.append(
            blocker_checks.loc[
                :, ["check", "status", "expected", "observed", "details"]
            ].to_markdown(index=False)
        )
    elif mismatch_items:
        lines.extend(f"- {item}" for item in mismatch_items)
    else:
        lines.append("- None. Every bound input still matches the passing gate receipt.")
    lines.extend(
        [
            "",
            "## Safety boundary",
            "",
            "This verification is read-only except for these report outputs. "
            "Nothing was applied. It did not edit provider policy, allowlist a "
            "provider, run a provider, promote staging, enable cron, generate "
            "picks, place bets, or modify protected manual data.",
        ]
    )
    return "\n".join(lines) + "\n"


def save_provider_policy_pr_gate_receipt_verification(
    provider_name: str,
    output_dir: Path | None = None,
    **kwargs: object,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    checks, summary = build_provider_policy_pr_gate_receipt_verification(
        provider_name,
        **kwargs,
    )
    json_path = outputs / VERIFICATION_JSON_FILENAME
    markdown_path = outputs / VERIFICATION_MARKDOWN_FILENAME
    csv_path = outputs / VERIFICATION_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        render_provider_policy_pr_gate_receipt_verification(checks, summary).encode(
            "utf-8"
        ),
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
