from __future__ import annotations

import json

import pandas as pd
import pytest

import epl_betting_lab.dashboard_actions as dashboard_actions
from epl_betting_lab.dashboard_actions import (
    get_stale_current_odds_archive_confirmation_status,
    get_stale_current_odds_backup_list,
    require_existing_ledger,
    require_existing_current_odds,
    run_bet_ledger_report,
    run_create_current_odds_template,
    run_current_odds_completeness,
    run_current_odds_import_preview,
    run_current_odds_maintenance_preview,
    run_current_odds_validation,
    run_github_manual_thursday_verification,
    run_ledger_health_check,
    run_odds_export_conversion_preview,
    run_odds_export_profile_diagnostic,
    run_odds_export_profile_suggestion,
    run_odds_export_profile_suggestion_validation,
    run_odds_profile_install_preview,
    run_installed_odds_profile_verification,
    run_post_thursday_review,
    run_settlement_preview,
    run_stale_current_odds_archive_preview,
    run_stale_current_odds_archive_confirmation_status,
    run_stale_current_odds_archive_rollback_preview,
    run_stale_current_odds_backup_list,
    run_stale_current_odds_report,
    run_staging_input_validation,
    run_tier_performance_report,
    run_thursday_best_bets_comparison,
    run_thursday_best_bets_report,
    run_thursday_decision_queue,
    run_thursday_readiness_refresh,
)
from epl_betting_lab.reports.current_odds_validation import CurrentOddsValidationError
from epl_betting_lab.reports.bet_ledger import LEDGER_COLUMNS
from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256


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


