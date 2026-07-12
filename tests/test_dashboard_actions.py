from __future__ import annotations

import pandas as pd
import pytest

import epl_betting_lab.dashboard_actions as dashboard_actions
from epl_betting_lab.dashboard_actions import (
    require_existing_ledger,
    require_existing_current_odds,
    run_bet_ledger_report,
    run_create_current_odds_template,
    run_current_odds_completeness,
    run_current_odds_maintenance_preview,
    run_current_odds_validation,
    run_ledger_health_check,
    run_post_thursday_review,
    run_settlement_preview,
    run_tier_performance_report,
    run_thursday_best_bets_comparison,
    run_thursday_best_bets_report,
    run_thursday_decision_queue,
    run_thursday_readiness_refresh,
)
from epl_betting_lab.reports.current_odds_validation import CurrentOddsValidationError
from epl_betting_lab.reports.bet_ledger import LEDGER_COLUMNS


def _ledger(path) -> None:
    pd.DataFrame([
        {
            "bet_id": "bet-1",
            "date": "2026-08-21",
            "season": "2627",
            "match": "Arsenal vs Coventry",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": -120,
            "stake_units": 1.0,
            "result": "pending",
        }
    ], columns=LEDGER_COLUMNS).to_csv(path, index=False)


def _matches(path) -> None:
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "season": "2627",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "home_goals": 2,
            "away_goals": 0,
        }
    ]).to_csv(path, index=False)


def test_require_existing_ledger_does_not_create_missing_file(tmp_path) -> None:
    ledger_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        require_existing_ledger(ledger_path)

    assert not ledger_path.exists()


def test_require_existing_current_odds_shows_manual_copy_command(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"

    with pytest.raises(FileNotFoundError) as exc:
        require_existing_current_odds(odds_path)

    assert "cp data/manual/current_odds_template.csv data/manual/current_odds.csv" in str(exc.value)
    assert not odds_path.exists()


def test_run_current_odds_validation_writes_report_without_creating_odds_file(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"

    paths = run_current_odds_validation(odds_path, output_dir)

    assert paths["csv"].name == "current_odds_validation.csv"
    assert paths["markdown"].name == "current_odds_validation.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert not odds_path.exists()


def test_run_create_current_odds_template_creates_file_without_overwrite(tmp_path, monkeypatch) -> None:
    odds_path = tmp_path / "current_odds.csv"
    monkeypatch.setattr(
        dashboard_actions,
        "load_upcoming_fixtures",
        lambda: pd.DataFrame([{"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"}]),
    )

    paths = run_create_current_odds_template(odds_path, book="ExampleBook")

    assert paths["csv"] == odds_path
    assert odds_path.exists()
    original = odds_path.read_text(encoding="utf-8")
    assert "ExampleBook" in original

    with pytest.raises(FileExistsError):
        run_create_current_odds_template(odds_path)

    assert odds_path.read_text(encoding="utf-8") == original


def test_run_current_odds_maintenance_preview_does_not_edit_current_odds(tmp_path, monkeypatch) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-150",
            "closing_american_odds": "",
            "book": "FanDuel",
            "notes": "keep this price",
        }
    ]).to_csv(odds_path, index=False)
    original = odds_path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        dashboard_actions,
        "load_upcoming_fixtures",
        lambda: pd.DataFrame([{"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"}]),
    )

    paths = run_current_odds_maintenance_preview(odds_path, output_dir, book="FanDuel")

    assert paths["csv"].name == "current_odds_maintenance_preview.csv"
    assert paths["markdown"].name == "current_odds_maintenance_report.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert odds_path.read_text(encoding="utf-8") == original


def test_run_current_odds_completeness_writes_report_without_editing_odds(tmp_path, monkeypatch) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "",
            "book": "",
        }
    ]).to_csv(odds_path, index=False)
    original = odds_path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        dashboard_actions,
        "load_upcoming_fixtures",
        lambda: pd.DataFrame([{"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"}]),
    )

    paths = run_current_odds_completeness(odds_path, output_dir)

    assert paths["csv"].name == "current_odds_completeness.csv"
    assert paths["markdown"].name == "current_odds_completeness.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert odds_path.read_text(encoding="utf-8") == original


