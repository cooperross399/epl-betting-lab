from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.providers.base import atomic_write_report, file_sha256


PIPELINE_ARCHIVE_ROOT = Path("archive/epl_weekly_pipeline")
PIPELINE_ARCHIVE_JSON_FILENAME = "epl_weekly_pipeline_archive.json"
PIPELINE_ARCHIVE_MARKDOWN_FILENAME = "epl_weekly_pipeline_archive.md"
PIPELINE_ARCHIVE_CSV_FILENAME = "epl_weekly_pipeline_archive.csv"
PIPELINE_COMPARISON_JSON_FILENAME = "epl_weekly_pipeline_comparison.json"
PIPELINE_COMPARISON_MARKDOWN_FILENAME = "epl_weekly_pipeline_comparison.md"
PIPELINE_COMPARISON_CSV_FILENAME = "epl_weekly_pipeline_comparison.csv"

PIPELINE_REPORT_FILENAMES = (
    "epl_weekly_pipeline.json",
    "epl_weekly_pipeline.md",
    "epl_weekly_pipeline.csv",
)
HISTORY_REPORT_FILENAMES = {
    PIPELINE_ARCHIVE_JSON_FILENAME,
    PIPELINE_ARCHIVE_MARKDOWN_FILENAME,
    PIPELINE_ARCHIVE_CSV_FILENAME,
    PIPELINE_COMPARISON_JSON_FILENAME,
    PIPELINE_COMPARISON_MARKDOWN_FILENAME,
    PIPELINE_COMPARISON_CSV_FILENAME,
}
COMPARISON_VERDICTS = (
    "Stable ready state",
    "Improved",
    "New blockers",
    "More review needed",
    "Missing prior run",
    "Failed",
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


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _parse_datetime(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _display_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(output_dir.resolve()).as_posix()
    except ValueError:
        return str(path.resolve(strict=False))


def _is_history_path(path: Path, output_dir: Path) -> bool:
    if path.name in HISTORY_REPORT_FILENAMES or path.name in PIPELINE_REPORT_FILENAMES:
        return True
    try:
        relative = path.resolve(strict=False).relative_to(output_dir.resolve())
    except ValueError:
        return False
    return relative.parts[:2] == ("archive", "epl_weekly_pipeline")


def _safe_report_path(value: object, output_dir: Path) -> tuple[Path | None, str]:
    text = _clean(value)
    if not text:
        return None, "Report path is blank."
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(output_dir.resolve())
    except (OSError, RuntimeError, ValueError):
        return None, "Report path is outside the selected output directory."
    if resolved.is_symlink():
        return None, "Symlinked report paths are not archived."
    return resolved, ""


def build_pipeline_report_inventory(
    summary: Mapping[str, object],
    output_dir: Path | None = None,
) -> tuple[list[dict[str, object]], dict[str, Path]]:
    """Hash safe report outputs referenced by one pipeline summary."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    raw_paths = summary.get("generated_report_paths", [])
    values = list(raw_paths) if isinstance(raw_paths, (list, tuple)) else []
    for filename in ("current_odds_validation.csv", "current_odds_completeness.csv"):
        candidate = outputs / filename
        if candidate.exists():
            values.append(str(candidate))

    records: list[dict[str, object]] = []
    sources: dict[str, Path] = {}
    seen: set[str] = set()
    for value in values:
        path, path_note = _safe_report_path(value, outputs)
        if path is None:
            key = _clean(value) or "Missing path"
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "path": key,
                    "status": "Missing",
                    "checksum_sha256": "",
                    "size_bytes": 0,
                    "note": path_note,
                }
            )
            continue
        if _is_history_path(path, outputs):
            continue
        display = _display_path(path, outputs)
        if display in seen:
            continue
        seen.add(display)
        if not path.exists():
            records.append(
                {
                    "path": display,
                    "status": "Missing",
                    "checksum_sha256": "",
                    "size_bytes": 0,
                    "note": "The referenced report did not exist when the receipt was built.",
                }
            )
            continue
        if not path.is_file():
            records.append(
                {
                    "path": display,
                    "status": "Missing",
                    "checksum_sha256": "",
                    "size_bytes": 0,
                    "note": "The referenced path is not a regular file.",
                }
            )
            continue
        try:
            checksum = file_sha256(path)
            size = path.stat().st_size
        except OSError as exc:
            records.append(
                {
                    "path": display,
                    "status": "Missing",
                    "checksum_sha256": "",
                    "size_bytes": 0,
                    "note": f"The referenced report could not be read: {exc}",
                }
            )
            continue
        records.append(
            {
                "path": display,
                "status": "Included",
                "checksum_sha256": checksum,
                "size_bytes": int(size),
                "note": "Checksum recorded before the archive copy was written.",
            }
        )
        sources[display] = path

    records.sort(key=lambda row: _clean(row.get("path")))
    return records, sources


def _normalized_steps(summary: Mapping[str, object]) -> list[dict[str, object]]:
    steps = summary.get("steps", [])
    if not isinstance(steps, list):
        return []
    normalized = []
    for row in steps:
        if not isinstance(row, Mapping):
            continue
        normalized.append(
            {
                "step": _clean(row.get("step")),
                "status": _clean(row.get("status")),
                "warnings": sorted(_clean(item) for item in row.get("warnings", []) if _clean(item)),
                "blockers": sorted(_clean(item) for item in row.get("blockers", []) if _clean(item)),
            }
        )
    return normalized


def _normalized_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, raw_value in value.items():
        try:
            result[str(key)] = int(raw_value or 0)
        except (TypeError, ValueError):
            result[str(key)] = 0
    return dict(sorted(result.items()))


def _receipt_payload(
    summary: Mapping[str, object],
    report_inventory: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_timestamp": _clean(summary.get("run_timestamp")),
        "status": _clean(summary.get("status")),
        "step_outcomes": _normalized_steps(summary),
        "key_blockers": sorted(
            _clean(item) for item in summary.get("key_blockers", []) if _clean(item)
        ),
        "generated_reports": [
            {
                "path": _clean(row.get("path")),
                "status": _clean(row.get("status")),
                "checksum_sha256": _clean(row.get("checksum_sha256")),
            }
            for row in sorted(report_inventory, key=lambda item: _clean(item.get("path")))
        ],
        "card_counts": _normalized_counts(summary.get("card_counts")),
        "decision_queue_counts": _normalized_counts(
            summary.get("decision_queue_counts")
        ),
        "ledger_health_summary": _json_safe(
            summary.get("ledger_health_summary", {})
        ),
        "recommended_next_action": _clean(
            summary.get("recommended_next_action")
        ),
    }


def calculate_epl_weekly_pipeline_receipt_identity(
    summary: Mapping[str, object],
    report_inventory: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    """Return deterministic checksum and receipt ID for one pipeline run."""
    checksum = sha256(_canonical_json(_receipt_payload(summary, report_inventory))).hexdigest()
    return checksum, f"epl-weekly-{checksum[:24]}"


def _report_checksum(
    report_inventory: Sequence[Mapping[str, object]], filename: str
) -> str:
    for row in report_inventory:
        if Path(_clean(row.get("path"))).name == filename:
            return _clean(row.get("checksum_sha256"))
    return ""


def _unique_archive_dir(output_dir: Path, run_at: datetime) -> Path:
    date_dir = output_dir / PIPELINE_ARCHIVE_ROOT / run_at.strftime("%Y-%m-%d")
    stem = run_at.strftime("%H%M%S")
    candidate = date_dir / stem
    suffix = 2
    while candidate.exists():
        candidate = date_dir / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _snapshot(summary: Mapping[str, object]) -> dict[str, object]:
    return {
        "status": _clean(summary.get("status")),
        "steps": _normalized_steps(summary),
        "key_blockers": sorted(
            _clean(item) for item in summary.get("key_blockers", []) if _clean(item)
        ),
        "card_counts": _normalized_counts(summary.get("card_counts")),
        "decision_queue_counts": _normalized_counts(
            summary.get("decision_queue_counts")
        ),
        "ledger_health_summary": _json_safe(
            summary.get("ledger_health_summary", {})
        ),
        "recommended_next_action": _clean(
            summary.get("recommended_next_action")
        ),
    }


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _archive_sort_key(record: Mapping[str, object]) -> tuple[str, str]:
    return (
        _clean(record.get("run_timestamp")),
        _clean(record.get("archive_path")),
    )


def load_epl_weekly_pipeline_archives(
    output_dir: Path | None = None,
) -> list[dict[str, object]]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    root = outputs / PIPELINE_ARCHIVE_ROOT
    if not root.exists():
        return []
    records: list[dict[str, object]] = []
    for path in root.glob("*/*/epl_weekly_pipeline_archive.json"):
        data = _read_json(path)
        if data is None:
            continue
        data = dict(data)
        data["manifest_path"] = _display_path(path, outputs)
        records.append(data)
    return sorted(records, key=_archive_sort_key)


def _add_change(
    changes: list[dict[str, object]],
    category: str,
    item: str,
    previous: object,
    latest: object,
    reason: str,
) -> None:
    changes.append(
        {
            "category": category,
            "item": item,
            "previous": _json_safe(previous),
            "latest": _json_safe(latest),
            "reason": reason,
        }
    )


def _step_statuses(record: Mapping[str, object]) -> dict[str, str]:
    snapshot = record.get("summary_snapshot", {})
    if not isinstance(snapshot, Mapping):
        return {}
    steps = snapshot.get("steps", [])
    if not isinstance(steps, list):
        return {}
    return {
        _clean(row.get("step")): _clean(row.get("status"))
        for row in steps
        if isinstance(row, Mapping) and _clean(row.get("step"))
    }


def _record_counts(record: Mapping[str, object], name: str) -> dict[str, int]:
    snapshot = record.get("summary_snapshot", {})
    if not isinstance(snapshot, Mapping):
        return {}
    return _normalized_counts(snapshot.get(name))


def _record_mapping(record: Mapping[str, object], name: str) -> dict[str, object]:
    snapshot = record.get("summary_snapshot", {})
    if not isinstance(snapshot, Mapping):
        return {}
    value = snapshot.get(name, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _record_blockers(record: Mapping[str, object]) -> set[str]:
    snapshot = record.get("summary_snapshot", {})
    values = snapshot.get("key_blockers", []) if isinstance(snapshot, Mapping) else []
    return {_clean(item) for item in values if _clean(item)}


def _report_map(record: Mapping[str, object]) -> dict[str, str]:
    inventory = record.get("report_inventory", [])
    if not isinstance(inventory, list):
        return {}
    return {
        _clean(row.get("path")): _clean(row.get("checksum_sha256"))
        for row in inventory
        if isinstance(row, Mapping) and _clean(row.get("path"))
    }


def compare_epl_weekly_pipeline_records(
    previous: Mapping[str, object] | None,
    latest: Mapping[str, object],
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Compare two archive manifests without reading or changing manual inputs."""
    now = generated_at or datetime.now().astimezone()
    if previous is None:
        return {
            "schema_version": 1,
            "generated_at": now.isoformat(timespec="seconds"),
            "verdict": "Missing prior run",
            "previous_receipt_id": "",
            "latest_receipt_id": _clean(latest.get("receipt_id")),
            "previous_archive_path": "",
            "latest_archive_path": _clean(latest.get("archive_path")),
            "previous_status": "",
            "latest_status": _clean(latest.get("status")),
            "new_blockers": [],
            "resolved_blockers": [],
            "step_outcome_changes": [],
            "card_count_changes": {},
            "decision_queue_count_changes": {},
            "ledger_health_changes": {},
            "new_report_paths": [],
            "missing_report_paths": [],
            "changed_report_checksums": [],
            "recommended_next_action_change": {},
            "changes": [],
            "important_changes": [
                "No prior weekly pipeline receipt exists yet. This run is the comparison baseline."
            ],
        }

    changes: list[dict[str, object]] = []
    previous_status = _clean(previous.get("status"))
    latest_status = _clean(latest.get("status"))
    if previous_status != latest_status:
        _add_change(
            changes,
            "Final status",
            "status",
            previous_status,
            latest_status,
            f"Pipeline status changed from {previous_status} to {latest_status}.",
        )

    previous_blockers = _record_blockers(previous)
    latest_blockers = _record_blockers(latest)
    new_blockers = sorted(latest_blockers - previous_blockers)
    resolved_blockers = sorted(previous_blockers - latest_blockers)
    for blocker in new_blockers:
        _add_change(changes, "Blocker", blocker, "Absent", "Present", "New blocker added.")
    for blocker in resolved_blockers:
        _add_change(
            changes, "Blocker", blocker, "Present", "Resolved", "Prior blocker cleared."
        )

    previous_steps = _step_statuses(previous)
    latest_steps = _step_statuses(latest)
    step_changes: list[dict[str, str]] = []
    for name in sorted(set(previous_steps) | set(latest_steps)):
        before = previous_steps.get(name, "Missing")
        after = latest_steps.get(name, "Missing")
        if before == after:
            continue
        step_changes.append({"step": name, "previous": before, "latest": after})
        _add_change(
            changes,
            "Step outcome",
            name,
            before,
            after,
            f"{name} changed from {before} to {after}.",
        )

    def count_changes(name: str, category: str) -> dict[str, dict[str, int]]:
        before_counts = _record_counts(previous, name)
        after_counts = _record_counts(latest, name)
        result: dict[str, dict[str, int]] = {}
        for key in sorted(set(before_counts) | set(after_counts)):
            before = int(before_counts.get(key, 0))
            after = int(after_counts.get(key, 0))
            if before == after:
                continue
            result[key] = {"previous": before, "latest": after, "change": after - before}
            _add_change(
                changes,
                category,
                key,
                before,
                after,
                f"{key} changed by {after - before:+d}.",
            )
        return result

    card_changes = count_changes("card_counts", "Card count")
    queue_changes = count_changes("decision_queue_counts", "Decision queue count")

    previous_health = _record_mapping(previous, "ledger_health_summary")
    latest_health = _record_mapping(latest, "ledger_health_summary")
    ledger_changes: dict[str, dict[str, object]] = {}
    for key in sorted(set(previous_health) | set(latest_health)):
        before = _json_safe(previous_health.get(key))
        after = _json_safe(latest_health.get(key))
        if before == after:
            continue
        ledger_changes[key] = {"previous": before, "latest": after}
        _add_change(
            changes,
            "Ledger health",
            key,
            before,
            after,
            f"Ledger health field {key} changed.",
        )

    previous_reports = _report_map(previous)
    latest_reports = _report_map(latest)
    new_reports = sorted(set(latest_reports) - set(previous_reports))
    missing_reports = sorted(set(previous_reports) - set(latest_reports))
    for path in sorted(set(previous_reports) & set(latest_reports)):
        before_checksum = previous_reports[path]
        after_checksum = latest_reports[path]
        if before_checksum and not after_checksum:
            missing_reports.append(path)
        elif not before_checksum and after_checksum:
            new_reports.append(path)
    new_reports = sorted(set(new_reports))
    missing_reports = sorted(set(missing_reports))
    changed_reports = sorted(
        path
        for path in set(previous_reports) & set(latest_reports)
        if previous_reports[path]
        and latest_reports[path]
        and previous_reports[path] != latest_reports[path]
    )
    for path in new_reports:
        _add_change(changes, "Report", path, "Missing", "Present", "New report path added.")
    for path in missing_reports:
        _add_change(changes, "Report", path, "Present", "Missing", "Prior report path is missing.")
    for path in changed_reports:
        _add_change(
            changes,
            "Report checksum",
            path,
            previous_reports[path],
            latest_reports[path],
            "Report contents changed.",
        )

    previous_snapshot = previous.get("summary_snapshot", {})
    latest_snapshot = latest.get("summary_snapshot", {})
    previous_action = (
        _clean(previous_snapshot.get("recommended_next_action"))
        if isinstance(previous_snapshot, Mapping)
        else ""
    )
    latest_action = (
        _clean(latest_snapshot.get("recommended_next_action"))
        if isinstance(latest_snapshot, Mapping)
        else ""
    )
    action_change: dict[str, str] = {}
    if previous_action != latest_action:
        action_change = {"previous": previous_action, "latest": latest_action}
        _add_change(
            changes,
            "Recommended action",
            "recommended_next_action",
            previous_action,
            latest_action,
            "The recommended next human action changed.",
        )

    rank = {
        "Failed": 0,
        "Blocked": 1,
        "Needs odds": 2,
        "Needs odds fixes": 2,
        "Needs data refresh": 2,
        "Card generated with warnings": 4,
        "Ready for card review": 5,
    }
    substantive = bool(
        new_blockers
        or resolved_blockers
        or step_changes
        or card_changes
        or queue_changes
        or ledger_changes
        or action_change
    )
    if latest_status == "Failed":
        verdict = "Failed"
    elif new_blockers:
        verdict = "New blockers"
    elif rank.get(latest_status, 0) > rank.get(previous_status, 0) or (
        resolved_blockers
        and not new_blockers
        and rank.get(latest_status, 0) >= rank.get(previous_status, 0)
    ):
        verdict = "Improved"
    elif (
        previous_status in {"Ready for card review", "Card generated with warnings"}
        and latest_status in {"Ready for card review", "Card generated with warnings"}
        and not substantive
    ):
        verdict = "Stable ready state"
    else:
        verdict = "More review needed"

    important = [str(row["reason"]) for row in changes[:8]]
    if not important:
        important = ["No meaningful weekly workflow changes were detected."]
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "verdict": verdict,
        "previous_receipt_id": _clean(previous.get("receipt_id")),
        "latest_receipt_id": _clean(latest.get("receipt_id")),
        "previous_archive_path": _clean(previous.get("archive_path")),
        "latest_archive_path": _clean(latest.get("archive_path")),
        "previous_status": previous_status,
        "latest_status": latest_status,
        "new_blockers": new_blockers,
        "resolved_blockers": resolved_blockers,
        "step_outcome_changes": step_changes,
        "card_count_changes": card_changes,
        "decision_queue_count_changes": queue_changes,
        "ledger_health_changes": ledger_changes,
        "new_report_paths": new_reports,
        "missing_report_paths": missing_reports,
        "changed_report_checksums": changed_reports,
        "recommended_next_action_change": action_change,
        "changes": changes,
        "important_changes": important,
    }


def prepare_epl_weekly_pipeline_history(
    summary: Mapping[str, object],
    *,
    output_dir: Path | None = None,
    archived_at: datetime | None = None,
) -> dict[str, object]:
    """Reserve an archive directory and build receipt/comparison metadata."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    outputs.mkdir(parents=True, exist_ok=True)
    now = archived_at or datetime.now().astimezone()
    run_at = _parse_datetime(summary.get("run_timestamp")) or now
    inventory, sources = build_pipeline_report_inventory(summary, outputs)
    receipt_checksum, receipt_id = calculate_epl_weekly_pipeline_receipt_identity(
        summary, inventory
    )
    archive_dir = _unique_archive_dir(outputs, run_at)
    manifest = {
        "schema_version": 1,
        "receipt_id": receipt_id,
        "receipt_checksum_sha256": receipt_checksum,
        "run_timestamp": _clean(summary.get("run_timestamp")),
        "archived_at": now.isoformat(timespec="seconds"),
        "archive_path": _display_path(archive_dir, outputs),
        "status": _clean(summary.get("status")),
        "current_odds_validation_checksum_sha256": _report_checksum(
            inventory, "current_odds_validation.csv"
        ),
        "current_odds_completeness_checksum_sha256": _report_checksum(
            inventory, "current_odds_completeness.csv"
        ),
        "summary_snapshot": _snapshot(summary),
        "report_inventory": inventory,
        "pipeline_files": [],
        "safety": {
            "manual_files_edited": False,
            "force_mode_used": False,
            "settlement_applied": False,
            "staging_promoted": False,
            "live_provider_run": False,
            "provider_allowlisted": False,
            "cron_enabled": False,
            "bets_placed": False,
        },
    }
    prior_archives = load_epl_weekly_pipeline_archives(outputs)
    previous = prior_archives[-1] if prior_archives else None
    comparison = compare_epl_weekly_pipeline_records(
        previous, manifest, generated_at=now
    )
    manifest["comparison_verdict"] = comparison["verdict"]
    manifest["important_changes"] = comparison["important_changes"]
    return {
        "output_dir": outputs,
        "archive_dir": archive_dir,
        "manifest": manifest,
        "comparison": comparison,
        "report_sources": sources,
    }


def render_epl_weekly_pipeline_archive_receipt(
    manifest: Mapping[str, object],
) -> str:
    snapshot = manifest.get("summary_snapshot", {})
    counts = snapshot.get("card_counts", {}) if isinstance(snapshot, Mapping) else {}
    queue = (
        snapshot.get("decision_queue_counts", {})
        if isinstance(snapshot, Mapping)
        else {}
    )
    lines = [
        "# EPL Weekly Pipeline Archive Receipt",
        "",
        "This is a report-only audit receipt. No manual data, model logic, bets, or automation settings were changed.",
        "",
        f"- Pipeline run: {manifest.get('run_timestamp', '')}",
        f"- Final status: **{manifest.get('status', '')}**",
        f"- Receipt ID: `{manifest.get('receipt_id', '')}`",
        f"- Receipt checksum: `{manifest.get('receipt_checksum_sha256', '')}`",
        f"- Archive path: `{manifest.get('archive_path', '')}`",
        f"- Comparison verdict: **{manifest.get('comparison_verdict', '')}**",
        (
            "- Card counts: "
            f"{counts.get('best_bets', 0)} best bet(s), {counts.get('leans', 0)} lean(s), "
            f"{counts.get('passes', 0)} pass(es)."
        ),
        f"- Decision queue rows: {sum(int(value or 0) for value in queue.values()) if isinstance(queue, Mapping) else 0}",
        "",
        "## Important changes",
        "",
    ]
    lines.extend(
        [f"- {item}" for item in manifest.get("important_changes", [])]
        or ["- No comparison detail is available."]
    )
    lines.extend(["", "## Bound reports", ""])
    inventory = manifest.get("report_inventory", [])
    if inventory:
        table = pd.DataFrame(inventory)
        visible_columns = [
            column
            for column in ("path", "status", "checksum_sha256", "size_bytes")
            if column in table.columns
        ]
        table = table[visible_columns]
        lines.append(table.to_markdown(index=False))
    else:
        lines.append("No referenced reports were available to bind.")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "The archive copied report outputs only. It did not import odds, apply settlement, archive stale odds, roll back files, promote staging, run live providers, allowlist providers, enable cron, fabricate odds, or place bets.",
        ]
    )
    return "\n".join(lines)


def render_epl_weekly_pipeline_archive_csv(
    manifest: Mapping[str, object],
) -> bytes:
    rows: list[dict[str, object]] = [
        {
            "category": "Run",
            "item": "receipt_id",
            "status": manifest.get("status", ""),
            "value": manifest.get("receipt_id", ""),
            "checksum_sha256": manifest.get("receipt_checksum_sha256", ""),
            "note": manifest.get("comparison_verdict", ""),
        }
    ]
    snapshot = manifest.get("summary_snapshot", {})
    for step in snapshot.get("steps", []) if isinstance(snapshot, Mapping) else []:
        rows.append(
            {
                "category": "Step",
                "item": step.get("step", ""),
                "status": step.get("status", ""),
                "value": "",
                "checksum_sha256": "",
                "note": "",
            }
        )
    for report in manifest.get("report_inventory", []):
        rows.append(
            {
                "category": "Report",
                "item": report.get("path", ""),
                "status": report.get("status", ""),
                "value": report.get("size_bytes", 0),
                "checksum_sha256": report.get("checksum_sha256", ""),
                "note": report.get("note", ""),
            }
        )
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def _comparison_markdown(comparison: Mapping[str, object]) -> str:
    lines = [
        "# EPL Weekly Pipeline Comparison",
        "",
        "This report compares the latest two archived weekly pipeline receipts. It is read-only.",
        "",
        f"- Verdict: **{comparison.get('verdict', '')}**",
        f"- Previous status: {comparison.get('previous_status') or 'Not available'}",
        f"- Latest status: {comparison.get('latest_status') or 'Not available'}",
        f"- Previous receipt: `{comparison.get('previous_receipt_id') or 'Not available'}`",
        f"- Latest receipt: `{comparison.get('latest_receipt_id') or 'Not available'}`",
        "",
        "## Important changes",
        "",
    ]
    lines.extend(
        [f"- {item}" for item in comparison.get("important_changes", [])]
        or ["- No meaningful changes were detected."]
    )
    lines.extend(["", "## Full change table", ""])
    changes = comparison.get("changes", [])
    if changes:
        lines.append(pd.DataFrame(changes).to_markdown(index=False))
    elif comparison.get("verdict") == "Missing prior run":
        lines.append("A second archived weekly pipeline run is needed before a comparison is available.")
    else:
        lines.append("No detailed changes were detected.")
    lines.extend(
        [
            "",
            "Nothing was applied. Review status, blockers, prices, and the decision queue manually.",
        ]
    )
    return "\n".join(lines)


def _comparison_csv(comparison: Mapping[str, object]) -> bytes:
    changes = comparison.get("changes", [])
    if changes:
        frame = pd.DataFrame(changes)
    else:
        frame = pd.DataFrame(
            [
                {
                    "category": "Comparison",
                    "item": "verdict",
                    "previous": comparison.get("previous_status", ""),
                    "latest": comparison.get("latest_status", ""),
                    "reason": comparison.get("important_changes", [""])[0],
                }
            ]
        )
    return frame.to_csv(index=False).encode("utf-8")


def _copy_bound_reports(plan: Mapping[str, object]) -> list[dict[str, object]]:
    archive_dir = Path(plan["archive_dir"])
    sources = plan.get("report_sources", {})
    if not isinstance(sources, Mapping):
        return []
    manifest = plan.get("manifest", {})
    inventory = manifest.get("report_inventory", []) if isinstance(manifest, Mapping) else []
    expected_checksums = {
        _clean(row.get("path")): _clean(row.get("checksum_sha256"))
        for row in inventory
        if isinstance(row, Mapping)
    }
    copied: list[dict[str, object]] = []
    for display, source_value in sorted(sources.items()):
        source = Path(source_value)
        target = archive_dir / "reports" / Path(str(display))
        content = source.read_bytes()
        atomic_write_report(target, content)
        checksum = file_sha256(target)
        expected = expected_checksums.get(str(display), "")
        if not expected or checksum != expected:
            raise RuntimeError(
                f"Referenced report changed after receipt preparation: {display}. "
                "Rerun the weekly pipeline so the receipt binds the current report."
            )
        copied.append(
            {
                "source_path": str(display),
                "archive_path": target.relative_to(archive_dir).as_posix(),
                "checksum_sha256": checksum,
                "size_bytes": target.stat().st_size,
            }
        )
    return copied


def save_prepared_epl_weekly_pipeline_history(
    plan: Mapping[str, object],
    *,
    pipeline_summary: Mapping[str, object],
    pipeline_markdown_path: Path,
    pipeline_csv_path: Path,
) -> dict[str, object]:
    """Write report-only archive and comparison outputs for a prepared run."""
    outputs = Path(plan["output_dir"])
    archive_dir = Path(plan["archive_dir"])
    manifest = deepcopy(dict(plan["manifest"]))
    manifest["summary_snapshot"] = _snapshot(pipeline_summary)
    manifest["archived_reports"] = _copy_bound_reports(plan)

    pipeline_payloads = {
        "epl_weekly_pipeline.json": (
            json.dumps(_json_safe(pipeline_summary), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        "epl_weekly_pipeline.md": pipeline_markdown_path.read_bytes(),
        "epl_weekly_pipeline.csv": pipeline_csv_path.read_bytes(),
    }
    pipeline_files = []
    for filename, content in pipeline_payloads.items():
        target = archive_dir / filename
        atomic_write_report(target, content)
        pipeline_files.append(
            {
                "path": filename,
                "checksum_sha256": file_sha256(target),
                "size_bytes": target.stat().st_size,
            }
        )
    manifest["pipeline_files"] = pipeline_files

    archive_json = archive_dir / PIPELINE_ARCHIVE_JSON_FILENAME
    archive_markdown = archive_dir / PIPELINE_ARCHIVE_MARKDOWN_FILENAME
    archive_csv = archive_dir / PIPELINE_ARCHIVE_CSV_FILENAME
    latest_archive_json = outputs / PIPELINE_ARCHIVE_JSON_FILENAME
    latest_archive_markdown = outputs / PIPELINE_ARCHIVE_MARKDOWN_FILENAME
    latest_archive_csv = outputs / PIPELINE_ARCHIVE_CSV_FILENAME

    archive_json_bytes = (
        json.dumps(_json_safe(manifest), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    archive_markdown_bytes = (
        render_epl_weekly_pipeline_archive_receipt(manifest) + "\n"
    ).encode("utf-8")
    archive_csv_bytes = render_epl_weekly_pipeline_archive_csv(manifest)
    for path, content in (
        (archive_json, archive_json_bytes),
        (archive_markdown, archive_markdown_bytes),
        (archive_csv, archive_csv_bytes),
        (latest_archive_json, archive_json_bytes),
        (latest_archive_markdown, archive_markdown_bytes),
        (latest_archive_csv, archive_csv_bytes),
    ):
        atomic_write_report(path, content)

    comparison = dict(plan["comparison"])
    comparison_paths = save_epl_weekly_pipeline_comparison(
        comparison, output_dir=outputs
    )
    return {
        "receipt_id": manifest["receipt_id"],
        "receipt_checksum_sha256": manifest["receipt_checksum_sha256"],
        "archive_dir": archive_dir,
        "archive_json": archive_json,
        "archive_markdown": archive_markdown,
        "archive_csv": archive_csv,
        "latest_archive_json": latest_archive_json,
        "latest_archive_markdown": latest_archive_markdown,
        "latest_archive_csv": latest_archive_csv,
        "comparison": comparison,
        "comparison_paths": comparison_paths,
        "manifest": manifest,
    }


def save_epl_weekly_pipeline_comparison(
    comparison: Mapping[str, object],
    *,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    outputs.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": outputs / PIPELINE_COMPARISON_JSON_FILENAME,
        "markdown": outputs / PIPELINE_COMPARISON_MARKDOWN_FILENAME,
        "csv": outputs / PIPELINE_COMPARISON_CSV_FILENAME,
    }
    atomic_write_report(
        paths["json"],
        (json.dumps(_json_safe(comparison), indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )
    atomic_write_report(
        paths["markdown"], (_comparison_markdown(comparison) + "\n").encode("utf-8")
    )
    atomic_write_report(paths["csv"], _comparison_csv(comparison))
    return paths


def compare_latest_epl_weekly_pipeline_runs(
    output_dir: Path | None = None,
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    archives = load_epl_weekly_pipeline_archives(outputs)
    latest = archives[-1] if archives else {}
    previous = archives[-2] if len(archives) >= 2 else None
    comparison = compare_epl_weekly_pipeline_records(
        previous,
        latest,
        generated_at=generated_at,
    )
    paths = save_epl_weekly_pipeline_comparison(comparison, output_dir=outputs)
    return {"verdict": comparison["verdict"], "summary": comparison, **paths}


def archive_latest_epl_weekly_pipeline(
    output_dir: Path | None = None,
    *,
    archived_at: datetime | None = None,
) -> dict[str, object]:
    """Archive the latest generated pipeline reports without touching manual inputs."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    summary_path = outputs / "epl_weekly_pipeline.json"
    markdown_path = outputs / "epl_weekly_pipeline.md"
    csv_path = outputs / "epl_weekly_pipeline.csv"
    summary = _read_json(summary_path)
    if summary is None:
        raise FileNotFoundError(
            "No readable epl_weekly_pipeline.json exists. Run the weekly pipeline first."
        )
    missing = [path for path in (markdown_path, csv_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Weekly pipeline archive requires JSON, markdown, and CSV outputs. Missing: "
            + ", ".join(str(path) for path in missing)
        )
    plan = prepare_epl_weekly_pipeline_history(
        summary, output_dir=outputs, archived_at=archived_at
    )
    enriched = dict(summary)
    enriched.update(
        {
            "pipeline_receipt_id": plan["manifest"]["receipt_id"],
            "pipeline_receipt_checksum_sha256": plan["manifest"][
                "receipt_checksum_sha256"
            ],
            "pipeline_archive_path": str(plan["archive_dir"]),
            "pipeline_comparison_verdict": plan["comparison"]["verdict"],
            "important_changes_since_previous_run": plan["comparison"][
                "important_changes"
            ],
        }
    )
    return save_prepared_epl_weekly_pipeline_history(
        plan,
        pipeline_summary=enriched,
        pipeline_markdown_path=markdown_path,
        pipeline_csv_path=csv_path,
    )


def list_recent_epl_weekly_pipeline_runs(
    output_dir: Path | None = None,
    *,
    limit: int = 8,
) -> pd.DataFrame:
    if limit <= 0:
        return pd.DataFrame()
    archives = load_epl_weekly_pipeline_archives(output_dir)
    rows: list[dict[str, object]] = []
    for record in reversed(archives[-limit:]):
        snapshot = record.get("summary_snapshot", {})
        counts = snapshot.get("card_counts", {}) if isinstance(snapshot, Mapping) else {}
        queue = (
            snapshot.get("decision_queue_counts", {})
            if isinstance(snapshot, Mapping)
            else {}
        )
        health = (
            snapshot.get("ledger_health_summary", {})
            if isinstance(snapshot, Mapping)
            else {}
        )
        rows.append(
            {
                "run_timestamp": record.get("run_timestamp", ""),
                "status": record.get("status", ""),
                "receipt_id": record.get("receipt_id", ""),
                "comparison_verdict": record.get("comparison_verdict", ""),
                "best_bets": int(counts.get("best_bets", 0) or 0),
                "leans": int(counts.get("leans", 0) or 0),
                "passes": int(counts.get("passes", 0) or 0),
                "decision_queue_rows": sum(
                    int(value or 0) for value in queue.values()
                )
                if isinstance(queue, Mapping)
                else 0,
                "ledger_errors": int(health.get("error_count", 0) or 0)
                if isinstance(health, Mapping)
                else 0,
                "ledger_warnings": int(health.get("warning_count", 0) or 0)
                if isinstance(health, Mapping)
                else 0,
                "archive_path": record.get("archive_path", ""),
            }
        )
    return pd.DataFrame(rows)
