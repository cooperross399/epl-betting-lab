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
from epl_betting_lab.reports.epl_weekly_pipeline_receipt_verification import (
    VERIFICATION_CSV_FILENAME,
    VERIFICATION_JSON_FILENAME,
    VERIFICATION_MARKDOWN_FILENAME,
)


SIDECAR_JSON_FILENAME = "epl_weekly_pipeline_verification_sidecar.json"
SIDECAR_MARKDOWN_FILENAME = "epl_weekly_pipeline_verification_sidecar.md"
SIDECAR_CSV_FILENAME = "epl_weekly_pipeline_verification_sidecar.csv"
SIDECAR_ARCHIVE_ROOT = Path("archive/epl_weekly_pipeline_verifications")

SIDECAR_ARCHIVED_VERDICT = "Verification sidecar archived"
SIDECAR_NOT_READY_VERDICT = "Verification sidecar not ready"
SIDECAR_MISSING_VERDICT = "Missing verification report"
SIDECAR_FAILED_VERDICT = "Verification sidecar failed"

VERIFICATION_VERIFIED_VERDICT = "Weekly pipeline receipt verified"
VERIFICATION_NOT_READY_VERDICT = "Weekly pipeline receipt not ready"

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
        return raw, "Safe", "The pipeline receipt ID is safe for an archive folder."
    if not raw:
        return (
            "missing-receipt",
            "Missing",
            "The pipeline receipt ID is missing; a safe fallback folder name was used.",
        )
    digest = sha256(raw.encode("utf-8")).hexdigest()[:12]
    return (
        f"invalid-receipt-{digest}",
        "Invalid",
        "The pipeline receipt ID was unsafe for a path; a hashed fallback folder name was used.",
    )


