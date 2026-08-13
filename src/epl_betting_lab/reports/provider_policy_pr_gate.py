from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
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
from epl_betting_lab.reports.provider_allowlist_evidence_bundle_verification import (
    VERIFICATION_JSON_FILENAME as BUNDLE_VERIFICATION_JSON_FILENAME,
    VERIFIED_VERDICT as VERIFIED_BUNDLE_VERDICT,
    build_provider_allowlist_evidence_bundle_verification,
)
from epl_betting_lab.reports.provider_allowlist_pr_conformance import (
    CONFORMANCE_JSON_FILENAME,
    CONFORMS_VERDICT,
    UNSAFE_AUTOMATION_STATUS,
    UNSAFE_AUTOMATION_VERDICT,
    build_provider_allowlist_pr_conformance,
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    PREVIEW_JSON_FILENAME,
    READY_STATUS,
    REQUIRED_VERIFICATION_VERDICT,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt_verification import (
    VERIFICATION_JSON_FILENAME as RECEIPT_VERIFICATION_JSON_FILENAME,
)


POLICY_RELATIVE_PATH = "data/manual/staging_provider_policy.json"
GATE_JSON_FILENAME = "provider_policy_pr_gate.json"
GATE_MARKDOWN_FILENAME = "provider_policy_pr_gate.md"
GATE_CSV_FILENAME = "provider_policy_pr_gate.csv"

PASSED_STATUS = "Passed"
NOT_APPLICABLE_STATUS = "Not applicable"
MISSING_VERIFIED_BUNDLE_STATUS = "Missing verified bundle"
MISSING_CONFORMANCE_STATUS = "Missing conformance report"
CONFORMANCE_FAILED_STATUS = "Conformance failed"
RECEIPT_FAILED_STATUS = "Receipt verification failed"
UNSAFE_AUTOMATION_STATUS_GATE = "Unsafe automation change"
FAILED_STATUS = "Failed"
BOUND_STATUS = "Bound"
MISSING_GIT_CONTEXT_STATUS = "Missing Git context"
MISSING_CHANGED_FILE_DIGEST_STATUS = "Missing changed-file digest"
MISSING_EVIDENCE_DIGEST_STATUS = "Missing evidence digest"
DIGEST_MISMATCH_STATUS = "Digest mismatch"

GATE_STATUSES = (
    PASSED_STATUS,
    NOT_APPLICABLE_STATUS,
    MISSING_VERIFIED_BUNDLE_STATUS,
    MISSING_CONFORMANCE_STATUS,
    CONFORMANCE_FAILED_STATUS,
    RECEIPT_FAILED_STATUS,
    UNSAFE_AUTOMATION_STATUS_GATE,
    FAILED_STATUS,
    BOUND_STATUS,
    MISSING_GIT_CONTEXT_STATUS,
    MISSING_CHANGED_FILE_DIGEST_STATUS,
    MISSING_EVIDENCE_DIGEST_STATUS,
    DIGEST_MISMATCH_STATUS,
)

RECEIPT_BINDING_STATUSES = (
    BOUND_STATUS,
    MISSING_GIT_CONTEXT_STATUS,
    MISSING_CHANGED_FILE_DIGEST_STATUS,
    MISSING_EVIDENCE_DIGEST_STATUS,
    DIGEST_MISMATCH_STATUS,
    NOT_APPLICABLE_STATUS,
)

PASSED_VERDICT = "Provider policy PR gate passed"
NOT_APPLICABLE_VERDICT = "Provider policy PR gate not applicable"
BLOCKED_VERDICT = "Provider policy PR gate blocked"
FAILED_VERDICT = "Provider policy PR gate failed"
GATE_VERDICTS = (
    PASSED_VERDICT,
    NOT_APPLICABLE_VERDICT,
    BLOCKED_VERDICT,
    FAILED_VERDICT,
)

GATE_COLUMNS = (
    "category",
    "check",
    "evidence_path",
    "expected",
    "observed",
    "status",
    "details",
    "gate_receipt_id",
    "base_sha",
    "head_sha",
    "changed_files_digest",
    "evidence_digest",
    "policy_change_digest",
    "receipt_binding_status",
)

_SAFE_GIT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+~^{}-]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


@dataclass(frozen=True)
class PolicyChangeDetection:
    policy_changed: bool
    changed_files: tuple[str, ...]
    source: str
    base_ref: str = ""
    head_ref: str = ""
    base_sha: str = ""
    head_sha: str = ""
    merge_base_sha: str = ""
    gate_mode: str = ""
    error: str = ""


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


def _provider_matches(payload: Mapping[str, object], provider_name: str) -> bool:
    requested = _slug(provider_name)
    return requested in {
        _slug(payload.get("provider_key")),
        _slug(payload.get("provider_name")),
    }


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repository_root).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _normalize_changed_file(value: object) -> str:
    normalized = _clean(value).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _valid_git_ref(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 255
        and not value.startswith("-")
        and ".." not in value
        and bool(_SAFE_GIT_REF.fullmatch(value))
    )


