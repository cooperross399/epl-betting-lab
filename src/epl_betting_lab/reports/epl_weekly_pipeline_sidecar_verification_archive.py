from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.providers.base import atomic_write_report, file_sha256
from epl_betting_lab.reports.epl_weekly_pipeline_verification_sidecar_verification import (
    SIDECAR_VERIFICATION_CSV_FILENAME,
    SIDECAR_VERIFICATION_JSON_FILENAME,
    SIDECAR_VERIFICATION_MARKDOWN_FILENAME,
)


SIDECAR_VERIFICATION_ARCHIVE_JSON_FILENAME = (
    "epl_weekly_pipeline_sidecar_verification_archive.json"
)
SIDECAR_VERIFICATION_ARCHIVE_MARKDOWN_FILENAME = (
    "epl_weekly_pipeline_sidecar_verification_archive.md"
)
SIDECAR_VERIFICATION_ARCHIVE_CSV_FILENAME = (
    "epl_weekly_pipeline_sidecar_verification_archive.csv"
)
SIDECAR_VERIFICATION_ARCHIVE_ROOT = Path(
    "archive/epl_weekly_pipeline_sidecar_verifications"
)

SIDECAR_VERIFICATION_ARCHIVED_VERDICT = "Sidecar verification archived"
SIDECAR_VERIFICATION_ARCHIVE_NOT_READY_VERDICT = "Sidecar verification not ready"
SIDECAR_VERIFICATION_MISSING_VERDICT = "Missing sidecar verification report"
SIDECAR_VERIFICATION_ARCHIVE_FAILED_VERDICT = (
    "Sidecar verification archive failed"
)

SIDECAR_VERIFIED_VERDICT = "Weekly verification sidecar verified"
SIDECAR_NOT_READY_VERDICT = "Weekly verification sidecar not ready"

EVIDENCE_COLUMNS = (
    "evidence_type",
    "source_path",
    "archive_member_path",
    "archived_path",
    "checksum_sha256",
    "size_bytes",
    "status",
    "note",
)

_EXPECTED_REPORTS = {
    "sidecar_verification_json": SIDECAR_VERIFICATION_JSON_FILENAME,
    "sidecar_verification_markdown": SIDECAR_VERIFICATION_MARKDOWN_FILENAME,
    "sidecar_verification_csv": SIDECAR_VERIFICATION_CSV_FILENAME,
}
_SAFE_RECEIPT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")


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


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _display_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(
            output_dir.resolve(strict=False)
        ).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _safe_receipt_component(receipt_id: object) -> tuple[str, str, str]:
    raw = _clean(receipt_id)
    if raw and _SAFE_RECEIPT_RE.fullmatch(raw) and ".." not in raw:
        return raw, "Safe", "The sidecar receipt ID is safe for an archive folder."
    if not raw:
        return (
            "missing-receipt",
            "Missing",
            "The sidecar receipt ID is missing; a safe fallback folder name was used.",
        )
    digest = sha256(raw.encode("utf-8")).hexdigest()[:12]
    return (
        f"invalid-receipt-{digest}",
        "Invalid",
        "The sidecar receipt ID was unsafe for a path; a hashed fallback folder name was used.",
    )