def _unique_archive_dir(
    output_dir: Path,
    archived_at: datetime,
    receipt_component: str,
) -> Path:
    date_dir = output_dir / SIDECAR_ARCHIVE_ROOT / archived_at.strftime("%Y-%m-%d")
    stem = f"{archived_at.strftime('%H%M%S')}_{receipt_component}"
    candidate = date_dir / stem
    suffix = 2
    while candidate.exists():
        candidate = date_dir / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def calculate_epl_weekly_pipeline_verification_sidecar_identity(
    *,
    pipeline_receipt_id: str,
    pipeline_archive_path: str,
    verification_verdict: str,
    verification_status: str,
    original_receipt_id: str,
    recalculated_receipt_id: str,
    mismatch_count: int,
    sidecar_verdict: str,
    evidence_records: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    """Return the deterministic checksum and ID for a verification sidecar."""
    evidence = sorted(
        (
            {
                "evidence_type": _clean(record.get("evidence_type")),
                "archive_member_path": _clean(
                    record.get("archive_member_path")
                ),
                "checksum_sha256": _clean(record.get("checksum_sha256")).casefold(),
                "size_bytes": int(record.get("size_bytes", 0) or 0),
                "status": _clean(record.get("status")),
            }
            for record in evidence_records
        ),
        key=lambda item: (item["archive_member_path"], item["evidence_type"]),
    )
    payload = {
        "schema_version": 1,
        "pipeline_receipt_id": _clean(pipeline_receipt_id),
        "pipeline_archive_path": _clean(pipeline_archive_path),
        "verification_verdict": _clean(verification_verdict),
        "verification_status": _clean(verification_status),
        "original_receipt_id": _clean(original_receipt_id),
        "recalculated_receipt_id": _clean(recalculated_receipt_id),
        "mismatch_count": int(mismatch_count),
        "sidecar_verdict": _clean(sidecar_verdict),
        "evidence": evidence,
    }
    checksum = sha256(_canonical_json(payload)).hexdigest()
    return checksum, f"epl-weekly-verification-{checksum[:24]}"


def _evidence_record(
    evidence_type: str,
    path: Path | None,
    *,
    output_dir: Path,
) -> tuple[dict[str, object], bytes | None]:
    if path is None:
        return (
            {
                "evidence_type": evidence_type,
                "source_path": "",
                "archive_member_path": "",
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Missing",
                "note": "The automatic verifier did not return this report path.",
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
                "archive_member_path": "",
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Unreadable",
                "note": "Verification evidence must stay inside the report output folder.",
            },
            None,
        )
    if not selected.exists():
        return (
            {
                "evidence_type": evidence_type,
                "source_path": source_display,
                "archive_member_path": selected.name,
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Missing",
                "note": "The verification report does not exist.",
            },
            None,
        )
    if not selected.is_file() or selected.is_symlink():
        return (
            {
                "evidence_type": evidence_type,
                "source_path": source_display,
                "archive_member_path": selected.name,
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
                "archive_member_path": selected.name,
                "archived_path": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "status": "Unreadable",
                "note": f"The verification report could not be read: {exc}",
            },
            None,
        )
    return (
        {
            "evidence_type": evidence_type,
            "source_path": source_display,
            "archive_member_path": selected.name,
            "archived_path": "",
            "checksum_sha256": sha256(content).hexdigest(),
            "size_bytes": len(content),
            "status": "Archived",
            "note": "Prepared for checksum-verified archival.",
        },
        content,
    )


def _read_verification_json(content: bytes | None) -> tuple[dict[str, object], str]:
    if content is None:
        return {}, "The verification JSON report is missing."
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"The verification JSON report is malformed: {exc}"
    if not isinstance(value, dict):
        return {}, "The verification JSON report must contain a JSON object."
    return value, ""


def _same_path(left: object, right: Path) -> bool:
    text = _clean(left)
    if not text:
        return False
    return Path(text).resolve(strict=False) == right.resolve(strict=False)


def _render_markdown(summary: Mapping[str, object], evidence: pd.DataFrame) -> str:
    blockers = summary.get("blockers", [])
    blocker_items = blockers if isinstance(blockers, list) else []
    lines = [
        "# EPL Weekly Pipeline Verification Sidecar",
        "",
        "**Nothing was applied.** This sidecar only preserves checksum-bound copies of "
        "the automatic weekly pipeline receipt verification reports. The sealed weekly "
        "pipeline archive was not modified.",
        "",
        "## Sidecar summary",
        "",
        f"- Verdict: **{summary.get('verdict', SIDECAR_FAILED_VERDICT)}**",
        f"- Pipeline receipt ID: `{summary.get('pipeline_receipt_id') or 'Missing'}`",
        f"- Pipeline archive: `{summary.get('pipeline_archive_path') or 'Missing'}`",
        f"- Verification verdict: **{summary.get('verification_verdict') or 'Missing'}**",
        f"- Verification status: {summary.get('verification_status') or 'Missing'}",
        f"- Original receipt ID: `{summary.get('original_receipt_id') or 'Missing'}`",
        f"- Recalculated receipt ID: `{summary.get('recalculated_receipt_id') or 'Missing'}`",
        f"- Mismatch/blocker count: {int(summary.get('mismatch_count', 0) or 0)}",
        f"- Sidecar receipt ID: `{summary.get('sidecar_receipt_id') or 'Missing'}`",
        "- Sidecar receipt SHA-256: "
        f"`{summary.get('sidecar_receipt_checksum_sha256') or 'Missing'}`",
        f"- Sidecar archive: `{summary.get('sidecar_archive_path') or 'Missing'}`",
        "",
        "## Archived verification evidence",
        "",
        (
            evidence.to_markdown(index=False)
            if not evidence.empty
            else "No evidence rows were available."
        ),
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
            "This receipt proves which automatic verification bytes were preserved. It "
            "does not alter the sealed pipeline archive, edit protected inputs, run a live "
            "provider, apply settlement, enable cron, fabricate odds, or place bets.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_csv(summary: Mapping[str, object], evidence: pd.DataFrame) -> bytes:
    rows = evidence.copy()
    prefix = {
        "sidecar_verdict": summary.get("verdict", ""),
        "sidecar_receipt_id": summary.get("sidecar_receipt_id", ""),
        "pipeline_receipt_id": summary.get("pipeline_receipt_id", ""),
        "pipeline_archive_path": summary.get("pipeline_archive_path", ""),
        "verification_verdict": summary.get("verification_verdict", ""),
        "verification_status": summary.get("verification_status", ""),
        "original_receipt_id": summary.get("original_receipt_id", ""),
        "recalculated_receipt_id": summary.get("recalculated_receipt_id", ""),
        "mismatch_count": int(summary.get("mismatch_count", 0) or 0),
    }
    if rows.empty:
        rows = pd.DataFrame([{column: "" for column in EVIDENCE_COLUMNS}])
    for column, value in reversed(tuple(prefix.items())):
        rows.insert(0, column, value)
    return rows.to_csv(index=False, lineterminator="\n").encode("utf-8")


def save_epl_weekly_pipeline_verification_sidecar(
    *,
    pipeline_archive_path: Path,
    pipeline_receipt_id: str,
    verification_paths: Mapping[str, Path | None],
    verification_verdict: str,
    verification_status: str,
    original_receipt_id: str,
    recalculated_receipt_id: str,
    mismatch_count: int,
    output_dir: Path | None = None,
    archived_at: datetime | None = None,
) -> dict[str, object]:
    """Archive exact verifier reports without modifying the sealed pipeline archive."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    outputs.mkdir(parents=True, exist_ok=True)
    timestamp = archived_at or datetime.now().astimezone()
    if timestamp.tzinfo is None:
        timestamp = timestamp.astimezone()

    receipt_component, receipt_path_status, receipt_path_note = (
        _safe_receipt_component(pipeline_receipt_id)
    )
    selected_paths = {
        "verification_json": verification_paths.get("json"),
        "verification_markdown": verification_paths.get("markdown"),
        "verification_csv": verification_paths.get("csv"),
    }
    evidence_records: list[dict[str, object]] = []
    evidence_payloads: dict[str, bytes] = {}
    for evidence_type, path in selected_paths.items():
        record, content = _evidence_record(
            evidence_type,
            Path(path) if path is not None else None,
            output_dir=outputs,
        )
        evidence_records.append(record)
        if content is not None:
            evidence_payloads[str(record["archive_member_path"])] = content

    blockers: list[str] = []
    if receipt_path_status != "Safe":
        blockers.append(receipt_path_note)
    archive_path = pipeline_archive_path.resolve(strict=False)
    if not archive_path.exists() or not archive_path.is_dir() or archive_path.is_symlink():
        blockers.append(
            "The sealed weekly pipeline archive path is missing, unreadable, or unsafe."
        )

    verification_json_content = evidence_payloads.get(VERIFICATION_JSON_FILENAME)
    verification_payload, verification_json_error = _read_verification_json(
        verification_json_content
    )
    if verification_json_error:
        blockers.append(verification_json_error)
    elif verification_payload:
        comparisons = (
            (
                "verification verdict",
                _clean(verification_payload.get("verdict")),
                _clean(verification_verdict),
            ),
            (
                "original receipt ID",
                _clean(verification_payload.get("original_receipt_id")),
                _clean(original_receipt_id),
            ),
            (
                "recalculated receipt ID",
                _clean(verification_payload.get("recalculated_receipt_id")),
                _clean(recalculated_receipt_id),
            ),
            (
                "mismatch count",
                str(int(verification_payload.get("mismatch_count", 0) or 0)),
                str(int(mismatch_count)),
            ),
        )
        for label, reported, supplied in comparisons:
            if reported != supplied:
                blockers.append(
                    f"The supplied {label} does not match the automatic verification JSON."
                )
        if not _same_path(verification_payload.get("archive_path"), archive_path):
            blockers.append(
                "The automatic verification JSON refers to a different pipeline archive."
            )

    missing_reports = any(
        record["status"] == "Missing" for record in evidence_records
    )
    unreadable_reports = any(
        record["status"] == "Unreadable" for record in evidence_records
    )
    receipt_ids_match = bool(
        _clean(pipeline_receipt_id)
        and _clean(pipeline_receipt_id) == _clean(original_receipt_id)
        and _clean(pipeline_receipt_id) == _clean(recalculated_receipt_id)
    )
    if not receipt_ids_match:
        blockers.append(
            "The pipeline, original, and recalculated receipt IDs do not all match."
        )

    if missing_reports:
        verdict = SIDECAR_MISSING_VERDICT
        sidecar_status = "Missing"
    elif unreadable_reports or verification_json_error:
        verdict = SIDECAR_FAILED_VERDICT
        sidecar_status = "Failed"
    elif receipt_path_status != "Safe":
        verdict = SIDECAR_NOT_READY_VERDICT
        sidecar_status = "Not ready"
    elif (
        verification_verdict == VERIFICATION_VERIFIED_VERDICT
        and verification_status == "Verified"
        and int(mismatch_count) == 0
        and receipt_ids_match
        and not blockers
    ):
        verdict = SIDECAR_ARCHIVED_VERDICT
        sidecar_status = "Archived"
    elif (
        verification_verdict == VERIFICATION_NOT_READY_VERDICT
        and verification_status == "Not ready"
        and int(mismatch_count) == 0
        and receipt_ids_match
        and not blockers
    ):
        verdict = SIDECAR_NOT_READY_VERDICT
        sidecar_status = "Not ready"
    else:
        verdict = SIDECAR_FAILED_VERDICT
        sidecar_status = "Failed"

    pipeline_archive_display = _display_path(archive_path, outputs)
    checksum, receipt_id = calculate_epl_weekly_pipeline_verification_sidecar_identity(
        pipeline_receipt_id=pipeline_receipt_id,
        pipeline_archive_path=pipeline_archive_display,
        verification_verdict=verification_verdict,
        verification_status=verification_status,
        original_receipt_id=original_receipt_id,
        recalculated_receipt_id=recalculated_receipt_id,
        mismatch_count=int(mismatch_count),
        sidecar_verdict=verdict,
        evidence_records=evidence_records,
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
            raise OSError(f"Archived verification evidence could not be verified: {target}")
        record["archived_path"] = _display_path(target, outputs)
        record["note"] = "Copied and checksum-verified in the sidecar archive."

    evidence = pd.DataFrame(evidence_records, columns=EVIDENCE_COLUMNS)
    summary: dict[str, object] = {
        "schema_version": 1,
        "archived_at": timestamp.isoformat(timespec="seconds"),
        "verdict": verdict,
        "status": sidecar_status,
        "pipeline_receipt_id": _clean(pipeline_receipt_id),
        "pipeline_receipt_path_status": receipt_path_status,
        "pipeline_receipt_path_note": receipt_path_note,
        "pipeline_archive_path": pipeline_archive_display,
        "verification_verdict": _clean(verification_verdict),
        "verification_status": _clean(verification_status),
        "original_receipt_id": _clean(original_receipt_id),
        "recalculated_receipt_id": _clean(recalculated_receipt_id),
        "mismatch_count": int(mismatch_count),
        "sidecar_receipt_id": receipt_id,
        "sidecar_receipt_checksum_sha256": checksum,
        "sidecar_archive_path": _display_path(archive_dir, outputs),
        "verification_report_count": sum(
            record["status"] == "Archived" for record in evidence_records
        ),
        "evidence_status_counts": dict(
            sorted(Counter(_clean(record["status"]) for record in evidence_records).items())
        ),
        "blockers": blockers,
        "evidence": evidence_records,
        "safety": {
            "sealed_pipeline_archive_modified": False,
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
        SIDECAR_JSON_FILENAME: (
            json.dumps(_json_safe(summary), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        SIDECAR_MARKDOWN_FILENAME: _render_markdown(summary, evidence).encode(
            "utf-8"
        ),
        SIDECAR_CSV_FILENAME: _render_csv(summary, evidence),
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
        "summary": summary,
        "evidence": evidence,
        "verdict": verdict,
        "json": latest_paths[SIDECAR_JSON_FILENAME],
        "markdown": latest_paths[SIDECAR_MARKDOWN_FILENAME],
        "csv": latest_paths[SIDECAR_CSV_FILENAME],
        "archive_dir": archive_dir,
        "archive_paths": archive_paths,
    }


def archive_latest_epl_weekly_pipeline_verification(
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

    archive_text = _clean(
        pipeline.get("archive_path") or pipeline.get("pipeline_archive_path")
    )
    if not archive_text:
        raise ValueError("The weekly pipeline summary does not identify its archive path.")
    return save_epl_weekly_pipeline_verification_sidecar(
        pipeline_archive_path=Path(archive_text),
        pipeline_receipt_id=_clean(
            pipeline.get("archive_receipt_id") or pipeline.get("pipeline_receipt_id")
        ),
        verification_paths={
            "json": outputs / VERIFICATION_JSON_FILENAME,
            "markdown": outputs / VERIFICATION_MARKDOWN_FILENAME,
            "csv": outputs / VERIFICATION_CSV_FILENAME,
        },
        verification_verdict=_clean(pipeline.get("receipt_verification_verdict")),
        verification_status=_clean(pipeline.get("receipt_verification_status")),
        original_receipt_id=_clean(
            pipeline.get("receipt_verification_original_id")
        ),
        recalculated_receipt_id=_clean(
            pipeline.get("receipt_verification_recalculated_id")
        ),
        mismatch_count=int(
            pipeline.get("receipt_verification_mismatch_count", 0) or 0
        ),
        output_dir=outputs,
        archived_at=archived_at,
    )


def list_recent_epl_weekly_pipeline_verification_sidecars(
    output_dir: Path | None = None,
    *,
    limit: int = 8,
) -> pd.DataFrame:
    if limit <= 0:
        return pd.DataFrame()
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    root = outputs / SIDECAR_ARCHIVE_ROOT
    rows: list[dict[str, object]] = []
    for path in root.glob(f"*/*/{SIDECAR_JSON_FILENAME}"):
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
                "pipeline_receipt_id": payload.get("pipeline_receipt_id", ""),
                "sidecar_receipt_id": payload.get("sidecar_receipt_id", ""),
                "verification_verdict": payload.get("verification_verdict", ""),
                "mismatch_count": int(payload.get("mismatch_count", 0) or 0),
                "archive_path": payload.get("sidecar_archive_path", ""),
            }
        )
    rows.sort(key=lambda row: (_clean(row["archived_at"]), _clean(row["archive_path"])))
    return pd.DataFrame(list(reversed(rows[-limit:])))
