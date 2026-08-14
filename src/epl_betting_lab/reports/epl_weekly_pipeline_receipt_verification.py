from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Mapping

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import atomic_write_report, file_sha256, sha256_bytes
from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    PIPELINE_ARCHIVE_CSV_FILENAME,
    PIPELINE_ARCHIVE_JSON_FILENAME,
    PIPELINE_ARCHIVE_MARKDOWN_FILENAME,
    PIPELINE_ARCHIVE_ROOT,
    calculate_epl_weekly_pipeline_receipt_identity,
    render_epl_weekly_pipeline_archive_csv,
    render_epl_weekly_pipeline_archive_receipt,
)


VERIFICATION_JSON_FILENAME = "epl_weekly_pipeline_receipt_verification.json"
VERIFICATION_MARKDOWN_FILENAME = "epl_weekly_pipeline_receipt_verification.md"
VERIFICATION_CSV_FILENAME = "epl_weekly_pipeline_receipt_verification.csv"

VERIFICATION_STATUSES = (
    "Verified",
    "Missing archive",
    "Missing file",
    "Checksum mismatch",
    "Receipt ID mismatch",
    "Malformed archive",
    "Referenced report changed",
    "Not applicable",
)
FINAL_VERDICTS = (
    "Weekly pipeline receipt verified",
    "Weekly pipeline receipt changed",
    "Missing weekly pipeline archive",
    "Malformed weekly pipeline archive",
    "Weekly pipeline receipt not ready",
)
READY_PIPELINE_STATUSES = {
    "Ready for card review",
    "Card generated with warnings",
}
REQUIRED_ARCHIVE_FILES = (
    "epl_weekly_pipeline.json",
    "epl_weekly_pipeline.md",
    "epl_weekly_pipeline.csv",
    PIPELINE_ARCHIVE_JSON_FILENAME,
    PIPELINE_ARCHIVE_MARKDOWN_FILENAME,
    PIPELINE_ARCHIVE_CSV_FILENAME,
)
REQUIRED_MANIFEST_FIELDS = (
    "receipt_id",
    "receipt_checksum_sha256",
    "run_timestamp",
    "status",
    "summary_snapshot",
    "report_inventory",
    "pipeline_files",
)


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _json_safe(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is pd.NA:
        return None
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (AttributeError, TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _canonical(value: object) -> str:
    return json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted(_clean(item) for item in value if _clean(item))


def _normalized_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key, raw_value in value.items():
        try:
            counts[str(key)] = int(raw_value or 0)
        except (TypeError, ValueError):
            counts[str(key)] = 0
    return dict(sorted(counts.items()))


def _normalized_steps(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    steps: list[dict[str, object]] = []
    for row in value:
        if not isinstance(row, Mapping):
            continue
        steps.append(
            {
                "step": _clean(row.get("step")),
                "status": _clean(row.get("status")),
                "warnings": _string_list(row.get("warnings")),
                "blockers": _string_list(row.get("blockers")),
            }
        )
    return steps


def _add_check(
    checks: list[dict[str, object]],
    *,
    category: str,
    item: str,
    status: str,
    expected: object = "",
    actual: object = "",
    note: str = "",
) -> None:
    if status not in VERIFICATION_STATUSES:
        raise ValueError(f"Unexpected receipt verification status: {status}")
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


def _latest_archive_dir(output_dir: Path) -> Path | None:
    root = output_dir / PIPELINE_ARCHIVE_ROOT
    if not root.exists():
        return None
    candidates = sorted(path for path in root.glob("*/*") if path.is_dir())
    return candidates[-1] if candidates else None


def _resolve_archive_dir(
    archive_path: Path | None,
    output_dir: Path,
) -> tuple[Path | None, str]:
    if archive_path is None:
        latest = _latest_archive_dir(output_dir)
        if latest is None:
            return None, "No archived EPL weekly pipeline runs were found."
        return latest.resolve(), "Latest archived weekly pipeline run selected."

    candidate = archive_path
    if not candidate.is_absolute():
        project_candidate = PROJECT_ROOT / candidate
        output_candidate = output_dir / candidate
        candidate = project_candidate if project_candidate.exists() else output_candidate
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        return None, f"Archive path could not be resolved: {exc}"
    if resolved.name == PIPELINE_ARCHIVE_JSON_FILENAME:
        resolved = resolved.parent
    return resolved, "Provided archive path selected."


def _archive_output_dir(archive_dir: Path, fallback: Path) -> Path:
    for parent in archive_dir.parents:
        if parent.name == "archive":
            return parent.parent.resolve()
    return fallback.resolve()


def _safe_member(archive_dir: Path, value: object) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    candidate = archive_dir / text
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(archive_dir.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _safe_reference(output_dir: Path, value: object) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(output_dir.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _check_markdown(path: Path) -> tuple[bool, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return False, f"Markdown could not be read: {exc}"
    if not text.strip():
        return False, "Markdown is empty."
    if not text.lstrip().startswith("#"):
        return False, "Markdown does not start with a heading."
    return True, "Markdown is readable and non-empty."


def _check_csv(path: Path) -> tuple[bool, str]:
    try:
        frame = pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        return False, f"CSV could not be read: {exc}"
    if not list(frame.columns):
        return False, "CSV has no columns."
    return True, f"CSV is readable with {len(frame)} row(s)."


def _missing_archive_summary(
    archive_path: Path | None,
    note: str,
    generated_at: datetime,
) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    _add_check(
        checks,
        category="Archive",
        item="archive_path",
        status="Missing archive",
        expected="Existing archived weekly pipeline folder",
        actual=str(archive_path or ""),
        note=note,
    )
    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "verdict": "Missing weekly pipeline archive",
        "archive_path": str(archive_path or ""),
        "original_receipt_id": "",
        "recalculated_receipt_id": "",
        "original_receipt_checksum_sha256": "",
        "recalculated_receipt_checksum_sha256": "",
        "pipeline_status": "",
        "comparison_verdict": "",
        "mismatch_count": 1,
        "blockers": [note],
        "checks": checks,
        "safety": _safety_summary(),
    }


def _safety_summary() -> dict[str, bool]:
    return {
        "manual_files_edited": False,
        "odds_imported": False,
        "settlement_applied": False,
        "staging_promoted": False,
        "live_provider_run": False,
        "provider_allowlisted": False,
        "cron_enabled": False,
        "bets_placed": False,
    }


def _verify_required_files(
    archive_dir: Path,
    checks: list[dict[str, object]],
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for filename in REQUIRED_ARCHIVE_FILES:
        path = archive_dir / filename
        paths[filename] = path
        _add_check(
            checks,
            category="Archive file",
            item=filename,
            status="Verified" if path.is_file() else "Missing file",
            expected="Regular file",
            actual="Present" if path.is_file() else "Missing",
            note=(
                "Required archive file exists."
                if path.is_file()
                else "The archived receipt is incomplete."
            ),
        )
    return paths


def _verify_formats(
    paths: Mapping[str, Path],
    checks: list[dict[str, object]],
) -> tuple[dict[str, object] | None, bool]:
    pipeline_json: dict[str, object] | None = None
    malformed = False
    for filename in ("epl_weekly_pipeline.json",):
        path = paths[filename]
        if not path.is_file():
            continue
        pipeline_json, note = _read_json(path)
        status = "Verified" if pipeline_json is not None else "Malformed archive"
        malformed = malformed or pipeline_json is None
        _add_check(
            checks,
            category="File format",
            item=filename,
            status=status,
            expected="Readable JSON object",
            actual="Readable" if pipeline_json is not None else "Malformed",
            note=note or "Archived pipeline JSON is readable.",
        )

    for filename in ("epl_weekly_pipeline.md", PIPELINE_ARCHIVE_MARKDOWN_FILENAME):
        path = paths[filename]
        if not path.is_file():
            continue
        valid, note = _check_markdown(path)
        malformed = malformed or not valid
        _add_check(
            checks,
            category="File format",
            item=filename,
            status="Verified" if valid else "Malformed archive",
            expected="Readable non-empty markdown",
            actual="Readable" if valid else "Malformed",
            note=note,
        )

    for filename in ("epl_weekly_pipeline.csv", PIPELINE_ARCHIVE_CSV_FILENAME):
        path = paths[filename]
        if not path.is_file():
            continue
        valid, note = _check_csv(path)
        malformed = malformed or not valid
        _add_check(
            checks,
            category="File format",
            item=filename,
            status="Verified" if valid else "Malformed archive",
            expected="Readable CSV",
            actual="Readable" if valid else "Malformed",
            note=note,
        )
    return pipeline_json, malformed


def _records_by_key(value: object, key: str) -> dict[str, Mapping[str, object]]:
    if not isinstance(value, list):
        return {}
    return {
        _clean(row.get(key)): row
        for row in value
        if isinstance(row, Mapping) and _clean(row.get(key))
    }


def _verify_pipeline_checksums(
    archive_dir: Path,
    manifest: Mapping[str, object],
    checks: list[dict[str, object]],
) -> None:
    records = _records_by_key(manifest.get("pipeline_files"), "path")
    for filename in (
        "epl_weekly_pipeline.json",
        "epl_weekly_pipeline.md",
        "epl_weekly_pipeline.csv",
    ):
        record = records.get(filename)
        path = archive_dir / filename
        if record is None:
            _add_check(
                checks,
                category="Archived checksum",
                item=filename,
                status="Missing file",
                expected="Recorded checksum entry",
                actual="Missing",
                note="The manifest does not bind this required pipeline file.",
            )
            continue
        if not path.is_file():
            continue
        expected = _clean(record.get("checksum_sha256"))
        try:
            actual = file_sha256(path)
        except OSError as exc:
            _add_check(
                checks,
                category="Archived checksum",
                item=filename,
                status="Missing file",
                expected=expected,
                actual="Unreadable",
                note=f"Archived file could not be hashed: {exc}",
            )
            continue
        _add_check(
            checks,
            category="Archived checksum",
            item=filename,
            status="Verified" if expected and actual == expected else "Checksum mismatch",
            expected=expected or "Recorded SHA-256 checksum",
            actual=actual,
            note=(
                "Archived pipeline file matches its receipt checksum."
                if expected and actual == expected
                else "Archived pipeline file changed after the receipt was written."
            ),
        )


def _verify_derived_archive_views(
    paths: Mapping[str, Path],
    manifest: Mapping[str, object],
    checks: list[dict[str, object]],
) -> None:
    expected_payloads = {
        PIPELINE_ARCHIVE_MARKDOWN_FILENAME: (
            render_epl_weekly_pipeline_archive_receipt(manifest) + "\n"
        ).encode("utf-8"),
        PIPELINE_ARCHIVE_CSV_FILENAME: render_epl_weekly_pipeline_archive_csv(
            manifest
        ),
    }
    for filename, expected_content in expected_payloads.items():
        path = paths[filename]
        if not path.is_file():
            continue
        expected_checksum = sha256_bytes(expected_content)
        try:
            actual_checksum = file_sha256(path)
        except OSError as exc:
            _add_check(
                checks,
                category="Derived archive view",
                item=filename,
                status="Missing file",
                expected=expected_checksum,
                actual="Unreadable",
                note=f"Derived archive view could not be hashed: {exc}",
            )
            continue
        matches = actual_checksum == expected_checksum
        _add_check(
            checks,
            category="Derived archive view",
            item=filename,
            status="Verified" if matches else "Checksum mismatch",
            expected=expected_checksum,
            actual=actual_checksum,
            note=(
                "Archive view matches the receipt manifest."
                if matches
                else "Archive view changed after it was rendered from the receipt manifest."
            ),
        )


def _verify_archived_reports(
    archive_dir: Path,
    manifest: Mapping[str, object],
    output_dir: Path,
    checks: list[dict[str, object]],
) -> None:
    inventory = _records_by_key(manifest.get("report_inventory"), "path")
    archived = _records_by_key(manifest.get("archived_reports"), "source_path")
    for source_path, inventory_row in sorted(inventory.items()):
        expected = _clean(inventory_row.get("checksum_sha256"))
        inventory_status = _clean(inventory_row.get("status"))
        if inventory_status != "Included" or not expected:
            _add_check(
                checks,
                category="Archived report",
                item=source_path,
                status="Not applicable",
                expected=expected,
                actual=inventory_status or "Not included",
                note="This report was not checksum-bound as an available report.",
            )
            continue
        archived_row = archived.get(source_path)
        if archived_row is None:
            _add_check(
                checks,
                category="Archived report",
                item=source_path,
                status="Missing file",
                expected=expected,
                actual="Missing archive record",
                note="A checksum-bound report has no archived copy record.",
            )
        else:
            archived_path = _safe_member(archive_dir, archived_row.get("archive_path"))
            if archived_path is None or not archived_path.is_file():
                _add_check(
                    checks,
                    category="Archived report",
                    item=source_path,
                    status="Missing file",
                    expected=expected,
                    actual=_clean(archived_row.get("archive_path")) or "Missing",
                    note="The archived report copy is missing or uses an unsafe path.",
                )
            else:
                try:
                    actual = file_sha256(archived_path)
                except OSError as exc:
                    _add_check(
                        checks,
                        category="Archived report",
                        item=source_path,
                        status="Missing file",
                        expected=expected,
                        actual="Unreadable",
                        note=f"Archived report could not be hashed: {exc}",
                    )
                else:
                    recorded_archive_checksum = _clean(
                        archived_row.get("checksum_sha256")
                    )
                    matches = actual == expected == recorded_archive_checksum
                    _add_check(
                        checks,
                        category="Archived report",
                        item=source_path,
                        status="Verified" if matches else "Checksum mismatch",
                        expected=expected,
                        actual=actual,
                        note=(
                            "Archived report matches the receipt inventory."
                            if matches
                            else "Archived report no longer matches its bound checksum."
                        ),
                    )

        current_path = _safe_reference(output_dir, source_path)
        if current_path is None:
            _add_check(
                checks,
                category="Referenced report",
                item=source_path,
                status="Not applicable",
                expected=expected,
                actual="Unsafe or unavailable path",
                note="Only report paths inside the output directory are checked.",
            )
        elif not current_path.is_file():
            _add_check(
                checks,
                category="Referenced report",
                item=source_path,
                status="Not applicable",
                expected=expected,
                actual="No current file",
                note="The original report path no longer exists; the archived copy remains checked.",
            )
        else:
            try:
                current_checksum = file_sha256(current_path)
            except OSError as exc:
                _add_check(
                    checks,
                    category="Referenced report",
                    item=source_path,
                    status="Referenced report changed",
                    expected=expected,
                    actual="Unreadable",
                    note=f"Current referenced report could not be hashed: {exc}",
                )
            else:
                matches = current_checksum == expected
                _add_check(
                    checks,
                    category="Referenced report",
                    item=source_path,
                    status="Verified" if matches else "Referenced report changed",
                    expected=expected,
                    actual=current_checksum,
                    note=(
                        "Current referenced report still matches this receipt."
                        if matches
                        else "The report at the original path changed after this run was archived."
                    ),
                )


def _field_check(
    checks: list[dict[str, object]],
    *,
    item: str,
    expected: object,
    actual: object,
    note: str,
) -> None:
    matches = _canonical(expected) == _canonical(actual)
    _add_check(
        checks,
        category="Receipt field",
        item=item,
        status="Verified" if matches else "Checksum mismatch",
        expected=expected,
        actual=actual,
        note=note if matches else f"{note} The archived values do not agree.",
    )


def _verify_bound_fields(
    manifest: Mapping[str, object],
    pipeline: Mapping[str, object],
    checks: list[dict[str, object]],
) -> None:
    snapshot = manifest.get("summary_snapshot", {})
    if not isinstance(snapshot, Mapping):
        _add_check(
            checks,
            category="Receipt field",
            item="summary_snapshot",
            status="Malformed archive",
            expected="JSON object",
            actual=type(snapshot).__name__,
            note="The receipt snapshot is not a JSON object.",
        )
        return
    _field_check(
        checks,
        item="final_status_manifest_snapshot",
        expected=_clean(manifest.get("status")),
        actual=_clean(snapshot.get("status")),
        note="Manifest status matches the receipt snapshot.",
    )
    _field_check(
        checks,
        item="final_status_snapshot_pipeline",
        expected=_clean(snapshot.get("status")),
        actual=_clean(pipeline.get("status")),
        note="Receipt snapshot status matches the archived pipeline summary.",
    )
    _field_check(
        checks,
        item="run_timestamp",
        expected=_clean(manifest.get("run_timestamp")),
        actual=_clean(pipeline.get("run_timestamp")),
        note="Manifest and archived pipeline run timestamps agree.",
    )
    _field_check(
        checks,
        item="step_outcomes",
        expected=_normalized_steps(snapshot.get("steps")),
        actual=_normalized_steps(pipeline.get("steps")),
        note="Archived step outcomes match the receipt snapshot.",
    )
    _field_check(
        checks,
        item="blocker_list",
        expected=_string_list(snapshot.get("key_blockers")),
        actual=_string_list(pipeline.get("key_blockers")),
        note="Archived blockers match the receipt snapshot.",
    )
    _field_check(
        checks,
        item="card_counts",
        expected=_normalized_counts(snapshot.get("card_counts")),
        actual=_normalized_counts(pipeline.get("card_counts")),
        note="Archived best-bet, lean, pass, and total counts match.",
    )
    _field_check(
        checks,
        item="decision_queue_counts",
        expected=_normalized_counts(snapshot.get("decision_queue_counts")),
        actual=_normalized_counts(pipeline.get("decision_queue_counts")),
        note="Archived decision queue counts match the receipt snapshot.",
    )
    _field_check(
        checks,
        item="ledger_health_summary",
        expected=snapshot.get("ledger_health_summary", {}),
        actual=pipeline.get("ledger_health_summary", {}),
        note="Archived ledger health matches the receipt snapshot.",
    )
    _field_check(
        checks,
        item="comparison_verdict",
        expected=_clean(manifest.get("comparison_verdict")),
        actual=_clean(pipeline.get("pipeline_comparison_verdict")),
        note="Archived comparison verdict matches the pipeline summary.",
    )
    _field_check(
        checks,
        item="comparison_changes",
        expected=manifest.get("important_changes", []),
        actual=pipeline.get("important_changes_since_previous_run", []),
        note="Archived important comparison changes match the pipeline summary.",
    )


def _receipt_source(
    manifest: Mapping[str, object],
    pipeline: Mapping[str, object],
) -> dict[str, object]:
    return {
        "run_timestamp": pipeline.get("run_timestamp", manifest.get("run_timestamp", "")),
        "status": pipeline.get("status", ""),
        "steps": pipeline.get("steps", []),
        "key_blockers": pipeline.get("key_blockers", []),
        "card_counts": pipeline.get("card_counts", {}),
        "decision_queue_counts": pipeline.get("decision_queue_counts", {}),
        "ledger_health_summary": pipeline.get("ledger_health_summary", {}),
        "recommended_next_action": pipeline.get("recommended_next_action", ""),
    }


def build_epl_weekly_pipeline_receipt_verification(
    *,
    archive_path: Path | None = None,
    output_dir: Path | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Verify one archived pipeline receipt without changing any source input."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    now = generated_at or datetime.now().astimezone()
    archive_dir, selection_note = _resolve_archive_dir(archive_path, outputs)
    if archive_dir is None or not archive_dir.is_dir():
        return _missing_archive_summary(archive_dir, selection_note, now)

    checks: list[dict[str, object]] = []
    _add_check(
        checks,
        category="Archive",
        item="archive_path",
        status="Verified",
        expected="Existing archived weekly pipeline folder",
        actual=str(archive_dir),
        note=selection_note,
    )
    paths = _verify_required_files(archive_dir, checks)
    manifest_path = paths[PIPELINE_ARCHIVE_JSON_FILENAME]
    manifest, manifest_note = _read_json(manifest_path)
    malformed = False
    if manifest is None:
        malformed = manifest_path.is_file()
        _add_check(
            checks,
            category="File format",
            item=PIPELINE_ARCHIVE_JSON_FILENAME,
            status="Malformed archive" if manifest_path.is_file() else "Missing file",
            expected="Readable archive receipt JSON object",
            actual="Malformed" if manifest_path.is_file() else "Missing",
            note=manifest_note,
        )
    else:
        _add_check(
            checks,
            category="File format",
            item=PIPELINE_ARCHIVE_JSON_FILENAME,
            status="Verified",
            expected="Readable archive receipt JSON object",
            actual="Readable",
            note="Archive receipt JSON is readable.",
        )

    pipeline, format_malformed = _verify_formats(paths, checks)
    malformed = malformed or format_malformed
    if manifest is None:
        verdict = (
            "Malformed weekly pipeline archive"
            if malformed
            else "Missing weekly pipeline archive"
        )
        blockers = [
            _clean(row.get("note"))
            for row in checks
            if row.get("status") not in {"Verified", "Not applicable"}
        ]
        return {
            "schema_version": 1,
            "generated_at": now.isoformat(timespec="seconds"),
            "verdict": verdict,
            "archive_path": str(archive_dir),
            "original_receipt_id": "",
            "recalculated_receipt_id": "",
            "original_receipt_checksum_sha256": "",
            "recalculated_receipt_checksum_sha256": "",
            "pipeline_status": "",
            "comparison_verdict": "",
            "mismatch_count": len(blockers),
            "blockers": blockers,
            "checks": checks,
            "safety": _safety_summary(),
        }

    missing_fields = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    _add_check(
        checks,
        category="Receipt structure",
        item="required_manifest_fields",
        status="Verified" if not missing_fields else "Malformed archive",
        expected=list(REQUIRED_MANIFEST_FIELDS),
        actual=[field for field in REQUIRED_MANIFEST_FIELDS if field in manifest],
        note=(
            "All required receipt fields are present."
            if not missing_fields
            else "Missing receipt field(s): " + ", ".join(missing_fields)
        ),
    )
    malformed = malformed or bool(missing_fields)
    type_errors = []
    for field, expected_type in (
        ("summary_snapshot", Mapping),
        ("report_inventory", list),
        ("pipeline_files", list),
    ):
        if field in manifest and not isinstance(manifest.get(field), expected_type):
            type_errors.append(field)
    inventory = manifest.get("report_inventory")
    if isinstance(inventory, list) and any(
        not isinstance(row, Mapping) for row in inventory
    ):
        type_errors.append("report_inventory entries")
    pipeline_files = manifest.get("pipeline_files")
    if isinstance(pipeline_files, list) and any(
        not isinstance(row, Mapping) for row in pipeline_files
    ):
        type_errors.append("pipeline_files entries")
    _add_check(
        checks,
        category="Receipt structure",
        item="manifest_field_types",
        status="Verified" if not type_errors else "Malformed archive",
        expected="summary_snapshot object; report_inventory and pipeline_files arrays",
        actual="Valid" if not type_errors else ", ".join(type_errors),
        note=(
            "Required receipt fields use the expected JSON types."
            if not type_errors
            else "Malformed receipt field type(s): " + ", ".join(type_errors)
        ),
    )
    malformed = malformed or bool(type_errors)

    _verify_pipeline_checksums(archive_dir, manifest, checks)
    _verify_derived_archive_views(paths, manifest, checks)
    source_output_dir = _archive_output_dir(archive_dir, outputs)
    _verify_archived_reports(
        archive_dir,
        manifest,
        source_output_dir,
        checks,
    )

    original_receipt_id = _clean(manifest.get("receipt_id"))
    original_receipt_checksum = _clean(manifest.get("receipt_checksum_sha256"))
    recalculated_receipt_id = ""
    recalculated_receipt_checksum = ""
    if pipeline is not None and not missing_fields and not type_errors:
        _verify_bound_fields(manifest, pipeline, checks)
        recalculated_receipt_checksum, recalculated_receipt_id = (
            calculate_epl_weekly_pipeline_receipt_identity(
                _receipt_source(manifest, pipeline),
                manifest.get("report_inventory", []),
            )
        )
        checksum_matches = (
            bool(original_receipt_checksum)
            and original_receipt_checksum == recalculated_receipt_checksum
        )
        _add_check(
            checks,
            category="Receipt identity",
            item="receipt_checksum_sha256",
            status="Verified" if checksum_matches else "Checksum mismatch",
            expected=original_receipt_checksum or "Recorded receipt checksum",
            actual=recalculated_receipt_checksum,
            note=(
                "Canonical receipt checksum matches."
                if checksum_matches
                else "Canonical receipt content changed or its checksum was altered."
            ),
        )
        receipt_matches = (
            bool(original_receipt_id) and original_receipt_id == recalculated_receipt_id
        )
        _add_check(
            checks,
            category="Receipt identity",
            item="receipt_id",
            status="Verified" if receipt_matches else "Receipt ID mismatch",
            expected=original_receipt_id or "Recorded receipt ID",
            actual=recalculated_receipt_id,
            note=(
                "Deterministic pipeline receipt ID matches."
                if receipt_matches
                else "The archived receipt ID does not match recalculated run content."
            ),
        )
        _field_check(
            checks,
            item="pipeline_receipt_id",
            expected=original_receipt_id,
            actual=_clean(pipeline.get("pipeline_receipt_id")),
            note="Archived pipeline JSON names the same receipt ID.",
        )
        _field_check(
            checks,
            item="pipeline_receipt_checksum",
            expected=original_receipt_checksum,
            actual=_clean(pipeline.get("pipeline_receipt_checksum_sha256")),
            note="Archived pipeline JSON names the same receipt checksum.",
        )

    pipeline_status = _clean(
        pipeline.get("status") if pipeline is not None else manifest.get("status")
    )
    comparison_verdict = _clean(manifest.get("comparison_verdict"))
    _add_check(
        checks,
        category="Review readiness",
        item="pipeline_status",
        status="Verified" if pipeline_status in READY_PIPELINE_STATUSES else "Not applicable",
        expected=sorted(READY_PIPELINE_STATUSES),
        actual=pipeline_status or "Missing",
        note=(
            "Pipeline status is eligible for manual card review."
            if pipeline_status in READY_PIPELINE_STATUSES
            else "Receipt integrity can be checked, but this pipeline run was not ready for card review."
        ),
    )

    blocking_checks = [
        row
        for row in checks
        if row.get("status") not in {"Verified", "Not applicable"}
    ]
    statuses = {_clean(row.get("status")) for row in blocking_checks}
    if "Malformed archive" in statuses or malformed:
        verdict = "Malformed weekly pipeline archive"
    elif "Missing archive" in statuses:
        verdict = "Missing weekly pipeline archive"
    elif blocking_checks:
        verdict = "Weekly pipeline receipt changed"
    elif pipeline_status not in READY_PIPELINE_STATUSES:
        verdict = "Weekly pipeline receipt not ready"
    else:
        verdict = "Weekly pipeline receipt verified"
    if verdict not in FINAL_VERDICTS:
        raise ValueError(f"Unexpected receipt verification verdict: {verdict}")

    blockers = [
        f"{row['item']}: {row['note']}"
        for row in blocking_checks
        if _clean(row.get("note"))
    ]
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "verdict": verdict,
        "archive_path": str(archive_dir),
        "original_receipt_id": original_receipt_id,
        "recalculated_receipt_id": recalculated_receipt_id,
        "original_receipt_checksum_sha256": original_receipt_checksum,
        "recalculated_receipt_checksum_sha256": recalculated_receipt_checksum,
        "pipeline_status": pipeline_status,
        "comparison_verdict": comparison_verdict,
        "mismatch_count": len(blocking_checks),
        "blockers": blockers,
        "checks": checks,
        "safety": _safety_summary(),
    }


def render_epl_weekly_pipeline_receipt_verification(
    summary: Mapping[str, object],
) -> str:
    checks = pd.DataFrame(summary.get("checks", []))
    lines = [
        "# EPL Weekly Pipeline Receipt Verification",
        "",
        "This checker only reads archived and referenced report files and writes verification reports. Nothing was applied.",
        "",
        f"- Archive path: `{summary.get('archive_path') or 'Not available'}`",
        f"- Final verdict: **{summary.get('verdict', '')}**",
        f"- Original receipt ID: `{summary.get('original_receipt_id') or 'Not available'}`",
        f"- Recalculated receipt ID: `{summary.get('recalculated_receipt_id') or 'Not available'}`",
        f"- Final pipeline status: {summary.get('pipeline_status') or 'Not available'}",
        f"- Comparison verdict: {summary.get('comparison_verdict') or 'Not available'}",
        f"- Mismatch/blocker count: {int(summary.get('mismatch_count', 0) or 0)}",
        "",
        "## Verification table",
        "",
    ]
    if checks.empty:
        lines.append("No verification checks were available.")
    else:
        lines.append(checks.to_markdown(index=False))
    lines.extend(["", "## Mismatches and blockers", ""])
    lines.extend(
        [f"- {item}" for item in summary.get("blockers", [])]
        or ["- None."]
    )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "Verification does not import odds, edit manual files, run live providers, apply settlement, promote staging, allowlist providers, enable cron, fabricate odds, place bets, or change model logic.",
        ]
    )
    return "\n".join(lines)


def save_epl_weekly_pipeline_receipt_verification(
    *,
    archive_path: Path | None = None,
    output_dir: Path | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    outputs.mkdir(parents=True, exist_ok=True)
    summary = build_epl_weekly_pipeline_receipt_verification(
        archive_path=archive_path,
        output_dir=outputs,
        generated_at=generated_at,
    )
    paths = {
        "json": outputs / VERIFICATION_JSON_FILENAME,
        "markdown": outputs / VERIFICATION_MARKDOWN_FILENAME,
        "csv": outputs / VERIFICATION_CSV_FILENAME,
    }
    atomic_write_report(
        paths["json"],
        (json.dumps(_json_safe(summary), indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )
    atomic_write_report(
        paths["markdown"],
        (render_epl_weekly_pipeline_receipt_verification(summary) + "\n").encode(
            "utf-8"
        ),
    )
    atomic_write_report(
        paths["csv"],
        pd.DataFrame(summary["checks"]).to_csv(index=False).encode("utf-8"),
    )
    return {"summary": summary, "verdict": summary["verdict"], **paths}
