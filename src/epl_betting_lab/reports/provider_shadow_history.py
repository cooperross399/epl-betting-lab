from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.providers.base import atomic_write_report, file_sha256


SHADOW_ARCHIVE_ROOT = Path("archive") / "provider_shadow_runs"
ARCHIVE_METADATA_FILENAME = "archive_metadata.json"
SHADOW_JSON_FILENAME = "provider_shadow_verification.json"
SHADOW_MARKDOWN_FILENAME = "provider_shadow_verification.md"
SHADOW_CSV_FILENAME = "provider_shadow_verification.csv"
COMPARISON_JSON_FILENAME = "provider_shadow_run_comparison.json"
COMPARISON_MARKDOWN_FILENAME = "provider_shadow_run_comparison.md"
COMPARISON_CSV_FILENAME = "provider_shadow_run_comparison.csv"
COMPARISON_VERDICTS = (
    "Stable enough for review",
    "Needs more shadow runs",
    "Coverage changed",
    "Mapping issue",
    "Market coverage issue",
    "Provider policy issue",
    "Failed/untrusted",
)
COMPARISON_COLUMNS = (
    "category",
    "metric",
    "previous_value",
    "latest_value",
    "change",
    "change_status",
    "previous_run",
    "latest_run",
    "details",
)
CHECKSUM_STATUS_FIELDS = (
    "provenance_status",
    "source_odds_checksum_status",
    "source_fixtures_checksum_status",
    "staging_odds_checksum_status",
    "staging_fixtures_checksum_status",
    "odds_checksum_pair_status",
    "fixtures_checksum_pair_status",
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


def _as_float(value: object) -> float | None:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None
    return float(numeric)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).casefold() in {"true", "yes", "1", "allowed", "ready"}


