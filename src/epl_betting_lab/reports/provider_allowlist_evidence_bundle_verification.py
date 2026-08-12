from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime
import json
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import (
    atomic_write_report,
    file_sha256,
    path_contains_symlink,
)
from epl_betting_lab.providers.provider_registry import create_provider
from epl_betting_lab.reports.provider_allowlist_evidence_bundle import (
    BUNDLE_ARCHIVE_ROOT,
    BUNDLE_JSON_FILENAME,
    SHA256_PATTERN,
    calculate_provider_allowlist_evidence_bundle_identity,
)
from epl_betting_lab.reports.provider_allowlist_pr_conformance import (
    CONFORMS_VERDICT,
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import READY_STATUS
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    ProviderHumanAcceptanceReceiptError,
    calculate_shadow_archive_bundle_checksum,
)


VERIFICATION_JSON_FILENAME = (
    "provider_allowlist_evidence_bundle_verification.json"
)
VERIFICATION_MARKDOWN_FILENAME = (
    "provider_allowlist_evidence_bundle_verification.md"
)
VERIFICATION_CSV_FILENAME = (
    "provider_allowlist_evidence_bundle_verification.csv"
)
READY_BUNDLE_VERDICT = "Evidence bundle ready for PR review"
READY_RECEIPT_VERIFICATION_VERDICT = "Verified for allowlist PR review"
VERIFIED_VERDICT = "Evidence bundle verified for PR approval review"

VERIFICATION_STATUSES = (
    "Verified",
    "Missing evidence",
    "Checksum mismatch",
    "Bundle ID mismatch",
    "Malformed bundle",
    "Not ready",
    "Not applicable",
)
VERIFICATION_VERDICTS = (
    VERIFIED_VERDICT,
    "Missing required evidence",
    "Evidence changed",
    "Bundle mismatch",
    "Malformed bundle",
    "Not ready for PR approval review",
)
VERIFICATION_COLUMNS = (
    "category",
    "check",
    "evidence_type",
    "evidence_path",
    "required",
    "expected",
    "observed",
    "status",
    "details",
)
REQUIRED_EVIDENCE_TYPES = (
    "provider_allowlist_pr_preview",
    "provider_human_acceptance_receipt_verification",
    "provider_human_acceptance_receipt",
    "provider_acceptance_checklist",
    "provider_shadow_run_comparison",
    "reviewed_shadow_archive_bundle",
    "reviewed_shadow_archive_file",
    "staging_provider_policy",
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


def _slug(value: object) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", _clean(value).casefold()).strip("_")
    return slug or "unknown_provider"


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repository_root).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _provider_matches(payload: Mapping[str, object], provider_name: str) -> bool:
    requested = _slug(provider_name)
    return requested in {
        _slug(payload.get("provider_key")),
        _slug(payload.get("provider_name")),
    }


def _add_check(
    rows: list[dict[str, object]],
    *,
    category: str,
    check: str,
    status: str,
    evidence_type: object = "",
    evidence_path: object = "",
    required: bool = False,
    expected: object = "",
    observed: object = "",
    details: str = "",
) -> None:
    if status not in VERIFICATION_STATUSES:
        raise ValueError(f"Unexpected evidence bundle verification status: {status}")
    rows.append(
        {
            "category": category,
            "check": check,
            "evidence_type": _clean(evidence_type),
            "evidence_path": _clean(evidence_path),
            "required": "Yes" if required else "No",
            "expected": _clean(expected),
            "observed": _clean(observed),
            "status": status,
            "details": details,
        }
    )


def _resolve_repository_path(
    value: object,
    *,
    repository_root: Path,
    output_dir: Path,
    output_relative: bool = True,
) -> tuple[Path | None, str]:
    text = _clean(value)
    if not text:
        return None, "Evidence path is blank."
    raw = Path(text)
    if raw.is_absolute():
        candidate = raw
    elif text.replace("\\", "/").startswith("data/") or not output_relative:
        candidate = repository_root / raw
    else:
        candidate = output_dir / raw
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(repository_root)
    except (OSError, RuntimeError, ValueError):
        return candidate, "Path must remain inside the repository."
    if path_contains_symlink(candidate.absolute(), repository_root):
        return resolved, "Path cannot use a symbolic link."
    return resolved, ""