def test_run_staging_input_validation_is_report_only(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "outputs"
    odds_path = tmp_path / "staging" / "odds.csv"
    fixtures_path = tmp_path / "staging" / "fixtures.csv"
    expected = {
        "csv": output_dir / "staging_input_validation.csv",
        "markdown": output_dir / "staging_input_validation.md",
        "json": output_dir / "staging_input_validation.json",
        "verdict": "Missing staging inputs",
    }

    def fake_save(selected_odds, selected_fixtures, *, output_dir):
        assert selected_odds == odds_path
        assert selected_fixtures == fixtures_path
        assert output_dir == tmp_path / "outputs"
        return expected

    monkeypatch.setattr(
        dashboard_actions,
        "save_staging_input_validation",
        fake_save,
    )

    assert (
        run_staging_input_validation(odds_path, fixtures_path, output_dir)
        == expected
    )


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


def test_run_current_odds_import_preview_does_not_edit_current_odds(tmp_path) -> None:
    import_path = tmp_path / "current_odds_import.csv"
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    row = {
        "date": "2026-08-21",
        "home_team": "Arsenal",
        "away_team": "Coventry",
        "market": "1x2",
        "selection": "home",
        "american_odds": "+120",
        "book": "ExampleBook",
    }
    pd.DataFrame([row]).to_csv(import_path, index=False)
    pd.DataFrame([{**row, "american_odds": "+110", "custom_column": "keep"}]).to_csv(odds_path, index=False)
    original = odds_path.read_text(encoding="utf-8")
    fixtures = pd.DataFrame([{"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"}])

    paths = run_current_odds_import_preview(
        import_path,
        odds_path,
        output_dir,
        fixtures=fixtures,
        matches=pd.DataFrame(),
    )

    assert paths["csv"].name == "current_odds_import_preview.csv"
    assert paths["markdown"].name == "current_odds_import_report.md"
    assert odds_path.read_text(encoding="utf-8") == original


def test_run_odds_export_conversion_preview_never_writes_import_file(tmp_path, monkeypatch) -> None:
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    monkeypatch.setattr(dashboard_actions, "MANUAL_DIR", manual_dir)
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    profiles_path.write_text(
        '{"profiles":{"generic":{"column_map":{'
        '"game_date":"date","home":"home_team","away":"away_team",'
        '"bet_type":"market","pick":"selection","odds":"american_odds",'
        '"sportsbook":"book"}}}}',
        encoding="utf-8",
    )
    pd.DataFrame([
        {
            "game_date": "2026-08-21",
            "home": "Arsenal",
            "away": "Coventry",
            "bet_type": "1x2",
            "pick": "home",
            "odds": "+120",
            "sportsbook": "ExampleBook",
        }
    ]).to_csv(source_path, index=False)

    paths = run_odds_export_conversion_preview(
        "generic",
        source_path,
        profiles_path,
        output_dir,
    )

    assert paths["status"] == "preview_only"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert not (manual_dir / "current_odds_import.csv").exists()


def test_run_odds_export_conversion_preview_reports_missing_source_cleanly(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    output_dir = tmp_path / "outputs"
    profiles_path.write_text(
        '{"profiles":{"generic":{"column_map":{'
        '"game_date":"date","home":"home_team","away":"away_team",'
        '"bet_type":"market","pick":"selection","odds":"american_odds",'
        '"sportsbook":"book"}}}}',
        encoding="utf-8",
    )

    with pytest.raises(dashboard_actions.OddsExportConversionError) as exc:
        run_odds_export_conversion_preview(
            "generic",
            tmp_path / "missing.csv",
            profiles_path,
            output_dir,
        )

    assert "Missing source export" in str(exc.value)
    assert (output_dir / "odds_export_conversion_report.md").exists()


def test_run_odds_export_profile_diagnostic_is_read_only(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    profiles_path.write_text(
        '{"profiles":{"generic":{"column_map":{'
        '"game_date":"date","home":"home_team","away":"away_team",'
        '"bet_type":"market","pick":"selection","odds":"american_odds",'
        '"sportsbook":"book"}}}}',
        encoding="utf-8",
    )
    pd.DataFrame([
        {
            "game_date": "2026-08-21",
            "home": "Arsenal",
            "away": "Coventry",
            "bet_type": "1x2",
            "pick": "home",
            "odds": "+120",
            "sportsbook": "ExampleBook",
        }
    ]).to_csv(source_path, index=False)

    paths = run_odds_export_profile_diagnostic(source_path, profiles_path, output_dir)

    assert paths["status"] == "match_found"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert not (tmp_path / "current_odds_import.csv").exists()
    assert not (tmp_path / "current_odds.csv").exists()


def test_run_odds_export_profile_diagnostic_reports_missing_source_cleanly(tmp_path) -> None:
    profiles_path = tmp_path / "profiles.json"
    output_dir = tmp_path / "outputs"
    profiles_path.write_text('{"profiles":{"generic":{"column_map":{}}}}', encoding="utf-8")

    with pytest.raises(dashboard_actions.OddsExportProfileDiagnosticError) as exc:
        run_odds_export_profile_diagnostic(
            tmp_path / "missing.csv",
            profiles_path,
            output_dir,
        )

    assert "Missing source export" in str(exc.value)
    assert (output_dir / "odds_export_profile_diagnostic.md").exists()


def test_run_odds_export_profile_suggestion_is_read_only(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    profiles_path = tmp_path / "odds_import_profiles.json"
    current_odds_path = tmp_path / "current_odds.csv"
    import_path = tmp_path / "current_odds_import.csv"
    pd.DataFrame([
        {
            "game_date": "2026-08-21",
            "home": "Arsenal",
            "away": "Coventry",
            "bet_type": "1x2",
            "pick": "home",
            "odds": "+120",
            "sportsbook": "ExampleBook",
        }
    ]).to_csv(source_path, index=False)
    profiles_path.write_text('{"profiles":{"keep":{}}}\n', encoding="utf-8")
    current_odds_path.write_text("keep current odds\n", encoding="utf-8")
    import_path.write_text("keep import\n", encoding="utf-8")
    originals = {
        path: path.read_text(encoding="utf-8")
        for path in [profiles_path, current_odds_path, import_path]
    }

    paths = run_odds_export_profile_suggestion("example_book", source_path, output_dir)

    assert paths["status"] == "draft_ready_for_review"
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    for path, original in originals.items():
        assert path.read_text(encoding="utf-8") == original


def test_run_odds_export_profile_suggestion_reports_missing_source_cleanly(tmp_path) -> None:
    output_dir = tmp_path / "outputs"

    with pytest.raises(dashboard_actions.OddsExportProfileSuggestionError) as exc:
        run_odds_export_profile_suggestion(
            "draft_sportsbook",
            tmp_path / "missing.csv",
            output_dir,
        )

    assert "Missing source export" in str(exc.value)
    assert (output_dir / "odds_export_profile_suggestion.md").exists()


def test_run_odds_export_profile_suggestion_validation_is_read_only(tmp_path) -> None:
    source_path = tmp_path / "sportsbook_export.csv"
    suggestion_dir = tmp_path / "suggestion_outputs"
    validation_dir = tmp_path / "validation_outputs"
    profiles_path = tmp_path / "odds_import_profiles.json"
    current_odds_path = tmp_path / "current_odds.csv"
    import_path = tmp_path / "current_odds_import.csv"
    pd.DataFrame([
        {
            "game_date": "2026-08-21",
            "home": "Arsenal",
            "away": "Coventry",
            "bet_type": "1x2",
            "pick": "home",
            "odds": "+120",
            "sportsbook": "ExampleBook",
        }
    ]).to_csv(source_path, index=False)
    profiles_path.write_text('{"profiles":{"keep":{}}}\n', encoding="utf-8")
    current_odds_path.write_text("keep odds\n", encoding="utf-8")
    import_path.write_text("keep import\n", encoding="utf-8")
    originals = {
        path: path.read_text(encoding="utf-8")
        for path in [profiles_path, current_odds_path, import_path]
    }
    suggestion_paths = dashboard_actions.suggest_odds_export_profile(
        source_path,
        "example_book",
        suggestion_dir,
    )

    paths = run_odds_export_profile_suggestion_validation(
        suggestion_paths["json"],
        output_dir=validation_dir,
    )

    assert paths["status"] == "ready"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    for path, original in originals.items():
        assert path.read_text(encoding="utf-8") == original


def test_run_odds_export_profile_suggestion_validation_reports_missing_draft(tmp_path) -> None:
    output_dir = tmp_path / "outputs"

    with pytest.raises(dashboard_actions.OddsExportProfileSuggestionValidationError) as exc:
        run_odds_export_profile_suggestion_validation(
            tmp_path / "missing.json",
            output_dir=output_dir,
        )

    assert "Missing draft suggestion" in str(exc.value)
    assert (output_dir / "odds_export_profile_suggestion_validation.md").exists()


def test_run_odds_profile_install_preview_never_edits_registry(tmp_path) -> None:
    suggestion_path = tmp_path / "suggestion.json"
    validation_markdown = tmp_path / "validation.md"
    validation_csv = tmp_path / "validation.csv"
    registry_path = tmp_path / "odds_import_profiles.json"
    output_dir = tmp_path / "outputs"
    profile = {
        "description": "Reviewed profile",
        "column_map": {
            "game_date": "date",
            "home": "home_team",
            "away": "away_team",
            "bet_type": "market",
            "pick": "selection",
            "odds": "american_odds",
            "sportsbook": "book",
        },
    }
    suggestion_path.write_text(
        json.dumps({"profile_name": "example_book", "suggested_profile": profile}),
        encoding="utf-8",
    )
    validation_markdown.write_text(
        "## Verdict: Ready for manual profile review\n",
        encoding="utf-8",
    )
    pd.DataFrame({"validation_status": ["valid"]}).to_csv(validation_csv, index=False)
    registry_path.write_text('{"profiles":{"generic":{}}}\n', encoding="utf-8")
    original = registry_path.read_text(encoding="utf-8")

    paths = run_odds_profile_install_preview(
        suggestion_path,
        validation_markdown,
        validation_csv,
        registry_path,
        output_dir,
    )

    assert paths["status"] == "preview_ready"
    assert paths["json"].exists()
    assert paths["markdown"].exists()
    assert registry_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "backups").exists()


def test_run_odds_profile_install_preview_reports_missing_suggestion(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    output_dir = tmp_path / "outputs"
    registry_path.write_text('{"profiles":{"generic":{}}}\n', encoding="utf-8")

    with pytest.raises(dashboard_actions.OddsProfileInstallPreviewError) as exc:
        run_odds_profile_install_preview(
            tmp_path / "missing.json",
            registry_path=registry_path,
            output_dir=output_dir,
        )

    assert "Missing suggestion file" in str(exc.value)
    assert (output_dir / "odds_profile_install_preview.md").exists()


def test_run_installed_odds_profile_verification_is_read_only(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    profile = {
        "description": "Installed profile",
        "column_map": {
            "game_date": "date",
            "home": "home_team",
            "away": "away_team",
            "bet_type": "market",
            "pick": "selection",
            "odds": "american_odds",
            "sportsbook": "book",
        },
    }
    registry_path.write_text(
        json.dumps({"profiles": {"example": profile}}),
        encoding="utf-8",
    )
    original = registry_path.read_text(encoding="utf-8")
    pd.DataFrame([
        {
            "game_date": "2026-08-21",
            "home": "Arsenal",
            "away": "Coventry",
            "bet_type": "1x2",
            "pick": "home",
            "odds": "+120",
            "sportsbook": "ExampleBook",
        }
    ]).to_csv(source_path, index=False)

    paths = run_installed_odds_profile_verification(
        "example",
        source_path,
        registry_path,
        output_dir,
    )

    assert paths["status"] == "verified"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert registry_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "current_odds.csv").exists()
    assert not (tmp_path / "current_odds_import.csv").exists()


def test_run_installed_odds_profile_verification_reports_missing_profile(tmp_path) -> None:
    registry_path = tmp_path / "odds_import_profiles.json"
    source_path = tmp_path / "sportsbook_export.csv"
    output_dir = tmp_path / "outputs"
    registry_path.write_text('{"profiles":{"generic":{}}}\n', encoding="utf-8")

    with pytest.raises(dashboard_actions.InstalledOddsProfileVerificationError) as exc:
        run_installed_odds_profile_verification(
            "missing",
            source_path,
            registry_path,
            output_dir,
        )

    assert "not installed" in str(exc.value)
    assert (output_dir / "odds_profile_post_install_verification.md").exists()


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


def test_run_stale_current_odds_report_writes_report_without_editing_odds(tmp_path) -> None:
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
            "book": "FanDuel",
        }
    ]).to_csv(odds_path, index=False)
    original = odds_path.read_text(encoding="utf-8")

    paths = run_stale_current_odds_report(odds_path, output_dir)

    assert paths["csv"].name == "stale_current_odds_report.csv"
    assert paths["markdown"].name == "stale_current_odds_report.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert odds_path.read_text(encoding="utf-8") == original


def test_run_stale_current_odds_archive_preview_never_edits_odds(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([
        {
            "date": "2000-01-01",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-150",
            "book": "FanDuel",
        }
    ]).to_csv(odds_path, index=False)
    original = odds_path.read_bytes()

    paths = run_stale_current_odds_archive_preview(odds_path, output_dir)

    assert paths["status"] == "preview_ready"
    assert paths["csv"].name == "stale_current_odds_archive_preview.csv"
    assert paths["markdown"].name == "stale_current_odds_archive_preview.md"
    assert paths["metadata"].name == "stale_current_odds_archive_preview.json"
    assert len(str(paths["confirm_id"])) == 64
    assert paths["confirmation_gate_result"] == "Preview ready"
    assert odds_path.read_bytes() == original
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()


def test_stale_archive_confirmation_dashboard_actions_are_read_only(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([
        {
            "date": "2000-01-01",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-150",
            "book": "FanDuel",
        }
    ]).to_csv(odds_path, index=False)
    run_stale_current_odds_archive_preview(odds_path, output_dir)
    original = odds_path.read_bytes()

    report, summary = get_stale_current_odds_archive_confirmation_status(
        odds_path,
        output_dir,
    )
    paths = run_stale_current_odds_archive_confirmation_status(
        odds_path,
        output_dir,
    )

    assert len(report) == 1
    assert summary["status"] == "Ready"
    assert paths["status"] == "Ready"
    assert paths["csv"].name == "stale_current_odds_archive_confirmation_status.csv"
    assert paths["markdown"].name == "stale_current_odds_archive_confirmation_status.md"
    assert odds_path.read_bytes() == original
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()


def test_run_stale_current_odds_archive_rollback_preview_never_edits_odds(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    backup_path = tmp_path / "2026-07-21_current_odds_pre_stale_archive.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-150",
            "book": "FanDuel",
        }
    ]).to_csv(odds_path, index=False)
    pd.DataFrame([
        {
            "date": "2026-07-20",
            "home_team": "Chelsea",
            "away_team": "Everton",
            "market": "1x2",
            "selection": "draw",
            "american_odds": "+240",
            "book": "FanDuel",
        },
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-150",
            "book": "FanDuel",
        },
    ]).to_csv(backup_path, index=False)
    odds_before = odds_path.read_bytes()
    backup_before = backup_path.read_bytes()

    paths = run_stale_current_odds_archive_rollback_preview(
        backup_path,
        odds_path,
        output_dir,
    )

    assert paths["status"] == "preview_ready"
    assert paths["csv"].name == "stale_current_odds_archive_rollback_preview.csv"
    assert paths["markdown"].name == "stale_current_odds_archive_rollback_preview.md"
    assert paths["metadata"].name == "stale_current_odds_archive_rollback_preview.json"
    assert paths["confirm_id"]
    assert paths["confirmation_gate_result"] == "Preview ready"
    assert odds_path.read_bytes() == odds_before
    assert backup_path.read_bytes() == backup_before
    assert not (tmp_path / "backups").exists()
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()


