from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
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
from epl_betting_lab.providers.base import (
    atomic_write_report,
    file_sha256,
    path_contains_symlink,
)
from epl_betting_lab.providers.provider_registry import create_provider
from epl_betting_lab.reports.provider_acceptance_checklist import (
    ACCEPTANCE_JSON_FILENAME,
)
from epl_betting_lab.reports.provider_allowlist_pr_conformance import (
    CONFORMANCE_JSON_FILENAME,
    CONFORMS_VERDICT,
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    PREVIEW_JSON_FILENAME,
    READY_STATUS,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    APPROVAL_DECISION,
    READY_VERDICT,
    RECEIPT_JSON_FILENAME,
    ProviderHumanAcceptanceReceiptError,
    calculate_shadow_archive_bundle_checksum,
    verify_shadow_archive_integrity,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt_verification import (
    VERIFICATION_JSON_FILENAME,
)
from epl_betting_lab.reports.provider_shadow_history import (
    ARCHIVE_METADATA_FILENAME,
    COMPARISON_JSON_FILENAME,
    load_provider_shadow_run_history,
)


BUNDLE_JSON_FILENAME = "provider_allowlist_evidence_bundle.json"
BUNDLE_MARKDOWN_FILENAME = "provider_allowlist_evidence_bundle.md"
BUNDLE_CSV_FILENAME = "provider_allowlist_evidence_bundle.csv"
BUNDLE_ARCHIVE_ROOT = Path("archive") / "provider_allowlist_evidence_bundles"

EVIDENCE_STATUSES = (
    "Included",
    "Missing",
    "Checksum mismatch",
    "Stale",
    "Not applicable",
)
BUNDLE_VERDICTS = (
    "Evidence bundle ready for PR review",
    "Missing required evidence",
    "Evidence changed",
    "Not ready for PR review",
)
BUNDLE_COLUMNS = (
    "evidence_type",
    "evidence_path",
    "required",
    "expected_checksum_sha256",
    "current_checksum_sha256",
    "status",
    "verdict",
    "generated_at",
    "details",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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


def _resolve_reference(
    value: object,
    *,
    repository_root: Path,
    output_dir: Path,
) -> tuple[Path | None, str]:
    text = _clean(value)
    if not text:
        return None, "Evidence path is blank."
    raw = Path(text)
    if raw.is_absolute():
        candidate = raw
    elif text.replace("\\", "/").startswith("data/"):
        candidate = repository_root / raw
    else:
        candidate = output_dir / raw
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(repository_root)
    except (OSError, RuntimeError, ValueError):
        return candidate, "Evidence path must stay inside the repository."
    if path_contains_symlink(candidate.absolute(), repository_root):
        return resolved, "Evidence path cannot use a symbolic link."
    return resolved, ""


def _read_json_file(
    path: Path | None,
    *,
    label: str,
) -> tuple[dict[str, object] | None, str, str]:
    if path is None or not path.exists():
        return None, "", f"{label} is missing."
    if not path.is_file() or path.is_symlink():
        return None, "", f"{label} must be a regular, non-symlinked JSON file."
    try:
        content = path.read_bytes()
        checksum = sha256(content).hexdigest()
        payload = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, "", f"{label} is unreadable or malformed: {exc}"
    if not isinstance(payload, dict):
        return None, checksum, f"{label} must contain one JSON object."
    return payload, checksum, ""


def _reference_matches(
    value: object,
    expected_path: Path,
    *,
    repository_root: Path,
    output_dir: Path,
) -> bool:
    resolved, error = _resolve_reference(
        value,
        repository_root=repository_root,
        output_dir=output_dir,
    )
    return not error and resolved == expected_path.resolve(strict=False)


def _provider_matches(payload: Mapping[str, object], provider_name: str) -> bool:
    requested = _slug(provider_name)
    return requested in {
        _slug(payload.get("provider_key")),
        _slug(payload.get("provider_name")),
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _expected_checksums(*values: object) -> list[str]:
    checksums = [_clean(value).casefold() for value in values if _clean(value)]
    return list(dict.fromkeys(checksums))


def _format_expected(checksums: list[str]) -> str:
    return " | ".join(checksums)


def _add_evidence(
    rows: list[dict[str, object]],
    *,
    evidence_type: str,
    evidence_path: object,
    required: bool,
    expected_checksums: list[str] | None = None,
    current_checksum: str = "",
    status: str,
    verdict: object = "",
    generated_at: object = "",
    details: str = "",
) -> None:
    if status not in EVIDENCE_STATUSES:
        raise ValueError(f"Unexpected evidence bundle status: {status}")
    rows.append(
        {
            "evidence_type": evidence_type,
            "evidence_path": _clean(evidence_path),
            "required": "Yes" if required else "No",
            "expected_checksum_sha256": _format_expected(expected_checksums or []),
            "current_checksum_sha256": _clean(current_checksum),
            "status": status,
            "verdict": _clean(verdict),
            "generated_at": _clean(generated_at),
            "details": details,
        }
    )


def _checksum_status(
    current_checksum: str,
    expected_checksums: list[str],
) -> tuple[str, str]:
    if not current_checksum:
        return "Missing", "The evidence file could not be hashed."
    invalid = [
        item for item in expected_checksums if not SHA256_PATTERN.fullmatch(item)
    ]
    if invalid:
        return "Stale", "A bound checksum is missing or malformed."
    if expected_checksums and any(
        current_checksum != item for item in expected_checksums
    ):
        return "Checksum mismatch", "Current bytes differ from bound evidence."
    return "Included", "Current checksum matches every available binding."


def _record_json_evidence(
    rows: list[dict[str, object]],
    *,
    evidence_type: str,
    display_path: str,
    payload: dict[str, object] | None,
    checksum: str,
    error: str,
    required: bool,
    expected_checksums: list[str] | None = None,
    stale_reasons: list[str] | None = None,
    verdict_field: str = "verdict",
) -> str:
    expected = expected_checksums or []
    stale = [item for item in (stale_reasons or []) if item]
    if error or payload is None:
        status = "Missing" if required else "Stale"
        details = error or "Evidence JSON is unavailable."
    else:
        status, details = _checksum_status(checksum, expected)
        if status == "Included" and stale:
            status = "Stale"
            details = " ".join(stale)
    _add_evidence(
        rows,
        evidence_type=evidence_type,
        evidence_path=display_path,
        required=required,
        expected_checksums=expected,
        current_checksum=checksum,
        status=status,
        verdict=payload.get(verdict_field, "") if payload else "",
        generated_at=payload.get("generated_at", "") if payload else "",
        details=details,
    )
    return status


def _archive_file_expectations(
    metadata: Mapping[str, object],
) -> dict[str, str]:
    files = metadata.get("files", {})
    if not isinstance(files, Mapping):
        return {}
    expectations: dict[str, str] = {}
    for record in files.values():
        if not isinstance(record, Mapping):
            continue
        archive_path = _clean(record.get("archive_path"))
        checksum = _clean(record.get("checksum_sha256")).casefold()
        if archive_path and SHA256_PATTERN.fullmatch(checksum):
            expectations[Path(archive_path).name] = checksum
    return expectations


def _collect_reviewed_archives(
    rows: list[dict[str, object]],
    *,
    receipt: Mapping[str, object],
    checklist: Mapping[str, object],
    repository_root: Path,
    output_dir: Path,
) -> tuple[set[str], list[str]]:
    evidence = _mapping(receipt.get("evidence"))
    archive_records = _list_of_mappings(evidence.get("reviewed_shadow_archives"))
    checklist_runs = _list_of_mappings(checklist.get("reviewed_runs"))

    def normalized_references(records: list[Mapping[str, object]]) -> set[str]:
        normalized: set[str] = set()
        for item in records:
            reference = _clean(item.get("archive_path"))
            if not reference:
                continue
            path, error = _resolve_reference(
                reference,
                repository_root=repository_root,
                output_dir=output_dir,
            )
            if not error and path is not None:
                normalized.add(_display_path(path, repository_root))
        return normalized

    checklist_paths = normalized_references(checklist_runs)
    receipt_paths = normalized_references(archive_records)
    relationship_issues: list[str] = []
    if not archive_records:
        _add_evidence(
            rows,
            evidence_type="reviewed_shadow_archives",
            evidence_path="data/outputs/archive/provider_shadow_runs",
            required=True,
            status="Missing",
            details="The human receipt does not bind any reviewed shadow archive.",
        )
        return set(), ["No reviewed shadow archives are bound by the receipt."]
    if checklist_paths != receipt_paths:
        relationship_issues.append(
            "Receipt and acceptance checklist reference different shadow archives."
        )

    normalized_paths: set[str] = set()
    archive_root = (output_dir / "archive" / "provider_shadow_runs").resolve()
    for index, record in enumerate(archive_records, start=1):
        recorded_path = _clean(record.get("archive_path"))
        archive_dir, path_error = _resolve_reference(
            recorded_path,
            repository_root=repository_root,
            output_dir=output_dir,
        )
        expected_bundle = _clean(record.get("checksum_sha256")).casefold()
        expected_metadata = _clean(
            record.get("metadata_checksum_sha256")
        ).casefold()
        display = (
            _display_path(archive_dir, repository_root)
            if archive_dir is not None
            else recorded_path
        )
        safe = False
        if archive_dir is not None:
            try:
                archive_dir.relative_to(archive_root)
                safe = True
            except ValueError:
                path_error = "Reviewed archive is outside the provider archive root."
        if (
            path_error
            or not safe
            or archive_dir is None
            or not archive_dir.exists()
            or not archive_dir.is_dir()
            or archive_dir.is_symlink()
        ):
            _add_evidence(
                rows,
                evidence_type="reviewed_shadow_archive_bundle",
                evidence_path=display,
                required=True,
                expected_checksums=_expected_checksums(expected_bundle),
                status="Missing",
                details=path_error or "Reviewed shadow archive is missing or unreadable.",
            )
            continue

        normalized = _display_path(archive_dir, repository_root)
        normalized_paths.add(normalized)
        try:
            current_bundle, file_count = calculate_shadow_archive_bundle_checksum(
                archive_dir
            )
        except (OSError, ProviderHumanAcceptanceReceiptError) as exc:
            _add_evidence(
                rows,
                evidence_type="reviewed_shadow_archive_bundle",
                evidence_path=normalized,
                required=True,
                expected_checksums=_expected_checksums(expected_bundle),
                status="Missing",
                details=str(exc),
            )
            continue

        bundle_status, bundle_note = _checksum_status(
            current_bundle,
            _expected_checksums(expected_bundle),
        )
        if bundle_status == "Included" and not expected_bundle:
            bundle_status = "Stale"
            bundle_note = "Human receipt did not bind an archive bundle checksum."
        integrity_status, integrity_note = verify_shadow_archive_integrity(
            archive_dir
        )
        if bundle_status == "Included" and integrity_status != "Verified":
            bundle_status = "Stale"
            bundle_note = integrity_note
        if bundle_status == "Included" and normalized not in checklist_paths:
            bundle_status = "Stale"
            bundle_note = "Archive was not referenced by the acceptance checklist."
        if bundle_status == "Included" and any(
            _clean(record.get(field)) != expected
            for field, expected in (
                ("archive_integrity_status", "Verified"),
                ("current_integrity_status", "Verified"),
                ("provider_run_status", "Completed"),
            )
        ):
            bundle_status = "Stale"
            bundle_note = (
                "Human receipt does not record this archive as Verified and Completed."
            )
        try:
            recorded_file_count = int(record.get("file_count", -1))
        except (TypeError, ValueError):
            recorded_file_count = -1
        if bundle_status == "Included" and recorded_file_count != file_count:
            bundle_status = "Stale"
            bundle_note = "Archive file count differs from the human receipt."
        _add_evidence(
            rows,
            evidence_type="reviewed_shadow_archive_bundle",
            evidence_path=normalized,
            required=True,
            expected_checksums=_expected_checksums(expected_bundle),
            current_checksum=current_bundle,
            status=bundle_status,
            verdict=record.get("shadow_verdict", ""),
            generated_at=record.get("generated_at", ""),
            details=f"{bundle_note} Archive contains {file_count} file(s).",
        )

        metadata_path = archive_dir / ARCHIVE_METADATA_FILENAME
        metadata_payload, metadata_checksum, metadata_error = _read_json_file(
            metadata_path,
            label=f"Reviewed shadow archive {index} metadata",
        )
        metadata_reference_matches = _reference_matches(
            record.get("metadata_path"),
            metadata_path,
            repository_root=repository_root,
            output_dir=output_dir,
        )
        file_expectations = _archive_file_expectations(metadata_payload or {})
        for file_path in sorted(
            (path for path in archive_dir.rglob("*") if path.is_file()),
            key=lambda item: item.relative_to(archive_dir).as_posix(),
        ):
            relative = file_path.relative_to(archive_dir).as_posix()
            expected = (
                _expected_checksums(expected_metadata)
                if file_path == metadata_path
                else _expected_checksums(file_expectations.get(file_path.name))
            )
            try:
                current = file_sha256(file_path)
            except OSError as exc:
                _add_evidence(
                    rows,
                    evidence_type="reviewed_shadow_archive_file",
                    evidence_path=_display_path(file_path, repository_root),
                    required=True,
                    expected_checksums=expected,
                    status="Missing",
                    details=f"Archived file is unreadable: {exc}",
                )
                continue
            file_status, file_note = _checksum_status(current, expected)
            if file_path == metadata_path and not expected_metadata:
                file_status = "Stale"
                file_note = "Human receipt did not bind the metadata checksum."
            elif file_path == metadata_path and not metadata_reference_matches:
                file_status = "Stale"
                file_note = "Human receipt references a different metadata file."
            elif not expected and bundle_status == "Included":
                file_status = "Included"
                file_note = "File is bound through the verified archive checksum."
            elif not expected and bundle_status != "Included":
                file_status = "Checksum mismatch"
                file_note = "Archive bundle changed and this file has no direct checksum."
            _add_evidence(
                rows,
                evidence_type="reviewed_shadow_archive_file",
                evidence_path=_display_path(file_path, repository_root),
                required=True,
                expected_checksums=expected,
                current_checksum=current,
                status=file_status,
                details=f"{file_note} Archive-relative path: `{relative}`.",
            )
        if metadata_error:
            relationship_issues.append(metadata_error)

    return normalized_paths, relationship_issues


def calculate_provider_allowlist_evidence_bundle_identity(
    provider_key: str,
    evidence_manifest: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    """Return the canonical checksum and ID for a provider evidence manifest."""
    entries = {
        (
            _clean(item.get("path")),
            _clean(item.get("checksum_sha256")).casefold(),
        )
        for item in evidence_manifest
        if _clean(item.get("path"))
        and SHA256_PATTERN.fullmatch(
            _clean(item.get("checksum_sha256")).casefold()
        )
    }
    manifest = [
        {"path": path, "checksum_sha256": checksum}
        for path, checksum in sorted(entries)
    ]
    digest_payload = {
        "provider_key": provider_key,
        "evidence": manifest,
    }
    digest = sha256(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    bundle_id = f"{_slug(provider_key)}-allowlist-evidence-{digest[:16]}"
    return digest, bundle_id


def _bundle_manifest(
    provider_key: str,
    rows: list[dict[str, object]],
) -> tuple[list[dict[str, str]], str, str]:
    entries = {
        (
            _clean(row.get("evidence_path")),
            _clean(row.get("current_checksum_sha256")).casefold(),
        )
        for row in rows
        if _clean(row.get("evidence_path"))
        and SHA256_PATTERN.fullmatch(
            _clean(row.get("current_checksum_sha256")).casefold()
        )
    }
    manifest = [
        {"path": path, "checksum_sha256": checksum}
        for path, checksum in sorted(entries)
    ]
    digest, bundle_id = calculate_provider_allowlist_evidence_bundle_identity(
        provider_key,
        manifest,
    )
    return manifest, digest, bundle_id


def _bundle_verdict(rows: list[dict[str, object]]) -> str:
    if any(_clean(row.get("status")) == "Checksum mismatch" for row in rows):
        return "Evidence changed"
    if any(
        _clean(row.get("required")) == "Yes"
        and _clean(row.get("status")) == "Missing"
        for row in rows
    ):
        return "Missing required evidence"
    if any(_clean(row.get("status")) == "Stale" for row in rows):
        return "Not ready for PR review"
    return "Evidence bundle ready for PR review"


def build_provider_allowlist_evidence_bundle(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    policy_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    root = (repository_root or PROJECT_ROOT).resolve()
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    provider = create_provider(provider_name)
    provider_key = provider.provider_key
    canonical_name = provider.provider_name
    rows: list[dict[str, object]] = []

    selected_policy_path = (
        policy_path
        if policy_path is not None
        else root / "data" / "manual" / STAGING_PROVIDER_POLICY_PATH.name
    )
    if not selected_policy_path.is_absolute():
        selected_policy_path = root / selected_policy_path
    paths = {
        "preview": outputs / PREVIEW_JSON_FILENAME,
        "conformance": outputs / CONFORMANCE_JSON_FILENAME,
        "verification": outputs / VERIFICATION_JSON_FILENAME,
        "receipt": outputs / RECEIPT_JSON_FILENAME,
        "checklist": outputs / ACCEPTANCE_JSON_FILENAME,
        "comparison": outputs / COMPARISON_JSON_FILENAME,
        "policy": selected_policy_path.resolve(),
    }
    loaded: dict[str, dict[str, object] | None] = {}
    checksums: dict[str, str] = {}
    errors: dict[str, str] = {}
    for key, path in paths.items():
        payload, checksum, error = _read_json_file(path, label=key.replace("_", " "))
        loaded[key] = payload
        checksums[key] = checksum
        errors[key] = error

    preview = loaded["preview"] or {}
    verification = loaded["verification"] or {}
    receipt = loaded["receipt"] or {}
    checklist = loaded["checklist"] or {}
    comparison = loaded["comparison"] or {}
    conformance = loaded["conformance"] or {}
    policy = loaded["policy"] or {}

    preview_stale: list[str] = []
    if preview and not _provider_matches(preview, provider_key):
        preview_stale.append("Preview belongs to a different provider.")
    if _clean(preview.get("status")) != READY_STATUS:
        preview_stale.append("Preview is not Ready for a separate allowlist PR.")
    if not _clean(preview.get("recommended_pr_title")) or not _clean(
        preview.get("recommended_pr_description")
    ):
        preview_stale.append("Ready preview is missing recommended PR text.")
    _record_json_evidence(
        rows,
        evidence_type="provider_allowlist_pr_preview",
        display_path=_display_path(paths["preview"], root),
        payload=loaded["preview"],
        checksum=checksums["preview"],
        error=errors["preview"],
        required=True,
        stale_reasons=preview_stale,
        verdict_field="status",
    )

    preview_verification = _mapping(preview.get("verification"))
    verification_expected = _expected_checksums(
        preview_verification.get("checksum_sha256")
    )
    verification_stale: list[str] = []
    if not verification_expected:
        verification_stale.append(
            "Preview does not bind the receipt-verification checksum."
        )
    if not _reference_matches(
        preview_verification.get("path"),
        paths["verification"],
        repository_root=root,
        output_dir=outputs,
    ):
        verification_stale.append(
            "Preview references a different receipt-verification file."
        )
    if verification and not _provider_matches(verification, provider_key):
        verification_stale.append("Receipt verification belongs to another provider.")
    if _clean(verification.get("verdict")) != "Verified for allowlist PR review":
        verification_stale.append(
            "Human receipt verification is not Verified for allowlist PR review."
        )
    if _clean(verification.get("decision")) != APPROVAL_DECISION:
        verification_stale.append("Receipt verification does not record approval.")
    if _clean(verification.get("checklist_verdict")) != READY_VERDICT:
        verification_stale.append(
            "Receipt verification does not record a Ready acceptance checklist."
        )
    _record_json_evidence(
        rows,
        evidence_type="provider_human_acceptance_receipt_verification",
        display_path=_display_path(paths["verification"], root),
        payload=loaded["verification"],
        checksum=checksums["verification"],
        error=errors["verification"],
        required=True,
        expected_checksums=verification_expected,
        stale_reasons=verification_stale,
    )

    receipt_expected = _expected_checksums(
        verification.get("receipt_checksum_sha256"),
        preview_verification.get("receipt_checksum_sha256"),
    )
    receipt_stale: list[str] = []
    if not receipt_expected:
        receipt_stale.append(
            "Preview and verification do not bind the human receipt checksum."
        )
    receipt_references = (
        verification.get("receipt_path"),
        preview_verification.get("receipt_path"),
    )
    if any(
        not _reference_matches(
            reference,
            paths["receipt"],
            repository_root=root,
            output_dir=outputs,
        )
        for reference in receipt_references
    ):
        receipt_stale.append(
            "Preview or verification references a different human receipt file."
        )
    receipt_id = _clean(receipt.get("receipt_id"))
    bound_receipt_ids = {
        _clean(verification.get("receipt_id")),
        _clean(preview_verification.get("receipt_id")),
    }
    if not receipt_id or any(
        bound_id != receipt_id for bound_id in bound_receipt_ids
    ):
        receipt_stale.append("Human receipt ID does not match its bound evidence.")
    if receipt and not _provider_matches(receipt, provider_key):
        receipt_stale.append("Human acceptance receipt belongs to another provider.")
    if _clean(receipt.get("decision")) != APPROVAL_DECISION:
        receipt_stale.append("Human receipt decision does not approve an allowlist PR.")
    approval_gate = _mapping(receipt.get("approval_gate"))
    if (
        _clean(approval_gate.get("status")) != "Passed"
        or approval_gate.get("override_used") is True
    ):
        receipt_stale.append("Human approval gate did not pass without override.")
    if _clean(receipt.get("checklist_verdict")) != READY_VERDICT:
        receipt_stale.append("Receipt checklist verdict is not ready for human review.")
    if not _clean(receipt.get("reviewer_name")) or _clean(
        verification.get("reviewer_name")
    ) != _clean(receipt.get("reviewer_name")):
        receipt_stale.append("Receipt reviewer does not match its verification.")
    if not _clean(receipt.get("created_at")) or _clean(
        verification.get("receipt_created_at")
    ) != _clean(receipt.get("created_at")):
        receipt_stale.append("Receipt timestamp does not match its verification.")
    _record_json_evidence(
        rows,
        evidence_type="provider_human_acceptance_receipt",
        display_path=_display_path(paths["receipt"], root),
        payload=loaded["receipt"],
        checksum=checksums["receipt"],
        error=errors["receipt"],
        required=True,
        expected_checksums=receipt_expected,
        stale_reasons=receipt_stale,
        verdict_field="decision",
    )

    receipt_evidence = _mapping(receipt.get("evidence"))
    receipt_checklist = _mapping(receipt_evidence.get("checklist"))
    checklist_expected = _expected_checksums(
        receipt_checklist.get("checksum_sha256")
    )
    checklist_stale: list[str] = []
    if not checklist_expected:
        checklist_stale.append("Human receipt does not bind the checklist checksum.")
    if not _reference_matches(
        receipt_checklist.get("path"),
        paths["checklist"],
        repository_root=root,
        output_dir=outputs,
    ):
        checklist_stale.append("Human receipt references a different checklist file.")
    if checklist and not _provider_matches(checklist, provider_key):
        checklist_stale.append("Acceptance checklist belongs to another provider.")
    if _clean(checklist.get("verdict")) != READY_VERDICT:
        checklist_stale.append("Acceptance checklist is not ready for human review.")
    _record_json_evidence(
        rows,
        evidence_type="provider_acceptance_checklist",
        display_path=_display_path(paths["checklist"], root),
        payload=loaded["checklist"],
        checksum=checksums["checklist"],
        error=errors["checklist"],
        required=True,
        expected_checksums=checklist_expected,
        stale_reasons=checklist_stale,
    )

    receipt_comparison = _mapping(receipt_evidence.get("comparison"))
    comparison_expected = _expected_checksums(
        receipt_comparison.get("checksum_sha256")
    )
    comparison_stale: list[str] = []
    if not comparison_expected:
        comparison_stale.append("Human receipt does not bind the comparison checksum.")
    if _clean(receipt_comparison.get("status")) != "Bound":
        comparison_stale.append("Human receipt did not bind a shadow comparison.")
    if not _reference_matches(
        receipt_comparison.get("path"),
        paths["comparison"],
        repository_root=root,
        output_dir=outputs,
    ):
        comparison_stale.append("Human receipt references a different comparison file.")
    if comparison and not _provider_matches(comparison, provider_key):
        comparison_stale.append("Shadow comparison belongs to another provider.")
    if comparison and _clean(comparison.get("verdict")) != "Stable enough for review":
        comparison_stale.append("Shadow comparison is not stable enough for review.")
    if comparison and _clean(receipt_comparison.get("verdict")) != _clean(
        comparison.get("verdict")
    ):
        comparison_stale.append("Human receipt records a different comparison verdict.")

    reviewed_paths, archive_issues = _collect_reviewed_archives(
        rows,
        receipt=receipt,
        checklist=checklist,
        repository_root=root,
        output_dir=outputs,
    )
    live_history = [
        record
        for record in load_provider_shadow_run_history(
            outputs,
            provider_name=provider_key,
        )
        if _clean(record.get("mode")) == "Live shadow run"
    ]
    current_reviewed_paths: list[str] = []
    for record in live_history[: len(reviewed_paths)]:
        history_path, history_error = _resolve_reference(
            record.get("archive_path"),
            repository_root=root,
            output_dir=outputs,
        )
        if not history_error and history_path is not None:
            current_reviewed_paths.append(_display_path(history_path, root))
    if reviewed_paths and set(current_reviewed_paths) != reviewed_paths:
        archive_issues.append(
            "Newer or different live shadow archives exist than the receipt reviewed."
        )

    compared_paths = {
        key: _clean(_mapping(comparison.get(key)).get("archive_path"))
        for key in ("latest_run", "previous_run")
    }
    normalized_compared: dict[str, str] = {}
    for key, compared in compared_paths.items():
        if not compared:
            continue
        compared_path, compared_error = _resolve_reference(
            compared,
            repository_root=root,
            output_dir=outputs,
        )
        if compared_error or compared_path is None:
            comparison_stale.append(
                f"Comparison archive path is unsafe or missing: `{compared}`."
            )
        else:
            normalized_compared[key] = _display_path(compared_path, root)
    if normalized_compared and not set(normalized_compared.values()).issubset(
        reviewed_paths
    ):
        comparison_stale.append(
            "Latest shadow comparison does not use only receipt-reviewed archives."
        )
    expected_pair = current_reviewed_paths[:2]
    compared_pair = [
        normalized_compared.get("latest_run", ""),
        normalized_compared.get("previous_run", ""),
    ]
    if comparison and (len(expected_pair) < 2 or compared_pair != expected_pair):
        comparison_stale.append(
            "Shadow comparison does not identify the newest two reviewed live archives."
        )
    comparison_stale.extend(archive_issues)
    _record_json_evidence(
        rows,
        evidence_type="provider_shadow_run_comparison",
        display_path=_display_path(paths["comparison"], root),
        payload=loaded["comparison"],
        checksum=checksums["comparison"],
        error=errors["comparison"],
        required=True,
        expected_checksums=comparison_expected,
        stale_reasons=comparison_stale,
    )

    conformance_present = paths["conformance"].exists()
    conformance_stale: list[str] = []
    if conformance_present:
        if conformance and not _provider_matches(conformance, provider_key):
            conformance_stale.append("Conformance report belongs to another provider.")
        if _clean(conformance.get("verdict")) != CONFORMS_VERDICT:
            conformance_stale.append("Policy conformance verdict is not Conforms to preview.")
        conformance_preview = _mapping(conformance.get("preview"))
        conformance_bound_preview = _clean(
            conformance_preview.get("checksum_sha256")
        ).casefold()
        if not _reference_matches(
            conformance_preview.get("path"),
            paths["preview"],
            repository_root=root,
            output_dir=outputs,
        ):
            conformance_stale.append(
                "Conformance report references a different allowlist preview."
            )
        _record_json_evidence(
            rows,
            evidence_type="provider_allowlist_pr_conformance",
            display_path=_display_path(paths["conformance"], root),
            payload=loaded["conformance"],
            checksum=checksums["conformance"],
            error=errors["conformance"],
            required=False,
            stale_reasons=conformance_stale,
        )
        if conformance_bound_preview != checksums["preview"]:
            _add_evidence(
                rows,
                evidence_type="conformance_preview_binding",
                evidence_path=_display_path(paths["preview"], root),
                required=False,
                expected_checksums=_expected_checksums(conformance_bound_preview),
                current_checksum=checksums["preview"],
                status="Checksum mismatch",
                details="Conformance report binds a different preview checksum.",
            )
    else:
        _add_evidence(
            rows,
            evidence_type="provider_allowlist_pr_conformance",
            evidence_path=_display_path(paths["conformance"], root),
            required=False,
            status="Not applicable",
            details=(
                "No policy change has been checked yet; conformance is optional "
                "before PR review."
            ),
        )

    receipt_policy = _mapping(receipt_evidence.get("provider_policy"))
    preview_policy = _mapping(preview.get("policy"))
    conformance_policy = _mapping(conformance.get("policy"))
    policy_expected = (
        _expected_checksums(conformance_policy.get("checksum_sha256"))
        if conformance_present
        and _clean(conformance.get("verdict")) == CONFORMS_VERDICT
        else _expected_checksums(
            receipt_policy.get("checksum_sha256"),
            preview_policy.get("checksum_sha256"),
        )
    )
    policy_stale: list[str] = []
    if not policy_expected:
        policy_stale.append("No trusted policy checksum is bound by the evidence.")
    if _clean(receipt_policy.get("status")) != "Bound":
        policy_stale.append("Human receipt did not bind the provider policy.")
    if not _reference_matches(
        receipt_policy.get("path"),
        paths["policy"],
        repository_root=root,
        output_dir=outputs,
    ):
        policy_stale.append("Human receipt references a different provider policy file.")
    if not _reference_matches(
        preview_policy.get("path"),
        paths["policy"],
        repository_root=root,
        output_dir=outputs,
    ):
        policy_stale.append("Allowlist preview references a different policy file.")
    policy_reference = (
        conformance_policy.get("path")
        if conformance_present
        and _clean(conformance.get("verdict")) == CONFORMS_VERDICT
        else receipt_policy.get("path")
    )
    if not _reference_matches(
        policy_reference,
        paths["policy"],
        repository_root=root,
        output_dir=outputs,
    ):
        policy_stale.append("Evidence references a different provider policy file.")
    if conformance_present and _clean(conformance.get("verdict")) == CONFORMS_VERDICT:
        expected_policy = conformance.get("expected_policy")
        actual_policy = conformance.get("actual_policy")
        if expected_policy != policy or actual_policy != policy:
            policy_stale.append(
                "Current policy content differs from the conformance-verified policy."
            )
    _record_json_evidence(
        rows,
        evidence_type="staging_provider_policy",
        display_path=_display_path(paths["policy"], root),
        payload=loaded["policy"],
        checksum=checksums["policy"],
        error=errors["policy"],
        required=True,
        expected_checksums=policy_expected,
        stale_reasons=policy_stale,
        verdict_field="allowlist_status",
    )

    manifest, bundle_checksum, bundle_id = _bundle_manifest(provider_key, rows)
    verdict = _bundle_verdict(rows)
    if verdict not in BUNDLE_VERDICTS:
        raise ValueError(f"Unexpected provider evidence bundle verdict: {verdict}")
    generated_at = (run_at or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    status_counts = Counter(_clean(row.get("status")) for row in rows)
    summary: dict[str, object] = {
        "schema_version": 1,
        "generated_at": generated_at,
        "provider_key": provider_key,
        "provider_name": canonical_name,
        "bundle_id": bundle_id,
        "bundle_checksum_sha256": bundle_checksum,
        "verdict": verdict,
        "preview_verdict": _clean(preview.get("status")) or "Missing",
        "conformance_verdict": (
            _clean(conformance.get("verdict"))
            if conformance_present
            else "Not applicable"
        ),
        "receipt_verification_verdict": (
            _clean(verification.get("verdict")) or "Missing"
        ),
        "receipt_id": _clean(receipt.get("receipt_id")),
        "checklist_verdict": _clean(checklist.get("verdict")) or "Missing",
        "recommended_pr_title": _clean(preview.get("recommended_pr_title")),
        "recommended_pr_description": _clean(
            preview.get("recommended_pr_description")
        ),
        "evidence_file_count": len(manifest),
        "evidence_manifest": manifest,
        "status_counts": dict(sorted(status_counts.items())),
        "evidence": rows,
        "safety": {
            "read_only_evidence_bundle": True,
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
    return pd.DataFrame(rows, columns=BUNDLE_COLUMNS), summary


def render_provider_allowlist_evidence_bundle(
    evidence: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    lines = [
        "# Provider Allowlist PR Evidence Bundle",
        "",
        "**Nothing was applied.** This checksum-bound report only gathers and "
        "verifies existing review evidence. It does not edit provider policy, "
        "allowlist a provider, promote staging, run providers, generate picks, "
        "place bets, or enable cron.",
        "",
        "## Bundle verdict",
        "",
        f"- **{summary.get('verdict', 'Not ready for PR review')}**",
        f"- Provider: **{summary.get('provider_name', '')}** "
        f"(`{summary.get('provider_key', '')}`)",
        f"- Bundle ID: `{summary.get('bundle_id', '')}`",
        f"- Bundle SHA-256: `{summary.get('bundle_checksum_sha256', '')}`",
        f"- Included checksum entries: **{summary.get('evidence_file_count', 0)}**",
        "",
        "## Review decisions",
        "",
        f"- Preview verdict: **{summary.get('preview_verdict', 'Missing')}**",
        f"- Conformance verdict: **{summary.get('conformance_verdict', 'Not applicable')}**",
        "- Receipt verification verdict: "
        f"**{summary.get('receipt_verification_verdict', 'Missing')}**",
        f"- Human receipt ID: `{summary.get('receipt_id', '') or 'Missing'}`",
        f"- Checklist verdict: **{summary.get('checklist_verdict', 'Missing')}**",
        "",
        "## Included evidence and status",
        "",
        evidence.to_markdown(index=False),
        "",
        "## Checksum manifest",
        "",
        "```json",
        json.dumps(summary.get("evidence_manifest", []), indent=2, sort_keys=True),
        "```",
        "",
        "## Recommended provider allowlist PR",
        "",
        f"- Title: {summary.get('recommended_pr_title', '') or 'Not available'}",
        "- Description:",
        "",
        _clean(summary.get("recommended_pr_description"))
        or "Generate a Ready allowlist PR preview before opening a policy PR.",
        "",
        "## Decision boundary",
        "",
        "A ready bundle proves which evidence bytes were reviewed; it does not "
        "make the policy change. Provider allowlisting remains a separate PR, and "
        "cron remains disabled until a later independent review explicitly enables it.",
    ]
    return "\n".join(lines)


def _unique_archive_dir(
    output_dir: Path,
    summary: Mapping[str, object],
) -> Path:
    generated_at = datetime.fromisoformat(_clean(summary.get("generated_at")))
    date_dir = output_dir / BUNDLE_ARCHIVE_ROOT / generated_at.strftime("%Y-%m-%d")
    stem = (
        f"{generated_at.strftime('%H%M%S')}_"
        f"{_slug(summary.get('provider_key'))}_"
        f"{_clean(summary.get('bundle_checksum_sha256'))[:12]}"
    )
    candidate = date_dir / stem
    suffix = 2
    while candidate.exists():
        candidate = date_dir / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def save_provider_allowlist_evidence_bundle(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    policy_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    root = (repository_root or PROJECT_ROOT).resolve()
    evidence, summary = build_provider_allowlist_evidence_bundle(
        provider_name,
        outputs,
        policy_path=policy_path,
        repository_root=root,
        run_at=run_at,
    )
    archive_dir = _unique_archive_dir(outputs, summary)
    stored_summary = deepcopy(summary)
    stored_summary["bundle_storage"] = {
        "latest_json_path": _display_path(outputs / BUNDLE_JSON_FILENAME, root),
        "latest_markdown_path": _display_path(
            outputs / BUNDLE_MARKDOWN_FILENAME,
            root,
        ),
        "latest_csv_path": _display_path(outputs / BUNDLE_CSV_FILENAME, root),
        "archive_directory": _display_path(archive_dir, root),
    }
    payloads = {
        BUNDLE_JSON_FILENAME: (
            json.dumps(stored_summary, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        BUNDLE_MARKDOWN_FILENAME: render_provider_allowlist_evidence_bundle(
            evidence,
            stored_summary,
        ).encode("utf-8"),
        BUNDLE_CSV_FILENAME: evidence.to_csv(
            index=False,
            lineterminator="\n",
        ).encode("utf-8"),
    }
    latest_paths: dict[str, Path] = {}
    archive_paths: dict[str, Path] = {}
    for filename, content in payloads.items():
        latest = outputs / filename
        archived = archive_dir / filename
        atomic_write_report(latest, content)
        atomic_write_report(archived, content)
        latest_paths[filename] = latest
        archive_paths[filename] = archived
    return {
        "summary": stored_summary,
        "evidence": evidence,
        "verdict": stored_summary["verdict"],
        "json": latest_paths[BUNDLE_JSON_FILENAME],
        "markdown": latest_paths[BUNDLE_MARKDOWN_FILENAME],
        "csv": latest_paths[BUNDLE_CSV_FILENAME],
        "archive_directory": archive_dir,
        "archive_paths": archive_paths,
    }
