from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, MIN_EDGE, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_current_odds, load_matches, load_upcoming_fixtures
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.reports.bet_ledger import load_bet_ledger, save_bet_ledger_reports
from epl_betting_lab.reports.bet_ledger_health import save_bet_ledger_health_check
from epl_betting_lab.reports.bet_settlement import build_settlement_preview, save_settlement_preview
from epl_betting_lab.reports.current_odds_validation import (
    CurrentOddsValidationError,
    build_current_odds_validation,
    has_serious_issues,
    render_current_odds_validation_report,
    save_current_odds_validation,
    validation_stop_message,
)
from epl_betting_lab.reports.current_odds_completeness import save_current_odds_completeness
from epl_betting_lab.reports.current_odds_import import process_current_odds_import
from epl_betting_lab.reports.current_odds_template import create_current_odds_template
from epl_betting_lab.reports.current_odds_maintenance import maintain_current_odds
from epl_betting_lab.reports.github_manual_run_verification import (
    save_github_manual_run_verification,
)
from epl_betting_lab.reports.epl_weekly_pipeline_history import (
    compare_latest_epl_weekly_pipeline_runs,
)
from epl_betting_lab.reports.epl_weekly_pipeline_receipt_verification import (
    save_epl_weekly_pipeline_receipt_verification,
)
from epl_betting_lab.reports.odds_export_conversion import (
    OddsExportConversionError,
    convert_odds_export,
)
from epl_betting_lab.reports.odds_export_profile_diagnostic import (
    FATAL_DIAGNOSTIC_STATUSES,
    OddsExportProfileDiagnosticError,
    diagnose_odds_export_profiles,
)
from epl_betting_lab.reports.odds_export_profile_suggestion import (
    FATAL_SUGGESTION_STATUSES,
    OddsExportProfileSuggestionError,
    suggest_odds_export_profile,
)
from epl_betting_lab.reports.odds_export_profile_suggestion_validation import (
    FATAL_VALIDATION_STATUSES,
    OddsExportProfileSuggestionValidationError,
    validate_odds_export_profile_suggestion_file,
)
from epl_betting_lab.reports.odds_profile_install import (
    FATAL_INSTALL_PREVIEW_STATUSES,
    OddsProfileInstallPreviewError,
    process_odds_profile_install,
)
from epl_betting_lab.reports.odds_profile_verification import (
    FATAL_VERIFICATION_STATUSES,
    InstalledOddsProfileVerificationError,
    verify_installed_odds_profile,
)
from epl_betting_lab.reports.provider_acceptance_checklist import (
    save_provider_acceptance_checklist,
)
from epl_betting_lab.reports.provider_allowlist_pr_conformance import (
    save_provider_allowlist_pr_conformance,
)
from epl_betting_lab.reports.provider_allowlist_evidence_bundle import (
    save_provider_allowlist_evidence_bundle,
)
from epl_betting_lab.reports.provider_allowlist_evidence_bundle_verification import (
    save_provider_allowlist_evidence_bundle_verification,
)
from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    save_provider_allowlist_pr_preview,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt_verification import (
    save_provider_human_acceptance_receipt_verification,
)
from epl_betting_lab.reports.provider_policy_pr_gate import (
    save_provider_policy_pr_gate,
)
from epl_betting_lab.reports.provider_policy_pr_gate_receipt_verification import (
    save_provider_policy_pr_gate_receipt_verification,
)
from epl_betting_lab.reports.provider_policy_pr_gate_verification_archive import (
    save_provider_policy_pr_gate_verification_archive,
)
from epl_betting_lab.reports.provider_shadow_history import (
    save_provider_shadow_run_comparison,
)
from epl_betting_lab.reports.staging_input_validation import (
    save_staging_input_validation,
)
from epl_betting_lab.reports.stale_current_odds import save_stale_current_odds_report
from epl_betting_lab.reports.stale_current_odds_archive import (
    CONFIRMATION_METADATA_FILENAME,
    archive_stale_current_odds,
)
from epl_betting_lab.reports.stale_current_odds_archive_confirmation import (
    build_stale_current_odds_archive_confirmation_status,
    save_stale_current_odds_archive_confirmation_status,
)
from epl_betting_lab.reports.stale_current_odds_archive_rollback import (
    process_stale_current_odds_archive_rollback,
)
from epl_betting_lab.reports.stale_current_odds_backup_picker import (
    build_stale_current_odds_backup_list,
    save_stale_current_odds_backup_list,
)
from epl_betting_lab.reports.thursday_best_bets import (
    build_thursday_best_bets,
    list_recent_thursday_archives,
    missing_current_odds_message,
    save_thursday_best_bets,
)
from epl_betting_lab.reports.thursday_best_bets_comparison import save_thursday_best_bets_comparison
from epl_betting_lab.reports.thursday_decision_queue import save_thursday_decision_queue
from epl_betting_lab.reports.tier_performance import save_tier_performance_reports
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.totals import evaluate_total_25