def _archive_bundle_candidates(
    output_dir: Path,
    provider_key: str,
) -> list[Path]:
    root = output_dir / BUNDLE_ARCHIVE_ROOT
    provider_marker = f"_{_slug(provider_key)}_"
    if not root.is_dir() or root.is_symlink():
        return []
    candidates = [
        path
        for path in root.glob(f"*/*/{BUNDLE_JSON_FILENAME}")
        if path.is_file()
        and not path.is_symlink()
        and provider_marker in f"_{path.parent.name}_"
    ]
    return sorted(
        candidates,
        key=lambda path: path.relative_to(root).as_posix(),
        reverse=True,
    )


def select_provider_allowlist_evidence_bundle(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    bundle_path: Path | None = None,
    repository_root: Path | None = None,
) -> tuple[Path, str, str]:
    root = (repository_root or PROJECT_ROOT).resolve()
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    provider = create_provider(provider_name)
    if bundle_path is not None:
        selected, error = _resolve_repository_path(
            bundle_path,
            repository_root=root,
            output_dir=outputs,
            output_relative=False,
        )
        return (
            selected or bundle_path,
            "Provided bundle path",
            error,
        )
    archived = _archive_bundle_candidates(outputs, provider.provider_key)
    if archived:
        return archived[0], "Latest archived provider bundle", ""
    return (
        outputs / BUNDLE_JSON_FILENAME,
        "Latest output fallback",
        "No archived provider bundle was found; checking the latest output file.",
    )


def _load_bundle(
    path: Path,
) -> tuple[dict[str, object] | None, str, str]:
    if not path.exists():
        return None, "Missing evidence", "Bundle JSON does not exist."
    if not path.is_file() or path.is_symlink():
        return None, "Malformed bundle", (
            "Bundle path must be a regular, non-symlinked JSON file."
        )
    try:
        content = path.read_bytes()
        payload = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, "Malformed bundle", f"Bundle JSON could not be read: {exc}"
    if not isinstance(payload, dict):
        return None, "Malformed bundle", "Bundle JSON root must be an object."
    return payload, "Verified", "Bundle JSON is readable."


def _evidence_records(
    bundle: Mapping[str, object],
) -> tuple[list[Mapping[str, object]], str]:
    value = bundle.get("evidence")
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        return [], "Bundle `evidence` must be a list of objects."
    return list(value), ""


def _manifest_records(
    bundle: Mapping[str, object],
) -> tuple[list[dict[str, str]], list[str]]:
    value = bundle.get("evidence_manifest")
    if not isinstance(value, list):
        return [], ["Bundle `evidence_manifest` must be a list."]
    records: list[dict[str, str]] = []
    issues: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value, start=1):
        if not isinstance(item, Mapping):
            issues.append(f"Manifest entry {index} is not an object.")
            continue
        path = _clean(item.get("path"))
        checksum = _clean(item.get("checksum_sha256")).casefold()
        if not path or not SHA256_PATTERN.fullmatch(checksum):
            issues.append(
                f"Manifest entry {index} needs a path and 64-character SHA-256."
            )
            continue
        if path in seen:
            issues.append(f"Manifest path is duplicated: `{path}`.")
            continue
        seen.add(path)
        records.append({"path": path, "checksum_sha256": checksum})
    if not records:
        issues.append("Bundle manifest contains no readable evidence entries.")
    return records, issues


def _record_metadata(
    evidence: list[Mapping[str, object]],
) -> tuple[dict[str, set[str]], dict[str, bool]]:
    evidence_types: dict[str, set[str]] = {}
    required: dict[str, bool] = {}
    for record in evidence:
        path = _clean(record.get("evidence_path"))
        if not path:
            continue
        evidence_types.setdefault(path, set()).add(
            _clean(record.get("evidence_type"))
        )
        if _clean(record.get("required")).casefold() in {"yes", "true", "1"}:
            required[path] = True
        else:
            required.setdefault(path, False)
    return evidence_types, required


