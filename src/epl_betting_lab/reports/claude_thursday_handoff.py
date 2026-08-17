from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.providers.base import atomic_write_report
from epl_betting_lab.reports.epl_weekly_pipeline import (
    PIPELINE_JSON_FILENAME,
    run_epl_weekly_pipeline,
)


PACKET_JSON_FILENAME = "claude_thursday_epl_packet.json"
PACKET_MARKDOWN_FILENAME = "claude_thursday_epl_packet.md"
PACKET_CSV_FILENAME = "claude_thursday_epl_packet.csv"

CARD_READY_STATUSES = ("Ready for card review", "Card generated with warnings")
MISSING_SUMMARY_STATUS = "No weekly pipeline summary available"
NO_CARD_MESSAGE = "No card is ready."

CARD_SECTIONS = ("Best bets", "Leans", "Passes / notable avoids")
CARD_ROW_COLUMNS = [
    "section",
    "home_team",
    "away_team",
    "market",
    "selection",
    "status",
    "confidence_tier",
    "american_odds",
    "fair_american",
    "calibrated_model_prob",
    "calibrated_edge",
    "suggested_units",
    "book",
    "risk_flags",
    "qualifies_reason",
]
CSV_PLAY_COLUMNS = [
    "section",
    "home_team",
    "away_team",
    "market",
    "selection",
    "status",
    "confidence_tier",
    "american_odds",
    "calibrated_model_prob",
    "calibrated_edge",
    "suggested_units",
    "book",
]
VALIDATION_STEP_NAME = "Current odds validation"
COMPLETENESS_STEP_NAME = "Current odds completeness"


