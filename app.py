from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from epl_betting_lab.backtest.walk_forward import summarize_backtest
from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, MIN_EDGE, OUTPUTS_DIR
from epl_betting_lab.current_odds_status import build_current_odds_status
from epl_betting_lab.dashboard_portal import (
    HOME_PORTAL_SECTION,
    ODDS_IMPORT_STEPS,
    PORTAL_NAVIGATION_REQUEST_KEY,
    PORTAL_QUERY_PARAM,
    PORTAL_SECTION_STATE_KEY,
    PORTAL_SECTIONS,
    SECTION_DESCRIPTIONS,
    apply_portal_query_navigation,
    build_portal_breadcrumb,
    build_ledger_portal_summary,
    portal_slug_from_section,
    request_portal_home_navigation,
    resolve_open_next_section,
)
from epl_betting_lab.dashboard_actions import (
    get_stale_current_odds_archive_confirmation_status,
    get_stale_current_odds_backup_list,
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
    run_stale_current_odds_archive_preview,
    run_stale_current_odds_archive_confirmation_status,
    run_stale_current_odds_archive_rollback_preview,
    run_stale_current_odds_backup_list,
    run_stale_current_odds_report,
    run_staging_input_validation,
    run_settlement_preview,
    run_tier_performance_report,
    run_thursday_best_bets_comparison,
    run_thursday_best_bets_report,
    run_thursday_decision_queue,
    run_thursday_readiness_refresh,
)
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures, load_current_odds
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.models.ratings import simple_form_table
from epl_betting_lab.reports.current_odds_validation import CurrentOddsValidationError
from epl_betting_lab.reports.current_odds_import_audit import (
    load_current_odds_import_audit,
    summarize_current_odds_import_batches,
)
from epl_betting_lab.reports.odds_export_conversion import OddsExportConversionError
from epl_betting_lab.reports.odds_export_profile_diagnostic import (
    OddsExportProfileDiagnosticError,
)
from epl_betting_lab.reports.odds_export_profile_suggestion import (
    OddsExportProfileSuggestionError,
)
from epl_betting_lab.reports.odds_export_profile_suggestion_validation import (
    OddsExportProfileSuggestionValidationError,
)
from epl_betting_lab.reports.odds_profile_install import (
    OddsProfileInstallPreviewError,
)
from epl_betting_lab.reports.odds_profile_verification import (
    InstalledOddsProfileVerificationError,
)
from epl_betting_lab.reports.thursday_archive_pair import (
    build_thursday_archive_history_details,
    build_thursday_archive_count_change_note,
    build_thursday_archive_count_change_risk,
    build_thursday_archive_pair,
)
from epl_betting_lab.reports.thursday_best_bets import list_recent_thursday_archives
from epl_betting_lab.reports.thursday_best_bets_comparison import (
    build_recommended_next_action,
    build_top_card_movement_reason,
)
from epl_betting_lab.reports.weekly_card import build_weekly_card, card_to_markdown
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.promoted_fades import flag_promoted_team_spots
from epl_betting_lab.strategies.totals import evaluate_total_25
from epl_betting_lab.thursday_command_center import (
    ThursdayCommandCenter,
    build_thursday_command_center,
)
from epl_betting_lab.thursday_readiness import build_thursday_readiness
from epl_betting_lab.workflow_status import (
    build_data_freshness_status,
    build_workflow_status,
    recommend_data_freshness_action,
)
from scripts import run_backtest


def read_output_csv(filename: str) -> pd.DataFrame | None:
    path = OUTPUTS_DIR / filename
    if not path.exists():
        return None
    return pd.read_csv(path)


def show_missing_report(filename: str, command: str) -> None:
    st.info(f"No `{filename}` found yet. Run `{command}` from Terminal, then refresh the dashboard.")


def show_output_table(title: str, filename: str, command: str) -> pd.DataFrame | None:
    st.subheader(title)
    df = read_output_csv(filename)
    if df is None:
        show_missing_report(f"data/outputs/{filename}", command)
        return None
    if df.empty:
        st.info("The report exists, but it has no rows yet.")
    else:
        st.dataframe(df, width="stretch", hide_index=True)
    return df


