from __future__ import annotations

import json
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.providers.base import atomic_write_report
from epl_betting_lab.reports.fixture_slate_check import _assign_matchweek_groups


TRIM_PREVIEW_JSON_FILENAME = "fixture_slate_trim_preview.json"
TRIM_PREVIEW_MARKDOWN_FILENAME = "fixture_slate_trim_preview.md"
TRIM_PREVIEW_CSV_FILENAME = "fixture_slate_trim_preview.csv"
TRIM_AUDIT_CSV_FILENAME = "fixture_slate_trim_audit.csv"
TRIM_AUDIT_MARKDOWN_FILENAME = "fixture_slate_trim_audit.md"

DEFERRED_ARCHIVE_DIRNAME = "deferred_fixtures"

TRIM_STATUSES = (
    "Trim preview ready",
    "Nothing to defer",
    "Needs fixture refresh",
    "Missing fixtures",
    "Trim applied",
    "Blocked",
)
DECISION_KEEP = "Keep (imminent matchweek)"
DECISION_DEFER = "Defer (later matchweek)"
DECISION_ATTENTION = "Keep (needs manual attention)"


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _read_fixtures(fixtures_path: Path) -> pd.DataFrame:
    return pd.read_csv(fixtures_path, dtype=str, keep_default_na=False)


