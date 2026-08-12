from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import (
    OUTPUTS_DIR,
    PROJECT_ROOT,
    STAGING_PROVIDER_POLICY_PATH,
)
from epl_betting_lab.providers.base import atomic_write_report, file_sha256
from epl_betting_lab.reports.provider_acceptance_checklist import (
    ACCEPTANCE_JSON_FILENAME,
)
from epl_betting_lab.reports.provider_shadow_history import (
    ARCHIVE_METADATA_FILENAME,
    COMPARISON_JSON_FILENAME,
    load_provider_shadow_run_history,
)


RECEIPT_JSON_FILENAME = "provider_human_acceptance_receipt.json"
RECEIPT_MARKDOWN_FILENAME = "provider_human_acceptance_receipt.md"
RECEIPT_CSV_FILENAME = "provider_human_acceptance_receipt.csv"
RECEIPT_ARCHIVE_ROOT = Path("archive") / "provider_acceptance_receipts"
READY_VERDICT = "Ready for human allowlist review"
APPROVAL_DECISION = "approved_for_allowlist_pr"
SUPPORTED_DECISIONS = (
    APPROVAL_DECISION,
    "rejected",
    "needs_more_shadow_runs",
)
RECEIPT_COLUMNS = (
    "receipt_id",
    "provider_key",
    "reviewer_name",
    "decision",
    "created_at",
    "evidence_type",
    "evidence_path",
    "checksum_sha256",
    "evidence_status",
    "evidence_verdict",
    "evidence_generated_at",
    "details",
)