def _json_safe(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
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


def _strings(items: object) -> list[str]:
    if not isinstance(items, (list, tuple)):
        return []
    return [str(item) for item in items if str(item).strip()]


def load_latest_pipeline_summary(output_dir: Path) -> tuple[dict[str, object] | None, str]:
    """Read the most recent weekly pipeline JSON summary without rerunning it."""
    path = output_dir / PIPELINE_JSON_FILENAME
    if not path.exists():
        return None, (
            f"No weekly pipeline summary was found at {path}. Run "
            "`python scripts/run_epl_weekly_pipeline.py` first, or rerun this "
            "command without --read-latest."
        )
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return None, f"The weekly pipeline summary at {path} could not be read: {exc}"
    if not isinstance(loaded, dict):
        return None, f"The weekly pipeline summary at {path} is not a JSON object."
    return loaded, f"Read the latest weekly pipeline summary from {path}."


def _step_lookup(summary: dict[str, object], step_name: str) -> dict[str, object]:
    steps = summary.get("steps")
    if not isinstance(steps, list):
        return {}
    for step in steps:
        if isinstance(step, dict) and str(step.get("step", "")) == step_name:
            return step
    return {}


def _odds_validation_section(summary: dict[str, object]) -> dict[str, object]:
    step = _step_lookup(summary, VALIDATION_STEP_NAME)
    metadata = step.get("metadata") if isinstance(step.get("metadata"), dict) else {}
    return {
        "step_status": str(step.get("status", "Not checked")),
        "message": str(step.get("message", "Current odds validation was not recorded.")),
        "serious_issue_count": metadata.get("serious_issue_count"),
        "warning_count": metadata.get("warning_count"),
        "blockers": _strings(step.get("blockers")),
    }


def _odds_completeness_section(summary: dict[str, object]) -> dict[str, object]:
    step = _step_lookup(summary, COMPLETENESS_STEP_NAME)
    metadata = step.get("metadata") if isinstance(step.get("metadata"), dict) else {}
    return {
        "step_status": str(step.get("status", "Not checked")),
        "message": str(step.get("message", "Odds completeness was not recorded.")),
        "completion_percentage": metadata.get("completion_percentage"),
        "total_rows": metadata.get("total_rows"),
        "rows_missing_odds": metadata.get("rows_missing_odds"),
        "rows_non_numeric_odds": metadata.get("rows_non_numeric_odds"),
        "missing_expected_rows": metadata.get("missing_expected_rows"),
        "matches_incomplete": metadata.get("matches_incomplete"),
    }


def _load_card_rows(output_dir: Path) -> tuple[dict[str, list[dict[str, object]]], str]:
    empty = {section: [] for section in CARD_SECTIONS}
    card_path = output_dir / "thursday_best_bets.csv"
    if not card_path.exists():
        return empty, f"No Thursday card CSV was found at {card_path}."
    try:
        report = pd.read_csv(card_path)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        return empty, f"The Thursday card at {card_path} could not be read: {exc}"
    if report.empty or "section" not in report.columns:
        return empty, f"The Thursday card at {card_path} has no play sections."
    columns = [column for column in CARD_ROW_COLUMNS if column in report.columns]
    grouped = dict(empty)
    for section in CARD_SECTIONS:
        subset = report[report["section"].astype(str) == section]
        grouped[section] = [
            {column: _json_safe(row[column]) for column in columns}
            for _, row in subset.iterrows()
        ]
    return grouped, f"Card plays were read from {card_path}."


def _load_clv_summary(output_dir: Path) -> dict[str, object]:
    clv_path = output_dir / "clv_by_market.csv"
    if not clv_path.exists():
        return {
            "available": False,
            "note": f"No CLV report was found at {clv_path}. Run `python scripts/run_backtest.py` or enter closing odds first.",
        }
    try:
        clv = pd.read_csv(clv_path)
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        return {"available": False, "note": f"The CLV report at {clv_path} could not be read: {exc}"}
    if clv.empty or "bets" not in clv.columns:
        return {
            "available": True,
            "note": "The CLV report exists but has no tracked rows yet.",
            "tracked_bets": 0,
            "with_closing_odds": 0,
            "avg_clv_probability_points": None,
        }
    with_close = (
        int(pd.to_numeric(clv["with_closing_odds"], errors="coerce").fillna(0).sum())
        if "with_closing_odds" in clv.columns
        else 0
    )
    avg_clv = None
    if "avg_clv_probability_points" in clv.columns:
        values = pd.to_numeric(clv["avg_clv_probability_points"], errors="coerce").dropna()
        if not values.empty:
            avg_clv = round(float(values.mean()), 4)
    return {
        "available": True,
        "note": "CLV values stay blank until real closing odds are entered; nothing is guessed.",
        "tracked_bets": int(pd.to_numeric(clv["bets"], errors="coerce").fillna(0).sum()),
        "with_closing_odds": with_close,
        "avg_clv_probability_points": avg_clv,
        "by_market": [
            {key: _json_safe(value) for key, value in row.items()}
            for row in clv.to_dict(orient="records")
        ],
    }


def build_claude_thursday_packet(
    pipeline_summary: dict[str, object] | None,
    *,
    output_dir: Path,
    source_mode: str,
    source_note: str,
    generated_at: datetime,
) -> dict[str, object]:
    """Assemble the read-only Claude handoff packet from existing reports."""
    summary = pipeline_summary or {}
    pipeline_status = str(summary.get("status", MISSING_SUMMARY_STATUS))
    card_ready = pipeline_status in CARD_READY_STATUSES

    blockers = _strings(summary.get("key_blockers"))
    warnings = _strings(summary.get("key_warnings"))
    if pipeline_summary is None:
        blockers = [source_note]

    if card_ready:
        card_rows, card_note = _load_card_rows(output_dir)
        card_ready_note = (
            "A gated Thursday card is ready for manual review. Confirm every "
            "sportsbook price before deciding whether to bet."
        )
    else:
        card_rows = {section: [] for section in CARD_SECTIONS}
        card_note = (
            "Card plays were intentionally left empty because the weekly pipeline "
            "did not produce a card-ready run."
        )
        card_ready_note = f"{NO_CARD_MESSAGE} The weekly pipeline status is '{pipeline_status}'."
        if pipeline_status == "Needs odds" and not blockers:
            blockers = [
                "Current odds are missing. Fill data/manual/current_odds.csv with "
                "real sportsbook prices before a card can be generated."
            ]

    ledger_summary = summary.get("ledger_summary")
    ledger_summary = ledger_summary if isinstance(ledger_summary, dict) else {}
    ledger_health = summary.get("ledger_health_summary")
    ledger_health = ledger_health if isinstance(ledger_health, dict) else {}
    card_counts = summary.get("card_counts")
    card_counts = card_counts if isinstance(card_counts, dict) else {}

    recommended = str(
        summary.get(
            "recommended_next_action",
            "Run `python scripts/run_epl_weekly_pipeline.py` to create a fresh weekly summary.",
        )
    )
    safety = summary.get("safety") if isinstance(summary.get("safety"), dict) else {}

    packet = {
        "packet_type": "claude_thursday_epl_packet",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "source_mode": source_mode,
        "source_note": source_note,
        "pipeline_run_timestamp": summary.get("run_timestamp"),
        "pipeline_status": pipeline_status,
        "card_ready": card_ready,
        "card_ready_note": card_ready_note,
        "card_note": card_note,
        "card_counts": {
            "best_bets": int(card_counts.get("best_bets", 0) or 0),
            "leans": int(card_counts.get("leans", 0) or 0),
            "passes": int(card_counts.get("passes", 0) or 0),
            "total_candidates": int(card_counts.get("total_candidates", 0) or 0),
        },
        "best_bets": card_rows["Best bets"],
        "leans": card_rows["Leans"],
        "passes_and_avoids": card_rows["Passes / notable avoids"],
        "blockers": blockers,
        "warnings": warnings,
        "odds_validation": _odds_validation_section(summary),
        "odds_completeness": _odds_completeness_section(summary),
        "clv_summary": _load_clv_summary(output_dir),
        "ledger_available": bool(ledger_summary),
        "ledger_summary": _json_safe(ledger_summary),
        "ledger_health": _json_safe(ledger_health),
        "archive": {
            "receipt_id": summary.get("archive_receipt_id") or None,
            "archive_path": summary.get("archive_path") or None,
            "receipt_verification_verdict": summary.get("receipt_verification_verdict")
            or "Not checked",
            "receipt_verification_mismatch_count": int(
                summary.get("receipt_verification_mismatch_count", 0) or 0
            ),
            "verification_sidecar_verdict": summary.get("verification_sidecar_verdict")
            or "Not archived",
            "sidecar_verification_verdict": summary.get("sidecar_verification_verdict")
            or "Not checked",
            "sidecar_verification_archive_verdict": summary.get(
                "sidecar_verification_archive_verdict"
            )
            or "Not archived",
        },
        "recommended_next_action": recommended,
        "safety": {
            "report_only": True,
            "odds_fabricated": False,
            "bets_placed": bool(safety.get("bets_placed", False)),
            "force_mode_used": bool(safety.get("force_mode_used", False)),
            "settlement_applied": bool(safety.get("settlement_applied", False)),
            "manual_files_edited": bool(safety.get("manual_files_edited", False)),
            "live_provider_run": bool(safety.get("live_provider_run", False)),
            "cron_enabled": bool(safety.get("cron_enabled", False)),
        },
    }
    return packet


def _play_table(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["- None."]
    table = pd.DataFrame(rows)
    columns = [column for column in CSV_PLAY_COLUMNS if column in table.columns]
    if columns:
        table = table[columns]
    return [table.to_markdown(index=False)]


def render_packet_markdown(packet: dict[str, object]) -> str:
    validation = packet["odds_validation"]
    completeness = packet["odds_completeness"]
    clv = packet["clv_summary"]
    ledger = packet["ledger_summary"]
    health = packet["ledger_health"]
    archive = packet["archive"]
    counts = packet["card_counts"]

    lines = [
        "# Claude Thursday EPL Packet",
        "",
        (
            "This packet is a read-only handoff built from existing weekly pipeline "
            "reports. It never fabricates odds, places bets, uses force mode, applies "
            "settlement, runs live providers, edits protected manual files, or enables cron."
        ),
        "",
        "## Status",
        "",
        f"- Generated at: {packet['generated_at']}",
        f"- Source mode: {packet['source_mode']}",
        f"- Weekly pipeline status: **{packet['pipeline_status']}**",
        f"- Card ready: **{'Yes' if packet['card_ready'] else 'No'}**",
        f"- {packet['card_ready_note']}",
    ]
    if not packet["card_ready"]:
        lines.extend(
            [
                "",
                "## No card is ready",
                "",
                (
                    "The weekly pipeline did not produce a reviewable card. Do not pick "
                    "plays and do not invent odds. Resolve these blockers first:"
                ),
                "",
            ]
        )
        lines.extend([f"- {item}" for item in packet["blockers"]] or ["- No blocker detail was recorded."])
    lines.extend(
        [
            "",
            "## Card counts",
            "",
            (
                f"- {counts['best_bets']} best bet(s), {counts['leans']} lean(s), "
                f"{counts['passes']} pass/avoid row(s), "
                f"{counts['total_candidates']} total candidate(s)."
            ),
            "",
            "## Best bets",
            "",
        ]
    )
    lines.extend(_play_table(packet["best_bets"]))
    lines.extend(["", "## Leans", ""])
    lines.extend(_play_table(packet["leans"]))
    lines.extend(["", "## Passes / notable avoids", ""])
    lines.extend(_play_table(packet["passes_and_avoids"]))
    lines.extend(
        [
            "",
            "## Blockers",
            "",
        ]
    )
    lines.extend([f"- {item}" for item in packet["blockers"]] or ["- None."])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in packet["warnings"]] or ["- None."])
    lines.extend(
        [
            "",
            "## Current odds validation",
            "",
            f"- Step status: {validation['step_status']}",
            f"- {validation['message']}",
            f"- Serious issues: {validation['serious_issue_count'] if validation['serious_issue_count'] is not None else 'Not recorded'}",
            f"- Warnings: {validation['warning_count'] if validation['warning_count'] is not None else 'Not recorded'}",
            "",
            "## Odds completeness",
            "",
            f"- Step status: {completeness['step_status']}",
            f"- {completeness['message']}",
            f"- Rows missing odds: {completeness['rows_missing_odds'] if completeness['rows_missing_odds'] is not None else 'Not recorded'}",
            f"- Missing expected rows: {completeness['missing_expected_rows'] if completeness['missing_expected_rows'] is not None else 'Not recorded'}",
            f"- Incomplete matches: {completeness['matches_incomplete'] if completeness['matches_incomplete'] is not None else 'Not recorded'}",
            "",
            "## CLV summary",
            "",
        ]
    )
    if clv.get("available"):
        lines.extend(
            [
                f"- Tracked CLV bets: {clv.get('tracked_bets', 0)}",
                f"- Bets with closing odds: {clv.get('with_closing_odds', 0)}",
                (
                    "- Average CLV probability points: "
                    f"{clv['avg_clv_probability_points'] if clv.get('avg_clv_probability_points') is not None else 'Not available yet'}"
                ),
                f"- {clv.get('note', '')}",
            ]
        )
    else:
        lines.append(f"- Not available. {clv.get('note', '')}")
    lines.extend(["", "## Ledger summary", ""])
    if packet["ledger_available"]:
        lines.extend(
            [
                f"- Tracked bets: {ledger.get('tracked_bets', 0)}",
                f"- Pending bets: {ledger.get('pending_bets', 0)}",
                f"- Profit units: {ledger.get('profit_units', 0.0)}",
                f"- ROI: {ledger.get('roi', 0.0)}",
            ]
        )
    else:
        lines.append("- Not available. The weekly run did not record a ledger summary.")
    lines.extend(
        [
            "",
            "## Ledger health",
            "",
            (
                f"- {health.get('error_count', 0)} error(s), "
                f"{health.get('warning_count', 0)} warning(s), "
                f"{health.get('info_count', 0)} optional item(s)."
                if health
                else "- Not available. The weekly run did not record a ledger health check."
            ),
            "",
            "## Archive receipt and verification",
            "",
            f"- Archive receipt ID: `{archive['receipt_id'] or 'Not available'}`",
            f"- Archive path: `{archive['archive_path'] or 'Not available'}`",
            f"- Receipt verification: **{archive['receipt_verification_verdict']}** ({archive['receipt_verification_mismatch_count']} mismatch(es))",
            f"- Verification sidecar: **{archive['verification_sidecar_verdict']}**",
            f"- Sidecar verification: **{archive['sidecar_verification_verdict']}**",
            f"- Sidecar-verification archive: **{archive['sidecar_verification_archive_verdict']}**",
            "",
            "## Recommended next human action",
            "",
            f"- {packet['recommended_next_action']}",
            "",
            "## Human review remains required",
            "",
            (
                "This packet is research, not a bet slip. Respect the max-juice guard "
                "around -160, prefer alternate angles over heavy prices, and never treat "
                "a model edge as a guaranteed winner."
            ),
        ]
    )
    return "\n".join(lines)