def render_markdown_expander(
    title: str,
    filename: str,
    command: str,
    *,
    expanded: bool = False,
) -> None:
    with st.expander(title, expanded=expanded):
        path = OUTPUTS_DIR / filename
        if not path.exists():
            show_missing_report(f"data/outputs/{filename}", command)
            return
        try:
            st.markdown(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            st.warning(f"This report could not be read: {exc}")


def render_table_expander(
    title: str,
    filename: str,
    command: str,
    *,
    expanded: bool = False,
) -> pd.DataFrame | None:
    with st.expander(title, expanded=expanded):
        return show_output_table(title, filename, command)


def render_status_message(status: str, message: str) -> None:
    normalized = status.strip().lower()
    if normalized == "ready":
        st.success(message)
    elif normalized in {"blocked", "needs review"}:
        st.error(message)
    elif normalized in {"warnings only", "needs refresh"}:
        st.warning(message)
    else:
        st.info(message)


def sync_portal_query_param(section: object) -> None:
    slug = portal_slug_from_section(section)
    if st.query_params.get_all(PORTAL_QUERY_PARAM) != [slug]:
        st.query_params[PORTAL_QUERY_PARAM] = slug


def sync_portal_query_from_sidebar() -> None:
    sync_portal_query_param(st.session_state.get(PORTAL_SECTION_STATE_KEY))


def render_back_to_home() -> None:
    if st.button(
        "Back to Home",
        key="portal_back_to_home",
        help="Return to Home / Command Center without running any action.",
        width="content",
    ):
        destination = request_portal_home_navigation(st.session_state)
        sync_portal_query_param(destination)
        st.rerun()


def run_dashboard_action(label: str, action) -> None:
    try:
        action()
    except CurrentOddsValidationError as exc:
        st.error(f"{label} stopped.")
        st.info(str(exc))
    except OddsExportConversionError as exc:
        st.error(f"{label} could not run.")
        st.info(str(exc))
    except OddsExportProfileDiagnosticError as exc:
        st.error(f"{label} could not run.")
        st.info(str(exc))
    except OddsExportProfileSuggestionError as exc:
        st.error(f"{label} could not run.")
        st.info(str(exc))
    except OddsExportProfileSuggestionValidationError as exc:
        st.error(f"{label} could not run.")
        st.info(str(exc))
    except OddsProfileInstallPreviewError as exc:
        st.error(f"{label} could not run.")
        st.info(str(exc))
    except InstalledOddsProfileVerificationError as exc:
        st.error(f"{label} could not run.")
        st.info(str(exc))
    except FileExistsError as exc:
        st.warning(f"{label} stopped.")
        st.info(str(exc))
    except FileNotFoundError as exc:
        st.error(f"{label} failed.")
        st.info(str(exc))
    except Exception as exc:
        st.error(f"{label} failed.")
        st.exception(exc)
    else:
        st.success(f"{label} finished. Refreshing dashboard data.")
        st.rerun()


def run_dashboard_refresh_sequence() -> None:
    def progress(step_name: str, status: str, message: str) -> None:
        if status == "running":
            st.info(message)
        elif status == "success":
            st.success(message)
        else:
            st.error(message)

    try:
        run_thursday_readiness_refresh(progress=progress)
    except CurrentOddsValidationError as exc:
        st.error("Thursday readiness refresh stopped safely.")
        st.info(str(exc))
    except FileNotFoundError as exc:
        st.error("Thursday readiness refresh failed.")
        st.info(str(exc))
    except Exception as exc:
        st.error("Thursday readiness refresh failed.")
        st.exception(exc)
    else:
        st.success("Thursday readiness refresh finished. Refreshing dashboard data.")
        st.rerun()


def run_dashboard_post_thursday_review() -> None:
    def progress(step_name: str, status: str, message: str) -> None:
        if status == "running":
            st.info(message)
        elif status == "success":
            st.success(message)
        else:
            st.error(message)

    try:
        run_post_thursday_review(progress=progress)
    except FileNotFoundError as exc:
        st.warning("Post-refresh Thursday review stopped.")
        st.info(str(exc))
    except Exception as exc:
        st.error("Post-refresh Thursday review failed.")
        st.exception(exc)
    else:
        st.success("Post-refresh Thursday review finished. Refreshing dashboard data.")
        st.rerun()


def render_workflow_checklist() -> None:
    status = build_workflow_status()
    counts = status["status"].value_counts().to_dict()
    metric_cols = st.columns(3)
    metric_cols[0].metric("Complete", int(counts.get("Complete", 0)))
    metric_cols[1].metric("Needs refresh", int(counts.get("Needs refresh", 0)))
    metric_cols[2].metric("Missing", int(counts.get("Missing", 0)))
    st.dataframe(status, width="stretch", hide_index=True)


def render_data_freshness(command_center: ThursdayCommandCenter) -> None:
    freshness = build_data_freshness_status()
    counts = freshness["status"].value_counts().to_dict()

    st.subheader("Data freshness")
    metric_cols = st.columns(5)
    for column, label in zip(
        metric_cols,
        ("Fresh", "Stale", "Missing", "Needs refresh", "Not checked"),
        strict=True,
    ):
        column.metric(label, int(counts.get(label, 0)))

    recommendation = recommend_data_freshness_action(freshness)
    warning_mask = freshness["warning"].fillna("").astype(str).str.strip() != ""
    if (freshness["status"] == "Fresh").all() and not warning_mask.any():
        st.success(recommendation)
    else:
        st.warning(recommendation)

    attention = freshness[(freshness["status"] != "Fresh") | warning_mask]
    if not attention.empty:
        visible = attention.head(4)
        labels = [
            f"{row.item} ({'Warning' if row.status == 'Fresh' and row.warning else row.status})"
            for row in visible.itertuples()
        ]
        extra = len(attention) - len(visible)
        suffix = f"; plus {extra} more" if extra else ""
        st.caption(f"Needs attention: {', '.join(labels)}{suffix}. Open details below.")

    with st.expander("Data freshness details", expanded=False):
        detail_columns = [
            "item",
            "status",
            "last_modified",
            "source_last_modified",
            "earliest_fixture_date",
            "latest_fixture_date",
            "past_fixtures",
            "today_or_future_fixtures",
            "invalid_fixture_dates",
            "earliest_odds_date",
            "latest_odds_date",
            "past_odds_rows",
            "today_or_future_odds_rows",
            "invalid_odds_date_rows",
            "warning",
            "file",
            "source_files",
            "command",
            "note",
        ]
        st.dataframe(freshness[detail_columns], width="stretch", hide_index=True)
        st.markdown("**Stale odds archive confirmation**")
        st.caption(
            f"{command_center.archive_confirmation_status}. "
            f"{command_center.archive_confirmation_message}"
        )
        if command_center.archive_confirmation_id:
            st.caption(f"Confirmation ID: `{command_center.archive_confirmation_id}`")
        st.caption("Timestamps use your computer's local time. No files are changed by this check.")


def render_open_next_cue(cue: object) -> None:
    cue_text = str(cue or "").strip()
    destination = resolve_open_next_section(cue)
    if cue_text:
        st.caption(f"Open this next: {cue_text}")
    if destination is None:
        st.button(
            "Choose a portal section from the sidebar",
            key="open_next_unavailable",
            disabled=True,
            width="stretch",
        )
        st.caption("No safe direct destination is available for this cue yet.")
        return

    if st.button(
        f"Open {destination}",
        key="open_next_destination",
        width="stretch",
    ):
        st.session_state[PORTAL_NAVIGATION_REQUEST_KEY] = destination
        sync_portal_query_param(destination)
        st.rerun()


def render_command_center_card(command_center: ThursdayCommandCenter) -> None:
    ledger = build_ledger_portal_summary()
    units = "Missing" if ledger.profit_units is None else f"{ledger.profit_units:+.3f}u"
    roi = "Missing" if ledger.roi is None else f"{ledger.roi:.1%}"
    pending = "Missing" if ledger.pending_bets is None else ledger.pending_bets

    with st.container(border=True):
        st.subheader("Thursday command center")
        thursday_top = st.columns(2)
        thursday_top[0].metric("Thursday status", command_center.thursday_status)
        thursday_top[1].metric("Odds complete", command_center.odds_completion)
        thursday_issues = st.columns(2)
        thursday_issues[0].metric("Serious issues", command_center.serious_validation_issues)
        thursday_issues[1].metric("Warnings", command_center.validation_warnings)

        ledger_top = st.columns(2)
        ledger_top[0].metric("Ledger record", ledger.record)
        ledger_top[1].metric("Ledger units", units)
        ledger_bottom = st.columns(2)
        ledger_bottom[0].metric("Ledger ROI", roi)
        ledger_bottom[1].metric("Pending bets", pending)

        render_status_message(
            command_center.thursday_status,
            f"Current odds: {command_center.current_odds_status}. {command_center.explanation}",
        )
        archive_confirmation_text = (
            f"Stale odds archive confirmation: {command_center.archive_confirmation_status}. "
            f"{command_center.archive_confirmation_message}"
        )
        if command_center.archive_confirmation_level == "success":
            st.success(archive_confirmation_text)
        elif command_center.archive_confirmation_level == "warning":
            st.warning(archive_confirmation_text)
        elif command_center.archive_confirmation_level == "error":
            st.error(archive_confirmation_text)
        else:
            st.caption(archive_confirmation_text)
        if (
            command_center.archive_confirmation_status == "Ready"
            and command_center.archive_confirmation_id
        ):
            st.caption(f"Confirmation ID: `{command_center.archive_confirmation_id}`")
        st.info(f"Recommended next action: {command_center.recommended_next_action}")
        render_open_next_cue(command_center.detail_cue)

        st.markdown(f"**Latest archive pair**  \n{command_center.archive_pair_label}")
        signal_cols = st.columns(2)
        signal_cols[0].markdown(f"**Count-change risk**  \n{command_center.count_change_risk_flag}")
        signal_cols[1].markdown(f"**Top movement reason**  \n{command_center.top_card_movement_reason}")
        if ledger.status != "Ready":
            st.caption(f"Ledger: {ledger.message}")


def render_main_actions() -> None:
    st.subheader("Main actions")
    action_cols = st.columns(3)
    if action_cols[0].button(
        "Run Thursday readiness refresh",
        type="primary",
        width="stretch",
    ):
        run_dashboard_refresh_sequence()
    if action_cols[1].button("Run post-refresh Thursday review", width="stretch"):
        run_dashboard_post_thursday_review()
    if action_cols[2].button("Generate tier performance report", width="stretch"):
        run_dashboard_action("Tier performance report", run_tier_performance_report)
    st.caption(
        "These actions regenerate reports only. They do not force a card, apply an import, settle a bet, or place a bet."
    )


def render_home() -> None:
    st.header("Home / Command Center")
    st.caption("Start here each Thursday. Read the status, then follow the recommended manual step.")
    command_center = build_thursday_command_center()
    render_command_center_card(command_center)
    render_data_freshness(command_center)
    render_main_actions()
    with st.expander("Weekly workflow file status", expanded=False):
        render_workflow_checklist()


def render_thursday_readiness() -> None:
    readiness = build_thursday_readiness()
    completion = (
        "Missing"
        if readiness.odds_completion_percentage is None
        else f"{readiness.odds_completion_percentage:.1%}"
    )
    incomplete = "Missing" if readiness.incomplete_matches is None else int(readiness.incomplete_matches)
    serious = (
        "Missing"
        if readiness.serious_validation_issues is None
        else int(readiness.serious_validation_issues)
    )
    warnings = "Missing" if readiness.validation_warnings is None else int(readiness.validation_warnings)
    readiness_top = st.columns(3)
    readiness_top[0].metric("Thursday status", readiness.thursday_report_status)
    readiness_top[1].metric("Odds complete", completion)
    readiness_top[2].metric("Incomplete matches", incomplete)
    readiness_issues = st.columns(2)
    readiness_issues[0].metric("Serious issues", serious)
    readiness_issues[1].metric("Warnings", warnings)
    render_status_message(readiness.thursday_report_status, readiness.explanation)

    current_odds = build_current_odds_status()
    st.caption(
        f"Current odds validation: {current_odds.status}. {current_odds.explanation} "
        f"Refresh with `{current_odds.command}` when needed."
    )


def render_odds_completeness() -> None:
    st.subheader("Odds entry completeness")
    completeness = read_output_csv("current_odds_completeness.csv")
    if completeness is None:
        show_missing_report(
            "data/outputs/current_odds_completeness.csv",
            "python scripts/check_current_odds_completeness.py",
        )
    elif completeness.empty:
        st.success("No incomplete current-odds entries were found.")
    elif "issue" not in completeness.columns:
        st.warning("The completeness report needs to be regenerated before it can be filtered.")
    else:
        incomplete_issues = {
            "missing_current_odds_csv",
            "blank_american_odds",
            "non_numeric_american_odds",
            "missing_expected_market_row",
            "duplicate_market_selection_row",
        }
        incomplete = completeness[completeness["issue"].isin(incomplete_issues)]
        if incomplete.empty:
            st.success("All expected odds rows have numeric prices.")
        else:
            st.dataframe(incomplete, width="stretch", hide_index=True)

    render_markdown_expander(
        "Full completeness report",
        "current_odds_completeness.md",
        "python scripts/check_current_odds_completeness.py",
    )
    render_table_expander(
        "All completeness issues",
        "current_odds_completeness.csv",
        "python scripts/check_current_odds_completeness.py",
    )


def render_current_odds_validation_reports() -> None:
    render_markdown_expander(
        "Current odds validation report",
        "current_odds_validation.md",
        "python scripts/validate_current_odds.py",
    )
    render_table_expander(
        "Current odds validation issues",
        "current_odds_validation.csv",
        "python scripts/validate_current_odds.py",
    )


def render_thursday_card() -> None:
    st.header("Thursday Card")
    st.caption("Check odds quality first, then generate and review the latest best-bets card.")

    primary_top = st.columns(2)
    if primary_top[0].button(
        "Run Thursday readiness refresh",
        type="primary",
        width="stretch",
    ):
        run_dashboard_refresh_sequence()
    if primary_top[1].button("Check odds entry completeness", width="stretch"):
        run_dashboard_action("Current odds completeness", run_current_odds_completeness)
    primary_bottom = st.columns(2)
    if primary_bottom[0].button("Validate current odds", width="stretch"):
        run_dashboard_action("Current odds validation", run_current_odds_validation)
    if primary_bottom[1].button("Generate Thursday best-bets report", width="stretch"):
        run_dashboard_action("Thursday best-bets report", run_thursday_best_bets_report)

    with st.expander("Odds file helpers", expanded=False):
        helper_cols = st.columns(3)
        if helper_cols[0].button("Create current odds template", width="stretch"):
            run_dashboard_action("Current odds template", run_create_current_odds_template)
        if helper_cols[1].button("Preview current odds maintenance", width="stretch"):
            run_dashboard_action(
                "Current odds maintenance preview",
                run_current_odds_maintenance_preview,
            )
        if helper_cols[2].button("Refresh dashboard data", width="stretch"):
            st.rerun()

    render_thursday_readiness()
    render_odds_completeness()
    render_current_odds_validation_reports()

    st.subheader("Latest best-bets report")
    render_markdown_expander(
        "Best-bets writeup",
        "thursday_best_bets.md",
        "python scripts/generate_thursday_best_bets.py",
        expanded=True,
    )
    show_output_table(
        "Thursday best-bets table",
        "thursday_best_bets.csv",
        "python scripts/generate_thursday_best_bets.py",
    )


def render_import_step(label: str) -> None:
    step = next(step for step in ODDS_IMPORT_STEPS if step.label == label)
    st.markdown(f"#### {step.number}. {step.label}")
    st.caption(step.description)


def render_import_audits() -> None:
    audit, audit_message = load_current_odds_import_audit()
    if audit is None:
        st.warning(audit_message)
    elif audit.empty:
        st.info(audit_message)
    else:
        st.dataframe(summarize_current_odds_import_batches(audit), width="stretch", hide_index=True)
    render_markdown_expander(
        "Current odds import audit details",
        "current_odds_import_audit.md",
        "python scripts/import_current_odds.py --apply",
    )


def render_odds_import() -> None:
    st.header("Odds Import")
    st.caption("Follow the steps in order. Every dashboard action is preview-only or report-only.")
    st.warning(
        "Apply remains Terminal-only. This page cannot install profiles, restore registry backups, "
        "apply odds imports, or edit current_odds.csv."
    )

    render_import_step("Validate provider staging")
    st.caption(
        "Checks real provider odds and fixtures in data/staging before they can be "
        "considered for the GitHub runner handoff."
    )
    if st.button("Validate staging inputs", type="primary", width="stretch"):
        run_dashboard_action("Staging input validation", run_staging_input_validation)
    staging_command = "python scripts/validate_staging_inputs.py"
    staging_status_path = OUTPUTS_DIR / "staging_input_validation.json"
    if not staging_status_path.exists():
        st.info("Staging inputs have not been checked yet. Run the button above.")
    else:
        try:
            staging_status = json.loads(
                staging_status_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            st.warning(f"The staging validation status could not be read: {exc}")
        else:
            verdict = str(staging_status.get("verdict", "Not checked"))
            message = str(staging_status.get("next_step", "Review the report."))
            if verdict == "Ready for handoff":
                st.success(f"{verdict}. {message}")
            elif verdict == "Needs fixes":
                st.warning(f"{verdict}. {message}")
            else:
                st.error(f"{verdict}. {message}")
            proof_columns = st.columns(4)
            proof_columns[0].metric(
                "Provider proof",
                str(staging_status.get("provenance_status", "Not checked")),
            )
            proof_columns[1].metric(
                "Provider age",
                str(staging_status.get("provider_age_status", "Not checked")),
            )
            proof_columns[2].metric(
                "Odds pair",
                str(
                    staging_status.get(
                        "odds_checksum_pair_status", "Not checked"
                    )
                ),
            )
            proof_columns[3].metric(
                "Fixtures pair",
                str(
                    staging_status.get(
                        "fixtures_checksum_pair_status", "Not checked"
                    )
                ),
            )
            st.caption(
                "Recorded checksum status: "
                f"source odds {staging_status.get('source_odds_checksum_status', 'Not checked')}; "
                f"source fixtures {staging_status.get('source_fixtures_checksum_status', 'Not checked')}; "
                f"staging odds {staging_status.get('staging_odds_checksum_status', 'Not checked')}; "
                f"staging fixtures {staging_status.get('staging_fixtures_checksum_status', 'Not checked')}."
            )
            provenance_note = str(staging_status.get("provenance_note", "")).strip()
            if provenance_note and staging_status.get("provenance_status") != "Verified":
                st.warning(provenance_note)
            provider_age_note = str(
                staging_status.get("provider_age_note", "")
            ).strip()
            if provider_age_note and staging_status.get("provider_age_status") != "Fresh":
                st.warning(provider_age_note)
    render_markdown_expander(
        "Staging input validation report",
        "staging_input_validation.md",
        staging_command,
    )
    render_table_expander(
        "Staging input validation checks",
        "staging_input_validation.csv",
        staging_command,
    )
    st.caption(
        "Dashboard validation is read-only. It never promotes, copies, applies, or "
        "edits staging or manual files."
    )
    st.divider()

    render_import_step("Diagnose export")
    if st.button("Diagnose odds export profile", width="stretch"):
        run_dashboard_action("Odds export profile diagnostic", run_odds_export_profile_diagnostic)
    diagnostic_command = "python scripts/diagnose_odds_export.py --source data/manual/sportsbook_export.csv"
    render_markdown_expander(
        "Odds export profile diagnostic",
        "odds_export_profile_diagnostic.md",
        diagnostic_command,
    )
    render_table_expander(
        "Profile match table",
        "odds_export_profile_diagnostic.csv",
        diagnostic_command,
    )
    st.divider()

    render_import_step("Suggest profile")
    draft_profile_name = st.text_input("Draft profile name", value="draft_sportsbook")
    if st.button("Suggest odds export profile", width="stretch"):
        run_dashboard_action(
            "Odds export profile suggestion",
            lambda: run_odds_export_profile_suggestion(draft_profile_name),
        )
    render_markdown_expander(
        "Draft profile suggestion",
        "odds_export_profile_suggestion.md",
        "python scripts/suggest_odds_export_profile.py --source data/manual/sportsbook_export.csv --profile-name draft_sportsbook",
    )
    st.divider()

    render_import_step("Validate suggested profile")
    if st.button("Validate suggested odds profile", width="stretch"):
        run_dashboard_action(
            "Suggested odds profile validation",
            run_odds_export_profile_suggestion_validation,
        )
    suggestion_validation_command = "python scripts/validate_odds_export_profile_suggestion.py"
    render_markdown_expander(
        "Draft profile validation",
        "odds_export_profile_suggestion_validation.md",
        suggestion_validation_command,
    )
    render_table_expander(
        "Draft converted rows",
        "odds_export_profile_suggestion_validation.csv",
        suggestion_validation_command,
    )
    st.divider()

    render_import_step("Preview profile install")
    if st.button("Preview odds profile install", width="stretch"):
        run_dashboard_action("Odds profile installation preview", run_odds_profile_install_preview)
    render_markdown_expander(
        "Profile installation preview",
        "odds_profile_install_preview.md",
        "python scripts/preview_install_odds_profile.py",
    )
    st.divider()

    render_import_step("Verify installed profile")
    installed_profile_name = st.text_input("Installed profile name", value="generic")
    if st.button("Verify installed odds profile", width="stretch"):
        run_dashboard_action(
            "Installed odds profile verification",
            lambda: run_installed_odds_profile_verification(installed_profile_name),
        )
    verification_command = (
        "python scripts/verify_installed_odds_profile.py --profile PROFILE_NAME "
        "--source data/manual/sportsbook_export.csv"
    )
    render_markdown_expander(
        "Installed profile verification",
        "odds_profile_post_install_verification.md",
        verification_command,
    )
    render_table_expander(
        "Installed profile converted rows",
        "odds_profile_post_install_verification.csv",
        verification_command,
    )
    st.divider()

    render_import_step("Rollback preview")
    st.code("python scripts/rollback_odds_profile_registry.py --backup-path PATH", language="bash")
    st.caption("Enter the backup path in Terminal. The dashboard displays the preview and never applies rollback.")
    render_markdown_expander(
        "Latest registry rollback preview",
        "odds_profile_rollback_preview.md",
        "python scripts/rollback_odds_profile_registry.py --backup-path PATH",
    )
    st.divider()

    render_import_step("Convert export")
    if st.button("Preview odds export conversion", width="stretch"):
        run_dashboard_action("Odds export conversion preview", run_odds_export_conversion_preview)
    conversion_command = "python scripts/convert_odds_export.py --profile generic"
    render_markdown_expander(
        "Odds export conversion preview",
        "odds_export_conversion_report.md",
        conversion_command,
    )
    render_table_expander(
        "Converted export rows",
        "odds_export_conversion_preview.csv",
        conversion_command,
    )
    st.divider()

    render_import_step("Preview current odds import")
    if st.button("Preview current odds import", width="stretch"):
        run_dashboard_action("Current odds import preview", run_current_odds_import_preview)
    render_markdown_expander(
        "Current odds import preview",
        "current_odds_import_report.md",
        "python scripts/import_current_odds.py",
    )
    render_table_expander(
        "Current odds import rows",
        "current_odds_import_preview.csv",
        "python scripts/import_current_odds.py",
    )
    st.divider()

    render_import_step("View import audits")
    render_import_audits()


def render_tier_performance() -> None:
    render_markdown_expander(
        "Tier performance report",
        "tier_performance_report.md",
        "python scripts/generate_tier_performance_report.py",
    )
    tier_tabs = st.tabs(["Summary", "Market", "Team", "Odds range", "CLV"])
    tier_files = (
        ("Tier performance summary", "tier_performance_summary.csv"),
        ("Tier performance by market", "tier_performance_by_market.csv"),
        ("Tier performance by team", "tier_performance_by_team.csv"),
        ("Tier performance by odds range", "tier_performance_by_odds_range.csv"),
        ("Tier performance by CLV", "tier_performance_by_clv.csv"),
    )
    for tab, (title, filename) in zip(tier_tabs, tier_files, strict=True):
        with tab:
            show_output_table(title, filename, "python scripts/generate_tier_performance_report.py")


def render_backtest_outputs() -> None:
    try:
        bets = pd.read_csv(OUTPUTS_DIR / "backtest_bets.csv")
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
        st.info("No readable backtest results found yet. Run `python scripts/run_backtest.py`.")
    else:
        st.dataframe(summarize_backtest(bets), width="stretch", hide_index=True)


def render_performance_reports() -> None:
    st.header("Performance Reports")
    st.caption("Use settled ledger results, backtests, and CLV to judge which tiers and markets deserve trust.")
    action_cols = st.columns(3)
    if action_cols[0].button(
        "Generate tier performance report",
        type="primary",
        width="stretch",
    ):
        run_dashboard_action("Tier performance report", run_tier_performance_report)
    if action_cols[1].button("Run backtest reports", width="stretch"):
        run_dashboard_action("Backtest reports", run_backtest.main)
    if action_cols[2].button("Refresh dashboard data", width="stretch"):
        st.rerun()

    st.subheader("Tier performance")
    render_tier_performance()

    with st.expander("Backtest summary", expanded=False):
        render_backtest_outputs()
    render_markdown_expander("CLV report", "clv_report.md", "python scripts/run_backtest.py")
    render_table_expander("CLV by market", "clv_by_market.csv", "python scripts/run_backtest.py")

    st.subheader("Ledger profit breakdowns")
    breakdown_tabs = st.tabs(["Market", "Selection", "Team"])
    breakdown_files = (
        ("Profit by market", "bet_ledger_by_market.csv"),
        ("Profit by selection", "bet_ledger_by_selection.csv"),
        ("Profit by team", "bet_ledger_by_team.csv"),
    )
    for tab, (title, filename) in zip(breakdown_tabs, breakdown_files, strict=True):
        with tab:
            show_output_table(title, filename, "python scripts/run_bet_ledger.py")


def render_bet_ledger() -> None:
    st.header("Bet Ledger")
    st.caption("Review actual bets and previews here. Ledger edits and settlement apply remain outside the dashboard.")
    action_cols = st.columns(3)
    if action_cols[0].button("Run bet ledger report", type="primary", width="stretch"):
        run_dashboard_action("Bet ledger report", run_bet_ledger_report)
    if action_cols[1].button("Run ledger health check", width="stretch"):
        run_dashboard_action("Ledger health check", run_ledger_health_check)
    if action_cols[2].button("Run settlement preview", width="stretch"):
        run_dashboard_action("Settlement preview", run_settlement_preview)

    ledger = build_ledger_portal_summary()
    units = "Missing" if ledger.profit_units is None else f"{ledger.profit_units:+.3f}u"
    roi = "Missing" if ledger.roi is None else f"{ledger.roi:.1%}"
    pending = "Missing" if ledger.pending_bets is None else ledger.pending_bets
    ledger_top = st.columns(2)
    ledger_top[0].metric("Record", ledger.record)
    ledger_top[1].metric("Profit/Loss", units)
    ledger_bottom = st.columns(2)
    ledger_bottom[0].metric("ROI", roi)
    ledger_bottom[1].metric("Pending", pending)
    render_status_message(ledger.status, ledger.message)

    render_markdown_expander(
        "Ledger summary report",
        "bet_ledger_summary.md",
        "python scripts/run_bet_ledger.py",
    )
    render_table_expander(
        "Pending bets",
        "bet_ledger_pending.csv",
        "python scripts/run_bet_ledger.py",
        expanded=True,
    )

    with st.expander("Ledger health check", expanded=True):
        health = read_output_csv("bet_ledger_health_check.csv")
        if health is None:
            show_missing_report(
                "data/outputs/bet_ledger_health_check.csv",
                "python scripts/check_bet_ledger.py",
            )
        elif health.empty:
            st.success("No ledger health issues found in the latest health check.")
        else:
            st.dataframe(health, width="stretch", hide_index=True)

    render_table_expander(
        "Settlement preview",
        "bet_settlement_preview.csv",
        "python scripts/settle_bet_ledger.py",
    )
    with st.expander("Weekly ledger commands", expanded=False):
        st.code(
            "\n".join([
                "python scripts/prefill_bet_ledger.py",
                "python scripts/check_bet_ledger.py",
                "python scripts/settle_bet_ledger.py",
                "python scripts/run_bet_ledger.py",
            ]),
            language="bash",
        )


def render_archive_overview() -> None:
    archives = list_recent_thursday_archives()
    if archives.empty:
        st.info("No archived Thursday reports found yet. Generate Thursday best bets to save the first snapshot.")
    else:
        st.dataframe(archives, width="stretch", hide_index=True)

    archive_pair = build_thursday_archive_pair()
    render_status_message(
        "Ready" if archive_pair["available"] else "Not checked",
        str(archive_pair["label"]),
    )
    next_action = build_recommended_next_action()
    st.info(f"Recommended next action: {next_action['recommended_next_action']}")
    st.caption(f"Why: {next_action['next_action_reason']}")

    count_change = build_thursday_archive_count_change_note()
    count_risk = build_thursday_archive_count_change_risk()
    top_reason = build_top_card_movement_reason()
    st.caption(count_change["note"])
    st.caption(f"Count-change risk: {count_risk['risk_flag']}. {count_risk['risk_reason']}")
    st.caption(
        f"Top card movement reason: {top_reason['top_movement_reason']}. "
        f"{top_reason['movement_reason_detail']}"
    )


def render_archives_and_comparisons() -> None:
    st.header("Archives & Comparisons")
    st.caption("Review how the latest Thursday card moved and what needs a manual decision.")
    action_cols = st.columns(3)
    if action_cols[0].button(
        "Run post-refresh Thursday review",
        type="primary",
        width="stretch",
    ):
        run_dashboard_post_thursday_review()
    if action_cols[1].button("Compare latest Thursday reports", width="stretch"):
        run_dashboard_action("Thursday best-bets comparison", run_thursday_best_bets_comparison)
    if action_cols[2].button("Generate Thursday decision queue", width="stretch"):
        run_dashboard_action("Thursday decision queue", run_thursday_decision_queue)

    st.subheader("Recent Thursday archives")
    render_archive_overview()
    with st.expander("Archive history details", expanded=False):
        archive_details, archive_message = build_thursday_archive_history_details()
        if archive_details.empty:
            st.info(archive_message or "No archived snapshots found yet.")
        else:
            if archive_message:
                st.info(archive_message)
            st.dataframe(archive_details, width="stretch", hide_index=True)

    render_markdown_expander(
        "Latest Thursday snapshot comparison",
        "thursday_best_bets_comparison.md",
        "python scripts/compare_thursday_best_bets.py",
    )
    render_table_expander(
        "Thursday snapshot comparison table",
        "thursday_best_bets_comparison.csv",
        "python scripts/compare_thursday_best_bets.py",
    )
    render_markdown_expander(
        "Thursday decision queue",
        "thursday_decision_queue.md",
        "python scripts/generate_thursday_decision_queue.py",
        expanded=True,
    )
    render_table_expander(
        "Thursday decision queue table",
        "thursday_decision_queue.csv",
        "python scripts/generate_thursday_decision_queue.py",
    )


def render_model_workspace(min_edge: float, max_juice: int, recent_matches: int) -> None:
    try:
        matches = load_matches()
    except FileNotFoundError as exc:
        st.error(str(exc))
        return

    model = PoissonGoalsModel().fit(matches, last_n_matches_per_team=recent_matches)
    st.subheader("Recent form table")
    st.dataframe(simple_form_table(matches, last_n=6), width="stretch", hide_index=True)

    st.subheader("Upcoming fixtures and projections")
    try:
        fixtures = load_upcoming_fixtures()
        projections = model.project_fixtures(fixtures)
        st.dataframe(
            projections.drop(columns=["top_scores"], errors="ignore"),
            width="stretch",
            hide_index=True,
        )
    except FileNotFoundError as exc:
        st.warning(str(exc))
        fixtures = pd.DataFrame()
        projections = pd.DataFrame()

    if not fixtures.empty:
        st.subheader("Promoted team review spots")
        st.dataframe(flag_promoted_team_spots(fixtures), width="stretch", hide_index=True)

    st.subheader("Value board and weekly card")
    try:
        odds = load_current_odds()
    except FileNotFoundError as exc:
        st.warning(str(exc))
        return
    if projections.empty:
        st.info("Add upcoming fixtures before generating a value board.")
        return

    candidates = pd.concat(
        [
            evaluate_1x2_value(projections, odds, min_edge=min_edge, max_juice=max_juice),
            evaluate_total_25(
                projections,
                odds,
                min_edge=min_edge,
                max_juice=max_juice,
                matches=matches,
            ),
            evaluate_btts(projections, odds, min_edge=min_edge, max_juice=max_juice),
        ],
        ignore_index=True,
    )
    st.dataframe(candidates.sort_values("edge", ascending=False), width="stretch", hide_index=True)
    st.markdown(card_to_markdown(build_weekly_card(candidates)))


def render_tools_and_diagnostics(min_edge: float, max_juice: int, recent_matches: int) -> None:
    st.header("Tools / Diagnostics")
    st.caption("Advanced model views and file-level checks live here so the weekly workflow stays quiet.")
    render_markdown_expander(
        "Scheduled Thursday workflow summary",
        "scheduled_thursday_workflow_summary.md",
        "python scripts/run_scheduled_thursday_workflow.py",
    )
    verification_command = "python scripts/verify_github_manual_thursday_run.py"
    with st.container(border=True):
        verification_col, action_col = st.columns([3, 1])
        verification_col.markdown("**Manual GitHub Thursday run verification**")
        verification_col.caption(
            "Cross-check the handoff receipt, scheduled summary, and claimed output files."
        )
        if action_col.button(
            "Verify GitHub run",
            help="This reads report artifacts only and never changes odds or fixtures.",
            width="stretch",
        ):
            run_dashboard_action(
                "GitHub manual Thursday run verification",
                run_github_manual_thursday_verification,
            )
        verification = read_output_csv(
            "github_manual_thursday_run_verification.csv"
        )
        if verification is None or verification.empty:
            st.info(
                "No verification report yet. Run the button above after the GitHub "
                "artifact outputs are available."
            )
        else:
            verdict_rows = verification[
                verification["category"].astype(str).eq("Verdict")
            ]
            if verdict_rows.empty:
                st.warning("The verification CSV is missing its verdict row. Regenerate it.")
            else:
                verdict = str(verdict_rows.iloc[0].get("actual", "Unknown"))
                reason = str(verdict_rows.iloc[0].get("details", ""))
                if verdict == "Verified ready run":
                    st.success(verdict)
                elif verdict == "Verified blocked run":
                    st.warning(verdict)
                else:
                    st.error(verdict)
                st.caption(reason)
    render_markdown_expander(
        "GitHub manual Thursday run verification report",
        "github_manual_thursday_run_verification.md",
        verification_command,
    )
    render_table_expander(
        "GitHub manual Thursday run verification checks",
        "github_manual_thursday_run_verification.csv",
        verification_command,
    )
    action_cols = st.columns(4)
    if action_cols[0].button("Create current odds template", width="stretch"):
        run_dashboard_action("Current odds template", run_create_current_odds_template)
    if action_cols[1].button("Preview current odds maintenance", width="stretch"):
        run_dashboard_action(
            "Current odds maintenance preview",
            run_current_odds_maintenance_preview,
        )
    if action_cols[2].button("Report stale current odds", width="stretch"):
        run_dashboard_action("Stale current odds report", run_stale_current_odds_report)
    if action_cols[3].button("Refresh dashboard data", width="stretch"):
        st.rerun()
    archive_action_cols = st.columns(2)
    if archive_action_cols[0].button(
        "Preview stale odds archive",
        help=(
            "Preview which rows would be archived and removed, and create a confirmation ID. "
            "This never applies changes."
        ),
        width="stretch",
    ):
        run_dashboard_action(
            "Stale odds archive preview",
            run_stale_current_odds_archive_preview,
        )
    if archive_action_cols[1].button(
        "Check stale odds archive confirmation",
        help="Check whether the latest preview receipt still matches current_odds.csv.",
        width="stretch",
    ):
        run_dashboard_action(
            "Stale odds archive confirmation status",
            run_stale_current_odds_archive_confirmation_status,
        )
    st.caption(
        "Preview creates a reviewed confirmation ID and exact Terminal apply command. "
        "The confirmation check only reads that receipt and current odds. Apply and override remain Terminal-only."
    )
    _, archive_confirmation = get_stale_current_odds_archive_confirmation_status()
    with st.container(border=True):
        def confirmation_count(field: str) -> object:
            value = archive_confirmation.get(field, "")
            return "n/a" if value in {"", None} else value

        st.markdown("**Stale odds archive confirmation**")
        confirmation_status = str(archive_confirmation.get("status", "Not checked"))
        confirmation_reason = str(archive_confirmation.get("status_reason", ""))
        if confirmation_status == "Ready":
            st.success("Ready: the receipt still matches current_odds.csv.")
        elif confirmation_status in {"Missing receipt", "Missing current_odds.csv"}:
            st.info(confirmation_status)
        elif confirmation_status == "Odds changed after preview":
            st.warning(confirmation_status)
        else:
            st.error(confirmation_status)
        st.caption(confirmation_reason)
        st.caption(
            "Preview/current rows: "
            f"stale {confirmation_count('preview_stale_row_count')} / "
            f"{confirmation_count('current_stale_row_count')} | "
            f"keep {confirmation_count('preview_keep_row_count')} / "
            f"{confirmation_count('current_keep_row_count')} | "
            f"manual review {confirmation_count('preview_manual_review_row_count')} / "
            f"{confirmation_count('current_manual_review_row_count')}"
        )
        if archive_confirmation.get("exact_apply_command"):
            st.code(str(archive_confirmation["exact_apply_command"]), language="bash")
    selected_backup_path = ""
    backup_list, backup_summary = get_stale_current_odds_backup_list()
    with st.expander("Available stale odds backups", expanded=True):
        st.caption(
            "Choose a readable backup for rollback preview. Listing and selection never change a file."
        )
        if st.button("Refresh backup list report", width="content"):
            run_dashboard_action("Stale odds backup list", run_stale_current_odds_backup_list)
        if backup_list.empty:
            st.info(str(backup_summary.get("message", "No stale current-odds backups were found.")))
        else:
            audit_link_status = str(backup_summary.get("audit_link_status", "not_checked"))
            st.caption(
                f"Audit linkage: {audit_link_status} | "
                f"{int(backup_summary.get('matched_backups', 0))} matched | "
                f"{int(backup_summary.get('unmatched_backups', 0))} unknown"
            )
            st.caption(
                "Checksum status: "
                f"{int(backup_summary.get('verified_checksums', 0))} verified | "
                f"{int(backup_summary.get('mismatched_checksums', 0))} mismatch | "
                f"{int(backup_summary.get('unavailable_checksums', 0))} not available"
            )
            if audit_link_status == "no_history":
                st.info("No archive or rollback audit history is available yet. Backup creators show as unknown.")
            elif audit_link_status == "needs_review":
                st.warning("Some audit history is unreadable or malformed. Review the audit notes before choosing.")
            elif audit_link_status in {"partial", "no_matches"}:
                st.info("Some backup paths have no matching creator row. Those operations remain unknown.")
            if int(backup_summary.get("audit_warning_count", 0)):
                st.warning("Some audit rows or markdown files need review. Details are in the backup list report.")
            if int(backup_summary.get("mismatched_checksums", 0)):
                st.warning(
                    "One or more backups do not match their recorded checksums. Do not trust a mismatched "
                    "backup for rollback unless you inspect it manually."
                )
            compact_columns = [
                "backup_type",
                "filename_timestamp",
                "row_count",
                "valid",
                "created_by_operation",
                "audit_timestamp",
                "operation_status",
                "checksum_status",
                "rows_archived",
                "rows_restored",
                "rows_replaced",
                "backup_path",
            ]
            st.dataframe(
                backup_list[[column for column in compact_columns if column in backup_list.columns]],
                width="stretch",
                hide_index=True,
            )
            valid_backups = backup_list[backup_list["valid"].eq("Yes")]
            if valid_backups.empty:
                st.warning("Backups were found, but none are readable and valid for rollback preview.")
            else:
                backup_labels = {
                    str(row["backup_path"]): (
                        f"{row['filename_timestamp'] or row['file_modified_at'] or 'Unknown time'} | "
                        f"{Path(str(row['backup_path'])).name} | "
                        f"{row['created_by_operation']} | {row['checksum_status']} | "
                        f"{int(row['row_count'])} rows"
                    )
                    for _, row in valid_backups.iterrows()
                }
                selected_backup_path = st.selectbox(
                    "Select backup for rollback preview",
                    options=list(backup_labels),
                    format_func=lambda path: backup_labels[path],
                    key="stale_odds_rollback_backup_picker",
                )
                st.code(selected_backup_path, language="text")
                selected_record = valid_backups.loc[
                    valid_backups["backup_path"].eq(selected_backup_path)
                ].iloc[0]
                st.caption(
                    f"Creator: {selected_record['created_by_operation']} | "
                    f"Operation: {selected_record['operation_status'] or 'Not recorded'} | "
                    f"Checksum: {selected_record['checksum_status']}"
                )
                st.caption(str(selected_record["audit_note"]))
                if selected_record["checksum_status"] == "Mismatch":
                    st.warning(str(selected_record["checksum_note"]))
                else:
                    st.caption(str(selected_record["checksum_note"]))
    manual_backup_path = st.text_input(
        "Manual backup path (optional override)",
        placeholder="data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv",
        help="Use this only when the backup is not shown in the picker. Preview never restores it.",
        key="stale_odds_rollback_backup_path",
    )
    rollback_backup_path = manual_backup_path.strip() or selected_backup_path
    if st.button(
        "Preview stale odds rollback",
        help="Compare a selected backup with current_odds.csv. This never applies rollback.",
        width="content",
    ):
        if not rollback_backup_path.strip():
            st.warning("Enter a pre-archive CSV backup path before previewing rollback.")
        else:
            run_dashboard_action(
                "Stale odds rollback preview",
                lambda: run_stale_current_odds_archive_rollback_preview(rollback_backup_path),
            )
    st.caption(
        "Preview creates a confirmation ID and an exact Terminal command. Rollback apply, unconfirmed "
        "rollback overrides, and checksum-mismatch overrides remain Terminal-only."
    )

    with st.expander("Weekly workflow checklist", expanded=True):
        render_workflow_checklist()
    render_markdown_expander(
        "Current odds maintenance report",
        "current_odds_maintenance_report.md",
        "python scripts/maintain_current_odds.py",
    )
    render_table_expander(
        "Current odds maintenance rows",
        "current_odds_maintenance_preview.csv",
        "python scripts/maintain_current_odds.py",
    )
    render_markdown_expander(
        "Stale current odds report",
        "stale_current_odds_report.md",
        "python scripts/report_stale_current_odds.py",
    )
    render_table_expander(
        "Stale current odds rows",
        "stale_current_odds_report.csv",
        "python scripts/report_stale_current_odds.py",
    )
    render_markdown_expander(
        "Stale odds archive preview",
        "stale_current_odds_archive_preview.md",
        "python scripts/archive_stale_current_odds.py",
    )
    render_table_expander(
        "Stale odds archive row plan",
        "stale_current_odds_archive_preview.csv",
        "python scripts/archive_stale_current_odds.py",
    )
    render_markdown_expander(
        "Stale odds archive confirmation status",
        "stale_current_odds_archive_confirmation_status.md",
        "python scripts/check_stale_current_odds_archive_confirmation.py",
    )
    render_table_expander(
        "Stale odds archive confirmation details",
        "stale_current_odds_archive_confirmation_status.csv",
        "python scripts/check_stale_current_odds_archive_confirmation.py",
    )
    render_markdown_expander(
        "Stale odds archive audit",
        "stale_current_odds_archive_audit.md",
        "python scripts/archive_stale_current_odds.py --apply --confirm-id CONFIRM_ID",
    )
    render_markdown_expander(
        "Stale odds backup list report",
        "stale_current_odds_backup_list.md",
        "python scripts/list_stale_current_odds_backups.py",
    )
    render_table_expander(
        "Stale odds backup list table",
        "stale_current_odds_backup_list.csv",
        "python scripts/list_stale_current_odds_backups.py",
    )
    render_markdown_expander(
        "Stale odds rollback preview",
        "stale_current_odds_archive_rollback_preview.md",
        "python scripts/rollback_stale_current_odds_archive.py --backup-path PATH",
    )
    render_table_expander(
        "Stale odds rollback row changes",
        "stale_current_odds_archive_rollback_preview.csv",
        "python scripts/rollback_stale_current_odds_archive.py --backup-path PATH",
    )
    render_markdown_expander(
        "Stale odds rollback audit",
        "stale_current_odds_archive_rollback_audit.md",
        (
            "python scripts/rollback_stale_current_odds_archive.py "
            "--backup-path PATH --apply --confirm-id CONFIRM_ID"
        ),
    )
    with st.expander("Projection model views", expanded=False):
        render_model_workspace(min_edge, max_juice, recent_matches)


st.set_page_config(
    page_title="EPL Betting Lab",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
    .block-container {max-width: 1460px; padding-top: 1.5rem; padding-bottom: 3rem;}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap: 0.65rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

portal_query_values = st.query_params.get_all(PORTAL_QUERY_PARAM)
portal_query_value: object = (
    portal_query_values[0] if len(portal_query_values) == 1 else portal_query_values
)
apply_portal_query_navigation(st.session_state, portal_query_value)

with st.sidebar:
    st.title("EPL Betting Lab")
    st.caption("Weekly betting portal")
    selected_section = st.radio(
        "Portal navigation",
        PORTAL_SECTIONS,
        key=PORTAL_SECTION_STATE_KEY,
        on_change=sync_portal_query_from_sidebar,
        label_visibility="collapsed",
    )
    sync_portal_query_param(selected_section)
    st.caption(SECTION_DESCRIPTIONS[selected_section])
    st.divider()
    with st.expander("Model settings", expanded=False):
        min_edge = st.slider("Minimum edge", 0.0, 0.15, float(MIN_EDGE), 0.005)
        max_juice = st.number_input("Max default juice", value=int(MAX_DEFAULT_JUICE), step=5)
        recent_matches = st.number_input(
            "Recent matches per team",
            value=38,
            min_value=10,
            max_value=100,
            step=2,
        )
    st.caption("Dashboard actions generate reports only. Bets and apply actions stay manual.")

st.title("EPL Betting Lab")
st.caption(SECTION_DESCRIPTIONS[selected_section])
st.caption(f"Location: {build_portal_breadcrumb(selected_section)}")

if selected_section != HOME_PORTAL_SECTION:
    render_back_to_home()

if selected_section == "Home / Command Center":
    render_home()
elif selected_section == "Thursday Card":
    render_thursday_card()
elif selected_section == "Odds Import":
    render_odds_import()
elif selected_section == "Performance Reports":
    render_performance_reports()
elif selected_section == "Bet Ledger":
    render_bet_ledger()
elif selected_section == "Archives & Comparisons":
    render_archives_and_comparisons()
else:
    render_tools_and_diagnostics(float(min_edge), int(max_juice), int(recent_matches))