def test_stale_current_odds_backup_list_actions_are_read_only(tmp_path) -> None:
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()
    backup_path = backups_dir / "2026-07-21_110000_current_odds_pre_stale_archive.csv"
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    archive_audit_path = output_dir / "stale_current_odds_archive_audit.csv"
    rollback_audit_path = output_dir / "stale_current_odds_archive_rollback_audit.csv"
    pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "american_odds": "-150",
            "book": "FanDuel",
        }
    ]).to_csv(backup_path, index=False)
    pd.DataFrame([
        {
            "archive_id": "dashboard-archive",
            "applied_at": "2026-07-21T11:00:00-04:00",
            "status": "applied",
            "backup_path": str(backup_path),
            "stale_rows_archived": "1",
            "source_sha256_before": source_file_sha256(backup_path),
        }
    ]).to_csv(archive_audit_path, index=False)
    before = backup_path.read_bytes()

    backup_list, summary = get_stale_current_odds_backup_list(
        backups_dir,
        archive_audit_path,
        rollback_audit_path,
    )
    paths = run_stale_current_odds_backup_list(
        backups_dir,
        output_dir,
        archive_audit_path,
        rollback_audit_path,
    )

    assert summary["status"] == "ready"
    assert backup_list["backup_path"].tolist() == [str(backup_path)]
    assert backup_list.iloc[0]["created_by_operation"] == "archive_apply"
    assert backup_list.iloc[0]["checksum_status"] == "Verified"
    assert paths["csv"].name == "stale_current_odds_backup_list.csv"
    assert paths["markdown"].name == "stale_current_odds_backup_list.md"
    assert backup_path.read_bytes() == before
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()


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


def test_run_github_manual_thursday_verification_uses_selected_output_dir(
    tmp_path, monkeypatch
) -> None:
    output_dir = tmp_path / "outputs"
    expected = {
        "csv": output_dir / "github_manual_thursday_run_verification.csv",
        "markdown": output_dir / "github_manual_thursday_run_verification.md",
        "verdict": "Verified blocked run",
        "next_step": "Fix the listed blockers.",
    }

    def fake_save(selected_output_dir):
        assert selected_output_dir == output_dir
        return expected

    monkeypatch.setattr(
        dashboard_actions,
        "save_github_manual_run_verification",
        fake_save,
    )

    assert run_github_manual_thursday_verification(output_dir) == expected