def _hash_manifest_path(
    path: Path,
    evidence_types: set[str],
) -> tuple[str, str]:
    if not path.exists():
        return "", "Evidence path no longer exists."
    if path.is_symlink():
        return "", "Evidence path is a symbolic link."
    if path.is_file():
        try:
            return file_sha256(path), ""
        except OSError as exc:
            return "", f"Evidence file could not be hashed: {exc}"
    if path.is_dir() and "reviewed_shadow_archive_bundle" in evidence_types:
        try:
            checksum, _ = calculate_shadow_archive_bundle_checksum(path)
            return checksum, ""
        except (OSError, ProviderHumanAcceptanceReceiptError) as exc:
            return "", f"Reviewed archive could not be hashed: {exc}"
    return "", "Evidence path is not a supported regular file or archive bundle."


def _semantic_status(
    rows: list[dict[str, object]],
    *,
    check: str,
    expected: str,
    observed: object,
    not_applicable: str = "",
) -> None:
    actual = _clean(observed)
    if not_applicable and actual == not_applicable:
        status = "Not applicable"
        details = "This evidence stage was not applicable when the bundle was built."
    else:
        status = "Verified" if actual == expected else "Not ready"
        details = (
            "Recorded review verdict remains acceptable."
            if status == "Verified"
            else "Recorded review verdict is not acceptable for PR approval review."
        )
    _add_check(
        rows,
        category="Review state",
        check=check,
        status=status,
        expected=(
            f"{expected} or {not_applicable}" if not_applicable else expected
        ),
        observed=actual or "Missing",
        details=details,
    )


def _verification_verdict(rows: list[dict[str, object]]) -> str:
    statuses = {_clean(row.get("status")) for row in rows}
    if "Malformed bundle" in statuses:
        return "Malformed bundle"
    if "Missing evidence" in statuses:
        return "Missing required evidence"
    if "Checksum mismatch" in statuses:
        return "Evidence changed"
    if "Bundle ID mismatch" in statuses:
        return "Bundle mismatch"
    if "Not ready" in statuses:
        return "Not ready for PR approval review"
    return VERIFIED_VERDICT


def _blockers(rows: list[dict[str, object]]) -> list[str]:
    return list(
        dict.fromkeys(
            f"{row['check']}: {row['details']}"
            for row in rows
            if _clean(row.get("status")) not in {"Verified", "Not applicable"}
        )
    )


