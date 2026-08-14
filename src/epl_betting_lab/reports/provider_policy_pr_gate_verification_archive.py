from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import atomic_write_report, path_contains_symlink
from epl_betting_lab.providers.provider_registry import create_provider
from epl_betting_lab.reports.provider_policy_pr_gate import (
    GATE_CSV_FILENAME,
    GATE_JSON_FILENAME,
    GATE_MARKDOWN_FILENAME,
)
from epl_betting_lab.reports.provider_policy_pr_gate_receipt_verification import (
    VERIFICATION_CSV_FILENAME,
    VERIFICATION_JSON_FILENAME,
    VERIFICATION_MARKDOWN_FILENAME,
    VERIFIED_VERDICT,
)


ARCHIVE_JSON_FILENAME = "provider_policy_pr_gate_verification_archive.json"
ARCHIVE_MARKDOWN_FILENAME = "provider_policy_pr_gate_verification_archive.md"
ARCHIVE_CSV_FILENAME = "provider_policy_pr_gate_verification_archive.csv"
ARCHIVE_ROOT = Path("archive") / "provider_policy_pr_gate_verifications"

READY_VERDICT = "Verification archive ready for approval review"
NOT_READY_VERDICT = "Verification archive not ready for approval review"
FAILED_VERDICT = "Verification archive failed"

INCLUDED_STATUS = "Included"
ARCHIVED_STATUS = "Archived"
MISSING_STATUS = "Missing"
UNREADABLE_STATUS = "Unreadable"
NOT_APPLICABLE_STATUS = "Not applicable"
BLOCKED_STATUS = "Blocked"

ARCHIVE_COLUMNS = (
    "evidence_type",
    "source_path",
    "archived_path",
    "required",
    "checksum_sha256",
    "status",
    "note",
)

_REQUIRED_REPORTS = (
    ("gate_json", GATE_JSON_FILENAME),
    ("gate_markdown", GATE_MARKDOWN_FILENAME),
    ("gate_csv", GATE_CSV_FILENAME),
    ("gate_receipt_verification_json", VERIFICATION_JSON_FILENAME),
    ("gate_receipt_verification_markdown", VERIFICATION_MARKDOWN_FILENAME),
    ("gate_receipt_verification_csv", VERIFICATION_CSV_FILENAME),
)
_OPTIONAL_REPORTS = (
    (
        "allowlist_evidence_bundle_verification_json",
        "provider_allowlist_evidence_bundle_verification.json",
    ),
    (
        "allowlist_evidence_bundle_verification_markdown",
        "provider_allowlist_evidence_bundle_verification.md",
    ),
    (
        "allowlist_evidence_bundle_verification_csv",
        "provider_allowlist_evidence_bundle_verification.csv",
    ),
    ("allowlist_conformance_json", "provider_allowlist_pr_conformance.json"),
    ("allowlist_conformance_markdown", "provider_allowlist_pr_conformance.md"),
    ("allowlist_conformance_csv", "provider_allowlist_pr_conformance.csv"),
    ("allowlist_preview_json", "provider_allowlist_pr_preview.json"),
    ("allowlist_preview_markdown", "provider_allowlist_pr_preview.md"),
    ("allowlist_preview_csv", "provider_allowlist_pr_preview.csv"),
    (
        "human_receipt_verification_json",
        "provider_human_acceptance_receipt_verification.json",
    ),
    (
        "human_receipt_verification_markdown",
        "provider_human_acceptance_receipt_verification.md",
    ),
    (
        "human_receipt_verification_csv",
        "provider_human_acceptance_receipt_verification.csv",
    ),
)


class ProviderPolicyGateVerificationArchiveError(RuntimeError):
    """Raised when a gate verification archive cannot be created safely."""


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


def _timestamp(run_at: datetime | None) -> datetime:
    if run_at is None:
        return datetime.now().astimezone()
    return run_at if run_at.tzinfo is not None else run_at.astimezone()


def _sha256_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _resolve_repository_file(
    path: Path,
    *,
    repository_root: Path,
) -> tuple[Path, str]:
    candidate = path if path.is_absolute() else repository_root / path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(repository_root)
    except (OSError, RuntimeError, ValueError):
        return candidate, "The evidence path must stay inside the repository."
    if path_contains_symlink(candidate.absolute(), repository_root):
        return resolved, "The evidence path cannot contain a symbolic link."
    return resolved, ""