def _git_command(
    repository_root: Path,
    args: Sequence[str],
) -> tuple[str, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return "", f"Git could not run: {exc}"
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        return "", f"Git command failed: {detail or 'unknown error'}"
    return completed.stdout, ""


def _git_binary_command(
    repository_root: Path,
    args: Sequence[str],
) -> tuple[bytes, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repository_root,
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        return b"", f"Git could not run: {exc}"
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        return b"", f"Git command failed: {detail or 'unknown error'}"
    return completed.stdout, ""


def _git_ref_exists(repository_root: Path, reference: str) -> bool:
    if not _valid_git_ref(reference):
        return False
    _, error = _git_command(
        repository_root,
        ["rev-parse", "--verify", "--quiet", f"{reference}^{{commit}}"],
    )
    return not error


def _resolve_git_commit(repository_root: Path, reference: str) -> tuple[str, str]:
    if not _valid_git_ref(reference):
        return "", f"Unsafe or malformed Git ref: `{reference or 'blank'}`."
    output, error = _git_command(
        repository_root,
        ["rev-parse", "--verify", f"{reference}^{{commit}}"],
    )
    return (_clean(output.splitlines()[0]) if output else ""), error


def _resolve_git_comparison(
    repository_root: Path,
    *,
    base_ref: str,
    head_ref: str,
) -> tuple[str, str, str, str]:
    base_sha, base_error = _resolve_git_commit(repository_root, base_ref)
    head_sha, head_error = _resolve_git_commit(repository_root, head_ref)
    if base_error or head_error:
        return base_sha, head_sha, "", base_error or head_error
    merge_base, merge_error = _git_command(
        repository_root,
        ["merge-base", base_sha, head_sha],
    )
    return base_sha, head_sha, _clean(merge_base), merge_error


def _working_tree_changed_files(repository_root: Path) -> tuple[set[str], str]:
    output, error = _git_command(
        repository_root,
        ["diff", "--no-renames", "--name-only", "HEAD", "--"],
    )
    if error:
        return set(), error
    return {
        normalized
        for line in output.splitlines()
        if (normalized := _normalize_changed_file(line))
    }, ""


def _is_ci_pull_request(environment: Mapping[str, str]) -> bool:
    return (
        _clean(environment.get("GITHUB_ACTIONS")).casefold() == "true"
        and _clean(environment.get("GITHUB_EVENT_NAME")).casefold().startswith(
            "pull_request"
        )
    )


def _gate_mode(
    environment: Mapping[str, str],
    *,
    working_tree_changed: bool,
) -> str:
    if _is_ci_pull_request(environment):
        return "ci_pr"
    return "local_worktree" if working_tree_changed else "local_git"


def _git_changed_files(
    repository_root: Path,
    *,
    base_ref: str,
    head_ref: str,
    merge_base: bool,
) -> tuple[set[str], str]:
    if not _valid_git_ref(base_ref) or not _valid_git_ref(head_ref):
        return set(), "Base and head refs must be safe Git refs or commit SHAs."
    if not _git_ref_exists(repository_root, base_ref):
        return set(), f"Base ref is unavailable: `{base_ref}`."
    if not _git_ref_exists(repository_root, head_ref):
        return set(), f"Head ref is unavailable: `{head_ref}`."
    refs = [f"{base_ref}...{head_ref}"] if merge_base else [base_ref, head_ref]
    output, error = _git_command(
        repository_root,
        ["diff", "--no-renames", "--name-only", *refs, "--"],
    )
    if error:
        return set(), error
    return {
        normalized
        for line in output.splitlines()
        if (normalized := _normalize_changed_file(line))
    }, ""


def detect_provider_policy_change(
    repository_root: Path | None = None,
    *,
    policy_relative_path: str = POLICY_RELATIVE_PATH,
    base_ref: str | None = None,
    head_ref: str | None = None,
    changed_files: Sequence[str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> PolicyChangeDetection:
    root = (repository_root or PROJECT_ROOT).resolve()
    expected = _normalize_changed_file(policy_relative_path)
    env = environment if environment is not None else os.environ
    selected_base = _clean(base_ref or env.get("PROVIDER_POLICY_BASE_REF"))
    selected_head = _clean(
        head_ref or env.get("PROVIDER_POLICY_HEAD_REF") or "HEAD"
    )
    if changed_files is not None:
        normalized = tuple(
            sorted(
                {
                    path
                    for value in changed_files
                    if (path := _normalize_changed_file(value))
                }
            )
        )
        working, working_error = _working_tree_changed_files(root)
        base_sha = ""
        head_sha = ""
        merge_base_sha = ""
        comparison_error = ""
        if selected_base:
            base_sha, head_sha, merge_base_sha, comparison_error = (
                _resolve_git_comparison(
                    root,
                    base_ref=selected_base,
                    head_ref=selected_head,
                )
            )
        elif head_ref:
            comparison_error = "A head ref was supplied without a base ref."
        return PolicyChangeDetection(
            policy_changed=expected in normalized,
            changed_files=normalized,
            source="Provided changed-file list",
            base_ref=selected_base,
            head_ref=selected_head if selected_base or head_ref else "",
            base_sha=base_sha,
            head_sha=head_sha,
            merge_base_sha=merge_base_sha,
            gate_mode=_gate_mode(
                env,
                working_tree_changed=bool(working),
            ),
            error=comparison_error or (working_error if selected_base else ""),
        )

    if selected_base:
        files, error = _git_changed_files(
            root,
            base_ref=selected_base,
            head_ref=selected_head,
            merge_base=False,
        )
        working, working_error = _working_tree_changed_files(root)
        base_sha, head_sha, merge_base_sha, comparison_error = (
            _resolve_git_comparison(
                root,
                base_ref=selected_base,
                head_ref=selected_head,
            )
        )
        normalized = tuple(sorted(files))
        return PolicyChangeDetection(
            policy_changed=expected in files,
            changed_files=normalized,
            source="Explicit base/head Git diff",
            base_ref=selected_base,
            head_ref=selected_head,
            base_sha=base_sha,
            head_sha=head_sha,
            merge_base_sha=merge_base_sha,
            gate_mode=_gate_mode(
                env,
                working_tree_changed=bool(working),
            ),
            error=error or comparison_error or working_error,
        )
    if head_ref:
        return PolicyChangeDetection(
            policy_changed=False,
            changed_files=(),
            source="Explicit base/head Git diff",
            head_ref=selected_head,
            gate_mode=_gate_mode(env, working_tree_changed=False),
            error="A head ref was supplied without a base ref.",
        )

    local_base = next(
        (
            candidate
            for candidate in ("origin/main", "main", "origin/master", "master")
            if _git_ref_exists(root, candidate)
        ),
        "",
    )
    if not local_base:
        return PolicyChangeDetection(
            policy_changed=False,
            changed_files=(),
            source="Local Git fallback",
            head_ref="HEAD",
            gate_mode="local_git",
            error=(
                "Could not find origin/main, main, origin/master, or master. "
                "Pass --base-ref and --head-ref explicitly."
            ),
        )
    committed, committed_error = _git_changed_files(
        root,
        base_ref=local_base,
        head_ref="HEAD",
        merge_base=True,
    )
    working, working_error = _working_tree_changed_files(root)
    base_sha, head_sha, merge_base_sha, comparison_error = _resolve_git_comparison(
        root,
        base_ref=local_base,
        head_ref="HEAD",
    )
    error = committed_error or working_error or comparison_error
    files = committed | working
    return PolicyChangeDetection(
        policy_changed=expected in files,
        changed_files=tuple(sorted(files)),
        source="Local Git diff against default branch",
        base_ref=local_base,
        head_ref="HEAD",
        base_sha=base_sha,
        head_sha=head_sha,
        merge_base_sha=merge_base_sha,
        gate_mode=_gate_mode(env, working_tree_changed=bool(working)),
        error=error,
    )


def _resolve_json_path(
    selected: Path,
    *,
    repository_root: Path,
    label: str,
) -> tuple[Path, str]:
    candidate = selected if selected.is_absolute() else repository_root / selected
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(repository_root)
    except (OSError, RuntimeError, ValueError):
        return candidate, f"{label} must stay inside the repository."
    if resolved.suffix.casefold() != ".json":
        return resolved, f"{label} must be a JSON file."
    if path_contains_symlink(candidate.absolute(), repository_root):
        return resolved, f"{label} cannot use a symbolic link."
    if not resolved.exists():
        return resolved, f"{label} is missing."
    if not resolved.is_file() or resolved.is_symlink():
        return resolved, f"{label} must be a regular, non-symlinked file."
    return resolved, ""


def _read_json_object(path: Path, *, label: str) -> tuple[dict[str, object] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{label} is unreadable or malformed: {exc}"
    if not isinstance(payload, dict):
        return None, f"{label} must contain one JSON object."
    return payload, ""


def _load_json_evidence(
    selected: Path,
    *,
    repository_root: Path,
    label: str,
) -> tuple[Path, dict[str, object] | None, str]:
    path, path_error = _resolve_json_path(
        selected,
        repository_root=repository_root,
        label=label,
    )
    if path_error:
        return path, None, path_error
    payload, read_error = _read_json_object(path, label=label)
    return path, payload, read_error


def _canonical_sha256(payload: object) -> str:
    return sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _valid_repository_relative_path(value: str) -> bool:
    path = Path(value)
    return (
        bool(value)
        and not path.is_absolute()
        and ".." not in path.parts
        and (not path.parts or path.parts[0] != ".git")
    )


def _git_file_checksum(
    repository_root: Path,
    *,
    commit_sha: str,
    relative_path: str,
) -> tuple[str, str]:
    if not _GIT_COMMIT_PATTERN.fullmatch(commit_sha.casefold()):
        return "", "Git commit SHA is missing or malformed."
    if not _valid_repository_relative_path(relative_path):
        return "", f"Unsafe repository path: `{relative_path}`."
    content, error = _git_binary_command(
        repository_root,
        ["show", f"{commit_sha}:{relative_path}"],
    )
    return (sha256(content).hexdigest() if not error else ""), error


def _current_file_checksum(
    path: Path,
    *,
    repository_root: Path,
) -> tuple[str, str]:
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(repository_root)
    except (OSError, RuntimeError, ValueError):
        return "", "File path must stay inside the repository."
    if path_contains_symlink(path.absolute(), repository_root):
        return "", "Symbolic links are not accepted for receipt evidence."
    if not resolved.exists():
        return "", "File is missing."
    if not resolved.is_file() or resolved.is_symlink():
        return "", "Path is not a regular, non-symlinked file."
    try:
        return file_sha256(resolved), ""
    except OSError as exc:
        return "", f"File could not be hashed: {exc}"


def _deleted_path_checksum(relative_path: str) -> str:
    return _canonical_sha256(
        {
            "path": relative_path,
            "state": "deleted_from_head_or_worktree",
        }
    )


def _changed_file_digest_records(
    detection: PolicyChangeDetection,
    *,
    repository_root: Path,
) -> tuple[list[dict[str, str]], str, list[str]]:
    records: list[dict[str, str]] = []
    issues: list[str] = []
    comparison_start = detection.merge_base_sha or detection.base_sha
    for relative_path in sorted(set(detection.changed_files)):
        checksum = ""
        status = "Hashed"
        source = "working tree" if detection.gate_mode == "local_worktree" else "head commit"
        error = ""
        if detection.gate_mode == "local_worktree":
            candidate = repository_root / relative_path
            checksum, error = _current_file_checksum(
                candidate,
                repository_root=repository_root,
            )
            if error and "missing" in error.casefold():
                head_checksum, head_error = _git_file_checksum(
                    repository_root,
                    commit_sha=detection.head_sha,
                    relative_path=relative_path,
                )
                base_checksum, base_error = _git_file_checksum(
                    repository_root,
                    commit_sha=comparison_start,
                    relative_path=relative_path,
                )
                if (head_checksum or base_checksum) and (not head_checksum or not head_error):
                    checksum = _deleted_path_checksum(relative_path)
                    status = "Deleted"
                    source = "deletion marker"
                    error = ""
                elif not base_error and base_checksum:
                    checksum = _deleted_path_checksum(relative_path)
                    status = "Deleted"
                    source = "deletion marker"
                    error = ""
        else:
            checksum, error = _git_file_checksum(
                repository_root,
                commit_sha=detection.head_sha,
                relative_path=relative_path,
            )
            if error:
                base_checksum, base_error = _git_file_checksum(
                    repository_root,
                    commit_sha=comparison_start,
                    relative_path=relative_path,
                )
                if not base_error and base_checksum:
                    checksum = _deleted_path_checksum(relative_path)
                    status = "Deleted"
                    source = "deletion marker"
                    error = ""
        if error or not _SHA256_PATTERN.fullmatch(checksum.casefold()):
            status = "Missing digest"
            issues.append(f"`{relative_path}` could not be bound: {error or 'invalid digest'}")
        records.append(
            {
                "path": relative_path,
                "checksum_sha256": checksum.casefold(),
                "status": status,
                "content_source": source,
            }
        )
    if all(
        _SHA256_PATTERN.fullmatch(record["checksum_sha256"])
        for record in records
    ):
        digest = _canonical_sha256(
            [
                {
                    "path": record["path"],
                    "checksum_sha256": record["checksum_sha256"],
                }
                for record in records
            ]
        )
    else:
        digest = ""
    return records, digest, issues


def _evidence_digest_records(
    evidence_paths: Mapping[str, Path],
    *,
    repository_root: Path,
    required: bool,
) -> tuple[list[dict[str, str]], str, list[str]]:
    records: list[dict[str, str]] = []
    issues: list[str] = []
    for field_name, path in sorted(evidence_paths.items()):
        checksum, error = _current_file_checksum(
            path,
            repository_root=repository_root,
        )
        relative_path = _display_path(path, repository_root)
        status = "Included" if checksum else "Missing digest"
        if required and (error or not _SHA256_PATTERN.fullmatch(checksum.casefold())):
            issues.append(
                f"`{relative_path}` could not be bound: {error or 'invalid digest'}"
            )
        records.append(
            {
                "field": field_name,
                "path": relative_path,
                "checksum_sha256": checksum.casefold(),
                "status": status,
            }
        )
    valid_records = [
        {
            "field": record["field"],
            "path": record["path"],
            "checksum_sha256": record["checksum_sha256"],
        }
        for record in records
        if _SHA256_PATTERN.fullmatch(record["checksum_sha256"])
    ]
    if required and len(valid_records) != len(evidence_paths):
        digest = ""
    else:
        digest = _canonical_sha256(valid_records)
    return records, digest, issues


def calculate_provider_policy_gate_receipt_identity(
    *,
    provider_key: str,
    base_sha: str,
    head_sha: str,
    changed_file_digests: Sequence[Mapping[str, object]],
    changed_files_digest: str,
    policy_checksum_after_sha256: str,
    evidence_checksums: Sequence[Mapping[str, object]],
    evidence_digest: str,
    final_verdict: str,
) -> tuple[str, str]:
    """Return the canonical checksum and ID for one exact gate comparison."""
    normalized_changed = sorted(
        (
            {
                "path": _normalize_changed_file(item.get("path")),
                "checksum_sha256": _clean(item.get("checksum_sha256")).casefold(),
            }
            for item in changed_file_digests
        ),
        key=lambda item: (item["path"], item["checksum_sha256"]),
    )
    normalized_evidence = sorted(
        (
            {
                "field": _clean(item.get("field")),
                "path": _normalize_changed_file(item.get("path")),
                "checksum_sha256": _clean(item.get("checksum_sha256")).casefold(),
            }
            for item in evidence_checksums
        ),
        key=lambda item: (item["field"], item["path"], item["checksum_sha256"]),
    )
    payload = {
        "provider_key": _slug(provider_key),
        "base_sha": _clean(base_sha).casefold(),
        "head_sha": _clean(head_sha).casefold(),
        "changed_files": normalized_changed,
        "changed_files_digest": _clean(changed_files_digest).casefold(),
        "policy_checksum_after_sha256": _clean(
            policy_checksum_after_sha256
        ).casefold(),
        "evidence": normalized_evidence,
        "evidence_digest": _clean(evidence_digest).casefold(),
        "final_verdict": _clean(final_verdict),
    }
    digest = _canonical_sha256(payload)
    return digest, f"{_slug(provider_key)}-provider-policy-gate-{digest}"


def _build_receipt_binding(
    *,
    provider_key: str,
    detection: PolicyChangeDetection,
    repository_root: Path,
    policy_relative_path: str,
    evidence_paths: Mapping[str, Path],
) -> dict[str, object]:
    changed_records, changed_digest, changed_issues = _changed_file_digest_records(
        detection,
        repository_root=repository_root,
    )
    evidence_records, evidence_digest, evidence_issues = _evidence_digest_records(
        evidence_paths,
        repository_root=repository_root,
        required=detection.policy_changed,
    )
    comparison_start = detection.merge_base_sha or detection.base_sha
    policy_before, _ = _git_file_checksum(
        repository_root,
        commit_sha=comparison_start,
        relative_path=policy_relative_path,
    )
    changed_by_path = {record["path"]: record for record in changed_records}
    policy_record = changed_by_path.get(policy_relative_path, {})
    policy_after = (
        _clean(policy_record.get("checksum_sha256")).casefold()
        if _clean(policy_record.get("status")) != "Deleted"
        else ""
    )
    if not policy_after:
        if detection.gate_mode == "local_worktree":
            policy_after, _ = _current_file_checksum(
                repository_root / policy_relative_path,
                repository_root=repository_root,
            )
        else:
            policy_after, _ = _git_file_checksum(
                repository_root,
                commit_sha=detection.head_sha,
                relative_path=policy_relative_path,
            )
    policy_change_digest = (
        _canonical_sha256(
            {
                "path": policy_relative_path,
                "before_checksum_sha256": policy_before.casefold(),
                "after_checksum_sha256": policy_after.casefold(),
            }
        )
        if _SHA256_PATTERN.fullmatch(policy_after.casefold())
        else ""
    )

    mismatches: list[str] = []
    checked_out_head, checked_out_error = _resolve_git_commit(
        repository_root,
        "HEAD",
    )
    comparison_context_status = BOUND_STATUS
    if not detection.base_sha or not detection.head_sha:
        comparison_context_status = MISSING_GIT_CONTEXT_STATUS
    elif detection.gate_mode != "local_worktree" and checked_out_error:
        comparison_context_status = MISSING_GIT_CONTEXT_STATUS
    elif (
        detection.gate_mode != "local_worktree"
        and not checked_out_error
        and checked_out_head != detection.head_sha
    ):
        comparison_context_status = DIGEST_MISMATCH_STATUS
        mismatches.append(
            "The checked-out HEAD does not match the requested comparison head SHA."
        )

    for record in evidence_records:
        changed_record = changed_by_path.get(record["path"])
        if (
            changed_record
            and _SHA256_PATTERN.fullmatch(record["checksum_sha256"])
            and _SHA256_PATTERN.fullmatch(changed_record["checksum_sha256"])
            and record["checksum_sha256"] != changed_record["checksum_sha256"]
        ):
            mismatches.append(
                f"Evidence digest for `{record['path']}` differs from its changed-file digest."
            )
    if (
        policy_record
        and _SHA256_PATTERN.fullmatch(policy_after.casefold())
        and _SHA256_PATTERN.fullmatch(
            _clean(policy_record.get("checksum_sha256")).casefold()
        )
        and policy_after.casefold()
        != _clean(policy_record.get("checksum_sha256")).casefold()
    ):
        mismatches.append(
            "The current provider-policy checksum differs from its changed-file digest."
        )

    evidence_checksums = {
        record["field"]: record["checksum_sha256"] for record in evidence_records
    }
    if not detection.policy_changed:
        binding_status = NOT_APPLICABLE_STATUS
        binding_note = (
            "No provider-policy change was detected, so approval evidence binding "
            "is not required."
        )
    elif comparison_context_status != BOUND_STATUS:
        binding_status = comparison_context_status
        binding_note = "Exact PR base/head Git context is unavailable or inconsistent."
    elif changed_issues or not changed_digest or not policy_change_digest:
        binding_status = MISSING_CHANGED_FILE_DIGEST_STATUS
        binding_note = " ".join(changed_issues) or (
            "One or more changed files or the current policy could not be hashed."
        )
    elif evidence_issues or not evidence_digest:
        binding_status = MISSING_EVIDENCE_DIGEST_STATUS
        binding_note = " ".join(evidence_issues) or (
            "One or more required evidence reports could not be hashed."
        )
    elif mismatches:
        binding_status = DIGEST_MISMATCH_STATUS
        binding_note = " ".join(mismatches)
    else:
        binding_status = BOUND_STATUS
        binding_note = (
            "The exact Git comparison, changed-file contents, current policy, and "
            "required evidence reports are checksum-bound."
        )

    return {
        "provider_key": provider_key,
        "base_sha": detection.base_sha,
        "head_sha": detection.head_sha,
        "merge_base_sha": detection.merge_base_sha,
        "gate_mode": detection.gate_mode,
        "changed_file_digests": changed_records,
        "changed_files_digest": changed_digest,
        "policy_checksum_before_sha256": policy_before.casefold(),
        "policy_checksum_after_sha256": policy_after.casefold(),
        "policy_change_digest": policy_change_digest,
        "evidence_reports": evidence_records,
        "evidence_digest": evidence_digest,
        **evidence_checksums,
        "comparison_context_status": comparison_context_status,
        "receipt_binding_status": binding_status,
        "receipt_binding_note": binding_note,
        "digest_mismatches": mismatches,
        "gate_receipt_checksum_sha256": "",
        "gate_receipt_id": "",
    }


def _add_check(
    rows: list[dict[str, object]],
    *,
    category: str,
    check: str,
    status: str,
    evidence_path: object = "",
    expected: object = "",
    observed: object = "",
    details: str,
) -> None:
    if status not in GATE_STATUSES:
        raise ValueError(f"Unexpected provider policy PR gate status: {status}")
    rows.append(
        {
            "category": category,
            "check": check,
            "evidence_path": _clean(evidence_path),
            "expected": _clean(expected),
            "observed": _clean(observed),
            "status": status,
            "details": details,
            "gate_receipt_id": "",
            "base_sha": "",
            "head_sha": "",
            "changed_files_digest": "",
            "evidence_digest": "",
            "policy_change_digest": "",
            "receipt_binding_status": "",
        }
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _unsafe_conformance(
    checks: pd.DataFrame,
    summary: Mapping[str, object],
    stored: Mapping[str, object],
) -> bool:
    current_statuses = set(checks.get("status", pd.Series(dtype=str)).astype(str))
    stored_checks = stored.get("checks")
    stored_statuses = {
        _clean(item.get("status"))
        for item in stored_checks
        if isinstance(item, Mapping)
    } if isinstance(stored_checks, list) else set()
    return (
        _clean(summary.get("verdict")) == UNSAFE_AUTOMATION_VERDICT
        or _clean(stored.get("verdict")) == UNSAFE_AUTOMATION_VERDICT
        or UNSAFE_AUTOMATION_STATUS in current_statuses
        or UNSAFE_AUTOMATION_STATUS in stored_statuses
    )


def _gate_verdict(rows: Sequence[Mapping[str, object]]) -> str:
    statuses = {_clean(row.get("status")) for row in rows}
    if FAILED_STATUS in statuses:
        return FAILED_VERDICT
    if statuses == {NOT_APPLICABLE_STATUS}:
        return NOT_APPLICABLE_VERDICT
    if statuses and statuses <= {PASSED_STATUS, BOUND_STATUS}:
        return PASSED_VERDICT
    return BLOCKED_VERDICT


def _blockers(rows: Sequence[Mapping[str, object]]) -> list[str]:
    return list(
        dict.fromkeys(
            f"{row.get('check', 'Check')}: {row.get('details', '')}"
            for row in rows
            if _clean(row.get("status"))
            not in {PASSED_STATUS, BOUND_STATUS, NOT_APPLICABLE_STATUS}
        )
    )


def _build_summary(
    *,
    provider_key: str,
    provider_name: str,
    detection: PolicyChangeDetection,
    policy_relative_path: str,
    receipt_binding: dict[str, object],
    rows: list[dict[str, object]],
    run_at: datetime | None,
) -> dict[str, object]:
    verdict = _gate_verdict(rows)
    if verdict not in GATE_VERDICTS:
        raise ValueError(f"Unexpected provider policy PR gate verdict: {verdict}")
    status_counts = Counter(_clean(row.get("status")) for row in rows)
    generated_at = (run_at or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    binding_status = _clean(receipt_binding.get("receipt_binding_status"))
    can_issue_receipt = (
        binding_status == BOUND_STATUS
        or (
            binding_status == NOT_APPLICABLE_STATUS
            and _clean(receipt_binding.get("comparison_context_status"))
            == BOUND_STATUS
        )
    )
    if can_issue_receipt:
        receipt_checksum, receipt_id = calculate_provider_policy_gate_receipt_identity(
            provider_key=provider_key,
            base_sha=_clean(receipt_binding.get("base_sha")),
            head_sha=_clean(receipt_binding.get("head_sha")),
            changed_file_digests=(
                receipt_binding.get("changed_file_digests")
                if isinstance(receipt_binding.get("changed_file_digests"), list)
                else []
            ),
            changed_files_digest=_clean(
                receipt_binding.get("changed_files_digest")
            ),
            policy_checksum_after_sha256=_clean(
                receipt_binding.get("policy_checksum_after_sha256")
            ),
            evidence_checksums=(
                receipt_binding.get("evidence_reports")
                if isinstance(receipt_binding.get("evidence_reports"), list)
                else []
            ),
            evidence_digest=_clean(receipt_binding.get("evidence_digest")),
            final_verdict=verdict,
        )
        receipt_binding["gate_receipt_checksum_sha256"] = receipt_checksum
        receipt_binding["gate_receipt_id"] = receipt_id

    common_row_fields = {
        "gate_receipt_id": _clean(receipt_binding.get("gate_receipt_id")),
        "base_sha": _clean(receipt_binding.get("base_sha")),
        "head_sha": _clean(receipt_binding.get("head_sha")),
        "changed_files_digest": _clean(
            receipt_binding.get("changed_files_digest")
        ),
        "evidence_digest": _clean(receipt_binding.get("evidence_digest")),
        "policy_change_digest": _clean(
            receipt_binding.get("policy_change_digest")
        ),
        "receipt_binding_status": binding_status,
    }
    for row in rows:
        row.update(common_row_fields)

    return {
        "schema_version": 2,
        "generated_at": generated_at,
        "gate_generated_at": generated_at,
        "provider_key": provider_key,
        "provider_name": provider_name,
        "policy_path": policy_relative_path,
        "policy_changed": detection.policy_changed,
        "base_sha": _clean(receipt_binding.get("base_sha")),
        "head_sha": _clean(receipt_binding.get("head_sha")),
        "merge_base_sha": _clean(receipt_binding.get("merge_base_sha")),
        "gate_mode": _clean(receipt_binding.get("gate_mode")),
        "changed_files": list(detection.changed_files),
        "changed_file_digests": receipt_binding.get("changed_file_digests", []),
        "changed_files_digest": _clean(
            receipt_binding.get("changed_files_digest")
        ),
        "policy_checksum_before_sha256": _clean(
            receipt_binding.get("policy_checksum_before_sha256")
        ),
        "policy_checksum_after_sha256": _clean(
            receipt_binding.get("policy_checksum_after_sha256")
        ),
        "policy_change_digest": _clean(
            receipt_binding.get("policy_change_digest")
        ),
        "evidence_reports": receipt_binding.get("evidence_reports", []),
        "evidence_bundle_verification_checksum_sha256": _clean(
            receipt_binding.get(
                "evidence_bundle_verification_checksum_sha256"
            )
        ),
        "conformance_report_checksum_sha256": _clean(
            receipt_binding.get("conformance_report_checksum_sha256")
        ),
        "preview_report_checksum_sha256": _clean(
            receipt_binding.get("preview_report_checksum_sha256")
        ),
        "receipt_verification_report_checksum_sha256": _clean(
            receipt_binding.get("receipt_verification_report_checksum_sha256")
        ),
        "evidence_digest": _clean(receipt_binding.get("evidence_digest")),
        "comparison_context_status": _clean(
            receipt_binding.get("comparison_context_status")
        ),
        "receipt_binding_status": binding_status,
        "receipt_binding_note": _clean(
            receipt_binding.get("receipt_binding_note")
        ),
        "gate_receipt_checksum_sha256": _clean(
            receipt_binding.get("gate_receipt_checksum_sha256")
        ),
        "gate_receipt_id": _clean(receipt_binding.get("gate_receipt_id")),
        "change_detection": {
            "source": detection.source,
            "base_ref": detection.base_ref,
            "head_ref": detection.head_ref,
            "base_sha": detection.base_sha,
            "head_sha": detection.head_sha,
            "merge_base_sha": detection.merge_base_sha,
            "gate_mode": detection.gate_mode,
            "changed_files": list(detection.changed_files),
            "error": detection.error,
        },
        "verdict": verdict,
        "status_counts": dict(sorted(status_counts.items())),
        "blockers": _blockers(rows),
        "checks": rows,
        "safety": {
            "read_only_gate": True,
            "provider_policy_edited": False,
            "provider_allowlisted": False,
            "receipt_created": False,
            "preview_created": False,
            "provider_run": False,
            "staging_promoted": False,
            "cron_enabled": False,
            "secrets_required": False,
            "protected_files_edited": False,
            "picks_generated": False,
            "bets_placed": False,
        },
    }


def build_provider_policy_pr_gate(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    policy_path: Path | None = None,
    bundle_verification_path: Path | None = None,
    conformance_path: Path | None = None,
    preview_path: Path | None = None,
    receipt_verification_path: Path | None = None,
    repository_root: Path | None = None,
    base_ref: str | None = None,
    head_ref: str | None = None,
    changed_files: Sequence[str] | None = None,
    environment: Mapping[str, str] | None = None,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    root = (repository_root or PROJECT_ROOT).resolve()
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    provider = create_provider(provider_name)
    provider_key = provider.provider_key
    provider_display_name = provider.provider_name
    selected_policy = policy_path or root / POLICY_RELATIVE_PATH
    policy_relative = POLICY_RELATIVE_PATH
    try:
        policy_relative = selected_policy.resolve(strict=False).relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError):
        detection = PolicyChangeDetection(
            policy_changed=False,
            changed_files=(),
            source="Policy path validation",
            error="Provider policy path must stay inside the repository.",
        )
    else:
        detection = detect_provider_policy_change(
            root,
            policy_relative_path=policy_relative,
            base_ref=base_ref,
            head_ref=head_ref,
            changed_files=changed_files,
            environment=environment,
        )

    rows: list[dict[str, object]] = []
    if detection.error:
        _add_check(
            rows,
            category="Change detection",
            check="Provider policy changed",
            status=FAILED_STATUS,
            evidence_path=POLICY_RELATIVE_PATH,
            expected="Deterministic base/head comparison",
            observed="Unknown",
            details=detection.error,
        )
        receipt_binding = _build_receipt_binding(
            provider_key=provider_key,
            detection=detection,
            repository_root=root,
            policy_relative_path=policy_relative,
            evidence_paths={},
        )
        summary = _build_summary(
            provider_key=provider_key,
            provider_name=provider_display_name,
            detection=detection,
            policy_relative_path=policy_relative,
            receipt_binding=receipt_binding,
            rows=rows,
            run_at=run_at,
        )
        return pd.DataFrame(rows, columns=GATE_COLUMNS), summary

    if not detection.policy_changed:
        _add_check(
            rows,
            category="Change detection",
            check="Provider policy changed",
            status=NOT_APPLICABLE_STATUS,
            evidence_path=POLICY_RELATIVE_PATH,
            expected="Policy path present in changed files",
            observed="Policy path unchanged",
            details=(
                "The provider policy did not change, so allowlist evidence is not "
                "required for this PR."
            ),
        )
        receipt_binding = _build_receipt_binding(
            provider_key=provider_key,
            detection=detection,
            repository_root=root,
            policy_relative_path=policy_relative,
            evidence_paths={},
        )
        summary = _build_summary(
            provider_key=provider_key,
            provider_name=provider_display_name,
            detection=detection,
            policy_relative_path=policy_relative,
            receipt_binding=receipt_binding,
            rows=rows,
            run_at=run_at,
        )
        return pd.DataFrame(rows, columns=GATE_COLUMNS), summary

    _add_check(
        rows,
        category="Change detection",
        check="Provider policy changed",
        status=PASSED_STATUS,
        evidence_path=POLICY_RELATIVE_PATH,
        expected="Policy path present in changed files",
        observed="Policy path changed",
        details="Verified provider evidence is required before this PR can pass.",
    )

    selected_bundle_verification = (
        bundle_verification_path or outputs / BUNDLE_VERIFICATION_JSON_FILENAME
    )
    selected_conformance = conformance_path or outputs / CONFORMANCE_JSON_FILENAME
    selected_preview = preview_path or outputs / PREVIEW_JSON_FILENAME
    selected_receipt_verification = (
        receipt_verification_path
        or outputs / RECEIPT_VERIFICATION_JSON_FILENAME
    )

    bundle_file, bundle_report, bundle_error = _load_json_evidence(
        selected_bundle_verification,
        repository_root=root,
        label="Provider allowlist evidence bundle verification",
    )
    bundle_issues: list[str] = []
    current_bundle_summary: Mapping[str, object] = {}
    if bundle_error:
        bundle_issues.append(bundle_error)
    elif bundle_report is not None:
        if not _provider_matches(bundle_report, provider_key):
            bundle_issues.append("Bundle verification belongs to another provider.")
        if _clean(bundle_report.get("verdict")) != VERIFIED_BUNDLE_VERDICT:
            bundle_issues.append(
                "Stored bundle verification verdict is not approval-ready."
            )
        if _clean(bundle_report.get("conformance_verdict")) != CONFORMS_VERDICT:
            bundle_issues.append(
                "Verified bundle does not bind a conforming policy report."
            )
        bundle_path_text = _clean(bundle_report.get("bundle_path"))
        if not bundle_path_text:
            bundle_issues.append("Bundle verification does not identify its bundle.")
        else:
            try:
                _, current_bundle_summary = (
                    build_provider_allowlist_evidence_bundle_verification(
                        provider_key,
                        outputs,
                        bundle_path=Path(bundle_path_text),
                        repository_root=root,
                        run_at=run_at,
                    )
                )
            except Exception as exc:  # Report boundary must fail closed.
                bundle_issues.append(f"Bundle verification could not rerun: {exc}")
            else:
                if _clean(current_bundle_summary.get("verdict")) != VERIFIED_BUNDLE_VERDICT:
                    bundle_issues.append(
                        "Current evidence no longer verifies for PR approval review."
                    )
                if _clean(current_bundle_summary.get("conformance_verdict")) != CONFORMS_VERDICT:
                    bundle_issues.append(
                        "Current bundle does not include conforming policy evidence."
                    )
                for field in ("bundle_id", "bundle_checksum_sha256"):
                    if _clean(current_bundle_summary.get(field)) != _clean(
                        bundle_report.get(field)
                    ):
                        bundle_issues.append(
                            f"Current {field} differs from the stored verification."
                        )
    _add_check(
        rows,
        category="Evidence bundle",
        check="Verified allowlist evidence bundle",
        status=(
            MISSING_VERIFIED_BUNDLE_STATUS if bundle_issues else PASSED_STATUS
        ),
        evidence_path=_display_path(bundle_file, root),
        expected=VERIFIED_BUNDLE_VERDICT,
        observed=(
            _clean(bundle_report.get("verdict"))
            if bundle_report is not None
            else "Missing or unreadable"
        ),
        details=(
            " ".join(bundle_issues)
            if bundle_issues
            else "Stored and current bundle verification are approval-ready and match."
        ),
    )

    preview_file, preview, preview_error = _load_json_evidence(
        selected_preview,
        repository_root=root,
        label="Provider allowlist PR preview",
    )
    preview_issues: list[str] = []
    if preview_error:
        preview_issues.append(preview_error)
    elif preview is not None:
        if not _provider_matches(preview, provider_key):
            preview_issues.append("Allowlist preview belongs to another provider.")
        if _clean(preview.get("status")) != READY_STATUS:
            preview_issues.append("Allowlist preview is not ready for PR review.")
        if _clean(preview.get("proposed_allowlist_status")) != "Allowed":
            preview_issues.append("Allowlist preview does not propose Allowed status.")
    _add_check(
        rows,
        category="Preview",
        check="Ready provider allowlist preview",
        status=CONFORMANCE_FAILED_STATUS if preview_issues else PASSED_STATUS,
        evidence_path=_display_path(preview_file, root),
        expected=READY_STATUS,
        observed=(
            _clean(preview.get("status"))
            if preview is not None
            else "Missing or unreadable"
        ),
        details=(
            " ".join(preview_issues)
            if preview_issues
            else "The preview is ready and proposes the reviewed allowlist entry."
        ),
    )

    receipt_file, receipt_verification, receipt_error = _load_json_evidence(
        selected_receipt_verification,
        repository_root=root,
        label="Human acceptance receipt verification",
    )
    receipt_issues: list[str] = []
    if receipt_error:
        receipt_issues.append(receipt_error)
    elif receipt_verification is not None:
        if not _provider_matches(receipt_verification, provider_key):
            receipt_issues.append("Receipt verification belongs to another provider.")
        if (
            _clean(receipt_verification.get("verdict"))
            != REQUIRED_VERIFICATION_VERDICT
        ):
            receipt_issues.append("Human acceptance receipt is not verified.")
    _add_check(
        rows,
        category="Human review",
        check="Verified human acceptance receipt",
        status=RECEIPT_FAILED_STATUS if receipt_issues else PASSED_STATUS,
        evidence_path=_display_path(receipt_file, root),
        expected=REQUIRED_VERIFICATION_VERDICT,
        observed=(
            _clean(receipt_verification.get("verdict"))
            if receipt_verification is not None
            else "Missing or unreadable"
        ),
        details=(
            " ".join(receipt_issues)
            if receipt_issues
            else "Human acceptance evidence remains verified for allowlist PR review."
        ),
    )

    conformance_file, conformance, conformance_error = _load_json_evidence(
        selected_conformance,
        repository_root=root,
        label="Provider allowlist PR conformance report",
    )
    conformance_issues: list[str] = []
    current_conformance_checks = pd.DataFrame()
    current_conformance_summary: Mapping[str, object] = {}
    if conformance_error:
        conformance_issues.append(conformance_error)
    elif conformance is not None:
        if not _provider_matches(conformance, provider_key):
            conformance_issues.append("Conformance report belongs to another provider.")
        if _clean(conformance.get("verdict")) != CONFORMS_VERDICT:
            conformance_issues.append("Stored conformance verdict did not pass.")
        try:
            current_conformance_checks, current_conformance_summary = (
                build_provider_allowlist_pr_conformance(
                    provider_key,
                    outputs,
                    preview_path=preview_file,
                    policy_path=selected_policy,
                    repository_root=root,
                    run_at=run_at,
                )
            )
        except Exception as exc:  # Report boundary must fail closed.
            conformance_issues.append(f"Conformance could not rerun: {exc}")
        else:
            if _clean(current_conformance_summary.get("verdict")) != CONFORMS_VERDICT:
                conformance_issues.append(
                    "Current policy no longer conforms to the reviewed preview."
                )
            stored_policy = _mapping(conformance.get("policy"))
            current_policy = _mapping(current_conformance_summary.get("policy"))
            if _clean(stored_policy.get("checksum_sha256")) != _clean(
                current_policy.get("checksum_sha256")
            ):
                conformance_issues.append(
                    "Current policy checksum differs from the stored conformance report."
                )
    if conformance_error:
        conformance_status = MISSING_CONFORMANCE_STATUS
    elif _unsafe_conformance(
        current_conformance_checks,
        current_conformance_summary,
        conformance or {},
    ):
        conformance_status = UNSAFE_AUTOMATION_STATUS_GATE
    elif conformance_issues:
        conformance_status = CONFORMANCE_FAILED_STATUS
    else:
        conformance_status = PASSED_STATUS
    _add_check(
        rows,
        category="Policy conformance",
        check="Current policy conforms to reviewed preview",
        status=conformance_status,
        evidence_path=_display_path(conformance_file, root),
        expected=CONFORMS_VERDICT,
        observed=(
            _clean(conformance.get("verdict"))
            if conformance is not None
            else "Missing or unreadable"
        ),
        details=(
            " ".join(conformance_issues)
            if conformance_issues
            else "Stored and rerun conformance checks match the reviewed preview."
        ),
    )

    unsafe = _unsafe_conformance(
        current_conformance_checks,
        current_conformance_summary,
        conformance or {},
    )
    _add_check(
        rows,
        category="Safety",
        check="No cron or automation enablement",
        status=UNSAFE_AUTOMATION_STATUS_GATE if unsafe else PASSED_STATUS,
        evidence_path=_display_path(selected_policy, root),
        expected="No newly enabled cron, schedule, or automation setting",
        observed=(
            "Unsafe automation change detected"
            if unsafe
            else "No unsafe automation change detected"
        ),
        details=(
            "Provider allowlisting cannot be combined with cron or automation enablement."
            if unsafe
            else "The conformance check found no newly enabled automation setting."
        ),
    )

    receipt_binding = _build_receipt_binding(
        provider_key=provider_key,
        detection=detection,
        repository_root=root,
        policy_relative_path=policy_relative,
        evidence_paths={
            "evidence_bundle_verification_checksum_sha256": bundle_file,
            "conformance_report_checksum_sha256": conformance_file,
            "preview_report_checksum_sha256": preview_file,
            "receipt_verification_report_checksum_sha256": receipt_file,
        },
    )
    _add_check(
        rows,
        category="Receipt binding",
        check="Deterministic PR comparison receipt",
        status=_clean(receipt_binding.get("receipt_binding_status")),
        evidence_path=POLICY_RELATIVE_PATH,
        expected=BOUND_STATUS,
        observed=_clean(receipt_binding.get("receipt_binding_status")),
        details=_clean(receipt_binding.get("receipt_binding_note")),
    )

    summary = _build_summary(
        provider_key=provider_key,
        provider_name=provider_display_name,
        detection=detection,
        policy_relative_path=policy_relative,
        receipt_binding=receipt_binding,
        rows=rows,
        run_at=run_at,
    )
    return pd.DataFrame(rows, columns=GATE_COLUMNS), summary


def render_provider_policy_pr_gate(
    checks: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    detection = _mapping(summary.get("change_detection"))
    blockers = summary.get("blockers")
    blocker_lines = (
        [f"- {item}" for item in blockers]
        if isinstance(blockers, list) and blockers
        else ["- None."]
    )
    changed_files = detection.get("changed_files")
    changed_lines = (
        [f"- `{item}`" for item in changed_files]
        if isinstance(changed_files, list) and changed_files
        else ["- None detected."]
    )
    changed_digest_records = summary.get("changed_file_digests")
    changed_digest_lines = (
        [
            f"- `{item.get('path', '')}`: "
            f"`{item.get('checksum_sha256', '') or 'Missing'}` "
            f"({item.get('status', 'Unknown')}, {item.get('content_source', 'unknown source')})"
            for item in changed_digest_records
            if isinstance(item, Mapping)
        ]
        if isinstance(changed_digest_records, list) and changed_digest_records
        else ["- No changed-file content digests were recorded."]
    )
    evidence_records = summary.get("evidence_reports")
    evidence_lines = (
        [
            f"- `{item.get('path', '')}`: "
            f"`{item.get('checksum_sha256', '') or 'Missing'}` "
            f"({item.get('status', 'Unknown')})"
            for item in evidence_records
            if isinstance(item, Mapping)
        ]
        if isinstance(evidence_records, list) and evidence_records
        else ["- Not applicable or unavailable."]
    )
    lines = [
        "# Provider Policy PR Gate",
        "",
        "**Read-only PR check: nothing was applied.** This gate only reads Git "
        "change metadata, committed evidence reports, archived evidence, and the "
        "provider policy. It writes report outputs only.",
        "",
        "## Verdict",
        "",
        f"- **{summary.get('verdict', FAILED_VERDICT)}**",
        f"- Provider: **{summary.get('provider_name', '')}** "
        f"(`{summary.get('provider_key', '')}`)",
        f"- Policy changed: **{'Yes' if summary.get('policy_changed') else 'No'}**",
        f"- Gate mode: `{summary.get('gate_mode', '') or 'Unknown'}`",
        f"- Generated at: `{summary.get('gate_generated_at', '') or 'Unknown'}`",
        f"- Detection source: {detection.get('source', 'Unknown')}",
        f"- Base ref: `{detection.get('base_ref', '') or 'Not supplied'}`",
        f"- Head ref: `{detection.get('head_ref', '') or 'Not supplied'}`",
        f"- Base SHA: `{summary.get('base_sha', '') or 'Missing'}`",
        f"- Head SHA: `{summary.get('head_sha', '') or 'Missing'}`",
        f"- Merge base SHA: `{summary.get('merge_base_sha', '') or 'Not available'}`",
        "",
        "## Gate receipt",
        "",
        f"- Receipt binding: **{summary.get('receipt_binding_status', 'Unknown')}**",
        f"- Comparison context: **{summary.get('comparison_context_status', 'Unknown')}**",
        f"- Gate receipt ID: `{summary.get('gate_receipt_id', '') or 'Not issued'}`",
        f"- Gate receipt SHA-256: "
        f"`{summary.get('gate_receipt_checksum_sha256', '') or 'Not issued'}`",
        f"- Changed-files digest: "
        f"`{summary.get('changed_files_digest', '') or 'Missing'}`",
        f"- Evidence digest: `{summary.get('evidence_digest', '') or 'Missing'}`",
        f"- Policy-change digest: "
        f"`{summary.get('policy_change_digest', '') or 'Missing'}`",
        f"- Binding note: {summary.get('receipt_binding_note', '') or 'No note.'}",
        "",
        "## Changed files",
        "",
        *changed_lines,
        "",
        "## Changed-file content digests",
        "",
        *changed_digest_lines,
        "",
        "## Evidence report digests",
        "",
        *evidence_lines,
        "",
        "## Blockers",
        "",
        *blocker_lines,
        "",
        "## Gate checks",
        "",
        checks.to_markdown(index=False),
        "",
        "## Safety boundary",
        "",
        "Passing this gate confirms only that a provider-policy PR matches the "
        "reviewed evidence. It does not edit policy, allowlist a provider by "
        "itself, promote staging, run providers, create receipts or previews, "
        "generate picks, place bets, require secrets, or enable cron.",
    ]
    return "\n".join(lines)


def save_provider_policy_pr_gate(
    provider_name: str,
    output_dir: Path | None = None,
    **kwargs: object,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    checks, summary = build_provider_policy_pr_gate(
        provider_name,
        outputs,
        **kwargs,
    )
    json_path = outputs / GATE_JSON_FILENAME
    markdown_path = outputs / GATE_MARKDOWN_FILENAME
    csv_path = outputs / GATE_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        render_provider_policy_pr_gate(checks, summary).encode("utf-8"),
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