def test_run_thursday_best_bets_comparison_writes_report(tmp_path) -> None:
    paths = run_thursday_best_bets_comparison(tmp_path)

    assert paths["csv"].name == "thursday_best_bets_comparison.csv"
    assert paths["markdown"].name == "thursday_best_bets_comparison.md"
    assert paths["csv"].exists()
    assert "Comparison is not available yet" in paths["markdown"].read_text(encoding="utf-8")


def test_run_thursday_decision_queue_writes_report(tmp_path) -> None:
    paths = run_thursday_decision_queue(tmp_path)

    assert paths["csv"].name == "thursday_decision_queue.csv"
    assert paths["markdown"].name == "thursday_decision_queue.md"
    assert paths["csv"].exists()
    assert "comparison report is missing" in paths["markdown"].read_text(encoding="utf-8")


def test_run_tier_performance_report_writes_outputs(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    output_dir = tmp_path / "outputs"
    _ledger(ledger_path)

    paths = run_tier_performance_report(ledger_path, output_dir)

    assert paths["summary"].name == "tier_performance_summary.csv"
    assert paths["market"].name == "tier_performance_by_market.csv"
    assert paths["team"].name == "tier_performance_by_team.csv"
    assert paths["odds_range"].name == "tier_performance_by_odds_range.csv"
    assert paths["clv"].name == "tier_performance_by_clv.csv"
    assert paths["markdown"].name == "tier_performance_report.md"
    assert "Tier Performance Report" in paths["markdown"].read_text(encoding="utf-8")


def test_thursday_best_bets_stops_when_current_odds_missing(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"

    with pytest.raises(CurrentOddsValidationError) as exc:
        run_thursday_best_bets_report(odds_path, output_dir)

    assert "Thursday best-bets generation stopped" in str(exc.value)
    assert "python scripts/validate_current_odds.py" in str(exc.value)
    assert "cp data/manual/current_odds_template.csv data/manual/current_odds.csv" in str(exc.value)
    assert (output_dir / "current_odds_validation.csv").exists()
    assert (output_dir / "current_odds_validation.md").exists()
    assert not (output_dir / "thursday_best_bets.md").exists()
    assert not odds_path.exists()


def test_thursday_best_bets_stops_on_serious_validation_issues(tmp_path, monkeypatch) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "shots",
            "selection": "over",
            "american_odds": "+120",
            "book": "ExampleBook",
        }
    ]).to_csv(odds_path, index=False)
    monkeypatch.setattr(
        dashboard_actions,
        "load_matches",
        lambda: pd.DataFrame([{"home_team": "Arsenal", "away_team": "Coventry"}]),
    )
    monkeypatch.setattr(
        dashboard_actions,
        "load_upcoming_fixtures",
        lambda: pd.DataFrame([{"home_team": "Arsenal", "away_team": "Coventry"}]),
    )

    with pytest.raises(CurrentOddsValidationError) as exc:
        run_thursday_best_bets_report(odds_path, output_dir)

    assert "invalid_market" in str(exc.value)
    assert (output_dir / "current_odds_validation.md").exists()
    assert not (output_dir / "thursday_best_bets.md").exists()


