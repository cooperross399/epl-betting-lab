from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import json
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import atomic_write_report, file_sha256
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    APPROVAL_DECISION,
    READY_VERDICT,
    RECEIPT_JSON_FILENAME,
    SUPPORTED_DECISIONS,
    ProviderHumanAcceptanceReceiptError,
    calculate_provider_human_acceptance_receipt_id,
    calculate_shadow_archive_bundle_checksum,
    verify_shadow_archive_integrity,
)
from epl_betting_lab.reports.provider_shadow_history import (
    load_provider_shadow_run_history,
)


VERIFICATION_JSON_FILENAME = (
    "provider_human_acceptance_receipt_verification.json"
)
VERIFICATION_MARKDOWN_FILENAME = (
    "provider_human_acceptance_receipt_verification.md"
)
VERIFICATION_CSV_FILENAME = "provider_human_acceptance_receipt_verification.csv"
VERIFICATION_STATUSES = (
    "Verified",
    "Missing evidence",
    "Checksum mismatch",
    "Malformed receipt",
    "Stale evidence",
    "Decision not approval",
    "Not ready",
)
VERDICTS = (
    "Verified for allowlist PR review",
    "Receipt not approval",
    "Evidence changed",
    "Missing evidence",
    "Malformed receipt",
    "Not ready for allowlist PR",
)
VERIFICATION_COLUMNS = (
    "category",
    "check",
    "status",
    "expected",
    "observed",
    "evidence_path",
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


def _display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _resolve_reference(value: object, output_dir: Path) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    raw = Path(text)
    if raw.is_absolute():
        return raw.resolve(strict=False)
    repository_candidate = (PROJECT_ROOT / raw).resolve(strict=False)
    output_candidate = (output_dir / raw).resolve(strict=False)
    if text.replace("\\", "/").startswith("data/"):
        return repository_candidate
    if repository_candidate.exists() or not output_candidate.exists():
        return repository_candidate
    return output_candidate


def _parse_created_at(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _add_check(
    rows: list[dict[str, object]],
    category: str,
    check: str,
    status: str,
    *,
    expected: object = "",
    observed: object = "",
    evidence_path: object = "",
    details: str = "",
) -> None:
    if status not in VERIFICATION_STATUSES:
        raise ValueError(f"Unexpected receipt verification status: {status}")
    rows.append(
        {
            "category": category,
            "check": check,
            "status": status,
            "expected": expected,
            "observed": observed,
            "evidence_path": evidence_path,
            "details": details,
        }
    )


def _load_receipt(path: Path) -> tuple[dict[str, object] | None, str, str]:
    if not path.exists():
        return None, "Missing evidence", "Receipt JSON does not exist."
    if not path.is_file() or path.is_symlink():
        return None, "Malformed receipt", (
            "Receipt path must be a regular, non-symlinked JSON file."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, "Malformed receipt", f"Receipt JSON could not be read: {exc}"
    if not isinstance(payload, dict):
        return None, "Malformed receipt", "Receipt JSON root must be an object."
    return payload, "Verified", "Receipt JSON is readable."


def _check_bound_file(
    rows: list[dict[str, object]],
    *,
    category: str,
    check: str,
    record: object,
    output_dir: Path,
    required: bool,
    parse_json: bool = False,
) -> tuple[Path | None, dict[str, object] | None]:
    if not isinstance(record, Mapping):
        _add_check(
            rows,
            category,
            check,
            "Malformed receipt",
            expected="Structured evidence record",
            observed=type(record).__name__,
            details="The receipt evidence record is missing or malformed.",
        )
        return None, None

    recorded_status = _clean(record.get("status"))
    recorded_path = _clean(record.get("path"))
    recorded_checksum = _clean(record.get("checksum_sha256"))
    if recorded_status != "Bound":
        if required:
            _add_check(
                rows,
                category,
                check,
                "Missing evidence",
                expected="Bound evidence",
                observed=recorded_status or "Missing status",
                evidence_path=recorded_path,
                details="Required evidence was not bound in the receipt.",
            )
        else:
            _add_check(
                rows,
                category,
                check,
                "Verified",
                expected="Bound when available",
                observed=recorded_status or "Not available",
                evidence_path=recorded_path,
                details="No checksum was bound for this optional evidence.",
            )
        return None, None
    if not recorded_path or not SHA256_PATTERN.fullmatch(recorded_checksum):
        _add_check(
            rows,
            category,
            check,
            "Malformed receipt",
            expected="Evidence path and 64-character SHA-256",
            observed=recorded_checksum or "Missing checksum",
            evidence_path=recorded_path,
            details="Bound evidence has an invalid path or checksum field.",
        )
        return None, None

    path = _resolve_reference(recorded_path, output_dir)
    if path is None or not path.exists() or not path.is_file() or path.is_symlink():
        _add_check(
            rows,
            category,
            check,
            "Missing evidence",
            expected=recorded_checksum,
            observed="File missing or unreadable",
            evidence_path=recorded_path,
            details="The exact file bound by the receipt is no longer readable.",
        )
        return path, None
    try:
        current_checksum = file_sha256(path)
    except OSError as exc:
        _add_check(
            rows,
            category,
            check,
            "Missing evidence",
            expected=recorded_checksum,
            observed="Unreadable",
            evidence_path=recorded_path,
            details=str(exc),
        )
        return path, None
    status = "Verified" if current_checksum == recorded_checksum else "Checksum mismatch"
    _add_check(
        rows,
        category,
        check,
        status,
        expected=recorded_checksum,
        observed=current_checksum,
        evidence_path=recorded_path,
        details=(
            "Current file checksum matches the human receipt."
            if status == "Verified"
            else "The file changed after the human receipt was created."
        ),
    )
    if not parse_json:
        return path, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _add_check(
            rows,
            category,
            f"{check} JSON structure",
            "Malformed receipt",
            expected="Readable JSON object",
            observed="Unreadable",
            evidence_path=recorded_path,
            details=str(exc),
        )
        return path, None
    if not isinstance(payload, dict):
        _add_check(
            rows,
            category,
            f"{check} JSON structure",
            "Malformed receipt",
            expected="JSON object",
            observed=type(payload).__name__,
            evidence_path=recorded_path,
            details="Evidence JSON root is not an object.",
        )
        return path, None
    return path, payload


def _check_archives(
    rows: list[dict[str, object]],
    archives: object,
    output_dir: Path,
) -> list[Path]:
    if not isinstance(archives, list) or not archives:
        _add_check(
            rows,
            "Evidence",
            "Reviewed shadow archives",
            "Missing evidence",
            expected="At least one reviewed archive",
            observed="Missing or empty",
            details="Approval evidence must include reviewed live shadow archives.",
        )
        return []

    resolved_archives: list[Path] = []
    archive_root = (output_dir / "archive" / "provider_shadow_runs").resolve()
    for index, item in enumerate(archives, start=1):
        label = f"Reviewed shadow archive {index}"
        if not isinstance(item, Mapping):
            _add_check(
                rows,
                "Evidence",
                label,
                "Malformed receipt",
                expected="Structured archive evidence",
                observed=type(item).__name__,
            )
            continue
        recorded_path = _clean(item.get("archive_path"))
        recorded_checksum = _clean(item.get("checksum_sha256"))
        path = _resolve_reference(recorded_path, output_dir)
        if not recorded_path or not SHA256_PATTERN.fullmatch(recorded_checksum):
            _add_check(
                rows,
                "Evidence",
                f"{label} bundle checksum",
                "Malformed receipt",
                expected="Archive path and 64-character SHA-256",
                observed=recorded_checksum or "Missing checksum",
                evidence_path=recorded_path,
            )
            continue
        try:
            if path is None:
                raise ValueError("missing path")
            path.resolve(strict=False).relative_to(archive_root)
        except ValueError:
            _add_check(
                rows,
                "Evidence",
                f"{label} path",
                "Malformed receipt",
                expected=_display_path(archive_root),
                observed=recorded_path,
                details="Reviewed archive path is outside the provider archive root.",
            )
            continue
        if path is None or not path.exists() or not path.is_dir() or path.is_symlink():
            _add_check(
                rows,
                "Evidence",
                f"{label} bundle checksum",
                "Missing evidence",
                expected=recorded_checksum,
                observed="Archive missing or unreadable",
                evidence_path=recorded_path,
            )
            continue
        resolved_archives.append(path)
        try:
            current_checksum, current_file_count = (
                calculate_shadow_archive_bundle_checksum(path)
            )
        except (OSError, ProviderHumanAcceptanceReceiptError) as exc:
            _add_check(
                rows,
                "Evidence",
                f"{label} bundle checksum",
                "Missing evidence",
                expected=recorded_checksum,
                observed="Unreadable",
                evidence_path=recorded_path,
                details=str(exc),
            )
            continue
        bundle_status = (
            "Verified" if current_checksum == recorded_checksum else "Checksum mismatch"
        )
        _add_check(
            rows,
            "Evidence",
            f"{label} bundle checksum",
            bundle_status,
            expected=recorded_checksum,
            observed=current_checksum,
            evidence_path=recorded_path,
            details=f"Current archive contains {current_file_count} file(s).",
        )

        metadata_path = _resolve_reference(item.get("metadata_path"), output_dir)
        metadata_expected = _clean(item.get("metadata_checksum_sha256"))
        if not SHA256_PATTERN.fullmatch(metadata_expected):
            _add_check(
                rows,
                "Evidence",
                f"{label} metadata checksum",
                "Malformed receipt",
                expected="64-character SHA-256",
                observed=metadata_expected or "Missing checksum",
                evidence_path=_clean(item.get("metadata_path")),
            )
        elif (
            metadata_path is None
            or not metadata_path.is_file()
            or metadata_path.is_symlink()
        ):
            _add_check(
                rows,
                "Evidence",
                f"{label} metadata checksum",
                "Missing evidence",
                expected=metadata_expected,
                observed="Metadata missing or unreadable",
                evidence_path=_clean(item.get("metadata_path")),
            )
        else:
            try:
                metadata_current = file_sha256(metadata_path)
            except OSError as exc:
                _add_check(
                    rows,
                    "Evidence",
                    f"{label} metadata checksum",
                    "Missing evidence",
                    expected=metadata_expected,
                    observed="Unreadable",
                    evidence_path=_clean(item.get("metadata_path")),
                    details=str(exc),
                )
                continue
            _add_check(
                rows,
                "Evidence",
                f"{label} metadata checksum",
                (
                    "Verified"
                    if metadata_current == metadata_expected
                    else "Checksum mismatch"
                ),
                expected=metadata_expected,
                observed=metadata_current,
                evidence_path=_clean(item.get("metadata_path")),
            )

        integrity_status, integrity_note = verify_shadow_archive_integrity(path)
        receipt_integrity = _clean(item.get("current_integrity_status"))
        integrity_verified = (
            integrity_status == "Verified" and receipt_integrity == "Verified"
        )
        _add_check(
            rows,
            "Evidence",
            f"{label} archive integrity",
            "Verified" if integrity_verified else "Stale evidence",
            expected=receipt_integrity or "Verified",
            observed=integrity_status,
            evidence_path=recorded_path,
            details=integrity_note,
        )
    return resolved_archives


def _output_relative_archive_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve().relative_to(output_dir.resolve()).as_posix()
    except ValueError:
        return _display_path(path)


def _check_latest_archive_set(
    rows: list[dict[str, object]],
    record: object,
    archives: list[Path],
    *,
    provider_name: str,
    output_dir: Path,
) -> None:
    if not isinstance(record, Mapping):
        _add_check(
            rows,
            "Evidence",
            "Latest live archive set",
            "Malformed receipt",
            expected="Structured latest archive evidence",
            observed=type(record).__name__,
        )
        return
    expected_latest = record.get("latest_live_archive_paths", [])
    expected_reviewed = record.get("reviewed_archive_paths", [])
    try:
        review_window = max(1, int(record.get("review_window", 0)))
    except (TypeError, ValueError):
        _add_check(
            rows,
            "Evidence",
            "Latest live archive set",
            "Malformed receipt",
            expected="Positive review_window",
            observed=record.get("review_window", "Missing"),
        )
        return
    if not isinstance(expected_latest, list) or not isinstance(expected_reviewed, list):
        _add_check(
            rows,
            "Evidence",
            "Latest live archive set",
            "Malformed receipt",
            expected="Lists of archive paths",
            observed="Malformed path lists",
        )
        return

    history = load_provider_shadow_run_history(
        output_dir,
        provider_name=provider_name,
    )
    current_live = [
        record
        for record in history
        if _clean(record.get("mode")) == "Live shadow run"
    ][:review_window]
    current_latest = {
        _clean(item.get("archive_path"))
        for item in current_live
        if _clean(item.get("archive_path"))
    }
    recorded_latest = {_clean(item) for item in expected_latest if _clean(item)}
    recorded_reviewed = {_clean(item) for item in expected_reviewed if _clean(item)}
    bound_archives = {
        _output_relative_archive_path(path, output_dir) for path in archives
    }
    status = (
        "Verified"
        if current_latest == recorded_latest == recorded_reviewed == bound_archives
        and len(current_live) == len(recorded_latest)
        else "Stale evidence"
    )
    _add_check(
        rows,
        "Evidence",
        "Latest live archive set",
        status,
        expected=json.dumps(sorted(recorded_latest)),
        observed=json.dumps(sorted(current_latest)),
        evidence_path=_clean(record.get("path")),
        details=(
            "The same latest live archives remain current and bound."
            if status == "Verified"
            else "Live shadow archive history changed after receipt creation."
        ),
    )


def _verdict_for_statuses(statuses: set[str]) -> str:
    if "Malformed receipt" in statuses:
        return "Malformed receipt"
    if "Missing evidence" in statuses:
        return "Missing evidence"
    if statuses.intersection({"Checksum mismatch", "Stale evidence"}):
        return "Evidence changed"
    if "Decision not approval" in statuses:
        return "Receipt not approval"
    if "Not ready" in statuses:
        return "Not ready for allowlist PR"
    return "Verified for allowlist PR review"


def _next_step(verdict: str) -> str:
    return {
        "Verified for allowlist PR review": (
            "A separate human-reviewed provider allowlist PR may now be considered. "
            "This verifier does not edit policy or enable cron."
        ),
        "Receipt not approval": (
            "No allowlist PR should be considered from this receipt because the human "
            "decision was not approval."
        ),
        "Evidence changed": (
            "Stop and regenerate the checklist and human receipt after reviewing the "
            "changed evidence."
        ),
        "Missing evidence": (
            "Restore or regenerate the missing evidence, then create and verify a new "
            "human receipt."
        ),
        "Malformed receipt": (
            "Do not use this receipt. Inspect or recreate it from the Terminal preview "
            "workflow."
        ),
        "Not ready for allowlist PR": (
            "Complete the checklist requirements and create a new approved receipt "
            "without a not-ready override."
        ),
    }[verdict]


def build_provider_human_acceptance_receipt_verification(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    receipt_path: Path | None = None,
    run_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    selected_receipt = receipt_path or outputs / RECEIPT_JSON_FILENAME
    if not selected_receipt.is_absolute():
        selected_receipt = (PROJECT_ROOT / selected_receipt).resolve(strict=False)
    else:
        selected_receipt = selected_receipt.resolve(strict=False)
    rows: list[dict[str, object]] = []
    receipt, receipt_status, receipt_note = _load_receipt(selected_receipt)
    receipt_checksum = ""
    if selected_receipt.is_file() and not selected_receipt.is_symlink():
        try:
            receipt_checksum = file_sha256(selected_receipt)
        except OSError:
            receipt_checksum = ""
    _add_check(
        rows,
        "Receipt",
        "Receipt JSON",
        receipt_status,
        expected="Readable receipt JSON object",
        observed=receipt_checksum or receipt_note,
        evidence_path=_display_path(selected_receipt),
        details=receipt_note,
    )

    if receipt is not None:
        receipt_provider_key = _clean(receipt.get("provider_key"))
        receipt_provider_name = _clean(receipt.get("provider_name"))
        provider_matches = _slug(provider_name) in {
            _slug(receipt_provider_key),
            _slug(receipt_provider_name),
        }
        _add_check(
            rows,
            "Receipt fields",
            "Provider",
            "Verified" if provider_matches else "Malformed receipt",
            expected=provider_name,
            observed=receipt_provider_key or receipt_provider_name,
            details="The requested provider must match the receipt provider.",
        )
        reviewer = _clean(receipt.get("reviewer_name"))
        _add_check(
            rows,
            "Receipt fields",
            "Reviewer",
            "Verified" if reviewer else "Malformed receipt",
            expected="Non-empty reviewer name",
            observed=reviewer or "Missing",
        )
        created_at = _parse_created_at(receipt.get("created_at"))
        _add_check(
            rows,
            "Receipt fields",
            "Created at",
            "Verified" if created_at else "Malformed receipt",
            expected="Timezone-aware ISO timestamp",
            observed=_clean(receipt.get("created_at")) or "Missing",
        )
        decision = _clean(receipt.get("decision"))
        decision_known = decision in SUPPORTED_DECISIONS
        decision_status = (
            "Malformed receipt"
            if not decision_known
            else "Verified"
            if decision == APPROVAL_DECISION
            else "Decision not approval"
        )
        _add_check(
            rows,
            "Receipt fields",
            "Decision",
            decision_status,
            expected=APPROVAL_DECISION,
            observed=decision or "Missing",
        )

        evidence = receipt.get("evidence", {})
        if not isinstance(evidence, Mapping):
            _add_check(
                rows,
                "Receipt",
                "Evidence structure",
                "Malformed receipt",
                expected="Evidence object",
                observed=type(evidence).__name__,
            )
            evidence = {}
        _, checklist_payload = _check_bound_file(
            rows,
            category="Evidence",
            check="Provider acceptance checklist checksum",
            record=evidence.get("checklist"),
            output_dir=outputs,
            required=True,
            parse_json=True,
        )
        checklist_verdict = _clean(receipt.get("checklist_verdict"))
        current_checklist_verdict = _clean(
            checklist_payload.get("verdict") if checklist_payload else ""
        )
        if checklist_payload and checklist_verdict != current_checklist_verdict:
            checklist_status = "Malformed receipt"
        elif checklist_verdict == READY_VERDICT:
            checklist_status = "Verified"
        else:
            checklist_status = "Not ready"
        _add_check(
            rows,
            "Receipt fields",
            "Checklist verdict",
            checklist_status,
            expected=READY_VERDICT,
            observed=checklist_verdict or "Missing",
            details=(
                "Receipt and current checklist verdicts must agree."
                if checklist_payload
                else "Current checklist could not be read for comparison."
            ),
        )
        if checklist_payload:
            checklist_provider_matches = _slug(provider_name) in {
                _slug(checklist_payload.get("provider_key")),
                _slug(checklist_payload.get("provider_name")),
            }
            _add_check(
                rows,
                "Evidence",
                "Checklist provider",
                "Verified" if checklist_provider_matches else "Malformed receipt",
                expected=provider_name,
                observed=(
                    checklist_payload.get("provider_key")
                    or checklist_payload.get("provider_name")
                    or "Missing"
                ),
            )

        archives = _check_archives(
            rows,
            evidence.get("reviewed_shadow_archives"),
            outputs,
        )
        _check_latest_archive_set(
            rows,
            evidence.get("shadow_archive_set"),
            archives,
            provider_name=provider_name,
            output_dir=outputs,
        )
        _, comparison_payload = _check_bound_file(
            rows,
            category="Evidence",
            check="Matching shadow comparison checksum",
            record=evidence.get("comparison"),
            output_dir=outputs,
            required=False,
            parse_json=True,
        )
        if comparison_payload:
            comparison_matches = _slug(provider_name) in {
                _slug(comparison_payload.get("provider_key")),
                _slug(comparison_payload.get("provider_name")),
            }
            _add_check(
                rows,
                "Evidence",
                "Shadow comparison provider",
                "Verified" if comparison_matches else "Malformed receipt",
                expected=provider_name,
                observed=(
                    comparison_payload.get("provider_key")
                    or comparison_payload.get("provider_name")
                    or "Missing"
                ),
            )
        _check_bound_file(
            rows,
            category="Evidence",
            check="Provider policy checksum",
            record=evidence.get("provider_policy"),
            output_dir=outputs,
            required=False,
        )

        approval_gate = receipt.get("approval_gate", {})
        if not isinstance(approval_gate, Mapping):
            gate_status = "Malformed receipt"
            gate_observed = type(approval_gate).__name__
        else:
            gate_observed = _clean(approval_gate.get("status"))
            override_used = approval_gate.get("override_used") is True
            if decision != APPROVAL_DECISION:
                gate_status = "Decision not approval"
            elif gate_observed == "Passed" and not override_used:
                gate_status = "Verified"
            elif gate_observed == "Override used" or override_used:
                gate_status = "Not ready"
            else:
                gate_status = "Malformed receipt"
        _add_check(
            rows,
            "Receipt fields",
            "Approval gate",
            gate_status,
            expected="Passed without override",
            observed=gate_observed or "Missing",
        )

        receipt_id = _clean(receipt.get("receipt_id"))
        expected_receipt_id = ""
        if created_at and isinstance(evidence, Mapping):
            archive_records = evidence.get("reviewed_shadow_archives", [])
            archive_checksums = (
                [
                    item.get("checksum_sha256")
                    for item in archive_records
                    if isinstance(item, Mapping)
                ]
                if isinstance(archive_records, list)
                else []
            )
            comparison_record = evidence.get("comparison", {})
            policy_record = evidence.get("provider_policy", {})
            checklist_record = evidence.get("checklist", {})
            identity_payload = {
                "provider_key": receipt_provider_key,
                "reviewer_name": reviewer,
                "decision": decision,
                "notes": _clean(receipt.get("notes")),
                "created_at": _clean(receipt.get("created_at")),
                "checklist_checksum_sha256": (
                    checklist_record.get("checksum_sha256")
                    if isinstance(checklist_record, Mapping)
                    else ""
                ),
                "archive_checksums": archive_checksums,
                "comparison_checksum_sha256": (
                    comparison_record.get("checksum_sha256")
                    if isinstance(comparison_record, Mapping)
                    else ""
                ),
                "policy_checksum_sha256": (
                    policy_record.get("checksum_sha256")
                    if isinstance(policy_record, Mapping)
                    else ""
                ),
            }
            expected_receipt_id = calculate_provider_human_acceptance_receipt_id(
                identity_payload,
                created_at,
            )
        _add_check(
            rows,
            "Receipt fields",
            "Receipt ID",
            (
                "Verified"
                if receipt_id and receipt_id == expected_receipt_id
                else "Malformed receipt"
            ),
            expected=expected_receipt_id or "Recomputable receipt ID",
            observed=receipt_id or "Missing",
            details="Receipt ID binds human fields and recorded evidence checksums.",
        )

    checks = pd.DataFrame(rows, columns=VERIFICATION_COLUMNS)
    statuses = set(checks["status"].astype(str))
    verdict = _verdict_for_statuses(statuses)
    if verdict not in VERDICTS:
        raise ValueError(f"Unexpected receipt verification verdict: {verdict}")
    generated_at = (run_at or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    summary: dict[str, object] = {
        "generated_at": generated_at,
        "provider_key": _clean(receipt.get("provider_key")) if receipt else provider_name,
        "provider_name": _clean(receipt.get("provider_name")) if receipt else provider_name,
        "receipt_path": _display_path(selected_receipt),
        "receipt_checksum_sha256": receipt_checksum,
        "receipt_id": _clean(receipt.get("receipt_id")) if receipt else "",
        "reviewer_name": _clean(receipt.get("reviewer_name")) if receipt else "",
        "decision": _clean(receipt.get("decision")) if receipt else "",
        "receipt_created_at": _clean(receipt.get("created_at")) if receipt else "",
        "checklist_verdict": (
            _clean(receipt.get("checklist_verdict")) if receipt else ""
        ),
        "verdict": verdict,
        "next_step": _next_step(verdict),
        "status_counts": {
            status: int((checks["status"] == status).sum())
            for status in VERIFICATION_STATUSES
        },
        "checks": checks.to_dict(orient="records"),
        "safety": {
            "read_only_evidence_check": True,
            "provider_policy_edited": False,
            "provider_allowlisted": False,
            "staging_promoted": False,
            "cron_enabled": False,
            "live_provider_run": False,
            "manual_or_production_files_edited": False,
            "bets_placed": False,
        },
    }
    return checks, summary


def render_provider_human_acceptance_receipt_verification(
    checks: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    lines = [
        "# Provider Human Acceptance Receipt Verification",
        "",
        "This report recalculates receipt-bound evidence without editing policy, "
        "allowlisting a provider, promoting staging, enabling cron, running a live "
        "provider, generating picks, or placing bets.",
        "",
        "## Verdict",
        "",
        f"- **{summary.get('verdict', 'Malformed receipt')}**",
        (
            f"- Provider: **{summary.get('provider_name', '')}** "
            f"(`{summary.get('provider_key', '')}`)"
        ),
        f"- Reviewer: **{summary.get('reviewer_name', '') or 'Not available'}**",
        f"- Decision: **{summary.get('decision', '') or 'Not available'}**",
        f"- Receipt ID: `{summary.get('receipt_id', '') or 'Not available'}`",
        f"- Receipt: `{summary.get('receipt_path', '')}`",
        f"- Next step: {summary.get('next_step', '')}",
        "",
        "## Verification checks",
        "",
        checks.to_markdown(index=False),
        "",
        "## Status meanings",
        "",
        "- **Verified:** the field or current checksum matches the receipt.",
        "- **Missing evidence:** a required receipt or evidence file is unavailable.",
        "- **Checksum mismatch:** file bytes changed after the receipt was created.",
        "- **Malformed receipt:** required receipt structure or fields are invalid.",
        "- **Stale evidence:** current live archive history differs from the receipt.",
        "- **Decision not approval:** the human decision does not support an allowlist PR.",
        "- **Not ready:** the checklist or approval gate is not ready without override.",
        "",
        "## Decision boundary",
        "",
        "Even `Verified for allowlist PR review` only permits a separate human-reviewed "
        "policy PR to be considered. This report does not make that policy change. "
        "Cron remains disabled and requires a later, separate decision.",
    ]
    return "\n".join(lines)


def save_provider_human_acceptance_receipt_verification(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    receipt_path: Path | None = None,
    run_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    checks, summary = build_provider_human_acceptance_receipt_verification(
        provider_name,
        outputs,
        receipt_path=receipt_path,
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
        render_provider_human_acceptance_receipt_verification(
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
        "next_step": summary["next_step"],
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
    }
