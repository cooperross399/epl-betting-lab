from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import epl_betting_lab.dashboard_actions as dashboard_actions
import epl_betting_lab.reports.epl_weekly_pipeline_history as history_module
from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    archive_latest_epl_weekly_pipeline,
    calculate_epl_weekly_pipeline_receipt_identity,
    compare_epl_weekly_pipeline_records,
    compare_latest_epl_weekly_pipeline_runs,
    list_recent_epl_weekly_pipeline_runs,
)


RUN_AT = datetime(2026, 8, 13, 9, 15, 30, tzinfo=timezone.utc)


def _summary(output_dir: Path) -> dict[str, object]:
    validation = output_dir / "current_odds_validation.csv"
    completeness = output_dir / "current_odds_completeness.csv"
    card = output_dir / "thursday_best_bets.csv"
    validation.write_text("severity,message\ninfo,ready\n", encoding="utf-8")
    completeness.write_text("status,count\ncomplete,7\n", encoding="utf-8")
    card.write_text("section,selection\nBest bets,home\n", encoding="utf-8")
    return {
        "run_timestamp": RUN_AT.isoformat(timespec="seconds"),
        "status": "Ready for card review",
        "key_blockers": [],
        "key_warnings": [],
        "generated_report_paths": [str(validation), str(completeness), str(card)],
        "card_counts": {
            "best_bets": 1,
            "leans": 0,
            "passes": 0,
            "total_candidates": 1,
        },
        "decision_queue_counts": {"Review price": 1},
        "ledger_health_summary": {
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
        },
        "recommended_next_action": "Review the card manually.",
        "steps": [
            {
                "step": "Current odds validation",
                "status": "Completed",
                "warnings": [],
                "blockers": [],
            },
            {
                "step": "Thursday best-bets generation",
                "status": "Completed",
                "warnings": [],
                "blockers": [],
            },
        ],
    }


def _write_pipeline_outputs(output_dir: Path, summary: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "epl_weekly_pipeline.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "epl_weekly_pipeline.md").write_text(
        "# Weekly pipeline\n",
        encoding="utf-8",
    )
    (output_dir / "epl_weekly_pipeline.csv").write_text(
        "step,status\nvalidation,Completed\n",
        encoding="utf-8",
    )


def _inventory(checksum: str = "a" * 64) -> list[dict[str, object]]:
    return [
        {
            "path": "current_odds_validation.csv",
            "status": "Included",
            "checksum_sha256": checksum,
            "size_bytes": 10,
        }
    ]


def _record(
    summary: dict[str, object],
    *,
    receipt_id: str,
    archive_path: str,
    checksum: str = "a" * 64,
) -> dict[str, object]:
    return {
        "receipt_id": receipt_id,
        "archive_path": archive_path,
        "status": summary["status"],
        "summary_snapshot": {
            "status": summary["status"],
            "steps": summary["steps"],
            "key_blockers": summary["key_blockers"],
            "card_counts": summary["card_counts"],
            "decision_queue_counts": summary["decision_queue_counts"],
            "ledger_health_summary": summary["ledger_health_summary"],
            "recommended_next_action": summary["recommended_next_action"],
        },
        "report_inventory": _inventory(checksum),
    }


def test_receipt_id_is_deterministic_and_binds_required_run_content(tmp_path) -> None:
    summary = _summary(tmp_path)
    inventory = _inventory()

    checksum_one, receipt_one = calculate_epl_weekly_pipeline_receipt_identity(
        summary, inventory
    )
    checksum_two, receipt_two = calculate_epl_weekly_pipeline_receipt_identity(
        deepcopy(summary), deepcopy(inventory)
    )

    assert checksum_one == checksum_two
    assert receipt_one == receipt_two

    mutations = []
    changed_status = deepcopy(summary)
    changed_status["status"] = "Blocked"
    mutations.append((changed_status, inventory))

    changed_blocker = deepcopy(summary)
    changed_blocker["key_blockers"] = ["Odds validation blocked the card."]
    mutations.append((changed_blocker, inventory))

    changed_card_count = deepcopy(summary)
    changed_card_count["card_counts"]["best_bets"] = 2
    mutations.append((changed_card_count, inventory))

    changed_queue_count = deepcopy(summary)
    changed_queue_count["decision_queue_counts"]["Review price"] = 2
    mutations.append((changed_queue_count, inventory))

    changed_ledger = deepcopy(summary)
    changed_ledger["ledger_health_summary"]["warning_count"] = 1
    mutations.append((changed_ledger, inventory))

    changed_step = deepcopy(summary)
    changed_step["steps"][0]["status"] = "Blocked"
    mutations.append((changed_step, inventory))

    changed_inventory = deepcopy(inventory)
    changed_inventory[0]["checksum_sha256"] = "b" * 64
    mutations.append((summary, changed_inventory))

    for changed_summary, changed_reports in mutations:
        _, changed_receipt = calculate_epl_weekly_pipeline_receipt_identity(
            changed_summary, changed_reports
        )
        assert changed_receipt != receipt_one