def test_thursday_readiness_refresh_runs_safe_steps_in_order(tmp_path, monkeypatch) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    calls: list[str] = []
    progress_events: list[tuple[str, str]] = []

    def fake_completeness(path, out):
        calls.append(f"completeness:{path == odds_path}:{out == output_dir}")
        return {"csv": out / "current_odds_completeness.csv"}

    def fake_validation(path, out):
        calls.append(f"validation:{path == odds_path}:{out == output_dir}")
        return {"csv": out / "current_odds_validation.csv"}

    def fake_thursday(path, out, force=False):
        calls.append(f"thursday:{path == odds_path}:{out == output_dir}:force={force}")
        return {"csv": out / "thursday_best_bets.csv"}

    monkeypatch.setattr(dashboard_actions, "run_current_odds_completeness", fake_completeness)
    monkeypatch.setattr(dashboard_actions, "run_current_odds_validation", fake_validation)
    monkeypatch.setattr(dashboard_actions, "run_thursday_best_bets_report", fake_thursday)

    paths = run_thursday_readiness_refresh(
        odds_path,
        output_dir,
        progress=lambda step, status, message: progress_events.append((step, status)),
    )

    assert calls == [
        "completeness:True:True",
        "validation:True:True",
        "thursday:True:True:force=False",
    ]
    assert list(paths) == ["odds_completeness", "current_odds_validation", "thursday_best_bets"]
    assert progress_events == [
        ("Odds completeness check", "running"),
        ("Odds completeness check", "success"),
        ("Current odds validation", "running"),
        ("Current odds validation", "success"),
        ("Thursday best-bets generation", "running"),
        ("Thursday best-bets generation", "success"),
    ]


def test_thursday_readiness_refresh_stops_when_validation_gate_blocks(tmp_path, monkeypatch) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    calls: list[str] = []
    progress_events: list[tuple[str, str]] = []

    def fake_completeness(path, out):
        calls.append("completeness")
        return {"csv": out / "current_odds_completeness.csv"}

    def fake_validation(path, out):
        calls.append("validation")
        return {"csv": out / "current_odds_validation.csv"}

    def fake_thursday(path, out, force=False):
        calls.append(f"thursday:force={force}")
        raise CurrentOddsValidationError("serious validation issues")

    monkeypatch.setattr(dashboard_actions, "run_current_odds_completeness", fake_completeness)
    monkeypatch.setattr(dashboard_actions, "run_current_odds_validation", fake_validation)
    monkeypatch.setattr(dashboard_actions, "run_thursday_best_bets_report", fake_thursday)

    with pytest.raises(CurrentOddsValidationError):
        run_thursday_readiness_refresh(
            odds_path,
            output_dir,
            progress=lambda step, status, message: progress_events.append((step, status)),
        )

    assert calls == ["completeness", "validation", "thursday:force=False"]
    assert progress_events[-1] == ("Thursday best-bets generation", "error")


def test_thursday_readiness_refresh_stops_remaining_steps_after_failure(tmp_path, monkeypatch) -> None:
    calls: list[str] = []

    def fake_completeness(path, out):
        calls.append("completeness")
        raise FileNotFoundError("missing fixtures")

    def fake_validation(path, out):
        calls.append("validation")
        return {}

    def fake_thursday(path, out, force=False):
        calls.append("thursday")
        return {}

    monkeypatch.setattr(dashboard_actions, "run_current_odds_completeness", fake_completeness)
    monkeypatch.setattr(dashboard_actions, "run_current_odds_validation", fake_validation)
    monkeypatch.setattr(dashboard_actions, "run_thursday_best_bets_report", fake_thursday)

    with pytest.raises(FileNotFoundError):
        run_thursday_readiness_refresh(tmp_path / "current_odds.csv", tmp_path / "outputs")

    assert calls == ["completeness"]