def render_packet_csv(packet: dict[str, object]) -> bytes:
    archive = packet["archive"]
    shared = {
        "generated_at": packet["generated_at"],
        "source_mode": packet["source_mode"],
        "pipeline_status": packet["pipeline_status"],
        "card_ready": packet["card_ready"],
        "archive_receipt_id": archive["receipt_id"] or "",
        "receipt_verification_verdict": archive["receipt_verification_verdict"],
        "sidecar_verification_verdict": archive["sidecar_verification_verdict"],
        "blockers": " | ".join(packet["blockers"]),
        "recommended_next_action": packet["recommended_next_action"],
    }
    play_rows = []
    for section_key in ("best_bets", "leans", "passes_and_avoids"):
        for row in packet[section_key]:
            play_rows.append(
                {
                    "row_type": "play",
                    **shared,
                    **{column: row.get(column, "") for column in CSV_PLAY_COLUMNS},
                }
            )
    if not play_rows:
        play_rows.append(
            {
                "row_type": "summary",
                **shared,
                **{column: "" for column in CSV_PLAY_COLUMNS},
            }
        )
    return pd.DataFrame(play_rows).to_csv(index=False).encode("utf-8")


def save_claude_thursday_packet(
    packet: dict[str, object],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_packet = _json_safe(packet)
    if not isinstance(safe_packet, dict):
        raise TypeError("The Claude Thursday packet must serialize to a JSON object.")
    json_path = output_dir / PACKET_JSON_FILENAME
    markdown_path = output_dir / PACKET_MARKDOWN_FILENAME
    csv_path = output_dir / PACKET_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(safe_packet, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        (render_packet_markdown(safe_packet) + "\n").encode("utf-8"),
    )
    atomic_write_report(csv_path, render_packet_csv(safe_packet))
    return {"json": json_path, "markdown": markdown_path, "csv": csv_path}


def run_claude_thursday_handoff(
    *,
    read_latest: bool = False,
    current_odds_path: Path | None = None,
    fixtures_path: Path | None = None,
    matches_path: Path | None = None,
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
    repository_root: Path | None = None,
    run_at: datetime | None = None,
    pipeline_runner: Callable[..., dict[str, object]] | None = None,
    progress: Callable[[str, str, str], None] | None = None,
) -> dict[str, object]:
    """Create the Claude Thursday packet from a safe pipeline run or the latest summary."""
    repository_root = (repository_root or PROJECT_ROOT).resolve()
    selected_output_dir = output_dir or OUTPUTS_DIR
    if not selected_output_dir.is_absolute():
        selected_output_dir = (repository_root / selected_output_dir).resolve(strict=False)
    generated_at = run_at or datetime.now().astimezone()

    if read_latest:
        source_mode = "read_latest"
        pipeline_summary, source_note = load_latest_pipeline_summary(selected_output_dir)
    else:
        source_mode = "pipeline_run"
        runner = pipeline_runner or run_epl_weekly_pipeline
        result = runner(
            current_odds_path=current_odds_path,
            fixtures_path=fixtures_path,
            matches_path=matches_path,
            ledger_path=ledger_path,
            output_dir=output_dir,
            repository_root=repository_root,
            run_at=run_at,
            progress=progress,
        )
        pipeline_summary = result.get("summary") if isinstance(result, dict) else None
        if not isinstance(pipeline_summary, dict):
            pipeline_summary = None
            source_note = "The weekly pipeline run did not return a usable summary."
        else:
            source_note = "The safe weekly pipeline was run by this command."

    packet = build_claude_thursday_packet(
        pipeline_summary,
        output_dir=selected_output_dir,
        source_mode=source_mode,
        source_note=source_note,
        generated_at=generated_at,
    )
    paths = save_claude_thursday_packet(packet, selected_output_dir)
    return {
        "status": packet["pipeline_status"],
        "card_ready": packet["card_ready"],
        "packet": packet,
        "json": paths["json"],
        "markdown": paths["markdown"],
        "csv": paths["csv"],
    }
