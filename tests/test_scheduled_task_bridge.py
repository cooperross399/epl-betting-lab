from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.reports.scheduled_task_bridge import (
    BLOCKER_NEEDS_BTTS,
    BLOCKER_NEEDS_MAPPING,
    BLOCKER_NEEDS_ODDS,
    BLOCKER_NEEDS_VALIDATION,
    BLOCKER_PROVIDER_NOT_TRUSTED,
    build_epl_card_task,
    build_epl_model_task,
    build_epl_settle_preview_task,
    save_epl_card_task,
    save_epl_model_task,
    save_epl_settle_preview_task,
)


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def _write_readiness(output_dir: Path, **overrides: object) -> None:
    payload = {
        "status": "Ready for weekly pipeline",
        "fixture_status": "Fresh (10 upcoming match(es))",
        "odds_file_status": "Existing file preserved",
        "odds_completeness_percentage": 1.0,
        "missing_odds_count": 0,
        "invalid_odds_issue_count": 0,
        "validation_warning_count": 0,
        "selected_window": "2026-08-21 through 2026-08-24",
        "selected_window_fixture_count": 10,
        "fixtures_outside_selected_window_count": 0,
        "odds_rows_outside_selected_window_count": 0,
        "slate_warnings": [],
        "upcoming_fixture_count": 10,
    }
    payload.update(overrides)
    (output_dir / "week1_launch_readiness.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _write_shadow(output_dir: Path, **overrides: object) -> None:
    payload: dict[str, object] = {
        "verdict": "Shadow ready for review",
        "mode": "Live shadow run",
        "generated_at": "2026-08-17T12:00:00+00:00",
        "staging_validation": {
            "verdict": "Ready for handoff",
            "handoff_eligible": True,
        },
        "provider_policy": {"provider_allowed": True},
        "team_mapping": {
            "status": "Verified",
            "coverage_percentage": 1.0,
            "unmapped_teams": [],
        },
        "btts_availability": {"status": "Available", "btts_row_count": 20},
        "core_market_coverage": {"status": "Complete"},
        "slate_coverage": {},
    }
    payload.update(overrides)
    (output_dir / "provider_shadow_verification.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _all_green(output_dir: Path) -> None:
    _write_readiness(output_dir)
    _write_shadow(output_dir)


# --- EPL Model -------------------------------------------------------------


def test_model_task_reports_ready_when_every_gate_passes(tmp_path: Path) -> None:
    _all_green(tmp_path)
    summary = build_epl_model_task(output_dir=tmp_path, now=NOW)

    assert summary["model_readiness"] == "Ready"
    assert summary["blockers"] == []
    assert summary["epl_card_ready"] is True


def test_model_task_reports_every_required_field(tmp_path: Path) -> None:
    _all_green(tmp_path)
    summary = build_epl_model_task(output_dir=tmp_path, now=NOW)

    for field in (
        "model_readiness",
        "fixture_freshness",
        "selected_slate",
        "odds_status",
        "provider_status",
        "mapping_coverage",
        "market_coverage",
        "blockers",
        "next_action",
        "epl_card_ready",
    ):
        assert field in summary, field


def test_model_task_blocks_on_missing_odds(tmp_path: Path) -> None:
    _write_readiness(tmp_path, odds_completeness_percentage=0.0, missing_odds_count=140)
    _write_shadow(tmp_path)

    summary = build_epl_model_task(output_dir=tmp_path, now=NOW)

    assert BLOCKER_NEEDS_ODDS in summary["blockers"]
    assert summary["epl_card_ready"] is False


def test_model_task_blocks_on_mapping_and_btts(tmp_path: Path) -> None:
    _write_readiness(tmp_path)
    _write_shadow(
        tmp_path,
        team_mapping={
            "status": "Needs review",
            "coverage_percentage": 0.5,
            "unmapped_teams": ["Manchester City"],
        },
        btts_availability={"status": "Unavailable", "btts_row_count": 0},
    )

    summary = build_epl_model_task(output_dir=tmp_path, now=NOW)

    assert BLOCKER_NEEDS_MAPPING in summary["blockers"]
    assert BLOCKER_NEEDS_BTTS in summary["blockers"]
    assert summary["market_coverage"]["btts_trusted"] is False


def test_model_task_treats_missing_evidence_as_blocked_not_ready(
    tmp_path: Path,
) -> None:
    # No reports at all: absence must never be read as "nothing wrong".
    summary = build_epl_model_task(output_dir=tmp_path, now=NOW)

    assert summary["epl_card_ready"] is False
    assert BLOCKER_NEEDS_VALIDATION in summary["blockers"]
    assert summary["evidence_errors"]


def test_model_task_accepts_decorated_fresh_fixture_status(tmp_path: Path) -> None:
    _write_readiness(tmp_path, fixture_status="Fresh (10 upcoming match(es))")
    _write_shadow(tmp_path)

    summary = build_epl_model_task(output_dir=tmp_path, now=NOW)

    assert "Needs fixtures" not in summary["blockers"]


def test_model_task_writes_both_outputs(tmp_path: Path) -> None:
    _all_green(tmp_path)
    result = save_epl_model_task(output_dir=tmp_path, now=NOW)

    assert Path(result["json"]).is_file()
    assert Path(result["markdown"]).is_file()
    assert Path(result["json"]).name == "epl_model_task.json"
    assert Path(result["markdown"]).name == "epl_model_task.md"


# --- EPL CARD --------------------------------------------------------------


def test_card_withholds_every_selection_when_handoff_ineligible(
    tmp_path: Path,
) -> None:
    _write_readiness(tmp_path, odds_completeness_percentage=0.0, missing_odds_count=140)
    _write_shadow(
        tmp_path,
        staging_validation={"verdict": "Needs fixes", "handoff_eligible": False},
        provider_policy={"provider_allowed": False},
    )

    summary = build_epl_card_task(output_dir=tmp_path, now=NOW)

    assert summary["card_status"] == "Blocked"
    assert summary["card_ready"] is False
    assert summary["picks_suppressed"] is True
    # The critical assertion: nothing was invented.
    assert summary["best_bets"] == []
    assert summary["leans"] == []
    assert summary["passes_or_avoids"] == []
    assert summary["unit_suggestions"] == []
    assert summary["safety"]["picks_invented"] is False
    assert summary["safety"]["official_picks_generated"] is False


def test_card_reports_named_blockers(tmp_path: Path) -> None:
    _write_readiness(tmp_path, odds_completeness_percentage=0.0, missing_odds_count=140)
    _write_shadow(
        tmp_path,
        staging_validation={"verdict": "Needs fixes", "handoff_eligible": False},
        provider_policy={"provider_allowed": False},
        team_mapping={
            "status": "Needs review",
            "coverage_percentage": 0.5,
            "unmapped_teams": ["Hull City"],
        },
        btts_availability={"status": "Unavailable", "btts_row_count": 0},
    )

    blockers = build_epl_card_task(output_dir=tmp_path, now=NOW)["blockers"]

    assert BLOCKER_NEEDS_ODDS in blockers
    assert BLOCKER_NEEDS_MAPPING in blockers
    assert BLOCKER_NEEDS_BTTS in blockers
    assert BLOCKER_NEEDS_VALIDATION in blockers
    assert BLOCKER_PROVIDER_NOT_TRUSTED in blockers


def test_card_source_is_untrusted_until_the_provider_is_allowlisted(
    tmp_path: Path,
) -> None:
    _write_readiness(tmp_path)
    _write_shadow(tmp_path, provider_policy={"provider_allowed": False})

    summary = build_epl_card_task(output_dir=tmp_path, now=NOW)

    assert summary["provider_source"]["trusted"] is False
    assert BLOCKER_PROVIDER_NOT_TRUSTED in summary["blockers"]


def test_card_source_becomes_trusted_only_via_the_allowlist(tmp_path: Path) -> None:
    _all_green(tmp_path)
    summary = build_epl_card_task(output_dir=tmp_path, now=NOW)

    # Trust follows the reviewed allowlist, never market eligibility alone.
    assert summary["provider_source"]["trusted"] is True


def test_card_markdown_says_withheld_not_none_found(tmp_path: Path) -> None:
    _write_readiness(tmp_path, odds_completeness_percentage=0.0, missing_odds_count=140)
    _write_shadow(
        tmp_path,
        staging_validation={"verdict": "Needs fixes", "handoff_eligible": False},
        provider_policy={"provider_allowed": False},
    )
    result = save_epl_card_task(output_dir=tmp_path, now=NOW)
    text = Path(result["markdown"]).read_text(encoding="utf-8")

    assert "withheld" in text
    assert "blocked, not 'no value found'" in text


def test_card_blocked_when_provider_untrusted_even_if_odds_complete(
    tmp_path: Path,
) -> None:
    _write_readiness(tmp_path)
    _write_shadow(
        tmp_path,
        staging_validation={"verdict": "Ready for handoff", "handoff_eligible": False},
        provider_policy={"provider_allowed": False},
    )

    summary = build_epl_card_task(output_dir=tmp_path, now=NOW)

    assert summary["card_ready"] is False
    assert BLOCKER_PROVIDER_NOT_TRUSTED in summary["blockers"]


# --- EPL SETTLE (IGNORE) ---------------------------------------------------


def _ledger(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "bet_ledger.csv"
    pd.DataFrame(rows, columns=["bet_id", "match", "result"]).to_csv(path, index=False)
    return path


def test_settle_preview_never_modifies_the_ledger(tmp_path: Path) -> None:
    ledger = _ledger(
        tmp_path,
        [
            {"bet_id": "1", "match": "Arsenal vs Coventry", "result": ""},
            {"bet_id": "2", "match": "Hull vs Man United", "result": "win"},
        ],
    )
    before = ledger.read_bytes()

    build_epl_settle_preview_task(
        output_dir=tmp_path, ledger_path=ledger, now=NOW
    )

    assert ledger.read_bytes() == before


def test_settle_preview_save_also_never_modifies_the_ledger(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, [{"bet_id": "1", "match": "A vs B", "result": ""}])
    before = ledger.read_bytes()

    save_epl_settle_preview_task(output_dir=tmp_path, ledger_path=ledger, now=NOW)

    assert ledger.read_bytes() == before


def test_settle_preview_counts_open_and_settled_without_settling(
    tmp_path: Path,
) -> None:
    ledger = _ledger(
        tmp_path,
        [
            {"bet_id": "1", "match": "A vs B", "result": ""},
            {"bet_id": "2", "match": "C vs D", "result": ""},
            {"bet_id": "3", "match": "E vs F", "result": "loss"},
        ],
    )

    summary = build_epl_settle_preview_task(
        output_dir=tmp_path, ledger_path=ledger, now=NOW
    )

    assert summary["open_bet_count"] == 2
    assert summary["settled_bet_count"] == 1
    assert summary["would_settle_count"] == 0
    assert summary["mode"] == "Preview only"


def test_settle_preview_safety_flags_are_all_false(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, [{"bet_id": "1", "match": "A vs B", "result": ""}])

    safety = build_epl_settle_preview_task(
        output_dir=tmp_path, ledger_path=ledger, now=NOW
    )["safety"]

    assert safety["settlement_applied"] is False
    assert safety["ledger_edited"] is False
    assert safety["force_mode_used"] is False
    assert safety["bets_placed"] is False
    assert safety["write_path_exists"] is False


def test_settle_preview_exposes_no_apply_or_force_parameter() -> None:
    # A settle-capable parameter must not exist at all, not merely default off.
    import inspect

    signature = inspect.signature(build_epl_settle_preview_task)
    forbidden = {"apply", "force", "settle", "apply_settlement", "write"}
    assert forbidden.isdisjoint(signature.parameters)


def test_settle_preview_handles_missing_ledger_as_blocker(tmp_path: Path) -> None:
    summary = build_epl_settle_preview_task(
        output_dir=tmp_path, ledger_path=tmp_path / "absent.csv", now=NOW
    )

    assert summary["blockers"]
    assert summary["open_bet_count"] == 0


def test_settle_preview_writes_both_outputs(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path, [{"bet_id": "1", "match": "A vs B", "result": ""}])
    result = save_epl_settle_preview_task(
        output_dir=tmp_path, ledger_path=ledger, now=NOW
    )

    assert Path(result["json"]).name == "epl_settle_preview_task.json"
    assert Path(result["markdown"]).name == "epl_settle_preview_task.md"
    assert "never applies settlement" in Path(result["markdown"]).read_text(
        encoding="utf-8"
    ).lower() or "preview only" in Path(result["markdown"]).read_text(
        encoding="utf-8"
    ).lower()