def require_existing_ledger(ledger_path: Path | None = None) -> pd.DataFrame:
    path = ledger_path or MANUAL_DIR / "bet_ledger.csv"
    if not path.exists():
        raise FileNotFoundError(
            "Missing data/manual/bet_ledger.csv. Run `python scripts/run_bet_ledger.py` once from Terminal to create it."
        )
    return load_bet_ledger(path)


def require_existing_current_odds(current_odds_path: Path | None = None) -> Path:
    path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    if not path.exists():
        raise FileNotFoundError(missing_current_odds_message(path))
    return path


def run_bet_ledger_report(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_bet_ledger_reports(require_existing_ledger(ledger_path), output_dir or OUTPUTS_DIR)


def run_ledger_health_check(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_bet_ledger_health_check(require_existing_ledger(ledger_path), output_dir or OUTPUTS_DIR)


def run_settlement_preview(
    ledger_path: Path | None = None,
    matches_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    ledger = require_existing_ledger(ledger_path)
    matches = load_matches(matches_path)
    preview = build_settlement_preview(ledger, matches)
    return save_settlement_preview(preview, output_dir or OUTPUTS_DIR)


def run_current_odds_validation(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_current_odds_validation(current_odds_path or MANUAL_DIR / "current_odds.csv", output_dir or OUTPUTS_DIR)


def run_staging_input_validation(
    odds_path: Path | None = None,
    fixtures_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, object]:
    return save_staging_input_validation(
        odds_path,
        fixtures_path,
        output_dir=output_dir or OUTPUTS_DIR,
    )


def run_current_odds_completeness(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    fixtures = load_upcoming_fixtures()
    return save_current_odds_completeness(
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
        fixtures=fixtures,
    )


def _run_refresh_step(
    step_name: str,
    action,
    progress=None,
) -> dict[str, Path]:
    if progress is not None:
        progress(step_name, "running", f"Running {step_name}.")
    try:
        paths = action()
    except Exception as exc:
        if progress is not None:
            progress(step_name, "error", f"{step_name} stopped: {exc}")
        raise
    if progress is not None:
        progress(step_name, "success", f"{step_name} finished.")
    return paths


def run_thursday_readiness_refresh(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    progress=None,
) -> dict[str, dict[str, Path]]:
    """Run safe Thursday reports in order without editing odds or forcing generation."""
    odds_path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    outputs = output_dir or OUTPUTS_DIR
    return {
        "odds_completeness": _run_refresh_step(
            "Odds completeness check",
            lambda: run_current_odds_completeness(odds_path, outputs),
            progress,
        ),
        "current_odds_validation": _run_refresh_step(
            "Current odds validation",
            lambda: run_current_odds_validation(odds_path, outputs),
            progress,
        ),
        "thursday_best_bets": _run_refresh_step(
            "Thursday best-bets generation",
            lambda: run_thursday_best_bets_report(odds_path, outputs, force=False),
            progress,
        ),
    }


def run_create_current_odds_template(
    current_odds_path: Path | None = None,
    book: str = "",
) -> dict[str, Path]:
    fixtures = load_upcoming_fixtures()
    path, _, _ = create_current_odds_template(
        fixtures,
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        overwrite=False,
        book=book,
    )
    return {"csv": path}


def run_current_odds_maintenance_preview(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    book: str = "",
) -> dict[str, Path]:
    fixtures = load_upcoming_fixtures()
    return maintain_current_odds(
        fixtures,
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
        apply=False,
        book=book,
    )


def run_stale_current_odds_report(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_stale_current_odds_report(
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
    )


def run_stale_current_odds_archive_preview(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    return archive_stale_current_odds(
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
        apply=False,
    )


def get_stale_current_odds_archive_confirmation_status(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    outputs = output_dir or OUTPUTS_DIR
    return build_stale_current_odds_archive_confirmation_status(
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        outputs / CONFIRMATION_METADATA_FILENAME,
    )


def run_stale_current_odds_archive_confirmation_status(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    return save_stale_current_odds_archive_confirmation_status(
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
    )


def run_stale_current_odds_archive_rollback_preview(
    backup_path: Path | str | None,
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    return process_stale_current_odds_archive_rollback(
        backup_path,
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
        apply=False,
    )


def get_stale_current_odds_backup_list(
    backups_dir: Path | None = None,
    archive_audit_path: Path | None = None,
    rollback_audit_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    return build_stale_current_odds_backup_list(
        backups_dir or MANUAL_DIR / "backups",
        archive_audit_path=archive_audit_path,
        rollback_audit_path=rollback_audit_path,
    )


def run_stale_current_odds_backup_list(
    backups_dir: Path | None = None,
    output_dir: Path | None = None,
    archive_audit_path: Path | None = None,
    rollback_audit_path: Path | None = None,
) -> dict[str, Path | str]:
    return save_stale_current_odds_backup_list(
        backups_dir or MANUAL_DIR / "backups",
        output_dir or OUTPUTS_DIR,
        archive_audit_path=archive_audit_path,
        rollback_audit_path=rollback_audit_path,
    )


def run_current_odds_import_preview(
    import_path: Path | None = None,
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    fixtures: pd.DataFrame | None = None,
    matches: pd.DataFrame | None = None,
) -> dict[str, Path]:
    return process_current_odds_import(
        import_path or MANUAL_DIR / "current_odds_import.csv",
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
        apply=False,
        fixtures=fixtures,
        matches=matches,
    )


def run_odds_export_conversion_preview(
    profile_name: str = "generic",
    source_path: Path | None = None,
    profiles_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    paths = convert_odds_export(
        profile_name,
        source_path or MANUAL_DIR / "sportsbook_export.csv",
        profiles_path or MANUAL_DIR / "odds_import_profiles.json",
        MANUAL_DIR / "current_odds_import.csv",
        output_dir or OUTPUTS_DIR,
        write_import=False,
    )
    if paths["status"] != "preview_only":
        raise OddsExportConversionError(str(paths.get("message", "Conversion preview could not run.")))
    return paths


def run_odds_export_profile_diagnostic(
    source_path: Path | None = None,
    profiles_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    paths = diagnose_odds_export_profiles(
        source_path or MANUAL_DIR / "sportsbook_export.csv",
        profiles_path or MANUAL_DIR / "odds_import_profiles.json",
        output_dir or OUTPUTS_DIR,
    )
    if paths["status"] in FATAL_DIAGNOSTIC_STATUSES:
        raise OddsExportProfileDiagnosticError(
            str(paths.get("message", "Odds export profile diagnostic could not run."))
        )
    return paths


def run_odds_export_profile_suggestion(
    profile_name: str = "draft_sportsbook",
    source_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    paths = suggest_odds_export_profile(
        source_path or MANUAL_DIR / "sportsbook_export.csv",
        profile_name,
        output_dir or OUTPUTS_DIR,
    )
    if paths["status"] in FATAL_SUGGESTION_STATUSES:
        raise OddsExportProfileSuggestionError(
            str(paths.get("message", "Odds export profile suggestion could not run."))
        )
    return paths


def run_odds_export_profile_suggestion_validation(
    suggestion_path: Path | None = None,
    source_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    paths = validate_odds_export_profile_suggestion_file(
        suggestion_path or OUTPUTS_DIR / "odds_export_profile_suggestion.json",
        source_path,
        output_dir or OUTPUTS_DIR,
    )
    if paths["status"] in FATAL_VALIDATION_STATUSES:
        raise OddsExportProfileSuggestionValidationError(
            str(paths.get("message", "Draft odds profile validation could not run."))
        )
    return paths


def run_odds_profile_install_preview(
    suggestion_path: Path | None = None,
    validation_markdown_path: Path | None = None,
    validation_csv_path: Path | None = None,
    registry_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    outputs = output_dir or OUTPUTS_DIR
    paths = process_odds_profile_install(
        suggestion_path or outputs / "odds_export_profile_suggestion.json",
        validation_markdown_path or outputs / "odds_export_profile_suggestion_validation.md",
        validation_csv_path or outputs / "odds_export_profile_suggestion_validation.csv",
        registry_path or MANUAL_DIR / "odds_import_profiles.json",
        outputs,
        apply=False,
    )
    if paths["status"] in FATAL_INSTALL_PREVIEW_STATUSES:
        raise OddsProfileInstallPreviewError(
            str(paths.get("message", "Odds profile installation preview could not run."))
        )
    return paths


def run_installed_odds_profile_verification(
    profile_name: str = "generic",
    source_path: Path | None = None,
    registry_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    paths = verify_installed_odds_profile(
        profile_name,
        source_path or MANUAL_DIR / "sportsbook_export.csv",
        registry_path or MANUAL_DIR / "odds_import_profiles.json",
        output_dir or OUTPUTS_DIR,
    )
    if paths["status"] in FATAL_VERIFICATION_STATUSES:
        raise InstalledOddsProfileVerificationError(
            str(paths.get("message", "Installed odds profile verification could not run."))
        )
    return paths


def run_thursday_best_bets_comparison(output_dir: Path | None = None) -> dict[str, Path]:
    return save_thursday_best_bets_comparison(output_dir or OUTPUTS_DIR)


def run_provider_shadow_run_comparison(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
) -> dict[str, object]:
    return save_provider_shadow_run_comparison(
        provider_name,
        output_dir or OUTPUTS_DIR,
    )


def run_provider_acceptance_checklist(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
) -> dict[str, object]:
    return save_provider_acceptance_checklist(
        provider_name,
        output_dir or OUTPUTS_DIR,
    )


def run_provider_human_acceptance_receipt_verification(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
    receipt_path: Path | None = None,
) -> dict[str, object]:
    return save_provider_human_acceptance_receipt_verification(
        provider_name,
        output_dir or OUTPUTS_DIR,
        receipt_path=receipt_path,
    )


def run_provider_allowlist_pr_preview(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
    verification_path: Path | None = None,
) -> dict[str, object]:
    return save_provider_allowlist_pr_preview(
        provider_name,
        output_dir or OUTPUTS_DIR,
        verification_path=verification_path,
    )


def run_provider_allowlist_pr_conformance(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
    preview_path: Path | None = None,
    policy_path: Path | None = None,
) -> dict[str, object]:
    return save_provider_allowlist_pr_conformance(
        provider_name,
        output_dir or OUTPUTS_DIR,
        preview_path=preview_path,
        policy_path=policy_path,
    )


def run_provider_allowlist_evidence_bundle(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
    policy_path: Path | None = None,
) -> dict[str, object]:
    return save_provider_allowlist_evidence_bundle(
        provider_name,
        output_dir or OUTPUTS_DIR,
        policy_path=policy_path,
    )


def run_provider_allowlist_evidence_bundle_verification(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
    bundle_path: Path | None = None,
) -> dict[str, object]:
    return save_provider_allowlist_evidence_bundle_verification(
        provider_name,
        output_dir or OUTPUTS_DIR,
        bundle_path=bundle_path,
    )


def run_provider_policy_pr_gate(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
) -> dict[str, object]:
    return save_provider_policy_pr_gate(
        provider_name,
        output_dir or OUTPUTS_DIR,
    )


def run_provider_policy_pr_gate_receipt_verification(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
    gate_report_path: Path | None = None,
) -> dict[str, object]:
    return save_provider_policy_pr_gate_receipt_verification(
        provider_name,
        output_dir or OUTPUTS_DIR,
        gate_report_path=gate_report_path,
    )


def run_provider_policy_pr_gate_verification_archive(
    provider_name: str = "odds_api",
    output_dir: Path | None = None,
    verification_path: Path | None = None,
) -> dict[str, object]:
    return save_provider_policy_pr_gate_verification_archive(
        provider_name,
        output_dir or OUTPUTS_DIR,
        verification_path=verification_path,
    )


def run_thursday_decision_queue(output_dir: Path | None = None) -> dict[str, Path]:
    return save_thursday_decision_queue(output_dir or OUTPUTS_DIR)


def run_tier_performance_report(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_tier_performance_reports(ledger_path or MANUAL_DIR / "bet_ledger.csv", output_dir or OUTPUTS_DIR)


def run_epl_weekly_pipeline(
    output_dir: Path | None = None,
    progress=None,
) -> dict[str, object]:
    # Local import avoids the dashboard -> scheduled workflow -> dashboard import cycle.
    from epl_betting_lab.reports.epl_weekly_pipeline import (
        run_epl_weekly_pipeline as run_pipeline,
    )

    return run_pipeline(
        output_dir=output_dir or OUTPUTS_DIR,
        progress=progress,
    )


def run_epl_weekly_pipeline_comparison(
    output_dir: Path | None = None,
) -> dict[str, object]:
    return compare_latest_epl_weekly_pipeline_runs(output_dir or OUTPUTS_DIR)


def run_epl_weekly_pipeline_receipt_verification(
    output_dir: Path | None = None,
    archive_path: Path | None = None,
) -> dict[str, object]:
    return save_epl_weekly_pipeline_receipt_verification(
        archive_path=archive_path,
        output_dir=output_dir or OUTPUTS_DIR,
    )


def run_github_manual_thursday_verification(
    output_dir: Path | None = None,
) -> dict[str, object]:
    return save_github_manual_run_verification(output_dir or OUTPUTS_DIR)


def run_post_thursday_review(
    output_dir: Path | None = None,
    progress=None,
) -> dict[str, dict[str, Path]]:
    """Run the read-only post-refresh review reports without editing odds or ledger files."""
    outputs = output_dir or OUTPUTS_DIR
    comparison_paths = _run_refresh_step(
        "Thursday snapshot comparison",
        lambda: run_thursday_best_bets_comparison(outputs),
        progress,
    )
    archives = list_recent_thursday_archives(outputs, limit=2)
    if len(archives) < 2:
        message = (
            "Comparison is not available yet. Generate at least two Thursday best-bets archive snapshots first, "
            "then run post-refresh Thursday review again."
        )
        if progress is not None:
            progress("Thursday decision queue", "error", message)
        raise FileNotFoundError(message)

    decision_queue_paths = _run_refresh_step(
        "Thursday decision queue",
        lambda: run_thursday_decision_queue(outputs),
        progress,
    )
    return {
        "comparison": comparison_paths,
        "decision_queue": decision_queue_paths,
    }


def run_thursday_best_bets_report(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    force: bool = False,
    archive: bool = True,
    overwrite_archive: bool = False,
    matches_path: Path | None = None,
    fixtures_path: Path | None = None,
) -> dict[str, Path]:
    odds_path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    output_dir = output_dir or OUTPUTS_DIR
    if not odds_path.exists():
        validation_issues = build_current_odds_validation(odds_path, matches=pd.DataFrame(), fixtures=pd.DataFrame())
        output_dir.mkdir(parents=True, exist_ok=True)
        validation_issues.to_csv(output_dir / "current_odds_validation.csv", index=False)
        (output_dir / "current_odds_validation.md").write_text(
            render_current_odds_validation_report(validation_issues),
            encoding="utf-8",
        )
        raise CurrentOddsValidationError(validation_stop_message(validation_issues, output_dir))

    matches = load_matches(matches_path) if matches_path is not None else load_matches()
    fixtures = (
        load_upcoming_fixtures(fixtures_path)
        if fixtures_path is not None
        else load_upcoming_fixtures()
    )
    validation_issues = build_current_odds_validation(odds_path, matches=matches, fixtures=fixtures)
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_issues.to_csv(output_dir / "current_odds_validation.csv", index=False)
    (output_dir / "current_odds_validation.md").write_text(
        render_current_odds_validation_report(validation_issues),
        encoding="utf-8",
    )

    if has_serious_issues(validation_issues) and not force:
        raise CurrentOddsValidationError(validation_stop_message(validation_issues, output_dir))

    odds = load_current_odds(odds_path)

    model = PoissonGoalsModel().fit(matches, last_n_matches_per_team=38)
    projections = model.project_fixtures(fixtures)
    candidates = pd.concat([
        evaluate_1x2_value(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
        evaluate_total_25(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE, matches=matches),
        evaluate_btts(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
    ], ignore_index=True)

    report = build_thursday_best_bets(candidates)
    return save_thursday_best_bets(
        report,
        output_dir,
        validation_issues=validation_issues,
        forced=force,
        archive=archive,
        overwrite_archive=overwrite_archive,
    )