def _parse_datetime(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _display_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve().relative_to(output_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _safe_source_path(value: object, output_dir: Path) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(output_dir.resolve())
    except ValueError:
        return None
    return resolved


def _unique_archive_dir(
    output_dir: Path,
    *,
    generated_at: datetime,
    provider_key: str,
) -> Path:
    date_dir = output_dir / SHADOW_ARCHIVE_ROOT / generated_at.strftime("%Y-%m-%d")
    stem = f"{generated_at.strftime('%H%M%S')}_{_slug(provider_key)}"
    candidate = date_dir / stem
    suffix = 2
    while candidate.exists():
        candidate = date_dir / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _report_specs(
    verification_paths: Mapping[str, object],
    provider_report_paths: Mapping[str, object],
    staging_validation_paths: Mapping[str, object],
) -> tuple[tuple[str, str, object, bool], ...]:
    return (
        ("shadow_json", SHADOW_JSON_FILENAME, verification_paths.get("json"), True),
        (
            "shadow_markdown",
            SHADOW_MARKDOWN_FILENAME,
            verification_paths.get("markdown"),
            True,
        ),
        ("shadow_csv", SHADOW_CSV_FILENAME, verification_paths.get("csv"), True),
        (
            "provider_report_json",
            "provider_run_report.json",
            provider_report_paths.get("json"),
            False,
        ),
        (
            "provider_report_markdown",
            "provider_run_report.md",
            provider_report_paths.get("markdown"),
            False,
        ),
        (
            "staging_validation_json",
            "staging_input_validation.json",
            staging_validation_paths.get("json"),
            False,
        ),
        (
            "staging_validation_markdown",
            "staging_input_validation.md",
            staging_validation_paths.get("markdown"),
            False,
        ),
        (
            "staging_validation_csv",
            "staging_input_validation.csv",
            staging_validation_paths.get("csv"),
            False,
        ),
    )


def archive_provider_shadow_run(
    summary: Mapping[str, object],
    *,
    verification_paths: Mapping[str, object],
    provider_report_paths: Mapping[str, object] | None = None,
    staging_validation_paths: Mapping[str, object] | None = None,
    output_dir: Path | None = None,
    archived_at: datetime | None = None,
) -> dict[str, object]:
    """Archive one completed report bundle without touching staging/manual inputs."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    generated_at = _parse_datetime(summary.get("generated_at")) or (
        archived_at or datetime.now().astimezone()
    )
    provider_key = _clean(summary.get("provider_key")) or _clean(
        summary.get("provider_name")
    )
    specs = _report_specs(
        verification_paths,
        provider_report_paths or {},
        staging_validation_paths or {},
    )

    payloads: list[tuple[str, str, Path, bytes]] = []
    file_records: dict[str, dict[str, object]] = {}
    archive_warnings: list[str] = []
    for key, archive_name, source_value, required in specs:
        source = _safe_source_path(source_value, outputs)
        if source is None:
            message = "Source report path is missing or outside data/outputs."
            if required:
                raise ValueError(f"Cannot archive required {key}: {message}")
            file_records[key] = {"status": "Not available", "note": message}
            continue
        try:
            content = source.read_bytes()
        except OSError as exc:
            if required:
                raise OSError(f"Cannot archive required report `{source}`: {exc}") from exc
            message = f"Optional report could not be read: {exc}"
            file_records[key] = {
                "status": "Unreadable",
                "source_path": _display_path(source, outputs),
                "note": message,
            }
            archive_warnings.append(message)
            continue
        payloads.append((key, archive_name, source, content))

    archive_dir = _unique_archive_dir(
        outputs,
        generated_at=generated_at,
        provider_key=provider_key,
    )
    for key, archive_name, source, content in payloads:
        target = archive_dir / archive_name
        atomic_write_report(target, content)
        file_records[key] = {
            "status": "Archived",
            "source_path": _display_path(source, outputs),
            "archive_path": _display_path(target, outputs),
            "checksum_sha256": file_sha256(target),
            "size_bytes": target.stat().st_size,
        }

    metadata = {
        "schema_version": 1,
        "archive_id": _display_path(archive_dir, outputs),
        "archived_at": (archived_at or datetime.now().astimezone()).isoformat(
            timespec="seconds"
        ),
        "generated_at": _clean(summary.get("generated_at")),
        "provider_key": provider_key,
        "provider_name": _clean(summary.get("provider_name")),
        "provider_type": _clean(summary.get("provider_type")),
        "mode": _clean(summary.get("mode")),
        "verdict": _clean(summary.get("verdict")),
        "files": file_records,
        "archive_warnings": archive_warnings,
        "safety": {
            "manual_or_production_files_edited": False,
            "staging_promoted": False,
            "provider_policy_edited": False,
            "cron_enabled": False,
            "bets_placed": False,
        },
    }
    metadata_path = archive_dir / ARCHIVE_METADATA_FILENAME
    atomic_write_report(
        metadata_path,
        (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return {
        "directory": archive_dir,
        "metadata": metadata_path,
        "files": file_records,
        "archive_id": metadata["archive_id"],
    }


def _read_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in `{path}`.")
    return payload


def _archive_integrity(
    archive_dir: Path,
    metadata: Mapping[str, object],
) -> tuple[str, str]:
    files = metadata.get("files", {})
    if not isinstance(files, dict):
        return "Not available", "Archive metadata has no readable file checksum map."
    checked = 0
    for record in files.values():
        if not isinstance(record, dict) or record.get("status") != "Archived":
            continue
        checksum = _clean(record.get("checksum_sha256"))
        archived_path = _clean(record.get("archive_path"))
        if not checksum or not archived_path:
            return "Not available", "At least one archived report lacks checksum metadata."
        candidate = archive_dir / Path(archived_path).name
        try:
            current = file_sha256(candidate)
        except OSError:
            return "Unreadable", f"Archived report could not be read: `{candidate}`."
        checked += 1
        if current != checksum:
            return "Mismatch", f"Archived report checksum changed: `{candidate.name}`."
    if checked == 0:
        return "Not available", "No archived report checksums were available."
    return "Verified", f"Verified {checked} archived report checksum(s)."


def _archive_record(archive_dir: Path, output_dir: Path) -> dict[str, object]:
    metadata_path = archive_dir / ARCHIVE_METADATA_FILENAME
    summary_path = archive_dir / SHADOW_JSON_FILENAME
    metadata: dict[str, object] = {}
    summary: dict[str, object] = {}
    errors: list[str] = []
    try:
        metadata = _read_json_object(metadata_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Metadata unreadable: {type(exc).__name__}: {exc}")
    try:
        summary = _read_json_object(summary_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"Shadow summary unreadable: {type(exc).__name__}: {exc}")

    generated_at = _clean(summary.get("generated_at")) or _clean(
        metadata.get("generated_at")
    )
    provider_key = _clean(summary.get("provider_key")) or _clean(
        metadata.get("provider_key")
    )
    provider_name = _clean(summary.get("provider_name")) or _clean(
        metadata.get("provider_name")
    )
    integrity_status, integrity_note = _archive_integrity(archive_dir, metadata)
    if integrity_status in {"Mismatch", "Unreadable"}:
        errors.append(integrity_note)
    timestamp = _parse_datetime(generated_at)
    if timestamp is None:
        timestamp = datetime.fromtimestamp(archive_dir.stat().st_mtime).astimezone()
    return {
        "archive_path": _display_path(archive_dir, output_dir),
        "metadata_path": _display_path(metadata_path, output_dir),
        "generated_at": generated_at or timestamp.isoformat(timespec="seconds"),
        "sort_timestamp": timestamp,
        "provider_key": provider_key,
        "provider_name": provider_name,
        "provider_type": _clean(summary.get("provider_type")) or _clean(
            metadata.get("provider_type")
        ),
        "mode": _clean(summary.get("mode")) or _clean(metadata.get("mode")),
        "verdict": _clean(summary.get("verdict")) or _clean(metadata.get("verdict")),
        "archive_integrity_status": integrity_status,
        "archive_integrity_note": integrity_note,
        "readable": not errors and bool(summary),
        "error": " ".join(errors),
        "summary": summary,
    }


def _discover_archives(output_dir: Path) -> list[dict[str, object]]:
    archive_root = output_dir / SHADOW_ARCHIVE_ROOT
    if not archive_root.exists():
        return []
    records = [
        _archive_record(path, output_dir)
        for path in archive_root.glob("*/*")
        if path.is_dir()
    ]
    return sorted(
        records,
        key=lambda item: (item["sort_timestamp"], str(item["archive_path"])),
        reverse=True,
    )


def _provider_matches(record: Mapping[str, object], provider_name: str) -> bool:
    requested = _slug(provider_name)
    return requested in {
        _slug(record.get("provider_key")),
        _slug(record.get("provider_name")),
    }


def load_provider_shadow_run_history(
    output_dir: Path | None = None,
    *,
    provider_name: str | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Load newest-first archived records, including verified summary evidence."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    records = _discover_archives(outputs)
    if provider_name:
        records = [item for item in records if _provider_matches(item, provider_name)]
    if limit is not None:
        return records[: max(0, limit)]
    return records


def list_recent_provider_shadow_runs(
    output_dir: Path | None = None,
    *,
    provider_name: str | None = None,
    limit: int = 10,
) -> list[dict[str, object]]:
    records = load_provider_shadow_run_history(
        output_dir,
        provider_name=provider_name,
        limit=limit,
    )
    visible = []
    for record in records:
        visible.append(
            {
                key: value
                for key, value in record.items()
                if key not in {"summary", "sort_timestamp"}
            }
        )
    return visible


def _nested(summary: Mapping[str, object], *keys: str, default: object = "") -> object:
    value: object = summary
    for key in keys:
        if not isinstance(value, Mapping):
            return default
        value = value.get(key, default)
    return value


def _display_value(value: object) -> str:
    if isinstance(value, (list, tuple, set)):
        return json.dumps(sorted(_clean(item) for item in value), sort_keys=True)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return _clean(value)


def _metric_row(
    *,
    category: str,
    metric: str,
    previous: object,
    latest: object,
    previous_run: str,
    latest_run: str,
    details: str,
    numeric: bool = False,
) -> dict[str, object]:
    previous_number = _as_float(previous) if numeric else None
    latest_number = _as_float(latest) if numeric else None
    if numeric and previous_number is not None and latest_number is not None:
        delta = latest_number - previous_number
        changed = abs(delta) > 1e-12
        change = round(delta, 6)
    else:
        previous_text = _display_value(previous)
        latest_text = _display_value(latest)
        changed = previous_text != latest_text
        change = f"{previous_text} -> {latest_text}" if changed else "No change"
    return {
        "category": category,
        "metric": metric,
        "previous_value": _display_value(previous),
        "latest_value": _display_value(latest),
        "change": change,
        "change_status": "Changed" if changed else "Stable",
        "previous_run": previous_run,
        "latest_run": latest_run,
        "details": details,
    }


def _set_change_rows(
    *,
    category: str,
    label: str,
    previous: Sequence[object],
    latest: Sequence[object],
    previous_run: str,
    latest_run: str,
) -> list[dict[str, object]]:
    previous_set = {_clean(item) for item in previous if _clean(item)}
    latest_set = {_clean(item) for item in latest if _clean(item)}
    return [
        _metric_row(
            category=category,
            metric=f"{label}_added",
            previous=[],
            latest=sorted(latest_set - previous_set),
            previous_run=previous_run,
            latest_run=latest_run,
            details=f"New {label.replace('_', ' ')} in the latest run.",
        ),
        _metric_row(
            category=category,
            metric=f"{label}_removed",
            previous=sorted(previous_set - latest_set),
            latest=[],
            previous_run=previous_run,
            latest_run=latest_run,
            details=f"Prior {label.replace('_', ' ')} no longer present.",
        ),
    ]


def build_provider_shadow_comparison_rows(
    previous_record: Mapping[str, object],
    latest_record: Mapping[str, object],
) -> pd.DataFrame:
    previous = previous_record.get("summary", {})
    latest = latest_record.get("summary", {})
    if not isinstance(previous, Mapping) or not isinstance(latest, Mapping):
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    previous_run = _clean(previous_record.get("generated_at"))
    latest_run = _clean(latest_record.get("generated_at"))
    specs = (
        ("Run", "verdict", ("verdict",), False),
        ("Evidence", "archive_integrity", (), False),
        ("Evidence", "raw_evidence_checksum", ("raw_evidence", "checksum_status"), False),
        ("Mapping", "team_mapping_status", ("team_mapping", "status"), False),
        ("Mapping", "team_mapping_coverage", ("team_mapping", "coverage_percentage"), True),
        ("Mapping", "unmapped_team_count", ("team_mapping", "unmapped_team_count"), True),
        ("Fixtures", "fixture_matching_status", ("fixture_matching", "status"), False),
        ("Fixtures", "fixture_matching_coverage", ("fixture_matching", "coverage_percentage"), True),
        ("Bookmakers", "bookmaker_count", ("bookmaker_coverage", "bookmaker_count"), True),
        ("Bookmakers", "bookmakers", ("bookmaker_coverage", "bookmakers"), False),
        ("Markets", "market_1x2_rows", ("market_coverage", "market_counts", "1x2"), True),
        ("Markets", "market_total_2_5_rows", ("market_coverage", "market_counts", "total_2_5"), True),
        ("Markets", "market_btts_rows", ("market_coverage", "market_counts", "btts"), True),
        ("Markets", "market_coverage_percentage", ("market_coverage", "coverage_percentage"), True),
        ("Markets", "missing_markets", ("market_coverage", "missing_markets"), False),
        ("Completeness", "odds_completeness", ("odds_completeness", "completion_percentage"), True),
        ("Policy", "provider_policy_status", ("provider_policy", "provider_policy_status"), False),
        ("Policy", "provider_allowed", ("provider_policy", "provider_allowed"), False),
        ("Policy", "all_policy_gates_allowed", ("provider_policy", "all_policy_gates_allowed"), False),
        ("Validation", "staging_validation_verdict", ("staging_validation", "verdict"), False),
        ("Validation", "handoff_eligible", ("staging_validation", "handoff_eligible"), False),
        ("Provider", "provider_age_status", ("provider_age", "status"), False),
        ("Quota", "requests_remaining", ("api_quota", "requests_remaining"), True),
        ("Quota", "requests_used", ("api_quota", "requests_used"), True),
        ("Quota", "requests_last", ("api_quota", "requests_last"), True),
    )
    rows: list[dict[str, object]] = []
    for category, metric, path, numeric in specs:
        if metric == "archive_integrity":
            previous_value = previous_record.get("archive_integrity_status", "")
            latest_value = latest_record.get("archive_integrity_status", "")
        else:
            previous_value = _nested(previous, *path)
            latest_value = _nested(latest, *path)
        rows.append(
            _metric_row(
                category=category,
                metric=metric,
                previous=previous_value,
                latest=latest_value,
                previous_run=previous_run,
                latest_run=latest_run,
                details="Latest archived value compared with the previous archived value.",
                numeric=numeric,
            )
        )

    for field in CHECKSUM_STATUS_FIELDS:
        rows.append(
            _metric_row(
                category="Evidence",
                metric=field,
                previous=_nested(previous, "checksums", field),
                latest=_nested(latest, "checksums", field),
                previous_run=previous_run,
                latest_run=latest_run,
                details="Existing source/staging provenance checksum proof status.",
            )
        )
    rows.extend(
        _set_change_rows(
            category="Warnings",
            label="warnings",
            previous=_nested(previous, "warnings", default=[]),
            latest=_nested(latest, "warnings", default=[]),
            previous_run=previous_run,
            latest_run=latest_run,
        )
    )
    rows.extend(
        _set_change_rows(
            category="Blockers",
            label="blockers",
            previous=_nested(previous, "blockers", default=[]),
            latest=_nested(latest, "blockers", default=[]),
            previous_run=previous_run,
            latest_run=latest_run,
        )
    )
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def _comparison_verdict(
    records: Sequence[Mapping[str, object]],
    rows: pd.DataFrame,
) -> tuple[str, str]:
    if len(records) < 2:
        return (
            "Needs more shadow runs",
            "At least two archived shadow runs are required for a comparison.",
        )
    latest = records[0]
    previous = records[1]
    if not latest.get("readable") or not previous.get("readable"):
        return "Failed/untrusted", "One of the latest two archives is unreadable or malformed."
    if latest.get("archive_integrity_status") != "Verified" or previous.get(
        "archive_integrity_status"
    ) != "Verified":
        return "Failed/untrusted", "One of the latest two archive checksum sets is not verified."

    summary = latest.get("summary", {})
    if not isinstance(summary, Mapping):
        return "Failed/untrusted", "The latest archived shadow summary is malformed."
    if _clean(summary.get("verdict")) in {"Failed", "Blocked"}:
        return "Failed/untrusted", "The latest shadow run was blocked or failed."
    if _nested(summary, "team_mapping", "status") != "Verified" or _nested(
        summary, "fixture_matching", "status"
    ) != "Verified":
        return "Mapping issue", "The latest run has unresolved team or fixture mapping coverage."
    if _nested(summary, "market_coverage", "status") != "Complete" or (
        _as_float(_nested(summary, "odds_completeness", "completion_percentage"))
        or 0.0
    ) < 1.0:
        return "Market coverage issue", "The latest run is missing required market rows or prices."

    previous_summary = previous.get("summary", {})
    if not isinstance(previous_summary, Mapping):
        return "Failed/untrusted", "The previous archived shadow summary is malformed."
    latest_policy_status = _clean(
        _nested(summary, "provider_policy", "provider_policy_status")
    )
    policy_metrics = {
        "provider_policy_status",
        "provider_allowed",
        "all_policy_gates_allowed",
    }
    policy_changed = not rows.loc[
        rows["metric"].isin(policy_metrics) & (rows["change_status"] == "Changed")
    ].empty
    latest_provider_allowed = _as_bool(
        _nested(summary, "provider_policy", "provider_allowed")
    )
    latest_policy_gates_allowed = _as_bool(
        _nested(summary, "provider_policy", "all_policy_gates_allowed")
    )
    if (
        not latest_policy_status
        or latest_policy_status.casefold() in {"not checked", "policy unavailable"}
        or policy_changed
        or (latest_provider_allowed and not latest_policy_gates_allowed)
    ):
        return (
            "Provider policy issue",
            "Provider allowlist or policy-gate state changed or is not trustworthy.",
        )

    coverage_metrics = {
        "team_mapping_coverage",
        "unmapped_team_count",
        "fixture_matching_coverage",
        "bookmaker_count",
        "bookmakers",
        "market_1x2_rows",
        "market_total_2_5_rows",
        "market_btts_rows",
        "market_coverage_percentage",
        "missing_markets",
        "odds_completeness",
    }
    coverage_changed = not rows.loc[
        rows["metric"].isin(coverage_metrics) & (rows["change_status"] == "Changed")
    ].empty
    if coverage_changed:
        return "Coverage changed", "Provider mapping, fixture, bookmaker, market, or completeness coverage changed."
    if len(records) < 3:
        return (
            "Needs more shadow runs",
            "The latest two runs are stable, but at least three archived runs are recommended before review.",
        )
    return (
        "Stable enough for review",
        "The latest two runs are technically consistent and at least three runs "
        "are archived; manual review is still required.",
    )


def _next_step(verdict: str) -> str:
    return {
        "Stable enough for review": (
            "Review raw evidence, quota behavior, and provider ownership manually. "
            "This is not automatic allowlist approval."
        ),
        "Needs more shadow runs": "Run another controlled live shadow verification, then compare again.",
        "Coverage changed": "Review changed coverage rows before trusting the provider bundle.",
        "Mapping issue": "Fix and test explicit team/fixture mappings; do not guess provider names.",
        "Market coverage issue": "Review missing 1X2, totals, or BTTS coverage without inventing prices.",
        "Provider policy issue": "Keep the provider disallowed until repeated evidence is manually reviewed.",
        "Failed/untrusted": "Inspect archive integrity and run blockers before using this history.",
    }[verdict]


def render_provider_shadow_run_comparison(
    rows: pd.DataFrame,
    summary: Mapping[str, object],
) -> str:
    previous = summary.get("previous_run", {})
    latest = summary.get("latest_run", {})
    changed = rows[rows["change_status"] == "Changed"] if not rows.empty else rows
    important = changed[changed["category"].isin(
        ["Mapping", "Fixtures", "Bookmakers", "Markets", "Completeness", "Policy", "Validation", "Evidence"]
    )]
    change_lines = [
        f"- **{row.metric.replace('_', ' ').title()}:** "
        f"{row.previous_value or 'missing'} -> {row.latest_value or 'missing'}"
        for row in important.head(12).itertuples()
    ] or ["- No major technical changes were detected."]
    lines = [
        "# Provider Shadow Run Comparison",
        "",
        "This report compares archived provider evidence only. It cannot "
        "allowlist a provider, enable cron, generate trusted picks, promote "
        "staging, or place bets.",
        "",
        "## Verdict",
        "",
        f"- **{summary['verdict']}**",
        f"- Reason: {summary['verdict_reason']}",
        f"- Next step: {summary['next_step']}",
        f"- Provider: **{summary['provider_name']}** (`{summary['provider_key']}`)",
        f"- Archived runs found: **{summary['archive_count']}**",
        "",
        "## Compared runs",
        "",
        (
            f"- Previous: **{previous.get('generated_at', 'not available')}** | "
            f"{previous.get('archive_path', 'not available')}"
        ),
        (
            f"- Latest: **{latest.get('generated_at', 'not available')}** | "
            f"{latest.get('archive_path', 'not available')}"
        ),
        "",
        "## Biggest technical changes",
        "",
        *change_lines,
        "",
        "## Safety review",
        "",
        f"- Latest archive integrity: **{latest.get('archive_integrity_status', 'Not available')}**",
        f"- Provider policy currently allowed: **{'Yes' if summary['latest_provider_allowed'] else 'No'}**",
        f"- Latest staging validation: **{summary['latest_staging_verdict']}**",
        f"- Latest completeness: **{summary['latest_completeness_percentage']:.1%}**",
        "- A stable comparison is evidence for manual review, not permission for automation.",
        "",
        "## Detailed comparison",
        "",
        rows.to_markdown(index=False) if not rows.empty else "No comparison rows are available yet.",
        "",
        "Cron and provider allowlisting remain disabled.",
    ]
    return "\n".join(lines)


def save_provider_shadow_run_comparison(
    provider_name: str,
    output_dir: Path | None = None,
    *,
    run_at: datetime | None = None,
) -> dict[str, object]:
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    records = [
        item
        for item in _discover_archives(outputs)
        if _provider_matches(item, provider_name)
    ]
    compared = records[:2]
    rows = (
        build_provider_shadow_comparison_rows(compared[1], compared[0])
        if len(compared) >= 2
        else pd.DataFrame(columns=COMPARISON_COLUMNS)
    )
    verdict, verdict_reason = _comparison_verdict(records, rows)
    if verdict not in COMPARISON_VERDICTS:
        raise ValueError(f"Unexpected provider shadow comparison verdict: {verdict}")

    latest = compared[0] if compared else {}
    previous = compared[1] if len(compared) > 1 else {}
    latest_summary = latest.get("summary", {})
    if not isinstance(latest_summary, Mapping):
        latest_summary = {}
    provider_key = _clean(latest.get("provider_key")) or _slug(provider_name)
    provider_display = _clean(latest.get("provider_name")) or provider_name
    summary: dict[str, object] = {
        "generated_at": (run_at or datetime.now().astimezone()).isoformat(
            timespec="seconds"
        ),
        "provider_key": provider_key,
        "provider_name": provider_display,
        "archive_count": len(records),
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "next_step": _next_step(verdict),
        "previous_run": {
            key: previous.get(key, "")
            for key in (
                "generated_at",
                "archive_path",
                "verdict",
                "archive_integrity_status",
            )
        },
        "latest_run": {
            key: latest.get(key, "")
            for key in (
                "generated_at",
                "archive_path",
                "verdict",
                "archive_integrity_status",
            )
        },
        "latest_provider_allowed": _as_bool(
            _nested(latest_summary, "provider_policy", "provider_allowed")
        ),
        "latest_staging_verdict": _clean(
            _nested(latest_summary, "staging_validation", "verdict")
        )
        or "Not available",
        "latest_completeness_percentage": _as_float(
            _nested(latest_summary, "odds_completeness", "completion_percentage")
        )
        or 0.0,
        "changed_metric_count": int(
            (rows["change_status"] == "Changed").sum()
        )
        if not rows.empty
        else 0,
        "comparison_rows": rows.to_dict(orient="records"),
        "safety": {
            "manual_or_production_files_edited": False,
            "staging_promoted": False,
            "provider_policy_edited": False,
            "cron_enabled": False,
            "bets_placed": False,
        },
    }
    json_path = outputs / COMPARISON_JSON_FILENAME
    markdown_path = outputs / COMPARISON_MARKDOWN_FILENAME
    csv_path = outputs / COMPARISON_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        render_provider_shadow_run_comparison(rows, summary).encode("utf-8"),
    )
    atomic_write_report(
        csv_path,
        rows.to_csv(index=False, lineterminator="\n").encode("utf-8"),
    )
    return {
        "summary": summary,
        "comparison": rows,
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
    }
