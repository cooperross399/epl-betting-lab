from __future__ import annotations

from datetime import date

import pandas as pd

import epl_betting_lab.dashboard_actions as dashboard_actions
from epl_betting_lab.reports.current_odds_template import build_current_odds_template
from epl_betting_lab.reports.week1_launch_readiness import run_week1_launch_readiness


TODAY = date(2026, 8, 14)


def _fixtures(path, fixture_date: str = "2026-08-21") -> pd.DataFrame:
    fixtures = pd.DataFrame(
        [
            {
                "date": fixture_date,
                "home_team": "Arsenal",
                "away_team": "Coventry",
                "matchweek": "1",
            }
        ]
    )
    fixtures.to_csv(path, index=False)
    return fixtures


def _complete_odds(path, fixtures: pd.DataFrame, *, odds_date: str | None = None) -> None:
    odds = build_current_odds_template(fixtures, book="ExampleBook")
    odds["american_odds"] = "-110"
    if odds_date is not None:
        odds["date"] = odds_date
    odds.to_csv(path, index=False)


def test_missing_odds_file_creates_blank_template_safely(tmp_path) -> None:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _fixtures(fixtures_path)

    result = run_week1_launch_readiness(
        fixtures_path,
        odds_path,
        output_dir,
        today=TODAY,
    )

    created = pd.read_csv(odds_path, dtype=str).fillna("")
    assert result["status"] == "Needs odds filled"
    assert result["summary"]["template_created"] is True
    assert result["summary"]["template_overwritten"] is False
    assert result["summary"]["missing_odds_count"] == 7
    assert len(created) == 7
    assert created["american_odds"].eq("").all()
    assert (output_dir / "current_odds_validation.csv").exists()
    assert (output_dir / "current_odds_completeness.csv").exists()
    assert result["json"].exists()
    assert result["markdown"].exists()
    assert result["csv"].exists()
    assert "never invents prices" in result["markdown"].read_text(encoding="utf-8")


def test_existing_odds_file_is_not_overwritten_by_default(tmp_path) -> None:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    odds_path = tmp_path / "current_odds.csv"
    _fixtures(fixtures_path)
    odds_path.write_text(
        "date,home_team,away_team,market,selection,american_odds,book\n"
        "2026-08-21,Arsenal,Coventry,1x2,home,,ExampleBook\n",
        encoding="utf-8",
    )
    original = odds_path.read_bytes()

    result = run_week1_launch_readiness(
        fixtures_path,
        odds_path,
        tmp_path / "outputs",
        today=TODAY,
    )

    assert result["status"] == "Needs odds filled"
    assert result["summary"]["template_created"] is False
    assert result["summary"]["odds_file_status"].startswith("Existing file preserved")
    assert odds_path.read_bytes() == original


def test_terminal_overwrite_flag_replaces_existing_file_with_blank_template(tmp_path) -> None:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    odds_path = tmp_path / "current_odds.csv"
    _fixtures(fixtures_path)
    odds_path.write_text("protected real odds\n", encoding="utf-8")

    result = run_week1_launch_readiness(
        fixtures_path,
        odds_path,
        tmp_path / "outputs",
        overwrite_template=True,
        today=TODAY,
    )

    rewritten = pd.read_csv(odds_path, dtype=str).fillna("")
    assert result["status"] == "Needs odds filled"
    assert result["summary"]["template_overwritten"] is True
    assert len(rewritten) == 7
    assert rewritten["american_odds"].eq("").all()


def test_missing_fixtures_blocks_without_creating_odds(tmp_path) -> None:
    fixtures_path = tmp_path / "missing_fixtures.csv"
    odds_path = tmp_path / "current_odds.csv"

    result = run_week1_launch_readiness(
        fixtures_path,
        odds_path,
        tmp_path / "outputs",
        today=TODAY,
    )

    assert result["status"] == "Missing fixtures"
    assert result["summary"]["fixture_status"] == "Missing"
    assert not odds_path.exists()
    assert "missing_upcoming_fixtures" in result["markdown"].read_text(encoding="utf-8")


def test_all_past_fixtures_need_refresh_without_creating_odds(tmp_path) -> None:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    odds_path = tmp_path / "current_odds.csv"
    _fixtures(fixtures_path, fixture_date="2026-08-13")

    result = run_week1_launch_readiness(
        fixtures_path,
        odds_path,
        tmp_path / "outputs",
        today=TODAY,
    )

    assert result["status"] == "Needs fixture refresh"
    assert "all in the past" in result["summary"]["fixture_note"]
    assert not odds_path.exists()


def test_complete_valid_odds_are_ready_for_weekly_pipeline(tmp_path) -> None:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    odds_path = tmp_path / "current_odds.csv"
    fixtures = _fixtures(fixtures_path)
    _complete_odds(odds_path, fixtures)

    result = run_week1_launch_readiness(
        fixtures_path,
        odds_path,
        tmp_path / "outputs",
        today=TODAY,
    )

    summary = result["summary"]
    assert result["status"] == "Ready for weekly pipeline"
    assert summary["odds_completeness_percentage"] == 1.0
    assert summary["missing_odds_count"] == 0
    assert summary["invalid_odds_issue_count"] == 0
    assert summary["run_weekly_pipeline_next"] is True
    assert "run_epl_weekly_pipeline.py" in summary["next_human_action"]


def test_stale_odds_are_surfaced_as_fixes(tmp_path) -> None:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    odds_path = tmp_path / "current_odds.csv"
    fixtures = _fixtures(fixtures_path)
    _complete_odds(odds_path, fixtures, odds_date="2026-08-13")

    result = run_week1_launch_readiness(
        fixtures_path,
        odds_path,
        tmp_path / "outputs",
        today=TODAY,
    )

    assert result["status"] == "Needs odds fixes"
    assert result["summary"]["stale_odds_row_count"] == 7
    assert "past_match_odds" in result["markdown"].read_text(encoding="utf-8")


def test_dashboard_helper_never_enables_template_overwrite(tmp_path, monkeypatch) -> None:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "Needs odds filled"}

    monkeypatch.setattr(dashboard_actions, "save_week1_launch_readiness", fake_run)

    result = dashboard_actions.run_week1_launch_readiness(
        fixtures_path,
        odds_path,
        output_dir,
    )

    assert result == {"status": "Needs odds filled"}
    assert captured["overwrite_template"] is False
    assert captured["fixtures_path"] == fixtures_path
    assert captured["current_odds_path"] == odds_path
    assert captured["output_dir"] == output_dir
