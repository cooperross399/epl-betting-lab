from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.claude_thursday_handoff import (
    PACKET_CSV_FILENAME,
    PACKET_JSON_FILENAME,
    PACKET_MARKDOWN_FILENAME,
    build_claude_thursday_packet,
    load_latest_pipeline_summary,
    run_claude_thursday_handoff,
)


FIXED_RUN_AT = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)


def _ready_summary() -> dict[str, object]:
    return {
        "run_timestamp": "2026-08-13T09:00:00+00:00",
        "status": "Ready for card review",
        "key_blockers": [],
        "key_warnings": ["Current odds: one book name is blank."],
        "card_counts": {
            "best_bets": 1,
            "leans": 1,
            "passes": 1,
            "total_candidates": 3,
        },
        "decision_queue_counts": {"Review price": 1},
        "ledger_health_summary": {
            "error_count": 0,
            "warning_count": 1,
            "info_count": 2,
        },
        "ledger_summary": {
            "tracked_bets": 4,
            "pending_bets": 1,
            "profit_units": 1.25,
            "roi": 0.31,
        },
        "recommended_next_action": "Review the generated Thursday card manually.",
        "archive_receipt_id": "epl-weekly-abc123",
        "archive_path": "data/outputs/archive/epl_weekly_pipeline/2026-08-13/090000",
        "receipt_verification_verdict": "Weekly pipeline receipt verified",
        "receipt_verification_mismatch_count": 0,
        "verification_sidecar_verdict": "Verification sidecar archived",
        "sidecar_verification_verdict": "Weekly verification sidecar verified",
        "sidecar_verification_archive_verdict": "Sidecar verification archived",
        "safety": {
            "force_mode_used": False,
            "settlement_applied": False,
            "manual_files_edited": False,
            "live_provider_run": False,
            "cron_enabled": False,
            "bets_placed": False,
        },
        "steps": [
            {
                "step": "Current odds validation",
                "status": "Completed",
                "message": "Current odds validation found 0 serious issue(s) and 1 warning(s).",
                "warnings": [],
                "blockers": [],
                "outputs": [],
                "metadata": {"serious_issue_count": 0, "warning_count": 1},
            },
            {
                "step": "Current odds completeness",
                "status": "Completed",
                "message": "Odds completeness is 100.0%; 0 match(es) are incomplete.",
                "warnings": [],
                "blockers": [],
                "outputs": [],
                "metadata": {
                    "completion_percentage": 1.0,
                    "total_rows": 7,
                    "rows_missing_odds": 0,
                    "rows_non_numeric_odds": 0,
                    "missing_expected_rows": 0,
                    "matches_incomplete": 0,
                },
            },
        ],
    }


def _needs_odds_summary() -> dict[str, object]:
    summary = _ready_summary()
    summary.update(
        {
            "status": "Needs odds",
            "key_blockers": ["Current odds are missing."],
            "key_warnings": [],
            "card_counts": {
                "best_bets": 0,
                "leans": 0,
                "passes": 0,
                "total_candidates": 0,
            },
            "recommended_next_action": (
                "Create or import real current odds, fill every sportsbook price and "
                "book, then rerun `python scripts/run_epl_weekly_pipeline.py`."
            ),
        }
    )
    return summary