def test_same_second_archives_are_durable_and_do_not_overwrite(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    summary = _summary(output_dir)
    _write_pipeline_outputs(output_dir, summary)

    first = archive_latest_epl_weekly_pipeline(output_dir, archived_at=RUN_AT)
    second = archive_latest_epl_weekly_pipeline(output_dir, archived_at=RUN_AT)

    assert first["archive_dir"] != second["archive_dir"]
    assert first["archive_dir"].name == "091530"
    assert second["archive_dir"].name == "091530_02"
    assert first["receipt_id"] == second["receipt_id"]
    for archive in (first, second):
        assert (archive["archive_dir"] / "epl_weekly_pipeline.json").exists()
        assert (archive["archive_dir"] / "epl_weekly_pipeline.md").exists()
        assert (archive["archive_dir"] / "epl_weekly_pipeline.csv").exists()
        assert (archive["archive_dir"] / "epl_weekly_pipeline_archive.json").exists()

    manifest = json.loads(
        second["archive_json"].read_text(encoding="utf-8")
    )
    assert manifest["current_odds_validation_checksum_sha256"]
    assert manifest["current_odds_completeness_checksum_sha256"]
    assert manifest["safety"]["manual_files_edited"] is False


def test_comparison_handles_missing_prior_run_safely(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    summary = _summary(output_dir)
    latest = _record(summary, receipt_id="latest", archive_path="archive/latest")

    comparison = compare_epl_weekly_pipeline_records(None, latest, generated_at=RUN_AT)

    assert comparison["verdict"] == "Missing prior run"
    assert comparison["changes"] == []
    assert "comparison baseline" in comparison["important_changes"][0]


def test_comparison_detects_new_blockers_and_count_changes(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    previous_summary = _summary(output_dir)
    latest_summary = deepcopy(previous_summary)
    latest_summary["status"] = "Needs odds fixes"
    latest_summary["key_blockers"] = ["American odds are incomplete."]
    latest_summary["card_counts"] = {
        "best_bets": 0,
        "leans": 1,
        "passes": 2,
        "total_candidates": 3,
    }
    latest_summary["decision_queue_counts"] = {
        "Review price": 3,
        "Likely remove from card": 1,
    }

    comparison = compare_epl_weekly_pipeline_records(
        _record(previous_summary, receipt_id="previous", archive_path="archive/previous"),
        _record(latest_summary, receipt_id="latest", archive_path="archive/latest"),
        generated_at=RUN_AT,
    )

    assert comparison["verdict"] == "New blockers"
    assert comparison["new_blockers"] == ["American odds are incomplete."]
    assert comparison["card_count_changes"]["best_bets"]["change"] == -1
    assert comparison["card_count_changes"]["leans"]["change"] == 1
    assert (
        comparison["decision_queue_count_changes"]["Review price"]["change"]
        == 2
    )


def test_latest_two_archive_comparison_and_history_listing(tmp_path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    summary = _summary(output_dir)
    _write_pipeline_outputs(output_dir, summary)
    archive_latest_epl_weekly_pipeline(output_dir, archived_at=RUN_AT)

    changed = deepcopy(summary)
    changed["card_counts"]["best_bets"] = 2
    changed["recommended_next_action"] = "Review two best bets manually."
    _write_pipeline_outputs(output_dir, changed)
    archive_latest_epl_weekly_pipeline(
        output_dir,
        archived_at=RUN_AT.replace(second=31),
    )

    result = compare_latest_epl_weekly_pipeline_runs(
        output_dir, generated_at=RUN_AT
    )
    history = list_recent_epl_weekly_pipeline_runs(output_dir)

    assert result["verdict"] == "More review needed"
    assert result["json"].exists()
    assert result["markdown"].exists()
    assert result["csv"].exists()
    assert len(history) == 2
    assert int(history.iloc[0]["best_bets"]) == 2


def test_dashboard_comparison_action_only_delegates_to_report_helper(
    tmp_path, monkeypatch
) -> None:
    expected = {"verdict": "Stable ready state"}
    calls: list[Path] = []

    def fake_compare(output_dir):
        calls.append(output_dir)
        return expected

    monkeypatch.setattr(
        history_module,
        "compare_latest_epl_weekly_pipeline_runs",
        fake_compare,
    )
    monkeypatch.setattr(
        dashboard_actions,
        "compare_latest_epl_weekly_pipeline_runs",
        fake_compare,
    )

    result = dashboard_actions.run_epl_weekly_pipeline_comparison(tmp_path)

    assert result == expected
    assert calls == [tmp_path]


def test_dashboard_displays_weekly_receipt_history_without_apply_controls() -> None:
    app_source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")

    assert "Pipeline receipt" in app_source
    assert '"Weekly pipeline run history"' in app_source
    assert '"Compare weekly pipeline runs"' in app_source
    assert "list_recent_epl_weekly_pipeline_runs" in app_source
    assert "apply_epl_weekly_pipeline" not in app_source
