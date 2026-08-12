from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import atomic_write_report, path_contains_symlink
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

GATE_STATUSES = (
    PASSED_STATUS,
    NOT_APPLICABLE_STATUS,
    MISSING_VERIFIED_BUNDLE_STATUS,
    MISSING_CONFORMANCE_STATUS,
    CONFORMANCE_FAILED_STATUS,
    RECEIPT_FAILED_STATUS,
    UNSAFE_AUTOMATION_STATUS_GATE,
    FAILED_STATUS,
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
)

_SAFE_GIT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+~^{}-]*$")


@dataclass(frozen=True)
class PolicyChangeDetection:
    policy_changed: bool
    changed_files: tuple[str, ...]
    source: str
    base_ref: str = ""
    head_ref: str = ""
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


def _git_ref_exists(repository_root: Path, reference: str) -> bool:
    if not _valid_git_ref(reference):
        return False
    _, error = _git_command(
        repository_root,
        ["rev-parse", "--verify", "--quiet", f"{reference}^{{commit}}"],
    )
    return not error


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
        return PolicyChangeDetection(
            policy_changed=expected in normalized,
            changed_files=normalized,
            source="Provided changed-file list",
            base_ref=_clean(base_ref),
            head_ref=_clean(head_ref),
        )

    env = environment if environment is not None else os.environ
    selected_base = _clean(base_ref or env.get("PROVIDER_POLICY_BASE_REF"))
    selected_head = _clean(
        head_ref or env.get("PROVIDER_POLICY_HEAD_REF") or "HEAD"
    )
    if selected_base:
        files, error = _git_changed_files(
            root,
            base_ref=selected_base,
            head_ref=selected_head,
            merge_base=False,
        )
        normalized = tuple(sorted(files))
        return PolicyChangeDetection(
            policy_changed=expected in files,
            changed_files=normalized,
            source="Explicit base/head Git diff",
            base_ref=selected_base,
            head_ref=selected_head,
            error=error,
        )
    if head_ref:
        return PolicyChangeDetection(
            policy_changed=False,
            changed_files=(),
            source="Explicit base/head Git diff",
            head_ref=selected_head,
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
    working_output, working_error = _git_command(
        root,
        ["diff", "--no-renames", "--name-only", "HEAD", "--"],
    )
    working = {
        normalized
        for line in working_output.splitlines()
        if (normalized := _normalize_changed_file(line))
    }
    error = committed_error or working_error
    files = committed | working
    return PolicyChangeDetection(
        policy_changed=expected in files,
        changed_files=tuple(sorted(files)),
        source="Local Git diff against default branch",
        base_ref=local_base,
        head_ref="HEAD plus working tree",
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
    if statuses and statuses <= {PASSED_STATUS}:
        return PASSED_VERDICT
    return BLOCKED_VERDICT


def _blockers(rows: Sequence[Mapping[str, object]]) -> list[str]:
    return list(
        dict.fromkeys(
            f"{row.get('check', 'Check')}: {row.get('details', '')}"
            for row in rows
            if _clean(row.get("status"))
            not in {PASSED_STATUS, NOT_APPLICABLE_STATUS}
        )
    )


def _build_summary(
    *,
    provider_key: str,
    provider_name: str,
    detection: PolicyChangeDetection,
    rows: list[dict[str, object]],
    run_at: datetime | None,
) -> dict[str, object]:
    verdict = _gate_verdict(rows)
    if verdict not in GATE_VERDICTS:
        raise ValueError(f"Unexpected provider policy PR gate verdict: {verdict}")
    status_counts = Counter(_clean(row.get("status")) for row in rows)
    return {
        "schema_version": 1,
        "generated_at": (run_at or datetime.now().astimezone()).isoformat(
            timespec="seconds"
        ),
        "provider_key": provider_key,
        "provider_name": provider_name,
        "policy_path": POLICY_RELATIVE_PATH,
        "policy_changed": detection.policy_changed,
        "change_detection": {
            "source": detection.source,
            "base_ref": detection.base_ref,
            "head_ref": detection.head_ref,
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
        summary = _build_summary(
            provider_key=provider_key,
            provider_name=provider_display_name,
            detection=detection,
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
        summary = _build_summary(
            provider_key=provider_key,
            provider_name=provider_display_name,
            detection=detection,
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

    summary = _build_summary(
        provider_key=provider_key,
        provider_name=provider_display_name,
        detection=detection,
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
        f"- Detection source: {detection.get('source', 'Unknown')}",
        f"- Base: `{detection.get('base_ref', '') or 'Not supplied'}`",
        f"- Head: `{detection.get('head_ref', '') or 'Not supplied'}`",
        "",
        "## Changed files",
        "",
        *changed_lines,
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
