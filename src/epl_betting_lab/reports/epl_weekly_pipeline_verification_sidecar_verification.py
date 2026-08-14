from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Mapping

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import atomic_write_report, file_sha256
from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    PIPELINE_ARCHIVE_ROOT,
)
from epl_betting_lab.reports.epl_weekly_pipeline_receipt_verification import (
    VERIFICATION_CSV_FILENAME,
    VERIFICATION_JSON_FILENAME,
    VERIFICATION_MARKDOWN_FILENAME,
    build_epl_weekly_pipeline_receipt_verification,
)
from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar import (
    EVIDENCE_COLUMNS,
    SIDECAR_ARCHIVED_VERDICT,
    SIDECAR_ARCHIVE_ROOT,
    SIDECAR_CSV_FILENAME,
    SIDECAR_FAILED_VERDICT,
    SIDECAR_JSON_FILENAME,
    SIDECAR_MARKDOWN_FILENAME,
    SIDECAR_MISSING_VERDICT,
    SIDECAR_NOT_READY_VERDICT,
    VERIFICATION_NOT_READY_VERDICT,
    VERIFICATION_VERIFIED_VERDICT,
    calculate_epl_weekly_pipeline_verification_sidecar_identity,
    render_epl_weekly_pipeline_verification_sidecar,
    render_epl_weekly_pipeline_verification_sidecar_csv,
)


SIDECAR_VERIFICATION_JSON_FILENAME = (
    "epl_weekly_pipeline_verification_sidecar_verification.json"
)
SIDECAR_VERIFICATION_MARKDOWN_FILENAME = (
    "epl_weekly_pipeline_verification_sidecar_verification.md"
)
SIDECAR_VERIFICATION_CSV_FILENAME = (
    "epl_weekly_pipeline_verification_sidecar_verification.csv"
)

VERIFICATION_STATUSES = (
    "Verified",
    "Missing sidecar",
    "Missing file",
    "Checksum mismatch",
    "Sidecar receipt ID mismatch",
    "Missing referenced archive",
    "Referenced archive changed",
    "Malformed sidecar",
    "Not applicable",
)

FINAL_VERDICTS = (
    "Weekly verification sidecar verified",
    "Weekly verification sidecar changed",
    "Missing weekly verification sidecar",
    "Malformed weekly verification sidecar",
    "Referenced pipeline archive changed",
    "Weekly verification sidecar not ready",
)

REQUIRED_SIDECAR_FIELDS = (
    "schema_version",
    "verdict",
    "status",
    "pipeline_receipt_id",
    "pipeline_archive_path",
    "verification_verdict",
    "verification_status",
    "original_receipt_id",
    "recalculated_receipt_id",
    "mismatch_count",
    "sidecar_receipt_id",
    "sidecar_receipt_checksum_sha256",
    "sidecar_archive_path",
    "evidence",
)