def _confirmation_id(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        {
            "fixtures_path": payload["fixtures_path"],
            "fixtures_checksum_sha256": payload["fixtures_checksum_sha256"],
            "kept_count": payload["kept_count"],
            "deferred_count": payload["deferred_count"],
            "attention_count": payload["attention_count"],
        },
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _decisions(
    fixtures: pd.DataFrame,
    today: date,
) -> tuple[list[str], list[str], int]:
    parsed = pd.to_datetime(fixtures["date"], errors="coerce", format="mixed")
    row_dates: list[date | None] = [
        value.date() if pd.notna(value) else None for value in parsed
    ]
    future_dates = [value for value in row_dates if value is not None and value >= today]
    groups = _assign_matchweek_groups(future_dates)
    first_group_dates = {value for value, group in groups.items() if group == 0}
    group_count = (max(groups.values()) + 1) if groups else 0

    decisions: list[str] = []
    notes: list[str] = []
    for value in row_dates:
        if value is None:
            decisions.append(DECISION_ATTENTION)
            notes.append("Unreadable date; fix it manually. Trim never drops this row.")
        elif value < today:
            decisions.append(DECISION_ATTENTION)
            notes.append(
                "Past date; remove or fix it manually. Trim never drops this row."
            )
        elif value in first_group_dates:
            decisions.append(DECISION_KEEP)
            notes.append("Imminent matchweek group.")
        else:
            decisions.append(DECISION_DEFER)
            notes.append("Later matchweek group; deferred until its odds are posted.")
    return decisions, notes, group_count


def build_fixture_slate_trim_preview(
    fixtures_path: Path | None = None,
    *,
    today: date | None = None,
) -> dict[str, object]:
    """Preview keeping only the imminent matchweek group. Nothing is edited."""
    fixtures_path = fixtures_path or MANUAL_DIR / "upcoming_fixtures.csv"
    today = today or date.today()

    if not fixtures_path.exists():
        return {
            "status": "Missing fixtures",
            "message": f"No fixture slate exists at {fixtures_path}.",
            "fixtures_path": str(fixtures_path),
            "confirm_id": "",
            "rows": pd.DataFrame(),
            "kept_count": 0,
            "deferred_count": 0,
            "attention_count": 0,
            "matchweek_group_count": 0,
        }

    raw_bytes = fixtures_path.read_bytes()
    fixtures = _read_fixtures(fixtures_path)
    if fixtures.empty or not {"date", "home_team", "away_team"}.issubset(fixtures.columns):
        return {
            "status": "Needs fixture refresh",
            "message": (
                f"The slate at {fixtures_path} is empty or missing required columns; "
                "there is nothing safe to trim."
            ),
            "fixtures_path": str(fixtures_path),
            "confirm_id": "",
            "rows": pd.DataFrame(),
            "kept_count": 0,
            "deferred_count": 0,
            "attention_count": 0,
            "matchweek_group_count": 0,
        }

    decisions, notes, group_count = _decisions(fixtures, today)
    rows = fixtures.copy()
    rows["trim_decision"] = decisions
    rows["trim_note"] = notes

    kept_count = int(sum(decision == DECISION_KEEP for decision in decisions))
    deferred_count = int(sum(decision == DECISION_DEFER for decision in decisions))
    attention_count = int(sum(decision == DECISION_ATTENTION for decision in decisions))

    if kept_count == 0:
        status = "Needs fixture refresh"
        message = (
            "No upcoming fixtures were found in the slate; refresh "
            "`data/manual/upcoming_fixtures.csv` instead of trimming."
        )
        confirm_id = ""
    elif deferred_count == 0:
        status = "Nothing to defer"
        message = (
            "The slate already covers a single upcoming matchweek group; no trim is "
            "needed."
        )
        confirm_id = ""
    else:
        status = "Trim preview ready"
        message = (
            f"Trimming would keep {kept_count} imminent fixture(s), defer "
            f"{deferred_count} later fixture(s) to a dated archive, and leave "
            f"{attention_count} row(s) needing manual attention untouched."
        )
        confirm_id = ""

    payload = {
        "status": status,
        "message": message,
        "fixtures_path": str(fixtures_path),
        "fixtures_checksum_sha256": sha256(raw_bytes).hexdigest(),
        "checked_on": today.isoformat(),
        "kept_count": kept_count,
        "deferred_count": deferred_count,
        "attention_count": attention_count,
        "matchweek_group_count": group_count,
    }
    if status == "Trim preview ready":
        confirm_id = _confirmation_id(payload)
    payload["confirm_id"] = confirm_id
    payload["rows"] = rows
    return payload


def _render_preview_markdown(preview: dict[str, object]) -> str:
    rows: pd.DataFrame = preview["rows"]
    lines = [
        "# Fixture Slate Trim Preview",
        "",
        (
            "Preview only: nothing was edited. Trimming keeps the imminent matchweek "
            "group in `upcoming_fixtures.csv`, moves later matchweek fixtures to a "
            "dated deferred-fixtures archive, and never touches rows that need manual "
            "attention. It never edits odds, fabricates prices, or places bets."
        ),
        "",
        f"- Status: **{preview['status']}**",
        f"- {preview['message']}",
        f"- Fixture file: `{preview['fixtures_path']}`",
        f"- Upcoming matchweek groups found: {preview['matchweek_group_count']}",
        (
            f"- Keep: {preview['kept_count']} | Defer: {preview['deferred_count']} | "
            f"Needs attention: {preview['attention_count']}"
        ),
    ]
    if preview["confirm_id"]:
        lines.extend(
            [
                "",
                "To apply this exact trim from Terminal:",
                "",
                "```bash",
                "python scripts/trim_upcoming_fixtures.py \\",
                "  --apply \\",
                f"  --confirm-id {preview['confirm_id']}",
                "```",
                "",
                (
                    "Apply is blocked if the fixture file changed after this preview. "
                    "After applying, rerun "
                    "`python scripts/run_week1_launch_readiness.py` and review its "
                    "odds-template guidance so the odds file matches the trimmed slate."
                ),
            ]
        )
    lines.extend(["", "## Row decisions", ""])
    if isinstance(rows, pd.DataFrame) and not rows.empty:
        lines.append(rows.to_markdown(index=False))
    else:
        lines.append("No fixture rows were available.")
    return "\n".join(lines)


def save_fixture_slate_trim_preview(
    preview: dict[str, object],
    output_dir: Path | None = None,
) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: pd.DataFrame = preview["rows"]
    json_payload = {
        key: value for key, value in preview.items() if key != "rows"
    }
    json_path = output_dir / TRIM_PREVIEW_JSON_FILENAME
    markdown_path = output_dir / TRIM_PREVIEW_MARKDOWN_FILENAME
    csv_path = output_dir / TRIM_PREVIEW_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(json_payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        (_render_preview_markdown(preview) + "\n").encode("utf-8"),
    )
    csv_bytes = (
        rows.to_csv(index=False).encode("utf-8")
        if isinstance(rows, pd.DataFrame) and not rows.empty
        else b"trim_decision\n"
    )
    atomic_write_report(csv_path, csv_bytes)
    return {"json": json_path, "markdown": markdown_path, "csv": csv_path}


def _timestamped_path(directory: Path, stem: str, suffix: str, now: datetime) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    base = now.strftime("%Y%m%d_%H%M%S")
    candidate = directory / f"{base}_{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{base}_{stem}_{counter:02d}{suffix}"
        counter += 1
    return candidate


def _write_audit(
    output_dir: Path,
    record: dict[str, object],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / TRIM_AUDIT_CSV_FILENAME
    frame = pd.DataFrame([record])
    if csv_path.exists():
        try:
            existing = pd.read_csv(csv_path, dtype=str)
            frame = pd.concat([existing, frame.astype(str)], ignore_index=True)
        except (OSError, UnicodeError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
            pass
    atomic_write_report(csv_path, frame.to_csv(index=False).encode("utf-8"))
    markdown_path = output_dir / TRIM_AUDIT_MARKDOWN_FILENAME
    lines = [
        "# Fixture Slate Trim Audit",
        "",
        "Most recent apply attempt:",
        "",
    ]
    lines.extend([f"- {key}: {value}" for key, value in record.items()])
    atomic_write_report(markdown_path, ("\n".join(lines) + "\n").encode("utf-8"))
    return {"csv": csv_path, "markdown": markdown_path}


def apply_fixture_slate_trim(
    fixtures_path: Path | None = None,
    *,
    confirm_id: str,
    manual_dir: Path | None = None,
    output_dir: Path | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Apply a previewed trim after re-verifying the confirmation gate."""
    fixtures_path = fixtures_path or MANUAL_DIR / "upcoming_fixtures.csv"
    manual_dir = manual_dir or fixtures_path.parent
    output_dir = output_dir or OUTPUTS_DIR
    now = now or datetime.now()

    preview = build_fixture_slate_trim_preview(fixtures_path, today=today)
    gate_note = ""
    if preview["status"] != "Trim preview ready":
        gate_note = (
            f"Nothing was applied: the current slate state is '{preview['status']}'."
        )
    elif not confirm_id or confirm_id.strip() != preview["confirm_id"]:
        gate_note = (
            "Nothing was applied: the provided confirmation ID does not match the "
            "current fixture file. Run the preview again and copy its exact "
            "confirmation ID."
        )
    if gate_note:
        record = {
            "applied_at": now.isoformat(timespec="seconds"),
            "status": "Blocked",
            "gate_note": gate_note,
            "fixtures_path": str(fixtures_path),
            "provided_confirm_id": confirm_id,
            "expected_confirm_id": preview.get("confirm_id", ""),
            "backup_path": "",
            "deferred_archive_path": "",
            "kept_count": preview.get("kept_count", 0),
            "deferred_count": preview.get("deferred_count", 0),
            "attention_count": preview.get("attention_count", 0),
        }
        paths = _write_audit(output_dir, record)
        return {"status": "Blocked", "message": gate_note, "audit": paths, "preview": preview}

    rows: pd.DataFrame = preview["rows"]
    kept_mask = rows["trim_decision"] != DECISION_DEFER
    deferred_mask = ~kept_mask
    original_columns = [
        column for column in rows.columns if column not in ("trim_decision", "trim_note")
    ]
    kept = rows.loc[kept_mask, original_columns]
    deferred = rows.loc[deferred_mask, original_columns]

    backup_dir = manual_dir / "backups"
    backup_path = _timestamped_path(backup_dir, "upcoming_fixtures_pre_trim", ".csv", now)
    backup_path.write_bytes(fixtures_path.read_bytes())

    archive_dir = manual_dir / "archive" / DEFERRED_ARCHIVE_DIRNAME
    deferred_archive_path = _timestamped_path(
        archive_dir, "deferred_fixtures", ".csv", now
    )
    atomic_write_report(
        deferred_archive_path, deferred.to_csv(index=False).encode("utf-8")
    )
    archived = pd.read_csv(deferred_archive_path, dtype=str, keep_default_na=False)
    if len(archived) != len(deferred):
        raise RuntimeError(
            "The deferred-fixtures archive did not verify; the fixture slate was "
            "not modified."
        )

    atomic_write_report(fixtures_path, kept.to_csv(index=False).encode("utf-8"))

    record = {
        "applied_at": now.isoformat(timespec="seconds"),
        "status": "Trim applied",
        "gate_note": "Confirmation ID and file checksum matched the preview.",
        "fixtures_path": str(fixtures_path),
        "provided_confirm_id": confirm_id,
        "expected_confirm_id": preview["confirm_id"],
        "backup_path": str(backup_path),
        "deferred_archive_path": str(deferred_archive_path),
        "kept_count": int(len(kept)),
        "deferred_count": int(len(deferred)),
        "attention_count": preview["attention_count"],
    }
    paths = _write_audit(output_dir, record)
    return {
        "status": "Trim applied",
        "message": (
            f"Kept {len(kept)} fixture row(s), archived {len(deferred)} deferred "
            f"row(s) to {deferred_archive_path}, and backed up the original slate to "
            f"{backup_path}."
        ),
        "backup_path": backup_path,
        "deferred_archive_path": deferred_archive_path,
        "audit": paths,
        "preview": preview,
    }