def test_post_thursday_review_runs_comparison_then_decision_queue(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "outputs"
    calls: list[str] = []
    progress_events: list[tuple[str, str]] = []

    def fake_comparison(out):
        calls.append(f"comparison:{out == output_dir}")
        return {"csv": out / "thursday_best_bets_comparison.csv"}

    def fake_archives(out, limit=8):
        calls.append(f"archives:{out == output_dir}:limit={limit}")
        return pd.DataFrame([
            {"generated_at": "2026-07-09T12:00:00"},
            {"generated_at": "2026-07-08T12:00:00"},
        ])

    def fake_decision_queue(out):
        calls.append(f"decision_queue:{out == output_dir}")
        return {"csv": out / "thursday_decision_queue.csv"}

    monkeypatch.setattr(dashboard_actions, "run_thursday_best_bets_comparison", fake_comparison)
    monkeypatch.setattr(dashboard_actions, "list_recent_thursday_archives", fake_archives)
    monkeypatch.setattr(dashboard_actions, "run_thursday_decision_queue", fake_decision_queue)

    paths = run_post_thursday_review(
        output_dir,
        progress=lambda step, status, message: progress_events.append((step, status)),
    )

    assert calls == [
        "comparison:True",
        "archives:True:limit=2",
        "decision_queue:True",
    ]
    assert list(paths) == ["comparison", "decision_queue"]
    assert progress_events == [
        ("Thursday snapshot comparison", "running"),
        ("Thursday snapshot comparison", "success"),
        ("Thursday decision queue", "running"),
        ("Thursday decision queue", "success"),
    ]


def test_post_thursday_review_stops_when_not_enough_archives(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "outputs"
    calls: list[str] = []
    progress_events: list[tuple[str, str]] = []

    def fake_comparison(out):
        calls.append("comparison")
        return {"csv": out / "thursday_best_bets_comparison.csv"}

    def fake_archives(out, limit=8):
        calls.append(f"archives:limit={limit}")
        return pd.DataFrame([{"generated_at": "2026-07-09T12:00:00"}])

    def fake_decision_queue(out):
        calls.append("decision_queue")
        return {}

    monkeypatch.setattr(dashboard_actions, "run_thursday_best_bets_comparison", fake_comparison)
    monkeypatch.setattr(dashboard_actions, "list_recent_thursday_archives", fake_archives)
    monkeypatch.setattr(dashboard_actions, "run_thursday_decision_queue", fake_decision_queue)

    with pytest.raises(FileNotFoundError) as exc:
        run_post_thursday_review(
            output_dir,
            progress=lambda step, status, message: progress_events.append((step, status)),
        )

    assert "at least two Thursday best-bets archive snapshots" in str(exc.value)
    assert calls == ["comparison", "archives:limit=2"]
    assert progress_events[-1] == ("Thursday decision queue", "error")


def test_post_thursday_review_stops_when_comparison_fails(tmp_path, monkeypatch) -> None:
    calls: list[str] = []
    progress_events: list[tuple[str, str]] = []

    def fake_comparison(out):
        calls.append("comparison")
        raise RuntimeError("comparison broke")

    def fake_decision_queue(out):
        calls.append("decision_queue")
        return {}

    monkeypatch.setattr(dashboard_actions, "run_thursday_best_bets_comparison", fake_comparison)
    monkeypatch.setattr(dashboard_actions, "run_thursday_decision_queue", fake_decision_queue)

    with pytest.raises(RuntimeError):
        run_post_thursday_review(
            tmp_path / "outputs",
            progress=lambda step, status, message: progress_events.append((step, status)),
        )

    assert calls == ["comparison"]
    assert progress_events == [
        ("Thursday snapshot comparison", "running"),
        ("Thursday snapshot comparison", "error"),
    ]


def test_dashboard_report_actions_write_outputs_without_editing_ledger(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    matches_path = tmp_path / "matches.csv"
    output_dir = tmp_path / "outputs"
    _ledger(ledger_path)
    _matches(matches_path)
    original = ledger_path.read_text(encoding="utf-8")

    ledger_paths = run_bet_ledger_report(ledger_path, output_dir)
    health_paths = run_ledger_health_check(ledger_path, output_dir)
    settlement_paths = run_settlement_preview(ledger_path, matches_path, output_dir)

    assert ledger_paths["markdown"].name == "bet_ledger_summary.md"
    assert health_paths["markdown"].name == "bet_ledger_health_check.md"
    assert settlement_paths["markdown"].name == "bet_settlement_preview.md"
    assert ledger_path.read_text(encoding="utf-8") == original