def _write_pipeline_summary(output_dir: Path, summary: dict[str, object]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "epl_weekly_pipeline.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    return path


def _write_card(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    card = pd.DataFrame(
        [
            {
                "section": "Best bets",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "market": "1x2",
                "selection": "home",
                "status": "BETTABLE",
                "confidence_tier": "A",
                "american_odds": -120,
                "fair_american": -145,
                "calibrated_model_prob": 0.59,
                "calibrated_edge": 0.045,
                "suggested_units": 0.5,
                "book": "FanDuel",
                "risk_flags": "",
                "qualifies_reason": "Calibrated edge above minimum.",
            },
            {
                "section": "Leans",
                "home_team": "Liverpool",
                "away_team": "Everton",
                "market": "btts",
                "selection": "yes",
                "status": "LEAN",
                "confidence_tier": "C",
                "american_odds": 105,
                "fair_american": -102,
                "calibrated_model_prob": 0.505,
                "calibrated_edge": 0.02,
                "suggested_units": 0.1,
                "book": "FanDuel",
                "risk_flags": "plus_money",
                "qualifies_reason": "Small calibrated edge.",
            },
            {
                "section": "Passes / notable avoids",
                "home_team": "Man City",
                "away_team": "Fulham",
                "market": "1x2",
                "selection": "home",
                "status": "PASS",
                "confidence_tier": "Pass/Avoid",
                "american_odds": -300,
                "fair_american": -280,
                "calibrated_model_prob": 0.72,
                "calibrated_edge": -0.01,
                "suggested_units": 0.0,
                "book": "FanDuel",
                "risk_flags": "heavy_juice",
                "qualifies_reason": "Worse than the -160 max-juice guard.",
            },
        ]
    )
    path = output_dir / "thursday_best_bets.csv"
    card.to_csv(path, index=False)
    return path


def _write_clv(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    clv = pd.DataFrame(
        [
            {
                "market": "1x2",
                "bets": 3,
                "with_closing_odds": 2,
                "missing_closing_odds": 1,
                "avg_clv_probability_points": 0.012,
            },
            {
                "market": "total_2_5",
                "bets": 1,
                "with_closing_odds": 0,
                "missing_closing_odds": 1,
                "avg_clv_probability_points": None,
            },
        ]
    )
    path = output_dir / "clv_by_market.csv"
    clv.to_csv(path, index=False)
    return path


def test_read_latest_ready_packet_includes_card_and_receipts(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    _write_pipeline_summary(output_dir, _ready_summary())
    _write_card(output_dir)
    _write_clv(output_dir)

    result = run_claude_thursday_handoff(
        read_latest=True,
        output_dir=output_dir,
        repository_root=tmp_path,
        run_at=FIXED_RUN_AT,
    )

    assert result["status"] == "Ready for card review"
    assert result["card_ready"] is True
    packet = result["packet"]
    assert packet["source_mode"] == "read_latest"
    assert len(packet["best_bets"]) == 1
    assert packet["best_bets"][0]["home_team"] == "Arsenal"
    assert len(packet["leans"]) == 1
    assert len(packet["passes_and_avoids"]) == 1
    assert packet["archive"]["receipt_id"] == "epl-weekly-abc123"
    assert (
        packet["archive"]["receipt_verification_verdict"]
        == "Weekly pipeline receipt verified"
    )
    assert (
        packet["archive"]["sidecar_verification_verdict"]
        == "Weekly verification sidecar verified"
    )
    assert packet["odds_validation"]["serious_issue_count"] == 0
    assert packet["odds_completeness"]["completion_percentage"] == 1.0
    assert packet["clv_summary"]["available"] is True
    assert packet["clv_summary"]["tracked_bets"] == 4
    assert packet["clv_summary"]["with_closing_odds"] == 2
    assert packet["ledger_available"] is True
    assert packet["ledger_summary"]["tracked_bets"] == 4
    assert packet["ledger_health"]["warning_count"] == 1
    assert packet["safety"]["odds_fabricated"] is False
    assert packet["safety"]["bets_placed"] is False

    for filename in (
        PACKET_JSON_FILENAME,
        PACKET_MARKDOWN_FILENAME,
        PACKET_CSV_FILENAME,
    ):
        assert (output_dir / filename).exists()

    saved = json.loads((output_dir / PACKET_JSON_FILENAME).read_text(encoding="utf-8"))
    assert saved["pipeline_status"] == "Ready for card review"
    assert saved["card_ready"] is True

    markdown = (output_dir / PACKET_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    assert "Card ready: **Yes**" in markdown
    assert "Arsenal" in markdown
    assert "epl-weekly-abc123" in markdown


def test_read_latest_needs_odds_reports_no_card_and_blockers(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    _write_pipeline_summary(output_dir, _needs_odds_summary())
    # A stale card from a previous week must not leak into the packet.
    _write_card(output_dir)

    result = run_claude_thursday_handoff(
        read_latest=True,
        output_dir=output_dir,
        repository_root=tmp_path,
        run_at=FIXED_RUN_AT,
    )

    assert result["status"] == "Needs odds"
    assert result["card_ready"] is False
    packet = result["packet"]
    assert packet["best_bets"] == []
    assert packet["leans"] == []
    assert packet["passes_and_avoids"] == []
    assert "No card is ready." in packet["card_ready_note"]
    assert packet["blockers"] == ["Current odds are missing."]

    markdown = (output_dir / PACKET_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    assert "## No card is ready" in markdown
    assert "Current odds are missing." in markdown

    csv_rows = pd.read_csv(output_dir / PACKET_CSV_FILENAME)
    assert len(csv_rows) == 1
    assert csv_rows.iloc[0]["row_type"] == "summary"
    assert csv_rows.iloc[0]["card_ready"] == False  # noqa: E712
    assert "Current odds are missing." in str(csv_rows.iloc[0]["blockers"])


def test_needs_odds_without_recorded_blockers_gets_a_clear_default(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    summary = _needs_odds_summary()
    summary["key_blockers"] = []

    packet = build_claude_thursday_packet(
        summary,
        output_dir=output_dir,
        source_mode="read_latest",
        source_note="test",
        generated_at=FIXED_RUN_AT,
    )

    assert packet["card_ready"] is False
    assert len(packet["blockers"]) == 1
    assert "Current odds are missing" in packet["blockers"][0]


def test_read_latest_with_missing_summary_is_safe(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"

    result = run_claude_thursday_handoff(
        read_latest=True,
        output_dir=output_dir,
        repository_root=tmp_path,
        run_at=FIXED_RUN_AT,
    )

    assert result["status"] == "No weekly pipeline summary available"
    assert result["card_ready"] is False
    packet = result["packet"]
    assert packet["best_bets"] == []
    assert len(packet["blockers"]) == 1
    assert "run_epl_weekly_pipeline.py" in packet["blockers"][0]
    assert "run_epl_weekly_pipeline.py" in packet["recommended_next_action"]
    assert (output_dir / PACKET_JSON_FILENAME).exists()
    assert (output_dir / PACKET_MARKDOWN_FILENAME).exists()
    assert (output_dir / PACKET_CSV_FILENAME).exists()


def test_load_latest_pipeline_summary_rejects_malformed_json(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True)
    (output_dir / "epl_weekly_pipeline.json").write_text("[1, 2, 3]", encoding="utf-8")

    summary, note = load_latest_pipeline_summary(output_dir)

    assert summary is None
    assert "not a JSON object" in note


def test_default_mode_runs_the_safe_pipeline_via_runner(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    _write_card(output_dir)
    calls: list[dict[str, object]] = []

    def fake_runner(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"summary": _ready_summary()}

    result = run_claude_thursday_handoff(
        read_latest=False,
        output_dir=output_dir,
        repository_root=tmp_path,
        run_at=FIXED_RUN_AT,
        pipeline_runner=fake_runner,
    )

    assert len(calls) == 1
    assert calls[0]["output_dir"] == output_dir
    assert result["card_ready"] is True
    assert result["packet"]["source_mode"] == "pipeline_run"
    assert "safe weekly pipeline was run" in result["packet"]["source_note"]


def test_missing_clv_and_ledger_sections_stay_unavailable(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    summary = _ready_summary()
    summary["ledger_summary"] = {}
    summary["ledger_health_summary"] = {}
    _write_pipeline_summary(output_dir, summary)
    _write_card(output_dir)

    result = run_claude_thursday_handoff(
        read_latest=True,
        output_dir=output_dir,
        repository_root=tmp_path,
        run_at=FIXED_RUN_AT,
    )

    packet = result["packet"]
    assert packet["clv_summary"]["available"] is False
    assert packet["ledger_available"] is False

    markdown = (output_dir / PACKET_MARKDOWN_FILENAME).read_text(encoding="utf-8")
    assert "## CLV summary" in markdown
    assert "Not available" in markdown


def test_csv_has_one_play_row_per_card_play(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    _write_pipeline_summary(output_dir, _ready_summary())
    _write_card(output_dir)

    run_claude_thursday_handoff(
        read_latest=True,
        output_dir=output_dir,
        repository_root=tmp_path,
        run_at=FIXED_RUN_AT,
    )

    csv_rows = pd.read_csv(output_dir / PACKET_CSV_FILENAME)
    assert len(csv_rows) == 3
    assert set(csv_rows["row_type"]) == {"play"}
    assert list(csv_rows["section"]) == [
        "Best bets",
        "Leans",
        "Passes / notable avoids",
    ]
    assert (csv_rows["archive_receipt_id"] == "epl-weekly-abc123").all()
    assert (csv_rows["pipeline_status"] == "Ready for card review").all()


def test_missing_card_csv_on_ready_run_is_reported_without_guessing(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    _write_pipeline_summary(output_dir, _ready_summary())

    result = run_claude_thursday_handoff(
        read_latest=True,
        output_dir=output_dir,
        repository_root=tmp_path,
        run_at=FIXED_RUN_AT,
    )

    packet = result["packet"]
    assert packet["card_ready"] is True
    assert packet["best_bets"] == []
    assert "No Thursday card CSV was found" in packet["card_note"]