class ProviderHumanAcceptanceReceiptError(RuntimeError):
    """Raised when exact human-review evidence cannot be safely bound."""


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


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.exists():
        raise ProviderHumanAcceptanceReceiptError(
            f"Missing {label} `{_display_path(path)}`. Generate it before creating "
            "a human acceptance receipt."
        )
    if not path.is_file() or path.is_symlink():
        raise ProviderHumanAcceptanceReceiptError(
            f"The {label} must be a regular, non-symlinked file: "
            f"`{_display_path(path)}`."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProviderHumanAcceptanceReceiptError(
            f"The {label} is unreadable or malformed: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderHumanAcceptanceReceiptError(
            f"The {label} must contain one JSON object."
        )
    return payload


def _safe_archive_path(value: object, output_dir: Path) -> Path:
    text = _clean(value)
    if not text:
        raise ProviderHumanAcceptanceReceiptError(
            "A reviewed shadow run is missing its archive path."
        )
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to((output_dir / "archive" / "provider_shadow_runs").resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProviderHumanAcceptanceReceiptError(
            f"Reviewed shadow archive path is missing or unsafe: `{text}`."
        ) from exc
    if not resolved.is_dir() or candidate.is_symlink():
        raise ProviderHumanAcceptanceReceiptError(
            f"Reviewed shadow archive is not a regular directory: `{text}`."
        )
    return resolved


def calculate_shadow_archive_bundle_checksum(archive_dir: Path) -> tuple[str, int]:
    files: list[Path] = []
    for path in archive_dir.rglob("*"):
        if path.is_symlink():
            raise ProviderHumanAcceptanceReceiptError(
                f"Reviewed shadow archive contains a symbolic link: "
                f"`{_display_path(path)}`."
            )
        if path.is_file():
            files.append(path)
    if not files:
        raise ProviderHumanAcceptanceReceiptError(
            f"Reviewed shadow archive is empty: `{_display_path(archive_dir)}`."
        )

    digest = sha256()
    for path in sorted(files, key=lambda item: item.relative_to(archive_dir).as_posix()):
        relative = path.relative_to(archive_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest(), len(files)


def verify_shadow_archive_integrity(archive_dir: Path) -> tuple[str, str]:
    metadata_path = archive_dir / ARCHIVE_METADATA_FILENAME
    try:
        metadata = _read_json_object(metadata_path, "shadow archive metadata")
    except ProviderHumanAcceptanceReceiptError as exc:
        return "Unreadable", str(exc)
    files = metadata.get("files", {})
    if not isinstance(files, Mapping):
        return "Not available", "Archive metadata has no readable checksum map."

    checked = 0
    for item in files.values():
        if not isinstance(item, Mapping) or _clean(item.get("status")) != "Archived":
            continue
        expected = _clean(item.get("checksum_sha256"))
        archived_path = _clean(item.get("archive_path"))
        if not expected or not archived_path:
            return "Not available", "An archived report lacks checksum metadata."
        candidate = archive_dir / Path(archived_path).name
        if not candidate.is_file() or candidate.is_symlink():
            return "Unreadable", f"Archived report is unreadable: `{candidate.name}`."
        checked += 1
        try:
            current = file_sha256(candidate)
        except OSError as exc:
            return "Unreadable", f"Archived report could not be hashed: {exc}"
        if current != expected:
            return "Mismatch", f"Archived report changed: `{candidate.name}`."
    if checked == 0:
        return "Not available", "No archived report checksums were available."
    return "Verified", f"Verified {checked} archived report checksum(s)."


def _provider_matches(payload: Mapping[str, object], provider_name: str) -> bool:
    requested = _slug(provider_name)
    return requested in {
        _slug(payload.get("provider_key")),
        _slug(payload.get("provider_name")),
    }


def _optional_file_evidence(
    path: Path,
    *,
    label: str,
    provider_name: str | None = None,
) -> tuple[dict[str, object], list[str]]:
    record: dict[str, object] = {
        "path": _display_path(path),
        "status": "Not available",
        "checksum_sha256": "",
        "verdict": "",
        "generated_at": "",
    }
    warnings: list[str] = []
    if not path.exists():
        warnings.append(f"No {label} was available to bind.")
        return record, warnings
    if not path.is_file() or path.is_symlink():
        record["status"] = "Unreadable"
        warnings.append(f"The {label} is not a regular, non-symlinked file.")
        return record, warnings
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        checksum = file_sha256(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        record["status"] = "Unreadable"
        warnings.append(f"The {label} could not be read: {exc}")
        return record, warnings
    if not isinstance(payload, dict):
        record["status"] = "Unreadable"
        warnings.append(f"The {label} does not contain one JSON object.")
        return record, warnings
    if provider_name and not _provider_matches(payload, provider_name):
        record["status"] = "Provider mismatch"
        warnings.append(
            f"The {label} belongs to a different provider and was not bound."
        )
        return record, warnings
    record.update(
        {
            "status": "Bound",
            "checksum_sha256": checksum,
            "verdict": _clean(payload.get("verdict")),
            "generated_at": _clean(payload.get("generated_at")),
        }
    )
    return record, warnings


def load_provider_human_acceptance_evidence(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    policy_path: Path | None = None,
) -> tuple[dict[str, object], list[str]]:
    """Load and checksum the exact evidence named by the latest checklist."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    checklist_path = outputs / ACCEPTANCE_JSON_FILENAME
    checklist = _read_json_object(checklist_path, "provider acceptance checklist")
    if not _provider_matches(checklist, provider_name):
        raise ProviderHumanAcceptanceReceiptError(
            "The latest provider acceptance checklist belongs to a different "
            "provider. Regenerate it with the requested `--provider`."
        )

    reviewed_runs = checklist.get("reviewed_runs", [])
    if not isinstance(reviewed_runs, list):
        raise ProviderHumanAcceptanceReceiptError(
            "The provider acceptance checklist has malformed `reviewed_runs` evidence."
        )

    archives: list[dict[str, object]] = []
    for index, reviewed in enumerate(reviewed_runs, start=1):
        if not isinstance(reviewed, Mapping):
            raise ProviderHumanAcceptanceReceiptError(
                f"Reviewed shadow run {index} is malformed."
            )
        archive_dir = _safe_archive_path(reviewed.get("archive_path"), outputs)
        bundle_checksum, file_count = calculate_shadow_archive_bundle_checksum(
            archive_dir
        )
        current_integrity_status, current_integrity_note = (
            verify_shadow_archive_integrity(archive_dir)
        )
        metadata_path = archive_dir / ARCHIVE_METADATA_FILENAME
        metadata_checksum = file_sha256(metadata_path) if metadata_path.is_file() else ""
        archives.append(
            {
                "archive_path": _display_path(archive_dir),
                "checksum_sha256": bundle_checksum,
                "metadata_path": _display_path(metadata_path),
                "metadata_checksum_sha256": metadata_checksum,
                "file_count": file_count,
                "generated_at": _clean(reviewed.get("generated_at")),
                "archive_integrity_status": _clean(
                    reviewed.get("archive_integrity_status")
                ),
                "current_integrity_status": current_integrity_status,
                "current_integrity_note": current_integrity_note,
                "provider_run_status": _clean(reviewed.get("provider_run_status")),
                "shadow_verdict": _clean(reviewed.get("shadow_verdict")),
                "staging_verdict": _clean(reviewed.get("staging_verdict")),
            }
        )

    history = load_provider_shadow_run_history(
        outputs,
        provider_name=provider_name,
    )
    current_live_runs = [
        record for record in history if _clean(record.get("mode")) == "Live shadow run"
    ]
    try:
        review_window = max(1, int(checklist.get("review_window", len(reviewed_runs))))
    except (TypeError, ValueError):
        review_window = max(1, len(reviewed_runs))
    latest_live_runs = current_live_runs[:review_window]
    reviewed_archive_paths = {
        _clean(item.get("archive_path"))
        for item in reviewed_runs
        if isinstance(item, Mapping) and _clean(item.get("archive_path"))
    }
    latest_archive_paths = {
        _clean(item.get("archive_path"))
        for item in latest_live_runs
        if _clean(item.get("archive_path"))
    }
    archive_set_verified = (
        reviewed_archive_paths == latest_archive_paths
        and len(reviewed_runs) == len(latest_live_runs)
    )
    archive_set_status = "Verified" if archive_set_verified else "Checklist stale"
    archive_set_note = (
        "The checklist reviewed the current latest live shadow-run archive set."
        if archive_set_verified
        else (
            "The current latest live shadow-run archives differ from the checklist. "
            "Regenerate the provider acceptance checklist before approval."
        )
    )

    comparison, comparison_warnings = _optional_file_evidence(
        outputs / COMPARISON_JSON_FILENAME,
        label="provider shadow-run comparison",
        provider_name=provider_name,
    )
    selected_policy_input = policy_path or STAGING_PROVIDER_POLICY_PATH
    policy_is_symlink = selected_policy_input.is_symlink()
    selected_policy_path = selected_policy_input.resolve()
    policy: dict[str, object] = {
        "path": _display_path(selected_policy_path),
        "status": "Not available",
        "checksum_sha256": "",
    }
    policy_warnings: list[str] = []
    if selected_policy_path.exists():
        if selected_policy_path.is_file() and not policy_is_symlink:
            try:
                policy["checksum_sha256"] = file_sha256(selected_policy_path)
                policy["status"] = "Bound"
            except OSError as exc:
                policy["status"] = "Unreadable"
                policy_warnings.append(f"Provider policy could not be read: {exc}")
        else:
            policy["status"] = "Unreadable"
            policy_warnings.append(
                "Provider policy is not a regular, non-symlinked file."
            )
    else:
        policy_warnings.append("No provider policy file was available to bind.")

    evidence = {
        "checklist": {
            "path": _display_path(checklist_path),
            "checksum_sha256": file_sha256(checklist_path),
            "status": "Bound",
            "verdict": _clean(checklist.get("verdict")),
            "generated_at": _clean(checklist.get("generated_at")),
            "provider_key": _clean(checklist.get("provider_key")) or provider_name,
            "provider_name": _clean(checklist.get("provider_name")) or provider_name,
        },
        "reviewed_shadow_archives": archives,
        "shadow_archive_set": {
            "path": _display_path(outputs / "archive" / "provider_shadow_runs"),
            "status": archive_set_status,
            "review_window": review_window,
            "reviewed_archive_count": len(reviewed_runs),
            "latest_live_archive_count": len(latest_live_runs),
            "reviewed_archive_paths": sorted(reviewed_archive_paths),
            "latest_live_archive_paths": sorted(latest_archive_paths),
            "note": archive_set_note,
        },
        "comparison": comparison,
        "provider_policy": policy,
    }
    archive_set_warnings = [] if archive_set_verified else [archive_set_note]
    return evidence, archive_set_warnings + comparison_warnings + policy_warnings


def calculate_provider_human_acceptance_receipt_id(
    payload: Mapping[str, object],
    created_at: datetime,
) -> str:
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return (
        f"{_slug(payload.get('provider_key'))}-"
        f"{created_at.strftime('%Y%m%dT%H%M%S%z')}-{digest}"
    )


def build_provider_human_acceptance_receipt(
    provider_name: str,
    reviewer_name: str,
    decision: str,
    *,
    notes: str = "",
    output_dir: Path | None = None,
    policy_path: Path | None = None,
    allow_not_ready_approval: bool = False,
    run_at: datetime | None = None,
) -> dict[str, object]:
    reviewer = _clean(reviewer_name)
    if not reviewer:
        raise ProviderHumanAcceptanceReceiptError("Reviewer name is required.")
    if decision not in SUPPORTED_DECISIONS:
        allowed = ", ".join(SUPPORTED_DECISIONS)
        raise ProviderHumanAcceptanceReceiptError(
            f"Unsupported decision `{decision}`. Choose one of: {allowed}."
        )

    evidence, warnings = load_provider_human_acceptance_evidence(
        provider_name,
        output_dir,
        policy_path=policy_path,
    )
    checklist = evidence["checklist"]
    checklist_verdict = _clean(checklist.get("verdict"))
    override_used = bool(
        decision == APPROVAL_DECISION
        and checklist_verdict != READY_VERDICT
        and allow_not_ready_approval
    )
    if decision == APPROVAL_DECISION and checklist_verdict != READY_VERDICT:
        if not allow_not_ready_approval:
            raise ProviderHumanAcceptanceReceiptError(
                "Approval receipt blocked: the provider acceptance checklist verdict "
                f"is `{checklist_verdict or 'missing'}`, not `{READY_VERDICT}`. "
                "Choose a non-approval decision or intentionally rerun from Terminal "
                "with `--allow-not-ready-approval`."
            )
        warnings.append(
            "Terminal override used: the approval decision does not match a Ready "
            "for human allowlist review checklist verdict."
        )

    archives = evidence["reviewed_shadow_archives"]
    archive_trust_failures = [
        _clean(item.get("archive_path"))
        for item in archives
        if _clean(item.get("archive_integrity_status")) != "Verified"
        or _clean(item.get("current_integrity_status")) != "Verified"
        or _clean(item.get("provider_run_status")) != "Completed"
    ]
    if decision == APPROVAL_DECISION and (not archives or archive_trust_failures):
        raise ProviderHumanAcceptanceReceiptError(
            "Approval receipt blocked: reviewed shadow archive evidence is missing "
            "or no longer Verified and Completed. Regenerate the provider acceptance "
            "checklist after fixing the archive evidence."
        )
    archive_set = evidence["shadow_archive_set"]
    if decision == APPROVAL_DECISION and archive_set.get("status") != "Verified":
        raise ProviderHumanAcceptanceReceiptError(
            "Approval receipt blocked: newer or different live shadow archives exist "
            "than the checklist reviewed. Regenerate the provider acceptance "
            "checklist first."
        )

    created_at = run_at or datetime.now().astimezone()
    if created_at.tzinfo is None:
        created_at = created_at.astimezone()
    created_text = created_at.isoformat(timespec="seconds")
    gate_status = "Override used" if override_used else (
        "Passed" if decision == APPROVAL_DECISION else "Not applicable"
    )
    gate_note = (
        "Checklist was ready for human allowlist review."
        if gate_status == "Passed"
        else (
            "Approval was recorded despite a non-ready checklist through the "
            "explicit Terminal-only override."
            if gate_status == "Override used"
            else "This decision does not approve an allowlist PR."
        )
    )
    identity_payload = {
        "provider_key": checklist.get("provider_key"),
        "reviewer_name": reviewer,
        "decision": decision,
        "notes": _clean(notes),
        "created_at": created_text,
        "checklist_checksum_sha256": checklist.get("checksum_sha256"),
        "archive_checksums": [
            item.get("checksum_sha256")
            for item in evidence["reviewed_shadow_archives"]
        ],
        "comparison_checksum_sha256": evidence["comparison"].get(
            "checksum_sha256"
        ),
        "policy_checksum_sha256": evidence["provider_policy"].get(
            "checksum_sha256"
        ),
    }
    receipt_id = calculate_provider_human_acceptance_receipt_id(
        identity_payload,
        created_at,
    )
    return {
        "schema_version": 1,
        "receipt_id": receipt_id,
        "created_at": created_text,
        "provider_key": checklist.get("provider_key"),
        "provider_name": checklist.get("provider_name"),
        "reviewer_name": reviewer,
        "decision": decision,
        "notes": _clean(notes),
        "checklist_verdict": checklist_verdict,
        "approval_gate": {
            "status": gate_status,
            "override_used": override_used,
            "note": gate_note,
        },
        "evidence": evidence,
        "warnings": warnings,
        "safety": {
            "human_review_documented_only": True,
            "provider_policy_edited": False,
            "provider_allowlisted": False,
            "staging_promoted": False,
            "cron_enabled": False,
            "manual_or_production_files_edited": False,
            "bets_placed": False,
        },
    }


def build_provider_human_acceptance_receipt_rows(
    receipt: Mapping[str, object],
) -> pd.DataFrame:
    evidence = receipt.get("evidence", {})
    if not isinstance(evidence, Mapping):
        evidence = {}
    common = {
        "receipt_id": receipt.get("receipt_id", ""),
        "provider_key": receipt.get("provider_key", ""),
        "reviewer_name": receipt.get("reviewer_name", ""),
        "decision": receipt.get("decision", ""),
        "created_at": receipt.get("created_at", ""),
    }
    rows: list[dict[str, object]] = []

    def add_row(
        evidence_type: str,
        item: Mapping[str, object],
        *,
        path_key: str = "path",
        verdict_key: str = "verdict",
        generated_key: str = "generated_at",
        details: str = "",
    ) -> None:
        rows.append(
            {
                **common,
                "evidence_type": evidence_type,
                "evidence_path": item.get(path_key, ""),
                "checksum_sha256": item.get("checksum_sha256", ""),
                "evidence_status": item.get("status", "Bound"),
                "evidence_verdict": item.get(verdict_key, ""),
                "evidence_generated_at": item.get(generated_key, ""),
                "details": details,
            }
        )

    checklist = evidence.get("checklist", {})
    if isinstance(checklist, Mapping):
        add_row("acceptance_checklist", checklist)
    archives = evidence.get("reviewed_shadow_archives", [])
    if isinstance(archives, list):
        for archive in archives:
            if isinstance(archive, Mapping):
                add_row(
                    "reviewed_shadow_archive",
                    archive,
                    path_key="archive_path",
                    verdict_key="shadow_verdict",
                    details=(
                        f"{archive.get('file_count', 0)} file(s); checklist integrity "
                        f"{archive.get('archive_integrity_status', 'not available')}; "
                        "current integrity "
                        f"{archive.get('current_integrity_status', 'not available')}"
                    ),
                )
    archive_set = evidence.get("shadow_archive_set", {})
    if isinstance(archive_set, Mapping):
        add_row(
            "latest_live_shadow_archive_set",
            archive_set,
            details=_clean(archive_set.get("note")),
        )
    comparison = evidence.get("comparison", {})
    if isinstance(comparison, Mapping):
        add_row("latest_shadow_comparison", comparison)
    policy = evidence.get("provider_policy", {})
    if isinstance(policy, Mapping):
        add_row("provider_policy", policy)
    return pd.DataFrame(rows, columns=RECEIPT_COLUMNS)


def render_provider_human_acceptance_receipt(
    receipt: Mapping[str, object],
    evidence_rows: pd.DataFrame,
) -> str:
    gate = receipt.get("approval_gate", {})
    if not isinstance(gate, Mapping):
        gate = {}
    warnings = receipt.get("warnings", [])
    warning_lines = (
        "\n".join(f"- {warning}" for warning in warnings)
        if isinstance(warnings, list) and warnings
        else "No evidence-binding warnings."
    )
    lines = [
        "# Provider Human Acceptance Receipt",
        "",
        "This receipt documents a human review decision and the exact evidence "
        "reviewed. It does **not** allowlist the provider, enable cron, promote "
        "staging, generate picks, or place bets.",
        "",
        "## Human decision",
        "",
        f"- Receipt ID: `{receipt.get('receipt_id', '')}`",
        f"- Created at: **{receipt.get('created_at', '')}**",
        (
            f"- Provider: **{receipt.get('provider_name', '')}** "
            f"(`{receipt.get('provider_key', '')}`)"
        ),
        f"- Reviewer: **{receipt.get('reviewer_name', '')}**",
        f"- Decision: **{receipt.get('decision', '')}**",
        f"- Checklist verdict: **{receipt.get('checklist_verdict', '')}**",
        f"- Approval gate: **{gate.get('status', 'Unknown')}**",
        f"- Gate note: {gate.get('note', '')}",
        f"- Reviewer notes: {receipt.get('notes', '') or 'None provided.'}",
        "",
        "## Bound evidence",
        "",
        evidence_rows.to_markdown(index=False),
        "",
        "Archive bundle checksums cover each reviewed archive's filenames and "
        "current file checksums in deterministic order.",
        "",
        "## Warnings",
        "",
        warning_lines,
        "",
        "## Decision boundary",
        "",
        "- `approved_for_allowlist_pr` means only that a separate allowlist PR may be considered.",
        "- A separate human-reviewed PR is still required to edit `staging_provider_policy.json`.",
        "- Cron remains disabled and requires its own later review.",
        "- This receipt never edits protected manual files or runs a provider.",
        "",
        "No provider was allowlisted and cron remains disabled.",
    ]
    return "\n".join(lines)


def _unique_receipt_archive_dir(
    output_dir: Path,
    *,
    receipt: Mapping[str, object],
) -> Path:
    created_at = datetime.fromisoformat(_clean(receipt.get("created_at")))
    date_dir = output_dir / RECEIPT_ARCHIVE_ROOT / created_at.strftime("%Y-%m-%d")
    stem = (
        f"{created_at.strftime('%H%M%S')}_"
        f"{_slug(receipt.get('provider_key'))}_"
        f"{_slug(receipt.get('decision'))}"
    )
    candidate = date_dir / stem
    suffix = 2
    while candidate.exists():
        candidate = date_dir / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def save_provider_human_acceptance_receipt(
    receipt: Mapping[str, object],
    output_dir: Path | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    evidence_rows = build_provider_human_acceptance_receipt_rows(receipt)
    archive_dir = _unique_receipt_archive_dir(outputs, receipt=receipt)
    stored_receipt = dict(receipt)
    stored_receipt["receipt_storage"] = {
        "latest_json_path": _display_path(outputs / RECEIPT_JSON_FILENAME),
        "latest_markdown_path": _display_path(outputs / RECEIPT_MARKDOWN_FILENAME),
        "latest_csv_path": _display_path(outputs / RECEIPT_CSV_FILENAME),
        "archive_directory": _display_path(archive_dir),
    }
    json_content = (
        json.dumps(stored_receipt, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    markdown_content = render_provider_human_acceptance_receipt(
        stored_receipt,
        evidence_rows,
    ).encode("utf-8")
    csv_content = evidence_rows.to_csv(index=False, lineterminator="\n").encode(
        "utf-8"
    )
    payloads = {
        RECEIPT_JSON_FILENAME: json_content,
        RECEIPT_MARKDOWN_FILENAME: markdown_content,
        RECEIPT_CSV_FILENAME: csv_content,
    }
    archive_paths: dict[str, Path] = {}
    for filename, content in payloads.items():
        archive_path = archive_dir / filename
        atomic_write_report(archive_path, content)
        archive_paths[filename] = archive_path
    latest_paths: dict[str, Path] = {}
    for filename, content in payloads.items():
        latest_path = outputs / filename
        atomic_write_report(latest_path, content)
        latest_paths[filename] = latest_path
    return {
        "receipt": stored_receipt,
        "evidence": evidence_rows,
        "written": True,
        "json": latest_paths[RECEIPT_JSON_FILENAME],
        "markdown": latest_paths[RECEIPT_MARKDOWN_FILENAME],
        "csv": latest_paths[RECEIPT_CSV_FILENAME],
        "archive_directory": archive_dir,
        "archive_paths": archive_paths,
    }


def process_provider_human_acceptance_receipt(
    provider_name: str,
    reviewer_name: str,
    decision: str,
    *,
    notes: str = "",
    output_dir: Path | None = None,
    policy_path: Path | None = None,
    allow_not_ready_approval: bool = False,
    write_receipt: bool = False,
    run_at: datetime | None = None,
) -> dict[str, object]:
    """Preview by default; write report-only receipt outputs when requested."""
    receipt = build_provider_human_acceptance_receipt(
        provider_name,
        reviewer_name,
        decision,
        notes=notes,
        output_dir=output_dir,
        policy_path=policy_path,
        allow_not_ready_approval=allow_not_ready_approval,
        run_at=run_at,
    )
    if write_receipt:
        return save_provider_human_acceptance_receipt(receipt, output_dir)
    return {
        "receipt": receipt,
        "evidence": build_provider_human_acceptance_receipt_rows(receipt),
        "written": False,
    }