def _unique_archive_dir(
    output_dir: Path,
    archived_at: datetime,
    receipt_component: str,
) -> Path:
    date_dir = (
        output_dir
        / SIDECAR_VERIFICATION_ARCHIVE_ROOT
        / archived_at.strftime("%Y-%m-%d")
    )
    stem = f"{archived_at.strftime('%H%M%S')}_{receipt_component}"
    candidate = date_dir / stem
    suffix = 2
    while candidate.exists():
        candidate = date_dir / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def calculate_epl_weekly_pipeline_sidecar_verification_archive_identity(
    *,
    referenced_pipeline_receipt_id: str,
    sidecar_receipt_id: str,
    sidecar_archive_path: str,
    sidecar_verification_verdict: str,
    sidecar_verification_status: str,
    original_sidecar_receipt_id: str,
    recalculated_sidecar_receipt_id: str,
    mismatch_count: int,
    archive_verdict: str,
    evidence_records: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    """Return a deterministic checksum and receipt ID for archived verification."""
    evidence = sorted(
        (
            {
                "evidence_type": _clean(record.get("evidence_type")),
                "archive_member_path": _clean(
                    record.get("archive_member_path")
                ),
                "checksum_sha256": _clean(
                    record.get("checksum_sha256")
                ).casefold(),
                "size_bytes": _to_int(record.get("size_bytes")),
                "status": _clean(record.get("status")),
            }
            for record in evidence_records
        ),
        key=lambda item: (item["archive_member_path"], item["evidence_type"]),
    )
    payload = {
        "schema_version": 1,
        "referenced_pipeline_receipt_id": _clean(
            referenced_pipeline_receipt_id
        ),
        "sidecar_receipt_id": _clean(sidecar_receipt_id),
        "sidecar_archive_path": _clean(sidecar_archive_path),
        "sidecar_verification_verdict": _clean(sidecar_verification_verdict),
        "sidecar_verification_status": _clean(sidecar_verification_status),
        "original_sidecar_receipt_id": _clean(original_sidecar_receipt_id),
        "recalculated_sidecar_receipt_id": _clean(
            recalculated_sidecar_receipt_id
        ),
        "mismatch_count": int(mismatch_count),
        "archive_verdict": _clean(archive_verdict),
        "evidence": evidence,
    }
    checksum = sha256(_canonical_json(payload)).hexdigest()
    return checksum, f"epl-weekly-sidecar-check-{checksum[:24]}"


def _evidence_record(
    evidence_type: str,
    expected_name: str,
    path: Path | None,
    *,
    output_dir: Path,
) -> tuple[dict[str, object], bytes | None]:
    if path is None:
        return (
            {
                "evidence_type": evidence_type,
                "source_path": "",
                "archive_member_path": expected_name,
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Missing",
                "note": "The automatic sidecar verifier did not return this report path.",
            },
            None,
        )
    selected = path.resolve(strict=False)
    source_display = _display_path(selected, output_dir)
    try:
        selected.relative_to(output_dir.resolve(strict=False))
    except ValueError:
        return (
            {
                "evidence_type": evidence_type,
                "source_path": source_display,
                "archive_member_path": expected_name,
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Unreadable",
                "note": "Verification evidence must stay inside the report output folder.",
            },
            None,
        )
    if selected.name != expected_name:
        return (
            {
                "evidence_type": evidence_type,
                "source_path": source_display,
                "archive_member_path": expected_name,
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Unreadable",
                "note": f"Expected the verifier report filename {expected_name}.",
            },
            None,
        )
    if not selected.exists():
        return (
            {
                "evidence_type": evidence_type,
                "source_path": source_display,
                "archive_member_path": expected_name,
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Missing",
                "note": "The sidecar verification report does not exist.",
            },
            None,
        )
    if not selected.is_file() or selected.is_symlink():
        return (
            {
                "evidence_type": evidence_type,
                "source_path": source_display,
                "archive_member_path": expected_name,
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Unreadable",
                "note": "Verification evidence must be a regular non-symlink file.",
            },
            None,
        )
    try:
        content = selected.read_bytes()
    except OSError as exc:
        return (
            {
                "evidence_type": evidence_type,
                "source_path": source_display,
                "archive_member_path": expected_name,
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Unreadable",
                "note": f"The sidecar verification report could not be read: {exc}",
            },
            None,
        )
    return (
        {
            "evidence_type": evidence_type,
            "source_path": source_display,
            "archive_member_path": expected_name,
            "archived_path": "",
            "checksum_sha256": sha256(content).hexdigest(),
            "size_bytes": len(content),
            "status": "Archived",
            "note": "Prepared for checksum-verified archival.",
        },
        content,
    )


def _read_json(content: bytes | None) -> tuple[dict[str, object], str]:
    if content is None:
        return {}, "The sidecar verification JSON report is missing."
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"The sidecar verification JSON report is malformed: {exc}"
    if not isinstance(value, dict):
        return {}, "The sidecar verification JSON report must contain an object."
    return value, ""


def _safe_existing_archive(
    path: Path | None,
    *,
    output_dir: Path,
    label: str,
) -> tuple[Path | None, str]:
    if path is None:
        return None, f"The {label} path is missing."
    selected = path.resolve(strict=False)
    try:
        selected.relative_to(output_dir.resolve(strict=False))
    except ValueError:
        return None, f"The {label} path is outside the report output folder."
    if not selected.is_dir() or selected.is_symlink():
        return None, f"The {label} path is missing, unreadable, or unsafe."
    return selected, ""


def _same_path(left: object, right: Path | None) -> bool:
    text = _clean(left)
    return bool(
        text
        and right is not None
        and Path(text).resolve(strict=False) == right.resolve(strict=False)
    )


def render_epl_weekly_pipeline_sidecar_verification_archive(
    summary: Mapping[str, object], evidence: pd.DataFrame
) -> str:
    blockers = summary.get("blockers", [])
    blocker_items = blockers if isinstance(blockers, list) else []
    lines = [
        "# EPL Weekly Pipeline Sidecar Verification Archive",
        "",
        "**Nothing was applied.** This separate receipt preserves the reports that "
        "checked a sealed weekly verification sidecar. The sealed pipeline archive "
        "and sealed sidecar archive were not modified.",
        "",
        "## Archive summary",
        "",
        f"- Verdict: **{summary.get('verdict', SIDECAR_VERIFICATION_ARCHIVE_FAILED_VERDICT)}**",
        "- Archive receipt ID: "
        f"`{summary.get('sidecar_verification_archive_receipt_id') or 'Missing'}`",
        "- Archive receipt SHA-256: "
        f"`{summary.get('sidecar_verification_archive_checksum_sha256') or 'Missing'}`",
        f"- Archive folder: `{summary.get('archive_path') or 'Missing'}`",
        f"- Sidecar receipt ID: `{summary.get('sidecar_receipt_id') or 'Missing'}`",
        f"- Sealed sidecar checked: `{summary.get('sidecar_archive_path') or 'Missing'}`",
        "- Sidecar verification verdict: "
        f"**{summary.get('sidecar_verification_verdict') or 'Missing'}**",
        "- Sidecar verification status: "
        f"{summary.get('sidecar_verification_status') or 'Missing'}",
        "- Original/recalculated sidecar IDs: "
        f"`{summary.get('original_sidecar_receipt_id') or 'Missing'}` / "
        f"`{summary.get('recalculated_sidecar_receipt_id') or 'Missing'}`",
        f"- Mismatch/blocker count: {int(summary.get('mismatch_count', 0) or 0)}",
        "- Referenced pipeline receipt ID: "
        f"`{summary.get('referenced_pipeline_receipt_id') or 'Missing'}`",
        "- Referenced sealed pipeline archive: "
        f"`{summary.get('referenced_pipeline_archive_path') or 'Missing'}`",
        "",
        "## Archived sidecar-verification evidence",
        "",
        evidence.to_markdown(index=False) if not evidence.empty else "No evidence rows.",
        "",
        "## Blockers and notes",
        "",
    ]
    lines.extend([f"- {item}" for item in blocker_items] or ["- None."])
    lines.extend(
        [
            "",
            "## Safety boundary",
            "",
            "This receipt only copies report outputs. It does not modify either sealed "
            "archive, edit protected files, run providers, apply settlement, allowlist "
            "providers, enable cron, fabricate odds, or place bets.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_epl_weekly_pipeline_sidecar_verification_archive_csv(
    summary: Mapping[str, object], evidence: pd.DataFrame
) -> bytes:
    rows = evidence.copy()
    if rows.empty:
        rows = pd.DataFrame([{column: "" for column in EVIDENCE_COLUMNS}])
    prefix = {
        "archive_verdict": summary.get("verdict", ""),
        "archive_status": summary.get("status", ""),
        "sidecar_verification_archive_receipt_id": summary.get(
            "sidecar_verification_archive_receipt_id", ""
        ),
        "sidecar_receipt_id": summary.get("sidecar_receipt_id", ""),
        "sidecar_archive_path": summary.get("sidecar_archive_path", ""),
        "sidecar_verification_verdict": summary.get(
            "sidecar_verification_verdict", ""
        ),
        "sidecar_verification_status": summary.get(
            "sidecar_verification_status", ""
        ),
        "original_sidecar_receipt_id": summary.get(
            "original_sidecar_receipt_id", ""
        ),
        "recalculated_sidecar_receipt_id": summary.get(
            "recalculated_sidecar_receipt_id", ""
        ),
        "mismatch_count": _to_int(summary.get("mismatch_count")),
        "referenced_pipeline_receipt_id": summary.get(
            "referenced_pipeline_receipt_id", ""
        ),
        "archive_path": summary.get("archive_path", ""),
    }
    for column, value in reversed(tuple(prefix.items())):
        rows.insert(0, column, value)
    return rows.to_csv(index=False, lineterminator="\n").encode("utf-8")


def save_epl_weekly_pipeline_sidecar_verification_archive(
    *,
    sidecar_archive_path: Path | None,
    sidecar_receipt_id: str,
    verification_paths: Mapping[str, Path | None],
    sidecar_verification_verdict: str,
    sidecar_verification_status: str,
    original_sidecar_receipt_id: str,
    recalculated_sidecar_receipt_id: str,
    mismatch_count: int,
    referenced_pipeline_archive_path: Path | None,
    referenced_pipeline_receipt_id: str,
    output_dir: Path | None = None,
    archived_at: datetime | None = None,
) -> dict[str, object]:
    """Archive exact sidecar-verifier reports outside both sealed archives."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    outputs.mkdir(parents=True, exist_ok=True)
    timestamp = archived_at or datetime.now().astimezone()
    if timestamp.tzinfo is None:
        timestamp = timestamp.astimezone()

    receipt_component, receipt_path_status, receipt_path_note = (
        _safe_receipt_component(sidecar_receipt_id)
    )
    evidence_records: list[dict[str, object]] = []
    evidence_payloads: dict[str, bytes] = {}
    for evidence_type, expected_name in _EXPECTED_REPORTS.items():
        key = evidence_type.removeprefix("sidecar_verification_")
        value = verification_paths.get(key)
        record, content = _evidence_record(
            evidence_type,
            expected_name,
            Path(value) if value is not None else None,
            output_dir=outputs,
        )
        evidence_records.append(record)
        if content is not None:
            evidence_payloads[expected_name] = content

    blockers: list[str] = []
    if receipt_path_status != "Safe":
        blockers.append(receipt_path_note)
    sidecar_dir, sidecar_path_error = _safe_existing_archive(
        sidecar_archive_path,
        output_dir=outputs,
        label="sealed verification sidecar archive",
    )
    if sidecar_path_error:
        blockers.append(sidecar_path_error)
    pipeline_dir, pipeline_path_error = _safe_existing_archive(
        referenced_pipeline_archive_path,
        output_dir=outputs,
        label="referenced sealed pipeline archive",
    )
    if pipeline_path_error:
        blockers.append(pipeline_path_error)

    verification_payload, json_error = _read_json(
        evidence_payloads.get(SIDECAR_VERIFICATION_JSON_FILENAME)
    )
    if json_error:
        blockers.append(json_error)
    elif verification_payload:
        comparisons = (
            (
                "sidecar verification verdict",
                _clean(verification_payload.get("verdict")),
                _clean(sidecar_verification_verdict),
            ),
            (
                "original sidecar receipt ID",
                _clean(verification_payload.get("original_sidecar_receipt_id")),
                _clean(original_sidecar_receipt_id),
            ),
            (
                "recalculated sidecar receipt ID",
                _clean(
                    verification_payload.get("recalculated_sidecar_receipt_id")
                ),
                _clean(recalculated_sidecar_receipt_id),
            ),
            (
                "mismatch count",
                str(_to_int(verification_payload.get("mismatch_count"))),
                str(int(mismatch_count)),
            ),
            (
                "referenced pipeline receipt ID",
                _clean(
                    verification_payload.get("referenced_pipeline_receipt_id")
                ),
                _clean(referenced_pipeline_receipt_id),
            ),
        )
        for label, reported, supplied in comparisons:
            if reported != supplied:
                blockers.append(
                    f"The supplied {label} does not match the sidecar verification JSON."
                )
        if not _same_path(
            verification_payload.get("sidecar_archive_path"), sidecar_dir
        ):
            blockers.append(
                "The sidecar verification JSON refers to a different sidecar archive."
            )
        if not _same_path(
            verification_payload.get("referenced_pipeline_archive_path"),
            pipeline_dir,
        ):
            blockers.append(
                "The sidecar verification JSON refers to a different pipeline archive."
            )

    expected_status = {
        SIDECAR_VERIFIED_VERDICT: "Verified",
        SIDECAR_NOT_READY_VERDICT: "Not ready",
    }.get(_clean(sidecar_verification_verdict), "Failed")
    if _clean(sidecar_verification_status) != expected_status:
        blockers.append(
            "The supplied sidecar verification status is inconsistent with its verdict."
        )

    ids_match = bool(
        _clean(sidecar_receipt_id)
        and _clean(sidecar_receipt_id) == _clean(original_sidecar_receipt_id)
        and _clean(sidecar_receipt_id) == _clean(recalculated_sidecar_receipt_id)
    )
    if not ids_match:
        blockers.append(
            "The sidecar, original, and recalculated receipt IDs do not all match."
        )
    if not _clean(referenced_pipeline_receipt_id):
        blockers.append("The referenced pipeline receipt ID is missing.")

    missing_reports = any(
        record["status"] == "Missing" for record in evidence_records
    )
    unreadable_reports = any(
        record["status"] == "Unreadable" for record in evidence_records
    )
    if missing_reports:
        verdict = SIDECAR_VERIFICATION_MISSING_VERDICT
        status = "Missing"
    elif unreadable_reports or json_error:
        verdict = SIDECAR_VERIFICATION_ARCHIVE_FAILED_VERDICT
        status = "Failed"
    elif (
        sidecar_verification_verdict == SIDECAR_VERIFIED_VERDICT
        and sidecar_verification_status == "Verified"
        and int(mismatch_count) == 0
        and ids_match
        and not blockers
    ):
        verdict = SIDECAR_VERIFICATION_ARCHIVED_VERDICT
        status = "Archived"
    elif (
        sidecar_verification_verdict == SIDECAR_NOT_READY_VERDICT
        and sidecar_verification_status == "Not ready"
        and int(mismatch_count) == 0
        and ids_match
        and not blockers
    ):
        verdict = SIDECAR_VERIFICATION_ARCHIVE_NOT_READY_VERDICT
        status = "Not ready"
    else:
        verdict = SIDECAR_VERIFICATION_ARCHIVE_FAILED_VERDICT
        status = "Failed"

    sidecar_display = (
        _display_path(sidecar_dir, outputs) if sidecar_dir is not None else ""
    )
    pipeline_display = (
        _display_path(pipeline_dir, outputs) if pipeline_dir is not None else ""
    )
    checksum, receipt_id = (
        calculate_epl_weekly_pipeline_sidecar_verification_archive_identity(
            referenced_pipeline_receipt_id=referenced_pipeline_receipt_id,
            sidecar_receipt_id=sidecar_receipt_id,
            sidecar_archive_path=sidecar_display,
            sidecar_verification_verdict=sidecar_verification_verdict,
            sidecar_verification_status=sidecar_verification_status,
            original_sidecar_receipt_id=original_sidecar_receipt_id,
            recalculated_sidecar_receipt_id=recalculated_sidecar_receipt_id,
            mismatch_count=int(mismatch_count),
            archive_verdict=verdict,
            evidence_records=evidence_records,
        )
    )
    archive_dir = _unique_archive_dir(outputs, timestamp, receipt_component)

    for record in evidence_records:
        member = _clean(record.get("archive_member_path"))
        content = evidence_payloads.get(member)
        if content is None:
            continue
        target = archive_dir / member
        atomic_write_report(target, content)
        if file_sha256(target) != record["checksum_sha256"]:
            raise OSError(
                f"Archived sidecar verification evidence could not be verified: {target}"
            )
        record["archived_path"] = _display_path(target, outputs)
        record["note"] = "Copied and checksum-verified in the verification archive."

    evidence = pd.DataFrame(evidence_records, columns=EVIDENCE_COLUMNS)
    summary: dict[str, object] = {
        "schema_version": 1,
        "archived_at": timestamp.isoformat(timespec="seconds"),
        "verdict": verdict,
        "status": status,
        "sidecar_receipt_id": _clean(sidecar_receipt_id),
        "sidecar_receipt_path_status": receipt_path_status,
        "sidecar_receipt_path_note": receipt_path_note,
        "sidecar_archive_path": sidecar_display,
        "sidecar_verification_verdict": _clean(sidecar_verification_verdict),
        "sidecar_verification_status": _clean(sidecar_verification_status),
        "original_sidecar_receipt_id": _clean(original_sidecar_receipt_id),
        "recalculated_sidecar_receipt_id": _clean(
            recalculated_sidecar_receipt_id
        ),
        "mismatch_count": int(mismatch_count),
        "referenced_pipeline_archive_path": pipeline_display,
        "referenced_pipeline_receipt_id": _clean(
            referenced_pipeline_receipt_id
        ),
        "sidecar_verification_archive_receipt_id": receipt_id,
        "sidecar_verification_archive_checksum_sha256": checksum,
        "archive_path": _display_path(archive_dir, outputs),
        "verification_report_count": sum(
            record["status"] == "Archived" for record in evidence_records
        ),
        "evidence_status_counts": dict(
            sorted(
                Counter(_clean(record["status"]) for record in evidence_records).items()
            )
        ),
        "blockers": blockers,
        "evidence": evidence_records,
        "safety": {
            "sealed_pipeline_archive_modified": False,
            "sealed_sidecar_archive_modified": False,
            "protected_files_edited": False,
            "force_mode_used": False,
            "settlement_applied": False,
            "staging_promoted": False,
            "live_provider_run": False,
            "provider_allowlisted": False,
            "cron_enabled": False,
            "odds_fabricated": False,
            "bets_placed": False,
        },
    }

    payloads = {
        SIDECAR_VERIFICATION_ARCHIVE_JSON_FILENAME: (
            json.dumps(_json_safe(summary), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        SIDECAR_VERIFICATION_ARCHIVE_MARKDOWN_FILENAME: (
            render_epl_weekly_pipeline_sidecar_verification_archive(
                summary, evidence
            )
        ).encode("utf-8"),
        SIDECAR_VERIFICATION_ARCHIVE_CSV_FILENAME: (
            render_epl_weekly_pipeline_sidecar_verification_archive_csv(
                summary, evidence
            )
        ),
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
        "summary": summary,
        "evidence": evidence,
        "verdict": verdict,
        "json": latest_paths[SIDECAR_VERIFICATION_ARCHIVE_JSON_FILENAME],
        "markdown": latest_paths[SIDECAR_VERIFICATION_ARCHIVE_MARKDOWN_FILENAME],
        "csv": latest_paths[SIDECAR_VERIFICATION_ARCHIVE_CSV_FILENAME],
        "archive_dir": archive_dir,
        "archive_paths": archive_paths,
    }


def archive_latest_epl_weekly_pipeline_sidecar_verification(
    output_dir: Path | None = None,
    *,
    archived_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    pipeline_path = outputs / "epl_weekly_pipeline.json"
    if not pipeline_path.is_file() or pipeline_path.is_symlink():
        raise FileNotFoundError(
            "No readable epl_weekly_pipeline.json exists. Run the weekly pipeline first."
        )
    try:
        pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"The weekly pipeline summary is unreadable: {exc}") from exc
    if not isinstance(pipeline, dict):
        raise ValueError("The weekly pipeline summary must contain a JSON object.")

    checked_sidecar = _clean(
        pipeline.get("sidecar_verification_checked_archive_path")
        or pipeline.get("verification_sidecar_archive_path")
    )
    pipeline_archive = _clean(
        pipeline.get("archive_path") or pipeline.get("pipeline_archive_path")
    )
    return save_epl_weekly_pipeline_sidecar_verification_archive(
        sidecar_archive_path=Path(checked_sidecar) if checked_sidecar else None,
        sidecar_receipt_id=_clean(
            pipeline.get("verification_sidecar_receipt_id")
        ),
        verification_paths={
            "json": outputs / SIDECAR_VERIFICATION_JSON_FILENAME,
            "markdown": outputs / SIDECAR_VERIFICATION_MARKDOWN_FILENAME,
            "csv": outputs / SIDECAR_VERIFICATION_CSV_FILENAME,
        },
        sidecar_verification_verdict=_clean(
            pipeline.get("sidecar_verification_verdict")
        ),
        sidecar_verification_status=_clean(
            pipeline.get("sidecar_verification_status")
        ),
        original_sidecar_receipt_id=_clean(
            pipeline.get("sidecar_verification_original_id")
        ),
        recalculated_sidecar_receipt_id=_clean(
            pipeline.get("sidecar_verification_recalculated_id")
        ),
        mismatch_count=_to_int(
            pipeline.get("sidecar_verification_mismatch_count")
        ),
        referenced_pipeline_archive_path=(
            Path(pipeline_archive) if pipeline_archive else None
        ),
        referenced_pipeline_receipt_id=_clean(
            pipeline.get("archive_receipt_id")
            or pipeline.get("pipeline_receipt_id")
        ),
        output_dir=outputs,
        archived_at=archived_at,
    )


def list_recent_epl_weekly_pipeline_sidecar_verification_archives(
    output_dir: Path | None = None,
    *,
    limit: int = 8,
) -> pd.DataFrame:
    if limit <= 0:
        return pd.DataFrame()
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    root = outputs / SIDECAR_VERIFICATION_ARCHIVE_ROOT
    rows: list[dict[str, object]] = []
    for path in root.glob(
        f"*/*/{SIDECAR_VERIFICATION_ARCHIVE_JSON_FILENAME}"
    ):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        rows.append(
            {
                "archived_at": payload.get("archived_at", ""),
                "verdict": payload.get("verdict", ""),
                "archive_receipt_id": payload.get(
                    "sidecar_verification_archive_receipt_id", ""
                ),
                "sidecar_receipt_id": payload.get("sidecar_receipt_id", ""),
                "sidecar_verification_verdict": payload.get(
                    "sidecar_verification_verdict", ""
                ),
                "mismatch_count": _to_int(payload.get("mismatch_count")),
                "archive_path": payload.get("archive_path", ""),
            }
        )
    rows.sort(
        key=lambda row: (_clean(row["archived_at"]), _clean(row["archive_path"]))
    )
    return pd.DataFrame(list(reversed(rows[-limit:])))