def build_provider_allowlist_evidence_bundle_verification(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    bundle_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    root = (repository_root or PROJECT_ROOT).resolve()
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    provider = create_provider(provider_name)
    selected, source, selection_note = select_provider_allowlist_evidence_bundle(
        provider.provider_key,
        outputs,
        bundle_path=bundle_path,
        repository_root=root,
    )
    rows: list[dict[str, object]] = []
    if source == "Provided bundle path" and selection_note:
        _add_check(
            rows,
            category="Bundle",
            check="Bundle path safety",
            status="Malformed bundle",
            evidence_type="provider_allowlist_evidence_bundle",
            evidence_path=_display_path(selected, root),
            required=True,
            expected="Repository-local non-symlinked bundle path",
            observed="Unsafe path",
            details=selection_note,
        )
        verdict = _verification_verdict(rows)
        summary = _build_summary(
            provider_key=provider.provider_key,
            provider_name=provider.provider_name,
            selected=selected,
            source=source,
            bundle={},
            rows=rows,
            verdict=verdict,
            run_at=run_at,
            repository_root=root,
        )
        return pd.DataFrame(rows, columns=VERIFICATION_COLUMNS), summary

    bundle, load_status, load_note = _load_bundle(selected)
    _add_check(
        rows,
        category="Bundle",
        check="Bundle file",
        status=load_status,
        evidence_type="provider_allowlist_evidence_bundle",
        evidence_path=_display_path(selected, root),
        required=True,
        expected="Readable bundle JSON",
        observed=load_status,
        details=" ".join(item for item in (load_note, selection_note) if item),
    )
    _add_check(
        rows,
        category="Bundle",
        check="Archived bundle selection",
        status=("Not ready" if source == "Latest output fallback" else "Verified"),
        evidence_type="provider_allowlist_evidence_bundle",
        evidence_path=_display_path(selected, root),
        required=True,
        expected="Latest archived bundle or explicit reviewed path",
        observed=source,
        details=(
            "No archived bundle was found. Build the evidence bundle before "
            "approval-time verification."
            if source == "Latest output fallback"
            else "The latest archived bundle or explicit reviewed path was selected."
        ),
    )

    if bundle is None:
        verdict = _verification_verdict(rows)
        summary = _build_summary(
            provider_key=provider.provider_key,
            provider_name=provider.provider_name,
            selected=selected,
            source=source,
            bundle={},
            rows=rows,
            verdict=verdict,
            run_at=run_at,
            repository_root=root,
        )
        return pd.DataFrame(rows, columns=VERIFICATION_COLUMNS), summary

    provider_status = (
        "Verified" if _provider_matches(bundle, provider.provider_key) else "Not ready"
    )
    _add_check(
        rows,
        category="Bundle",
        check="Provider identity",
        status=provider_status,
        expected=provider.provider_key,
        observed=bundle.get("provider_key", bundle.get("provider_name", "Missing")),
        details=(
            "Bundle provider matches the requested provider."
            if provider_status == "Verified"
            else "Bundle belongs to a different or unidentified provider."
        ),
    )
    _semantic_status(
        rows,
        check="Original bundle verdict",
        expected=READY_BUNDLE_VERDICT,
        observed=bundle.get("verdict"),
    )
    _semantic_status(
        rows,
        check="Allowlist preview verdict",
        expected=READY_STATUS,
        observed=bundle.get("preview_verdict"),
    )
    _semantic_status(
        rows,
        check="Receipt verification verdict",
        expected=READY_RECEIPT_VERIFICATION_VERDICT,
        observed=bundle.get("receipt_verification_verdict"),
    )
    _semantic_status(
        rows,
        check="Conformance verdict",
        expected=CONFORMS_VERDICT,
        observed=bundle.get("conformance_verdict"),
        not_applicable="Not applicable",
    )

    evidence, evidence_error = _evidence_records(bundle)
    if evidence_error:
        _add_check(
            rows,
            category="Bundle",
            check="Evidence records",
            status="Malformed bundle",
            expected="List of evidence objects",
            observed=type(bundle.get("evidence")).__name__,
            details=evidence_error,
        )
    manifest, manifest_issues = _manifest_records(bundle)
    for issue in manifest_issues:
        _add_check(
            rows,
            category="Bundle",
            check="Evidence manifest",
            status="Malformed bundle",
            expected="Unique paths with valid SHA-256 checksums",
            observed="Malformed entry",
            details=issue,
        )

    evidence_types, required_by_path = _record_metadata(evidence)
    manifest_paths = {record["path"] for record in manifest}
    manifest_checksums = {
        record["path"]: record["checksum_sha256"] for record in manifest
    }
    for evidence_type in REQUIRED_EVIDENCE_TYPES:
        matching = [
            record
            for record in evidence
            if _clean(record.get("evidence_type")) == evidence_type
        ]
        included = [
            record
            for record in matching
            if _clean(record.get("required")).casefold()
            in {"yes", "true", "1"}
            and _clean(record.get("status")) == "Included"
        ]
        if not matching:
            _add_check(
                rows,
                category="Evidence",
                check="Required evidence category",
                status="Missing evidence",
                evidence_type=evidence_type,
                required=True,
                expected="At least one checksum-bound Included row",
                observed="Missing category",
                details=(
                    "The bundle omits a required provider review evidence category."
                ),
            )
        elif not included:
            _add_check(
                rows,
                category="Evidence",
                check="Required evidence category",
                status="Not ready",
                evidence_type=evidence_type,
                required=True,
                expected="At least one checksum-bound Included row",
                observed="No required Included row",
                details=(
                    "This required evidence category was not ready when the bundle "
                    "was built."
                ),
            )

    for record in evidence:
        required = _clean(record.get("required")).casefold() in {
            "yes",
            "true",
            "1",
        }
        path = _clean(record.get("evidence_path"))
        recorded_status = _clean(record.get("status"))
        row_checksum = _clean(record.get("current_checksum_sha256")).casefold()
        if recorded_status == "Included":
            if not path or path not in manifest_checksums:
                _add_check(
                    rows,
                    category="Evidence",
                    check="Included evidence binding",
                    status="Malformed bundle",
                    evidence_type=record.get("evidence_type"),
                    evidence_path=path,
                    required=required,
                    expected="Included evidence path in manifest",
                    observed="Missing from manifest",
                    details="An Included evidence row is not checksum-bound.",
                )
            elif not SHA256_PATTERN.fullmatch(row_checksum):
                _add_check(
                    rows,
                    category="Evidence",
                    check="Included evidence checksum",
                    status="Malformed bundle",
                    evidence_type=record.get("evidence_type"),
                    evidence_path=path,
                    required=required,
                    expected="64-character SHA-256",
                    observed=row_checksum or "Missing",
                    details="An Included evidence row has no valid checksum.",
                )
            elif manifest_checksums[path] != row_checksum:
                _add_check(
                    rows,
                    category="Evidence",
                    check="Included evidence checksum",
                    status="Malformed bundle",
                    evidence_type=record.get("evidence_type"),
                    evidence_path=path,
                    required=required,
                    expected=manifest_checksums[path],
                    observed=row_checksum,
                    details=(
                        "The evidence row checksum disagrees with the bundle manifest."
                    ),
                )
        if not required:
            continue
        if not path or path not in manifest_paths:
            _add_check(
                rows,
                category="Evidence",
                check="Required evidence binding",
                status="Missing evidence",
                evidence_type=record.get("evidence_type"),
                evidence_path=path,
                required=True,
                expected="Required evidence path in manifest",
                observed="Missing from manifest",
                details="A required bundle evidence row is not checksum-bound.",
            )
        elif recorded_status != "Included":
            _add_check(
                rows,
                category="Evidence",
                check="Original required evidence status",
                status="Not ready",
                evidence_type=record.get("evidence_type"),
                evidence_path=path,
                required=True,
                expected="Included",
                observed=recorded_status or "Missing",
                details="Required evidence was not Included in the original bundle.",
            )

    current_manifest: list[dict[str, str]] = []
    policy_paths = {
        path
        for path, types in evidence_types.items()
        if "staging_provider_policy" in types
    }
    if not policy_paths:
        _add_check(
            rows,
            category="Evidence",
            check="Provider policy binding",
            status="Missing evidence",
            evidence_type="staging_provider_policy",
            required=True,
            expected="Checksum-bound provider policy",
            observed="Missing",
            details="Bundle does not identify a provider policy evidence file.",
        )

    for record in manifest:
        recorded_path = record["path"]
        expected_checksum = record["checksum_sha256"]
        types = evidence_types.get(recorded_path, set())
        required = required_by_path.get(recorded_path, True)
        resolved, path_error = _resolve_repository_path(
            recorded_path,
            repository_root=root,
            output_dir=outputs,
        )
        if path_error or resolved is None:
            _add_check(
                rows,
                category="Evidence",
                check="Evidence checksum",
                status="Malformed bundle",
                evidence_type=", ".join(sorted(types)),
                evidence_path=recorded_path,
                required=required,
                expected=expected_checksum,
                observed="Unsafe path",
                details=path_error,
            )
            continue
        current_checksum, hash_error = _hash_manifest_path(resolved, types)
        if not current_checksum:
            _add_check(
                rows,
                category="Evidence",
                check="Evidence checksum",
                status="Missing evidence",
                evidence_type=", ".join(sorted(types)),
                evidence_path=recorded_path,
                required=required,
                expected=expected_checksum,
                observed="Missing or unreadable",
                details=hash_error,
            )
            continue
        current_manifest.append(
            {"path": recorded_path, "checksum_sha256": current_checksum}
        )
        status = (
            "Verified"
            if current_checksum == expected_checksum
            else "Checksum mismatch"
        )
        _add_check(
            rows,
            category="Evidence",
            check=(
                "Provider policy checksum"
                if recorded_path in policy_paths
                else "Evidence checksum"
            ),
            status=status,
            evidence_type=", ".join(sorted(types)),
            evidence_path=recorded_path,
            required=required,
            expected=expected_checksum,
            observed=current_checksum,
            details=(
                "Current evidence checksum matches the bundle."
                if status == "Verified"
                else "Evidence bytes changed after the bundle was built."
            ),
        )

    recorded_provider = _clean(bundle.get("provider_key"))
    stored_checksum = _clean(bundle.get("bundle_checksum_sha256")).casefold()
    stored_id = _clean(bundle.get("bundle_id"))
    if (
        not recorded_provider
        or not SHA256_PATTERN.fullmatch(stored_checksum)
        or not stored_id
    ):
        _add_check(
            rows,
            category="Bundle identity",
            check="Stored bundle identity",
            status="Malformed bundle",
            expected="Provider, 64-character checksum, and bundle ID",
            observed=f"{recorded_provider or 'Missing'} | {stored_id or 'Missing'}",
            details="Bundle identity fields are missing or malformed.",
        )
        recorded_checksum = ""
        recorded_id = ""
    elif manifest_issues:
        recorded_checksum = ""
        recorded_id = ""
        _add_check(
            rows,
            category="Bundle identity",
            check="Recorded manifest identity",
            status="Malformed bundle",
            expected="Canonical readable manifest",
            observed="Manifest is malformed",
            details="Bundle identity cannot be trusted with a malformed manifest.",
        )
    else:
        recorded_checksum, recorded_id = (
            calculate_provider_allowlist_evidence_bundle_identity(
                recorded_provider,
                manifest,
            )
        )
        status = (
            "Verified"
            if stored_checksum == recorded_checksum and stored_id == recorded_id
            else "Bundle ID mismatch"
        )
        _add_check(
            rows,
            category="Bundle identity",
            check="Recorded manifest identity",
            status=status,
            expected=f"{stored_checksum} | {stored_id}",
            observed=f"{recorded_checksum} | {recorded_id}",
            details=(
                "Stored checksum and ID match the canonical recorded manifest."
                if status == "Verified"
                else "Stored bundle checksum or ID does not match its manifest."
            ),
        )

    current_checksum = ""
    current_id = ""
    if manifest and len(current_manifest) == len(manifest) and recorded_provider:
        current_checksum, current_id = (
            calculate_provider_allowlist_evidence_bundle_identity(
                recorded_provider,
                current_manifest,
            )
        )
        status = (
            "Verified"
            if current_checksum == stored_checksum and current_id == stored_id
            else "Bundle ID mismatch"
        )
        _add_check(
            rows,
            category="Bundle identity",
            check="Current evidence identity",
            status=status,
            expected=f"{stored_checksum} | {stored_id}",
            observed=f"{current_checksum} | {current_id}",
            details=(
                "Current evidence recreates the stored bundle identity."
                if status == "Verified"
                else "Current evidence no longer recreates the stored bundle identity."
            ),
        )
    else:
        _add_check(
            rows,
            category="Bundle identity",
            check="Current evidence identity",
            status="Not applicable",
            expected=f"{stored_checksum} | {stored_id}",
            observed="Not calculated",
            details="Identity cannot be recalculated until every manifest path is readable.",
        )

    try:
        expected_count = int(bundle.get("evidence_file_count", -1))
    except (TypeError, ValueError):
        expected_count = -1
    count_status = "Verified" if expected_count == len(manifest) else "Malformed bundle"
    _add_check(
        rows,
        category="Bundle",
        check="Evidence file count",
        status=count_status,
        expected=expected_count,
        observed=len(manifest),
        details=(
            "Manifest count matches the recorded evidence file count."
            if count_status == "Verified"
            else "Recorded evidence file count does not match the manifest."
        ),
    )

    verdict = _verification_verdict(rows)
    summary = _build_summary(
        provider_key=provider.provider_key,
        provider_name=provider.provider_name,
        selected=selected,
        source=source,
        bundle=bundle,
        rows=rows,
        verdict=verdict,
        run_at=run_at,
        repository_root=root,
        calculated_recorded_checksum=recorded_checksum,
        calculated_recorded_id=recorded_id,
        current_checksum=current_checksum,
        current_id=current_id,
    )
    return pd.DataFrame(rows, columns=VERIFICATION_COLUMNS), summary


def _build_summary(
    *,
    provider_key: str,
    provider_name: str,
    selected: Path,
    source: str,
    bundle: Mapping[str, object],
    rows: list[dict[str, object]],
    verdict: str,
    run_at: datetime | None,
    repository_root: Path,
    calculated_recorded_checksum: str = "",
    calculated_recorded_id: str = "",
    current_checksum: str = "",
    current_id: str = "",
) -> dict[str, object]:
    if verdict not in VERIFICATION_VERDICTS:
        raise ValueError(f"Unexpected bundle verification verdict: {verdict}")
    generated_at = (run_at or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    statuses = Counter(_clean(row.get("status")) for row in rows)
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "provider_key": provider_key,
        "provider_name": provider_name,
        "bundle_path": _display_path(selected, repository_root),
        "bundle_source": source,
        "bundle_id": _clean(bundle.get("bundle_id")),
        "bundle_checksum_sha256": _clean(bundle.get("bundle_checksum_sha256")),
        "calculated_recorded_bundle_id": calculated_recorded_id,
        "calculated_recorded_bundle_checksum_sha256": calculated_recorded_checksum,
        "current_evidence_bundle_id": current_id,
        "current_evidence_bundle_checksum_sha256": current_checksum,
        "original_bundle_verdict": _clean(bundle.get("verdict")) or "Missing",
        "preview_verdict": _clean(bundle.get("preview_verdict")) or "Missing",
        "receipt_verification_verdict": (
            _clean(bundle.get("receipt_verification_verdict")) or "Missing"
        ),
        "conformance_verdict": (
            _clean(bundle.get("conformance_verdict")) or "Missing"
        ),
        "verdict": verdict,
        "status_counts": dict(sorted(statuses.items())),
        "blockers": _blockers(rows),
        "checks": rows,
        "safety": {
            "read_only_verification": True,
            "provider_policy_edited": False,
            "provider_allowlisted": False,
            "receipt_created": False,
            "provider_run": False,
            "staging_promoted": False,
            "cron_enabled": False,
            "protected_files_edited": False,
            "picks_generated": False,
            "bets_placed": False,
        },
    }


def render_provider_allowlist_evidence_bundle_verification(
    checks: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    blockers = summary.get("blockers", [])
    blocker_lines = (
        [f"- {item}" for item in blockers]
        if isinstance(blockers, list) and blockers
        else ["- None."]
    )
    lines = [
        "# Provider Allowlist Evidence Bundle Verification",
        "",
        "**Nothing was applied.** This checker only reads an archived evidence "
        "bundle and its bound files. It does not edit provider policy, allowlist "
        "providers, promote staging, run providers, generate picks, place bets, "
        "or enable cron.",
        "",
        "## Final verdict",
        "",
        f"- **{summary.get('verdict', 'Not ready for PR approval review')}**",
        f"- Provider: **{summary.get('provider_name', '')}** "
        f"(`{summary.get('provider_key', '')}`)",
        f"- Bundle: `{summary.get('bundle_path', '')}`",
        f"- Bundle source: {summary.get('bundle_source', '')}",
        f"- Stored bundle ID: `{summary.get('bundle_id', '') or 'Missing'}`",
        "- Stored bundle SHA-256: "
        f"`{summary.get('bundle_checksum_sha256', '') or 'Missing'}`",
        "- Current evidence bundle ID: "
        f"`{summary.get('current_evidence_bundle_id', '') or 'Not calculated'}`",
        "- Current evidence SHA-256: "
        f"`{summary.get('current_evidence_bundle_checksum_sha256', '') or 'Not calculated'}`",
        "",
        "## Blockers and mismatches",
        "",
        *blocker_lines,
        "",
        "## Evidence verification",
        "",
        checks.to_markdown(index=False),
        "",
        "## Decision boundary",
        "",
        "A verified bundle only confirms that the reviewed evidence still matches. "
        "Provider allowlisting remains a separate human-reviewed policy PR, and "
        "cron remains disabled until another independent decision enables it.",
    ]
    return "\n".join(lines)


def save_provider_allowlist_evidence_bundle_verification(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    bundle_path: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    checks, summary = build_provider_allowlist_evidence_bundle_verification(
        provider_name,
        outputs,
        bundle_path=bundle_path,
        repository_root=repository_root,
        run_at=run_at,
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
        render_provider_allowlist_evidence_bundle_verification(
            checks,
            summary,
        ).encode("utf-8"),
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