def _load_json(path: Path) -> tuple[dict[str, object], str]:
    if not path.exists():
        return {}, "The JSON report is missing."
    if not path.is_file():
        return {}, "The JSON report is not a regular file."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"The JSON report is unreadable or malformed: {exc}"
    if not isinstance(payload, dict):
        return {}, "The JSON report must contain an object."
    return payload, ""


def collect_github_run_metadata(
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a secret-free subset of GitHub and pull-request run metadata."""
    env = environment if environment is not None else os.environ
    repository = _clean(env.get("GITHUB_REPOSITORY"))
    server_url = _clean(env.get("GITHUB_SERVER_URL")) or "https://github.com"
    pr_number = _clean(env.get("PROVIDER_POLICY_PR_NUMBER"))
    pr_url = _clean(env.get("PROVIDER_POLICY_PR_URL"))

    event_path = _clean(env.get("GITHUB_EVENT_PATH"))
    if event_path and (not pr_number or not pr_url):
        try:
            event_payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            event_payload = {}
        pull_request = (
            event_payload.get("pull_request")
            if isinstance(event_payload, dict)
            else None
        )
        if isinstance(pull_request, dict):
            pr_number = pr_number or _clean(pull_request.get("number"))
            pr_url = pr_url or _clean(pull_request.get("html_url"))

    if not pr_url and repository and pr_number:
        pr_url = f"{server_url.rstrip('/')}/{repository}/pull/{pr_number}"
    run_id = _clean(env.get("GITHUB_RUN_ID"))
    run_url = (
        f"{server_url.rstrip('/')}/{repository}/actions/runs/{run_id}"
        if repository and run_id
        else ""
    )
    return {
        "pr_number": pr_number,
        "pr_url": pr_url,
        "github_run_id": run_id,
        "github_run_attempt": _clean(env.get("GITHUB_RUN_ATTEMPT")),
        "github_run_url": run_url,
        "workflow_name": _clean(env.get("GITHUB_WORKFLOW")),
        "job_name": _clean(env.get("PROVIDER_POLICY_JOB_NAME"))
        or _clean(env.get("GITHUB_JOB")),
        "actor": _clean(env.get("GITHUB_ACTOR")),
        "repository": repository,
        "event_name": _clean(env.get("GITHUB_EVENT_NAME")),
    }


def calculate_provider_policy_gate_verification_archive_identity(
    provider_key: str,
    archive_metadata: Mapping[str, object],
    evidence_records: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    """Return a deterministic checksum and receipt ID for archived evidence."""
    stable_metadata = {
        key: archive_metadata.get(key, "")
        for key in (
            "verification_verdict",
            "approval_ready",
            "gate_receipt_id",
            "original_gate_receipt_id",
            "recalculated_gate_receipt_id",
            "base_sha",
            "head_sha",
            "merge_base_sha",
            "changed_files_digest",
            "evidence_digest",
            "policy_change_digest",
            "pr_number",
            "pr_url",
            "github_run_id",
            "github_run_attempt",
            "github_run_url",
            "workflow_name",
            "job_name",
            "actor",
            "repository",
            "event_name",
        )
    }
    manifest = sorted(
        (
            {
                "evidence_type": _clean(record.get("evidence_type")),
                "source_path": _clean(record.get("source_path")),
                "required": bool(record.get("required")),
                "checksum_sha256": _clean(record.get("checksum_sha256")).casefold(),
                "status": _clean(record.get("status")),
            }
            for record in evidence_records
        ),
        key=lambda item: (item["source_path"], item["evidence_type"]),
    )
    payload = {
        "schema_version": 1,
        "provider_key": _slug(provider_key),
        "archive_metadata": stable_metadata,
        "evidence": manifest,
    }
    checksum = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    receipt_id = f"{_slug(provider_key)}-policy-gate-archive-{checksum[:20]}"
    return checksum, receipt_id


def _evidence_record(
    evidence_type: str,
    path: Path,
    *,
    required: bool,
    repository_root: Path,
) -> dict[str, object]:
    display_path = _display_path(path, repository_root)
    if not path.exists():
        return {
            "evidence_type": evidence_type,
            "source_path": display_path,
            "archived_path": "",
            "required": required,
            "checksum_sha256": "",
            "status": MISSING_STATUS if required else NOT_APPLICABLE_STATUS,
            "note": (
                "Required report is missing."
                if required
                else "Optional report is not available."
            ),
        }
    if not path.is_file() or path.is_symlink():
        return {
            "evidence_type": evidence_type,
            "source_path": display_path,
            "archived_path": "",
            "required": required,
            "checksum_sha256": "",
            "status": UNREADABLE_STATUS,
            "note": (
                "Evidence must be a readable regular file without symbolic links."
            ),
        }
    try:
        content = path.read_bytes()
    except OSError as exc:
        return {
            "evidence_type": evidence_type,
            "source_path": display_path,
            "archived_path": "",
            "required": required,
            "checksum_sha256": "",
            "status": UNREADABLE_STATUS,
            "note": f"Evidence could not be read: {exc}",
        }
    return {
        "evidence_type": evidence_type,
        "source_path": display_path,
        "archived_path": "",
        "required": required,
        "checksum_sha256": _sha256_bytes(content),
        "status": INCLUDED_STATUS,
        "note": "Evidence is ready to be copied into the archive.",
    }


def build_provider_policy_pr_gate_verification_archive(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    verification_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
    environment: Mapping[str, str] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    root = (repository_root or PROJECT_ROOT).resolve()
    provider = create_provider(provider_name)
    provider_key = provider.provider_key
    archived_at = _timestamp(run_at)

    selected_verification = verification_path or outputs / VERIFICATION_JSON_FILENAME
    selected_verification, path_error = _resolve_repository_file(
        selected_verification,
        repository_root=root,
    )
    if not path_error and selected_verification.suffix.casefold() != ".json":
        path_error = "The receipt verification path must be a JSON file."
    source_dir = selected_verification.parent
    verification, verification_error = (
        ({}, path_error) if path_error else _load_json(selected_verification)
    )
    provider_matches = _clean(verification.get("provider_key")) == provider_key
    verification_verdict = _clean(verification.get("verdict")) or "Missing"

    report_paths: list[tuple[str, Path, bool]] = []
    for evidence_type, filename in _REQUIRED_REPORTS:
        path = (
            selected_verification
            if filename == VERIFICATION_JSON_FILENAME
            else source_dir / filename
        )
        report_paths.append((evidence_type, path, True))
    report_paths.extend(
        (evidence_type, source_dir / filename, False)
        for evidence_type, filename in _OPTIONAL_REPORTS
    )
    records = [
        _evidence_record(
            evidence_type,
            path,
            required=required,
            repository_root=root,
        )
        for evidence_type, path, required in report_paths
    ]

    required_evidence_ready = all(
        record["status"] == INCLUDED_STATUS
        for record in records
        if bool(record["required"])
    )
    approval_ready = bool(
        not verification_error
        and provider_matches
        and verification_verdict == VERIFIED_VERDICT
        and required_evidence_ready
    )
    if approval_ready:
        verdict = READY_VERDICT
        archive_status = "Approval ready"
    elif verification_error or not provider_matches or not required_evidence_ready:
        verdict = FAILED_VERDICT
        archive_status = BLOCKED_STATUS
    else:
        verdict = NOT_READY_VERDICT
        archive_status = BLOCKED_STATUS

    github = collect_github_run_metadata(environment)
    gate_receipt_id = _clean(verification.get("original_gate_receipt_id"))
    metadata: dict[str, object] = {
        "verification_verdict": verification_verdict,
        "approval_ready": approval_ready,
        "gate_receipt_id": gate_receipt_id,
        "original_gate_receipt_id": gate_receipt_id,
        "recalculated_gate_receipt_id": _clean(
            verification.get("recalculated_gate_receipt_id")
        ),
        "base_sha": _clean(verification.get("base_sha")),
        "head_sha": _clean(verification.get("head_sha")),
        "merge_base_sha": _clean(verification.get("merge_base_sha")),
        "changed_files_digest": _clean(
            verification.get("current_changed_files_digest")
        ),
        "evidence_digest": _clean(verification.get("current_evidence_digest")),
        "policy_change_digest": _clean(
            verification.get("current_policy_change_digest")
        ),
        **github,
    }
    archive_checksum, archive_receipt_id = (
        calculate_provider_policy_gate_verification_archive_identity(
            provider_key,
            metadata,
            records,
        )
    )
    blockers: list[str] = []
    if verification_error:
        blockers.append(verification_error)
    if verification and not provider_matches:
        blockers.append(
            "The receipt verification provider does not match the requested provider."
        )
    if verification_verdict != VERIFIED_VERDICT:
        blockers.append(
            "The receipt verification verdict is not approval-ready: "
            f"{verification_verdict}."
        )
    blockers.extend(
        f"{record['source_path']}: {record['note']}"
        for record in records
        if bool(record["required"]) and record["status"] != INCLUDED_STATUS
    )
    summary: dict[str, object] = {
        "schema_version": 1,
        "archived_at": archived_at.isoformat(timespec="seconds"),
        "provider_key": provider_key,
        "provider_name": provider.provider_name,
        "verdict": verdict,
        "archive_status": archive_status,
        "approval_ready": approval_ready,
        "verification_path": _display_path(selected_verification, root),
        "verification_verdict": verification_verdict,
        "verification_error": verification_error,
        "gate_receipt_id": gate_receipt_id,
        "original_gate_receipt_id": gate_receipt_id,
        "recalculated_gate_receipt_id": metadata[
            "recalculated_gate_receipt_id"
        ],
        "base_sha": metadata["base_sha"],
        "head_sha": metadata["head_sha"],
        "merge_base_sha": metadata["merge_base_sha"],
        "changed_files_digest": metadata["changed_files_digest"],
        "evidence_digest": metadata["evidence_digest"],
        "policy_change_digest": metadata["policy_change_digest"],
        **github,
        "archive_receipt_id": archive_receipt_id,
        "archive_receipt_checksum_sha256": archive_checksum,
        "archived_file_count": sum(
            record["status"] == INCLUDED_STATUS for record in records
        ),
        "status_counts": dict(
            sorted(Counter(_clean(record["status"]) for record in records).items())
        ),
        "blockers": blockers,
        "evidence": records,
        "safety": {
            "read_only_evidence_archive": True,
            "provider_policy_edited": False,
            "provider_allowlisted": False,
            "staging_promoted": False,
            "provider_run": False,
            "cron_enabled": False,
            "protected_files_edited": False,
            "picks_generated": False,
            "bets_placed": False,
        },
    }
    return pd.DataFrame(records, columns=ARCHIVE_COLUMNS), summary


def render_provider_policy_pr_gate_verification_archive(
    evidence: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    blockers = summary.get("blockers")
    blocker_items = blockers if isinstance(blockers, list) else []
    pr_context = (
        summary.get("pr_url")
        or summary.get("pr_number")
        or "Local/not available"
    )
    run_context = (
        summary.get("github_run_url")
        or summary.get("github_run_id")
        or "Local/not available"
    )
    lines = [
        "# Provider Policy PR Gate Verification Archive",
        "",
        "**Nothing was applied.** This report only preserves gate verification "
        "evidence for review. It does not edit policy, allowlist a provider, run "
        "providers, promote staging, generate picks, place bets, or enable cron.",
        "",
        "## Archive verdict",
        "",
        f"- Final verdict: **{summary.get('verdict', FAILED_VERDICT)}**",
        f"- Approval ready: **{'Yes' if summary.get('approval_ready') else 'No'}**",
        f"- Provider: **{summary.get('provider_name', '')}** "
        f"(`{summary.get('provider_key', '')}`)",
        f"- Archived at: `{summary.get('archived_at', '')}`",
        f"- Archive receipt ID: `{summary.get('archive_receipt_id', '')}`",
        "- Archive receipt SHA-256: "
        f"`{summary.get('archive_receipt_checksum_sha256', '')}`",
        f"- Gate receipt ID: `{summary.get('gate_receipt_id', '') or 'Missing'}`",
        f"- Verification verdict: **{summary.get('verification_verdict', 'Missing')}**",
        "",
        "## Pull request and run context",
        "",
        f"- PR: {pr_context}",
        f"- GitHub run: {run_context}",
        f"- Run attempt: `{summary.get('github_run_attempt') or 'Not available'}`",
        f"- Workflow / job: `{summary.get('workflow_name') or 'Not available'}` / "
        f"`{summary.get('job_name') or 'Not available'}`",
        f"- Actor / repository: `{summary.get('actor') or 'Not available'}` / "
        f"`{summary.get('repository') or 'Not available'}`",
        "",
        "## Bound gate context",
        "",
        f"- Base SHA: `{summary.get('base_sha') or 'Missing'}`",
        f"- Head SHA: `{summary.get('head_sha') or 'Missing'}`",
        f"- Merge-base SHA: `{summary.get('merge_base_sha') or 'Missing'}`",
        f"- Changed-files digest: `{summary.get('changed_files_digest') or 'Missing'}`",
        f"- Evidence digest: `{summary.get('evidence_digest') or 'Missing'}`",
        f"- Policy-change digest: `{summary.get('policy_change_digest') or 'Missing'}`",
        "",
        "## Archived files",
        "",
        (
            evidence.to_markdown(index=False)
            if not evidence.empty
            else "No files were archived."
        ),
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- {item}" for item in blocker_items)
    if not blocker_items:
        lines.append(
            "- None. The verified gate receipt is preserved for approval review."
        )
    lines.extend(
        [
            "",
            "## Decision boundary",
            "",
            "A successful archive proves which report bytes and PR/run context were "
            "preserved. It does not apply the policy change. Provider allowlisting "
            "still requires merging a separate human-reviewed policy PR, and cron "
            "remains disabled until a later independent approval.",
        ]
    )
    return "\n".join(lines) + "\n"


def _unique_archive_dir(
    output_dir: Path,
    provider_key: str,
    archived_at: datetime,
) -> Path:
    date_dir = output_dir / ARCHIVE_ROOT / archived_at.strftime("%Y-%m-%d")
    stem = f"{archived_at.strftime('%H%M%S')}_{_slug(provider_key)}"
    candidate = date_dir / stem
    suffix = 2
    while candidate.exists():
        candidate = date_dir / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def save_provider_policy_pr_gate_verification_archive(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    verification_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    root = (repository_root or PROJECT_ROOT).resolve()
    evidence, summary = build_provider_policy_pr_gate_verification_archive(
        provider_name,
        outputs,
        verification_path=verification_path,
        repository_root=root,
        run_at=run_at,
        environment=environment,
    )
    archived_at = datetime.fromisoformat(_clean(summary["archived_at"]))

    source_payloads: dict[str, bytes] = {}
    for index, record in evidence.iterrows():
        if record["status"] != INCLUDED_STATUS:
            continue
        source = root / str(record["source_path"])
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise ProviderPolicyGateVerificationArchiveError(
                f"Evidence changed while the archive was being built: {source}: {exc}"
            ) from exc
        if _sha256_bytes(content) != record["checksum_sha256"]:
            raise ProviderPolicyGateVerificationArchiveError(
                f"Evidence changed while the archive was being built: {source}. "
                "Rerun gate receipt verification before archiving."
            )
        filename = source.name
        if filename in source_payloads:
            raise ProviderPolicyGateVerificationArchiveError(
                f"Two evidence files use the same archive name: {filename}."
            )
        source_payloads[filename] = content

    archive_dir = _unique_archive_dir(
        outputs,
        str(summary["provider_key"]),
        archived_at,
    )
    stored_summary = deepcopy(summary)
    for index, record in evidence.iterrows():
        if record["status"] != INCLUDED_STATUS:
            continue
        archived_path = archive_dir / Path(str(record["source_path"])).name
        atomic_write_report(archived_path, source_payloads[archived_path.name])
        if _sha256_bytes(archived_path.read_bytes()) != record["checksum_sha256"]:
            raise ProviderPolicyGateVerificationArchiveError(
                f"Archived evidence could not be verified: {archived_path}."
            )
        evidence.at[index, "archived_path"] = _display_path(archived_path, root)
        evidence.at[index, "status"] = ARCHIVED_STATUS
        evidence.at[index, "note"] = "Copied and checksum-verified in the archive."

    records = evidence.to_dict(orient="records")
    stored_summary["archive_directory"] = _display_path(archive_dir, root)
    stored_summary["evidence"] = records
    stored_summary["archived_file_count"] = sum(
        record["status"] == ARCHIVED_STATUS for record in records
    )
    stored_summary["status_counts"] = dict(
        sorted(Counter(_clean(record["status"]) for record in records).items())
    )

    payloads = {
        ARCHIVE_JSON_FILENAME: (
            json.dumps(stored_summary, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        ARCHIVE_MARKDOWN_FILENAME: render_provider_policy_pr_gate_verification_archive(
            evidence,
            stored_summary,
        ).encode("utf-8"),
        ARCHIVE_CSV_FILENAME: evidence.to_csv(
            index=False,
            lineterminator="\n",
        ).encode("utf-8"),
    }
    latest_paths: dict[str, Path] = {}
    archive_paths: dict[str, Path] = {}
    for filename, content in payloads.items():
        latest_path = outputs / filename
        archived_path = archive_dir / filename
        atomic_write_report(latest_path, content)
        atomic_write_report(archived_path, content)
        latest_paths[filename] = latest_path
        archive_paths[filename] = archived_path

    return {
        "summary": stored_summary,
        "evidence": evidence,
        "verdict": stored_summary["verdict"],
        "json": latest_paths[ARCHIVE_JSON_FILENAME],
        "markdown": latest_paths[ARCHIVE_MARKDOWN_FILENAME],
        "csv": latest_paths[ARCHIVE_CSV_FILENAME],
        "archive_directory": archive_dir,
        "archive_paths": archive_paths,
    }