EXPECTED_EVIDENCE = {
    "verification_json": VERIFICATION_JSON_FILENAME,
    "verification_markdown": VERIFICATION_MARKDOWN_FILENAME,
    "verification_csv": VERIFICATION_CSV_FILENAME,
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


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _add_check(
    checks: list[dict[str, object]],
    *,
    category: str,
    item: str,
    status: str,
    expected: object,
    actual: object,
    note: str,
) -> None:
    if status not in VERIFICATION_STATUSES:
        raise ValueError(f"Unexpected sidecar verification status: {status}")
    checks.append(
        {
            "category": category,
            "item": item,
            "status": status,
            "expected": _json_safe(expected),
            "actual": _json_safe(actual),
            "note": note,
        }
    )


def _read_json(path: Path) -> tuple[dict[str, object] | None, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "File is missing."
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"JSON could not be read: {exc}"
    if not isinstance(value, dict):
        return None, "JSON root must be an object."
    return value, ""


def _latest_sidecar_dir(output_dir: Path) -> Path | None:
    root = output_dir / SIDECAR_ARCHIVE_ROOT
    if not root.exists():
        return None
    candidates = sorted(
        path.parent
        for path in root.glob(f"*/*/{SIDECAR_JSON_FILENAME}")
        if path.is_file() and not path.is_symlink()
    )
    return candidates[-1] if candidates else None


def _resolve_sidecar_dir(
    sidecar_path: Path | None,
    output_dir: Path,
) -> tuple[Path | None, str, bool]:
    root = (output_dir / SIDECAR_ARCHIVE_ROOT).resolve(strict=False)
    if sidecar_path is None:
        latest = _latest_sidecar_dir(output_dir)
        if latest is None:
            return None, "No archived weekly verification sidecars were found.", False
        return latest.resolve(), "Latest archived verification sidecar selected.", True

    candidate = sidecar_path
    if not candidate.is_absolute():
        project_candidate = PROJECT_ROOT / candidate
        output_candidate = output_dir / candidate
        candidate = project_candidate if project_candidate.exists() else output_candidate
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        return None, f"Sidecar path could not be resolved: {exc}", False
    if resolved.name == SIDECAR_JSON_FILENAME:
        resolved = resolved.parent
    try:
        resolved.relative_to(root)
    except ValueError:
        return (
            resolved,
            "Sidecar path must stay inside the weekly verification sidecar archive root.",
            False,
        )
    return resolved, "Provided archived verification sidecar selected.", True


def _display_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(
            output_dir.resolve(strict=False)
        ).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _safe_member(archive_dir: Path, value: object) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    try:
        resolved = (archive_dir / text).resolve(strict=False)
        resolved.relative_to(archive_dir.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _safe_pipeline_archive(output_dir: Path, value: object) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to((output_dir / PIPELINE_ARCHIVE_ROOT).resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _safety_summary() -> dict[str, bool]:
    return {
        "sealed_pipeline_archive_modified": False,
        "sidecar_archive_modified": False,
        "protected_files_edited": False,
        "odds_imported": False,
        "settlement_applied": False,
        "staging_promoted": False,
        "live_provider_run": False,
        "provider_allowlisted": False,
        "cron_enabled": False,
        "odds_fabricated": False,
        "bets_placed": False,
    }


def _missing_summary(
    sidecar_path: Path | None,
    note: str,
    generated_at: datetime,
    *,
    status: str = "Missing sidecar",
    verdict: str = "Missing weekly verification sidecar",
) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    _add_check(
        checks,
        category="Sidecar archive",
        item="sidecar_archive_path",
        status=status,
        expected="Readable archived weekly verification sidecar",
        actual=str(sidecar_path or ""),
        note=note,
    )
    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "verdict": verdict,
        "sidecar_archive_path": str(sidecar_path or ""),
        "original_sidecar_receipt_id": "",
        "recalculated_sidecar_receipt_id": "",
        "original_sidecar_checksum_sha256": "",
        "recalculated_sidecar_checksum_sha256": "",
        "referenced_pipeline_archive_path": "",
        "referenced_pipeline_receipt_id": "",
        "verification_verdict": "",
        "verification_status": "",
        "original_pipeline_receipt_id": "",
        "recalculated_pipeline_receipt_id": "",
        "reported_verification_mismatch_count": 0,
        "mismatch_count": 1,
        "blockers": [note],
        "checks": checks,
        "safety": _safety_summary(),
    }


def _verify_sidecar_views(
    archive_dir: Path,
    sidecar: Mapping[str, object],
    evidence: pd.DataFrame,
    checks: list[dict[str, object]],
) -> tuple[bool, bool]:
    changed = False
    try:
        expected_payloads = {
            SIDECAR_MARKDOWN_FILENAME: (
                render_epl_weekly_pipeline_verification_sidecar(
                    sidecar, evidence
                ).encode("utf-8")
            ),
            SIDECAR_CSV_FILENAME: (
                render_epl_weekly_pipeline_verification_sidecar_csv(
                    sidecar, evidence
                )
            ),
        }
    except Exception as exc:
        _add_check(
            checks,
            category="Sidecar file",
            item="rendered_report_views",
            status="Malformed sidecar",
            expected="Metadata that can reproduce sidecar Markdown and CSV",
            actual="Malformed metadata",
            note=f"Sidecar report views could not be reconstructed safely: {exc}",
        )
        return True, True
    for filename, expected_content in expected_payloads.items():
        path = archive_dir / filename
        if not path.is_file() or path.is_symlink():
            _add_check(
                checks,
                category="Sidecar file",
                item=filename,
                status="Missing file",
                expected="Readable regular file",
                actual="Missing or unsafe",
                note="A required sidecar report view is missing or unsafe.",
            )
            changed = True
            continue
        try:
            actual_content = path.read_bytes()
        except OSError as exc:
            _add_check(
                checks,
                category="Sidecar file",
                item=filename,
                status="Missing file",
                expected=sha256(expected_content).hexdigest(),
                actual="Unreadable",
                note=f"The sidecar report view could not be read: {exc}",
            )
            changed = True
            continue
        matches = actual_content == expected_content
        _add_check(
            checks,
            category="Sidecar file",
            item=filename,
            status="Verified" if matches else "Checksum mismatch",
            expected=sha256(expected_content).hexdigest(),
            actual=sha256(actual_content).hexdigest(),
            note=(
                "The sidecar report view matches its JSON metadata."
                if matches
                else "The sidecar report view no longer matches its JSON metadata."
            ),
        )
        changed = changed or not matches
    return changed, False


def _evidence_records_by_type(
    value: object,
) -> tuple[dict[str, Mapping[str, object]], bool]:
    if not isinstance(value, list):
        return {}, True
    records: dict[str, Mapping[str, object]] = {}
    malformed = False
    for item in value:
        if not isinstance(item, Mapping):
            malformed = True
            continue
        evidence_type = _clean(item.get("evidence_type"))
        if not evidence_type or evidence_type in records:
            malformed = True
            continue
        records[evidence_type] = item
    return records, malformed


def _verify_evidence(
    archive_dir: Path,
    sidecar: Mapping[str, object],
    output_dir: Path,
    checks: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, bytes], bool, bool, bool]:
    records, malformed = _evidence_records_by_type(sidecar.get("evidence"))
    current_records: list[dict[str, object]] = []
    contents: dict[str, bytes] = {}
    changed = False
    expected_missing = False

    for evidence_type, filename in EXPECTED_EVIDENCE.items():
        record = records.get(evidence_type)
        if record is None:
            _add_check(
                checks,
                category="Evidence metadata",
                item=evidence_type,
                status="Malformed sidecar",
                expected="One unique evidence record",
                actual="Missing",
                note="The sidecar metadata is missing a required evidence record.",
            )
            malformed = True
            current_records.append(
                {
                    "evidence_type": evidence_type,
                    "archive_member_path": filename,
                    "checksum_sha256": "",
                    "size_bytes": 0,
                    "status": "Missing",
                }
            )
            continue

        recorded_status = _clean(record.get("status"))
        recorded_member = _clean(record.get("archive_member_path"))
        if recorded_status not in {"Archived", "Missing", "Unreadable"}:
            _add_check(
                checks,
                category="Evidence metadata",
                item=f"{evidence_type}.status",
                status="Malformed sidecar",
                expected=["Archived", "Missing", "Unreadable"],
                actual=recorded_status or "Missing",
                note="The evidence status is not recognized.",
            )
            malformed = True
        raw_size = record.get("size_bytes", 0)
        try:
            int(raw_size or 0)
        except (TypeError, ValueError):
            _add_check(
                checks,
                category="Evidence metadata",
                item=f"{evidence_type}.size_bytes",
                status="Malformed sidecar",
                expected="Integer",
                actual=raw_size,
                note="The recorded evidence size is not numeric.",
            )
            malformed = True

        member = _safe_member(archive_dir, recorded_member or filename)
        if recorded_member and recorded_member != filename:
            _add_check(
                checks,
                category="Evidence metadata",
                item=f"{evidence_type}.archive_member_path",
                status="Malformed sidecar",
                expected=filename,
                actual=recorded_member,
                note="The evidence member name is not the expected verifier report name.",
            )
            malformed = True

        content: bytes | None = None
        if member is not None and member.is_file() and not member.is_symlink():
            try:
                content = member.read_bytes()
            except OSError:
                content = None

        if content is None:
            aligned_missing = recorded_status in {"Missing", "Unreadable"}
            _add_check(
                checks,
                category="Archived verification evidence",
                item=filename,
                status="Missing file",
                expected=(
                    "Absent as recorded by the non-ready sidecar"
                    if aligned_missing
                    else "Checksum-bound archived verifier report"
                ),
                actual="Missing or unreadable",
                note=(
                    "The missing report matches the sidecar's original non-ready state."
                    if aligned_missing
                    else "A report recorded as archived is now missing or unreadable."
                ),
            )
            expected_missing = expected_missing or aligned_missing
            changed = changed or not aligned_missing
            current_checksum = ""
            current_size = 0
        else:
            current_checksum = sha256(content).hexdigest()
            current_size = len(content)
            contents[evidence_type] = content
            checksum_matches = (
                recorded_status == "Archived"
                and current_checksum
                == _clean(record.get("checksum_sha256")).casefold()
                and current_size == _to_int(record.get("size_bytes", 0))
            )
            _add_check(
                checks,
                category="Archived verification evidence",
                item=filename,
                status="Verified" if checksum_matches else "Checksum mismatch",
                expected={
                    "checksum_sha256": _clean(record.get("checksum_sha256")),
                    "size_bytes": _to_int(record.get("size_bytes", 0)),
                    "status": "Archived",
                },
                actual={
                    "checksum_sha256": current_checksum,
                    "size_bytes": current_size,
                    "status": recorded_status,
                },
                note=(
                    "The archived verifier report matches the sidecar metadata."
                    if checksum_matches
                    else "The archived verifier report or its metadata changed."
                ),
            )
            changed = changed or not checksum_matches

        archived_path = _clean(record.get("archived_path"))
        if recorded_status == "Archived" and member is not None:
            expected_path = _display_path(member, output_dir)
            path_matches = archived_path == expected_path
            _add_check(
                checks,
                category="Evidence metadata",
                item=f"{evidence_type}.archived_path",
                status="Verified" if path_matches else "Checksum mismatch",
                expected=expected_path,
                actual=archived_path or "Missing",
                note=(
                    "The archived evidence path points to this sidecar folder."
                    if path_matches
                    else "The archived evidence path does not identify this sidecar copy."
                ),
            )
            changed = changed or not path_matches

        current_records.append(
            {
                "evidence_type": evidence_type,
                "archive_member_path": recorded_member,
                "checksum_sha256": current_checksum,
                "size_bytes": current_size,
                "status": recorded_status,
            }
        )

    extra_records = sorted(set(records) - set(EXPECTED_EVIDENCE))
    if extra_records:
        _add_check(
            checks,
            category="Evidence metadata",
            item="unexpected_evidence_records",
            status="Malformed sidecar",
            expected=sorted(EXPECTED_EVIDENCE),
            actual=extra_records,
            note="Unexpected evidence records were added to the sidecar metadata.",
        )
        malformed = True
    return current_records, contents, changed, malformed, expected_missing


def _verification_status_for_verdict(verdict: str) -> str:
    if verdict == VERIFICATION_VERIFIED_VERDICT:
        return "Verified"
    if verdict == VERIFICATION_NOT_READY_VERDICT:
        return "Not ready"
    return "Failed"


def _verify_verification_metadata(
    sidecar: Mapping[str, object],
    contents: Mapping[str, bytes],
    referenced_archive: Path | None,
    checks: list[dict[str, object]],
) -> tuple[bool, bool]:
    content = contents.get("verification_json")
    if content is None:
        return False, False
    try:
        verification = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        archived_ready = _clean(sidecar.get("verdict")) == SIDECAR_ARCHIVED_VERDICT
        _add_check(
            checks,
            category="Automatic verification",
            item=VERIFICATION_JSON_FILENAME,
            status="Malformed sidecar" if archived_ready else "Not applicable",
            expected="Readable verification JSON object",
            actual="Malformed",
            note=(
                "An archived-ready sidecar cannot contain malformed verification JSON."
                if archived_ready
                else "The original failed sidecar already recorded malformed verifier output."
            ),
        )
        return archived_ready, archived_ready
    if not isinstance(verification, Mapping):
        _add_check(
            checks,
            category="Automatic verification",
            item=VERIFICATION_JSON_FILENAME,
            status="Malformed sidecar",
            expected="JSON object",
            actual=type(verification).__name__,
            note="The archived verification JSON root is not an object.",
        )
        return True, True

    comparisons = (
        (
            "verification_verdict",
            _clean(verification.get("verdict")),
            _clean(sidecar.get("verification_verdict")),
        ),
        (
            "original_pipeline_receipt_id",
            _clean(verification.get("original_receipt_id")),
            _clean(sidecar.get("original_receipt_id")),
        ),
        (
            "recalculated_pipeline_receipt_id",
            _clean(verification.get("recalculated_receipt_id")),
            _clean(sidecar.get("recalculated_receipt_id")),
        ),
        (
            "verification_mismatch_count",
            _to_int(verification.get("mismatch_count", 0)),
            _to_int(sidecar.get("mismatch_count", 0)),
        ),
    )
    changed = False
    for item, expected, actual in comparisons:
        matches = expected == actual
        _add_check(
            checks,
            category="Automatic verification",
            item=item,
            status="Verified" if matches else "Checksum mismatch",
            expected=expected,
            actual=actual,
            note=(
                "Sidecar metadata matches the archived automatic verification."
                if matches
                else "Sidecar metadata no longer matches the archived automatic verification."
            ),
        )
        changed = changed or not matches

    expected_status = _verification_status_for_verdict(
        _clean(verification.get("verdict"))
    )
    actual_status = _clean(sidecar.get("verification_status"))
    status_matches = expected_status == actual_status
    _add_check(
        checks,
        category="Automatic verification",
        item="verification_status",
        status="Verified" if status_matches else "Checksum mismatch",
        expected=expected_status,
        actual=actual_status,
        note=(
            "Verification status matches its archived verdict."
            if status_matches
            else "Verification status no longer matches its archived verdict."
        ),
    )
    changed = changed or not status_matches

    archive_text = _clean(verification.get("archive_path"))
    archive_matches = bool(
        referenced_archive
        and archive_text
        and Path(archive_text).resolve(strict=False) == referenced_archive
    )
    _add_check(
        checks,
        category="Automatic verification",
        item="referenced_pipeline_archive_path",
        status="Verified" if archive_matches else "Checksum mismatch",
        expected=str(referenced_archive or "Missing"),
        actual=archive_text or "Missing",
        note=(
            "The automatic verification names the same sealed pipeline archive."
            if archive_matches
            else "The automatic verification names a different pipeline archive."
        ),
    )
    return changed or not archive_matches, False


def _verify_sidecar_state(
    sidecar: Mapping[str, object],
    evidence_records: list[dict[str, object]],
    checks: list[dict[str, object]],
) -> bool:
    verdict = _clean(sidecar.get("verdict"))
    status = _clean(sidecar.get("status"))
    expected_status = {
        SIDECAR_ARCHIVED_VERDICT: "Archived",
        SIDECAR_NOT_READY_VERDICT: "Not ready",
        SIDECAR_MISSING_VERDICT: "Missing",
        SIDECAR_FAILED_VERDICT: "Failed",
    }.get(verdict)
    pair_matches = bool(expected_status and status == expected_status)

    evidence_statuses = {_clean(record.get("status")) for record in evidence_records}
    pipeline_receipt_id = _clean(sidecar.get("pipeline_receipt_id"))
    ids_match = bool(
        pipeline_receipt_id
        and pipeline_receipt_id == _clean(sidecar.get("original_receipt_id"))
        and pipeline_receipt_id == _clean(sidecar.get("recalculated_receipt_id"))
    )
    coherent = pair_matches
    if verdict == SIDECAR_ARCHIVED_VERDICT:
        coherent = bool(
            coherent
            and _clean(sidecar.get("verification_verdict"))
            == VERIFICATION_VERIFIED_VERDICT
            and _clean(sidecar.get("verification_status")) == "Verified"
            and _to_int(sidecar.get("mismatch_count", 0)) == 0
            and evidence_statuses == {"Archived"}
            and ids_match
        )
    elif verdict == SIDECAR_NOT_READY_VERDICT:
        coherent = bool(
            coherent
            and (
                (
                    _clean(sidecar.get("verification_verdict"))
                    == VERIFICATION_NOT_READY_VERDICT
                    and _clean(sidecar.get("verification_status")) == "Not ready"
                    and _to_int(sidecar.get("mismatch_count", 0)) == 0
                    and ids_match
                )
                or _clean(sidecar.get("pipeline_receipt_path_status")) != "Safe"
            )
        )
    elif verdict == SIDECAR_MISSING_VERDICT:
        coherent = coherent and "Missing" in evidence_statuses

    _add_check(
        checks,
        category="Sidecar state",
        item="verdict_and_status",
        status="Verified" if coherent else "Checksum mismatch",
        expected={"verdict": verdict, "status": expected_status or "Known status"},
        actual={"verdict": verdict, "status": status},
        note=(
            "The sidecar verdict, status, evidence, and receipt fields are coherent."
            if coherent
            else "The sidecar verdict or status is inconsistent with its bound evidence."
        ),
    )
    return not coherent


def _verify_referenced_archive(
    sidecar: Mapping[str, object],
    output_dir: Path,
    generated_at: datetime,
    checks: list[dict[str, object]],
) -> tuple[Path | None, bool]:
    archive = _safe_pipeline_archive(output_dir, sidecar.get("pipeline_archive_path"))
    if archive is None or not archive.is_dir() or archive.is_symlink():
        _add_check(
            checks,
            category="Referenced pipeline archive",
            item="pipeline_archive_path",
            status="Missing referenced archive",
            expected=sidecar.get("pipeline_archive_path", "Existing archive"),
            actual="Missing, unsafe, or unreadable",
            note="The sealed pipeline archive referenced by the sidecar is unavailable.",
        )
        return archive, True

    verification = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archive,
        output_dir=output_dir,
        generated_at=generated_at,
    )
    expected_receipt = _clean(sidecar.get("pipeline_receipt_id"))
    original_receipt = _clean(verification.get("original_receipt_id"))
    recalculated_receipt = _clean(verification.get("recalculated_receipt_id"))
    ignored_categories = {"Referenced report", "Review readiness"}
    internal_failures = [
        row
        for row in verification.get("checks", [])
        if isinstance(row, Mapping)
        and _clean(row.get("category")) not in ignored_categories
        and _clean(row.get("status")) not in {"Verified", "Not applicable"}
    ]
    matches = bool(
        expected_receipt
        and expected_receipt == original_receipt == recalculated_receipt
        and not internal_failures
    )
    _add_check(
        checks,
        category="Referenced pipeline archive",
        item="pipeline_receipt_id",
        status="Verified" if matches else "Referenced archive changed",
        expected=expected_receipt or "Bound pipeline receipt ID",
        actual={
            "original_receipt_id": original_receipt,
            "recalculated_receipt_id": recalculated_receipt,
            "internal_mismatch_count": len(internal_failures),
        },
        note=(
            "The sealed pipeline archive still recalculates to the bound receipt ID."
            if matches
            else "The sealed pipeline archive or its receipt no longer matches the sidecar."
        ),
    )
    return archive, not matches


def build_epl_weekly_pipeline_verification_sidecar_verification(
    *,
    sidecar_path: Path | None = None,
    output_dir: Path | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Verify one archived weekly verification sidecar without changing it."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    now = generated_at or datetime.now().astimezone()
    sidecar_dir, selection_note, safe_selection = _resolve_sidecar_dir(
        sidecar_path, outputs
    )
    if sidecar_dir is None:
        return _missing_summary(sidecar_dir, selection_note, now)
    if not safe_selection:
        return _missing_summary(
            sidecar_dir,
            selection_note,
            now,
            status="Malformed sidecar",
            verdict="Malformed weekly verification sidecar",
        )
    if not sidecar_dir.is_dir() or sidecar_dir.is_symlink():
        return _missing_summary(sidecar_dir, selection_note, now)

    checks: list[dict[str, object]] = []
    _add_check(
        checks,
        category="Sidecar archive",
        item="sidecar_archive_path",
        status="Verified",
        expected="Existing archived weekly verification sidecar",
        actual=str(sidecar_dir),
        note=selection_note,
    )
    metadata_path = sidecar_dir / SIDECAR_JSON_FILENAME
    if metadata_path.is_symlink():
        return _missing_summary(
            sidecar_dir,
            "The sidecar metadata JSON must be a regular non-symlink file.",
            now,
            status="Malformed sidecar",
            verdict="Malformed weekly verification sidecar",
        )
    sidecar, metadata_note = _read_json(metadata_path)
    if sidecar is None:
        return _missing_summary(
            sidecar_dir,
            metadata_note,
            now,
            status=(
                "Malformed sidecar" if metadata_path.is_file() else "Missing sidecar"
            ),
            verdict=(
                "Malformed weekly verification sidecar"
                if metadata_path.is_file()
                else "Missing weekly verification sidecar"
            ),
        )
    _add_check(
        checks,
        category="Sidecar file",
        item=SIDECAR_JSON_FILENAME,
        status="Verified",
        expected="Readable sidecar metadata JSON object",
        actual=file_sha256(metadata_path),
        note="The archived sidecar metadata JSON is readable.",
    )

    missing_fields = [field for field in REQUIRED_SIDECAR_FIELDS if field not in sidecar]
    _add_check(
        checks,
        category="Sidecar metadata",
        item="required_fields",
        status="Verified" if not missing_fields else "Malformed sidecar",
        expected=list(REQUIRED_SIDECAR_FIELDS),
        actual=[field for field in REQUIRED_SIDECAR_FIELDS if field in sidecar],
        note=(
            "All required sidecar fields are present."
            if not missing_fields
            else "Missing sidecar field(s): " + ", ".join(missing_fields)
        ),
    )
    malformed = bool(missing_fields)
    raw_mismatch_count = sidecar.get("mismatch_count", 0)
    try:
        int(raw_mismatch_count or 0)
    except (TypeError, ValueError):
        _add_check(
            checks,
            category="Sidecar metadata",
            item="mismatch_count",
            status="Malformed sidecar",
            expected="Integer",
            actual=raw_mismatch_count,
            note="The recorded automatic verification mismatch count is not numeric.",
        )
        malformed = True
    evidence_records, evidence_malformed = _evidence_records_by_type(
        sidecar.get("evidence")
    )
    malformed = malformed or evidence_malformed
    evidence_frame = pd.DataFrame(
        list(evidence_records.values()), columns=EVIDENCE_COLUMNS
    )

    recorded_archive = _safe_member(outputs, sidecar.get("sidecar_archive_path"))
    archive_path_matches = bool(recorded_archive and recorded_archive == sidecar_dir)
    _add_check(
        checks,
        category="Sidecar metadata",
        item="recorded_sidecar_archive_path",
        status="Verified" if archive_path_matches else "Malformed sidecar",
        expected=_display_path(sidecar_dir, outputs),
        actual=_clean(sidecar.get("sidecar_archive_path")) or "Missing",
        note=(
            "The sidecar metadata identifies the selected archive folder."
            if archive_path_matches
            else "The sidecar metadata identifies a different or unsafe archive folder."
        ),
    )
    malformed = malformed or not archive_path_matches

    view_changed, view_malformed = _verify_sidecar_views(
        sidecar_dir, sidecar, evidence_frame, checks
    )
    malformed = malformed or view_malformed
    (
        current_evidence,
        evidence_contents,
        evidence_changed,
        evidence_structure_malformed,
        expected_missing,
    ) = _verify_evidence(sidecar_dir, sidecar, outputs, checks)
    malformed = malformed or evidence_structure_malformed

    referenced_archive, referenced_changed = _verify_referenced_archive(
        sidecar, outputs, now, checks
    )
    verification_changed, verification_malformed = _verify_verification_metadata(
        sidecar, evidence_contents, referenced_archive, checks
    )
    malformed = malformed or verification_malformed
    state_changed = _verify_sidecar_state(sidecar, current_evidence, checks)

    recalculated_checksum, recalculated_id = (
        calculate_epl_weekly_pipeline_verification_sidecar_identity(
            pipeline_receipt_id=_clean(sidecar.get("pipeline_receipt_id")),
            pipeline_archive_path=_clean(sidecar.get("pipeline_archive_path")),
            verification_verdict=_clean(sidecar.get("verification_verdict")),
            verification_status=_clean(sidecar.get("verification_status")),
            original_receipt_id=_clean(sidecar.get("original_receipt_id")),
            recalculated_receipt_id=_clean(sidecar.get("recalculated_receipt_id")),
            mismatch_count=_to_int(sidecar.get("mismatch_count", 0)),
            sidecar_verdict=_clean(sidecar.get("verdict")),
            evidence_records=current_evidence,
        )
    )
    original_checksum = _clean(sidecar.get("sidecar_receipt_checksum_sha256"))
    original_id = _clean(sidecar.get("sidecar_receipt_id"))
    checksum_matches = bool(original_checksum and original_checksum == recalculated_checksum)
    id_matches = bool(original_id and original_id == recalculated_id)
    _add_check(
        checks,
        category="Sidecar identity",
        item="sidecar_receipt_checksum_sha256",
        status="Verified" if checksum_matches else "Checksum mismatch",
        expected=original_checksum or "Recorded sidecar checksum",
        actual=recalculated_checksum,
        note=(
            "The canonical sidecar checksum matches."
            if checksum_matches
            else "The sidecar's checksum-bound content changed."
        ),
    )
    _add_check(
        checks,
        category="Sidecar identity",
        item="sidecar_receipt_id",
        status="Verified" if id_matches else "Sidecar receipt ID mismatch",
        expected=original_id or "Recorded sidecar receipt ID",
        actual=recalculated_id,
        note=(
            "The deterministic sidecar receipt ID matches."
            if id_matches
            else "The archived sidecar receipt ID does not match recalculated evidence."
        ),
    )

    safety = sidecar.get("safety")
    safety_matches = bool(
        isinstance(safety, Mapping)
        and all(value is False for value in safety.values())
    )
    _add_check(
        checks,
        category="Safety metadata",
        item="read_only_flags",
        status="Verified" if safety_matches else "Malformed sidecar",
        expected="All recorded mutation flags are false",
        actual=safety if isinstance(safety, Mapping) else "Missing or malformed",
        note=(
            "The sidecar records the expected read-only safety boundary."
            if safety_matches
            else "The sidecar safety metadata is missing, malformed, or unsafe."
        ),
    )
    malformed = malformed or not safety_matches

    identity_changed = not (checksum_matches and id_matches)
    integrity_changed = bool(
        view_changed
        or evidence_changed
        or verification_changed
        or state_changed
        or identity_changed
    )
    original_ready = (
        _clean(sidecar.get("verdict")) == SIDECAR_ARCHIVED_VERDICT
        and _clean(sidecar.get("status")) == "Archived"
    )
    if malformed:
        verdict = "Malformed weekly verification sidecar"
    elif referenced_changed:
        verdict = "Referenced pipeline archive changed"
    elif integrity_changed:
        verdict = "Weekly verification sidecar changed"
    elif not original_ready or expected_missing:
        verdict = "Weekly verification sidecar not ready"
    else:
        verdict = "Weekly verification sidecar verified"
    if verdict not in FINAL_VERDICTS:
        raise ValueError(f"Unexpected sidecar verification verdict: {verdict}")

    blocking_checks = [
        row
        for row in checks
        if _clean(row.get("status")) not in {"Verified", "Not applicable"}
    ]
    blockers = [
        f"{row['item']}: {row['note']}"
        for row in blocking_checks
        if _clean(row.get("note"))
    ]
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "verdict": verdict,
        "sidecar_archive_path": str(sidecar_dir),
        "original_sidecar_receipt_id": original_id,
        "recalculated_sidecar_receipt_id": recalculated_id,
        "original_sidecar_checksum_sha256": original_checksum,
        "recalculated_sidecar_checksum_sha256": recalculated_checksum,
        "referenced_pipeline_archive_path": str(referenced_archive or ""),
        "referenced_pipeline_receipt_id": _clean(sidecar.get("pipeline_receipt_id")),
        "verification_verdict": _clean(sidecar.get("verification_verdict")),
        "verification_status": _clean(sidecar.get("verification_status")),
        "original_pipeline_receipt_id": _clean(sidecar.get("original_receipt_id")),
        "recalculated_pipeline_receipt_id": _clean(
            sidecar.get("recalculated_receipt_id")
        ),
        "reported_verification_mismatch_count": _to_int(
            sidecar.get("mismatch_count", 0)
        ),
        "mismatch_count": len(blocking_checks),
        "blockers": blockers,
        "checks": checks,
        "safety": _safety_summary(),
    }


def render_epl_weekly_pipeline_verification_sidecar_verification(
    summary: Mapping[str, object],
) -> str:
    checks = pd.DataFrame(summary.get("checks", []))
    lines = [
        "# EPL Weekly Pipeline Verification Sidecar Verification",
        "",
        "**Nothing was applied.** This checker only reads an archived verification "
        "sidecar and its referenced sealed weekly pipeline archive, then writes "
        "separate verification reports.",
        "",
        f"- Sidecar archive: `{summary.get('sidecar_archive_path') or 'Not available'}`",
        f"- Final verdict: **{summary.get('verdict', '')}**",
        "- Original sidecar receipt ID: "
        f"`{summary.get('original_sidecar_receipt_id') or 'Not available'}`",
        "- Recalculated sidecar receipt ID: "
        f"`{summary.get('recalculated_sidecar_receipt_id') or 'Not available'}`",
        "- Referenced pipeline archive: "
        f"`{summary.get('referenced_pipeline_archive_path') or 'Not available'}`",
        "- Referenced pipeline receipt ID: "
        f"`{summary.get('referenced_pipeline_receipt_id') or 'Not available'}`",
        f"- Verification verdict: {summary.get('verification_verdict') or 'Not available'}",
        f"- Verification status: {summary.get('verification_status') or 'Not available'}",
        "- Automatic verification mismatch count: "
        f"{int(summary.get('reported_verification_mismatch_count', 0) or 0)}",
        f"- Sidecar mismatch/blocker count: {int(summary.get('mismatch_count', 0) or 0)}",
        "",
        "## Verification table",
        "",
        checks.to_markdown(index=False) if not checks.empty else "No checks were available.",
        "",
        "## Mismatches and blockers",
        "",
    ]
    lines.extend(
        [f"- {item}" for item in summary.get("blockers", [])] or ["- None."]
    )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "Verification does not modify the sealed pipeline archive or sidecar, import "
            "odds, edit manual files, run live providers, apply settlement, promote "
            "staging, allowlist providers, enable cron, fabricate odds, or place bets.",
        ]
    )
    return "\n".join(lines)


def save_epl_weekly_pipeline_verification_sidecar_verification(
    *,
    sidecar_path: Path | None = None,
    output_dir: Path | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    outputs.mkdir(parents=True, exist_ok=True)
    summary = build_epl_weekly_pipeline_verification_sidecar_verification(
        sidecar_path=sidecar_path,
        output_dir=outputs,
        generated_at=generated_at,
    )
    paths = {
        "json": outputs / SIDECAR_VERIFICATION_JSON_FILENAME,
        "markdown": outputs / SIDECAR_VERIFICATION_MARKDOWN_FILENAME,
        "csv": outputs / SIDECAR_VERIFICATION_CSV_FILENAME,
    }
    atomic_write_report(
        paths["json"],
        (json.dumps(_json_safe(summary), indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )
    atomic_write_report(
        paths["markdown"],
        (
            render_epl_weekly_pipeline_verification_sidecar_verification(summary)
            + "\n"
        ).encode("utf-8"),
    )
    atomic_write_report(
        paths["csv"],
        pd.DataFrame(summary["checks"]).to_csv(index=False).encode("utf-8"),
    )
    return {"summary": summary, "verdict": summary["verdict"], **paths}
