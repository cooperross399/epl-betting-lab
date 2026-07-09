from __future__ import annotations

import pandas as pd
import streamlit as st

from epl_betting_lab.backtest.walk_forward import summarize_backtest
from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, MIN_EDGE, OUTPUTS_DIR
from epl_betting_lab.current_odds_status import build_current_odds_status
from epl_betting_lab.dashboard_actions import (
    run_bet_ledger_report,
    run_create_current_odds_template,
    run_current_odds_completeness,
    run_current_odds_maintenance_preview,
    run_current_odds_validation,
    run_ledger_health_check,
    run_post_thursday_review,
    run_settlement_preview,
    run_thursday_best_bets_comparison,
    run_thursday_best_bets_report,
    run_thursday_decision_queue,
    run_thursday_readiness_refresh,
)
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures, load_current_odds
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.models.ratings import simple_form_table
from epl_betting_lab.reports.bet_ledger import load_bet_ledger, summarize_overall
from epl_betting_lab.reports.current_odds_validation import CurrentOddsValidationError
from epl_betting_lab.reports.thursday_archive_pair import build_thursday_archive_pair
from epl_betting_lab.reports.thursday_best_bets import list_recent_thursday_archives
from epl_betting_lab.reports.weekly_card import build_weekly_card, card_to_markdown
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.promoted_fades import flag_promoted_team_spots
from epl_betting_lab.strategies.totals import evaluate_total_25
from epl_betting_lab.thursday_readiness import build_thursday_readiness
from epl_betting_lab.workflow_status import build_workflow_status
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


def run_dashboard_action(label: str, action) -> None:
    try:
        action()
    except CurrentOddsValidationError as exc:
        st.error(f"{label} stopped.")
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


def render_report_buttons() -> None:
    st.subheader("Report controls")
    st.caption(
        "These buttons only regenerate reports. They do not place bets, confirm bets, edit odds, or apply settlements."
    )
    if st.button("Run Thursday readiness refresh", width="stretch"):
        run_dashboard_refresh_sequence()
    if st.button("Run post-refresh Thursday review", width="stretch"):
        run_dashboard_post_thursday_review()

    report_cols = st.columns(3)
    if report_cols[0].button("Run bet ledger report", width="stretch"):
        run_dashboard_action("Bet ledger report", run_bet_ledger_report)
    if report_cols[1].button("Run ledger health check", width="stretch"):
        run_dashboard_action("Ledger health check", run_ledger_health_check)
    if report_cols[2].button("Run settlement preview", width="stretch"):
        run_dashboard_action("Settlement preview", run_settlement_preview)

    workflow_cols = st.columns(9)
    if workflow_cols[0].button("Create current odds template", width="stretch"):
        run_dashboard_action("Current odds template", run_create_current_odds_template)
    if workflow_cols[1].button("Preview current odds maintenance", width="stretch"):
        run_dashboard_action("Current odds maintenance preview", run_current_odds_maintenance_preview)
    if workflow_cols[2].button("Check odds entry completeness", width="stretch"):
        run_dashboard_action("Current odds completeness", run_current_odds_completeness)
    if workflow_cols[3].button("Validate current odds", width="stretch"):
        run_dashboard_action("Current odds validation", run_current_odds_validation)
    if workflow_cols[4].button("Generate Thursday best-bets report", width="stretch"):
        run_dashboard_action("Thursday best-bets report", run_thursday_best_bets_report)
    if workflow_cols[5].button("Compare latest Thursday reports", width="stretch"):
        run_dashboard_action("Thursday best-bets comparison", run_thursday_best_bets_comparison)
    if workflow_cols[6].button("Generate Thursday decision queue", width="stretch"):
        run_dashboard_action("Thursday decision queue", run_thursday_decision_queue)
    if workflow_cols[7].button("Run backtest reports", width="stretch"):
        run_dashboard_action("Backtest reports", run_backtest.main)
    if workflow_cols[8].button("Refresh dashboard data", width="stretch"):
        st.rerun()


def render_thursday_best_bets_panel() -> None:
    st.subheader("Thursday best-bets report")
    st.info("Run `Validate current odds` before generating Thursday best bets so bad manual inputs do not create a bad card.")
    readiness = build_thursday_readiness()
    readiness_cols = st.columns(5)
    completion = "Missing" if readiness.odds_completion_percentage is None else f"{readiness.odds_completion_percentage:.1%}"
    incomplete_matches = "Missing" if readiness.incomplete_matches is None else int(readiness.incomplete_matches)
    serious = "Missing" if readiness.serious_validation_issues is None else int(readiness.serious_validation_issues)
    warnings = "Missing" if readiness.validation_warnings is None else int(readiness.validation_warnings)
    readiness_cols[0].metric("Odds complete", completion)
    readiness_cols[1].metric("Incomplete matches", incomplete_matches)
    readiness_cols[2].metric("Serious odds issues", serious)
    readiness_cols[3].metric("Odds warnings", warnings)
    readiness_cols[4].metric("Thursday status", readiness.thursday_report_status)
    st.caption(f"{readiness.explanation} Refresh with `{readiness.command}` or the dashboard buttons below.")

    status = build_current_odds_status()
    status_cols = st.columns([1, 3])
    status_cols[0].metric("Current odds", status.status)
    status_cols[1].caption(
        f"{status.explanation} Refresh with `{status.command}` or the `Validate current odds` dashboard button."
    )

    validation_path = OUTPUTS_DIR / "current_odds_validation.md"
    if validation_path.exists():
        with st.expander("Current odds validation", expanded=False):
            st.markdown(validation_path.read_text(encoding="utf-8"))
    else:
        show_missing_report("data/outputs/current_odds_validation.md", "python scripts/validate_current_odds.py")
    show_output_table("Current odds validation issues", "current_odds_validation.csv", "python scripts/validate_current_odds.py")

    maintenance_path = OUTPUTS_DIR / "current_odds_maintenance_report.md"
    if maintenance_path.exists():
        with st.expander("Current odds maintenance preview", expanded=False):
            st.markdown(maintenance_path.read_text(encoding="utf-8"))
    else:
        show_missing_report("data/outputs/current_odds_maintenance_report.md", "python scripts/maintain_current_odds.py")
    show_output_table("Current odds maintenance rows", "current_odds_maintenance_preview.csv", "python scripts/maintain_current_odds.py")

    st.subheader("Incomplete odds entries")
    completeness = read_output_csv("current_odds_completeness.csv")
    if completeness is None:
        show_missing_report("data/outputs/current_odds_completeness.csv", "python scripts/check_current_odds_completeness.py")
    elif completeness.empty:
        st.success("No incomplete current-odds entries found in the latest completeness report.")
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
            st.success("All expected odds rows have numeric prices. Review warnings below if needed.")
        else:
            st.caption("Fix these matches and markets before trusting Thursday best bets.")
            st.dataframe(incomplete, width="stretch", hide_index=True)

    completeness_path = OUTPUTS_DIR / "current_odds_completeness.md"
    if completeness_path.exists():
        with st.expander("Full odds completeness report", expanded=False):
            st.markdown(completeness_path.read_text(encoding="utf-8"))
    else:
        show_missing_report("data/outputs/current_odds_completeness.md", "python scripts/check_current_odds_completeness.py")
    completeness = show_output_table("All odds completeness issues", "current_odds_completeness.csv", "python scripts/check_current_odds_completeness.py")
    if completeness is not None and not completeness.empty:
        st.caption("Warnings like missing book names are useful for tracking, but they do not mean odds are missing.")

    markdown_path = OUTPUTS_DIR / "thursday_best_bets.md"
    if markdown_path.exists():
        with st.expander("Best-bets writeup", expanded=True):
            st.markdown(markdown_path.read_text(encoding="utf-8"))
    else:
        show_missing_report("data/outputs/thursday_best_bets.md", "python scripts/generate_thursday_best_bets.py")

    show_output_table("Thursday best-bets table", "thursday_best_bets.csv", "python scripts/generate_thursday_best_bets.py")

    st.subheader("Recent Thursday report archives")
    archives = list_recent_thursday_archives()
    if archives.empty:
        st.info("No archived Thursday reports found yet. Generate Thursday best bets to save the first snapshot.")
    else:
        st.caption("Each successful Thursday generation saves dated markdown, CSV, and metadata snapshots here.")
        st.dataframe(archives, width="stretch", hide_index=True)

    archive_pair = build_thursday_archive_pair()
    if archive_pair["available"]:
        st.caption(archive_pair["label"])
    elif archive_pair["status"] == "no_archives":
        st.info("No archived snapshots found. Generate Thursday best bets to create the first archive.")
    elif archive_pair["status"] == "one_archive":
        st.info(f"{archive_pair['label']}. Generate one more Thursday best-bets archive before comparing.")
    else:
        st.info("Comparison not available yet. Generate Thursday best bets on at least two refreshes first.")

    comparison_path = OUTPUTS_DIR / "thursday_best_bets_comparison.md"
    if comparison_path.exists():
        with st.expander("Latest Thursday snapshot comparison", expanded=False):
            st.markdown(comparison_path.read_text(encoding="utf-8"))
    else:
        show_missing_report("data/outputs/thursday_best_bets_comparison.md", "python scripts/compare_thursday_best_bets.py")
    show_output_table(
        "Thursday snapshot comparison table",
        "thursday_best_bets_comparison.csv",
        "python scripts/compare_thursday_best_bets.py",
    )

    decision_queue_path = OUTPUTS_DIR / "thursday_decision_queue.md"
    if decision_queue_path.exists():
        with st.expander("Thursday decision queue", expanded=True):
            st.markdown(decision_queue_path.read_text(encoding="utf-8"))
    else:
        show_missing_report("data/outputs/thursday_decision_queue.md", "python scripts/generate_thursday_decision_queue.py")
    show_output_table(
        "Thursday decision queue table",
        "thursday_decision_queue.csv",
        "python scripts/generate_thursday_decision_queue.py",
    )


def render_workflow_checklist() -> None:
    st.subheader("Weekly workflow checklist")
    st.caption("Read-only file check for the reports that power this dashboard.")
    status = build_workflow_status()
    counts = status["status"].value_counts().to_dict()
    metric_cols = st.columns(3)
    metric_cols[0].metric("Complete", int(counts.get("Complete", 0)))
    metric_cols[1].metric("Needs refresh", int(counts.get("Needs refresh", 0)))
    metric_cols[2].metric("Missing", int(counts.get("Missing", 0)))
    st.dataframe(status, width="stretch", hide_index=True)


def render_betting_ledger_tab() -> None:
    st.header("Betting ledger")
    st.caption(
        "Read-only view of your manual betting ledger workflow. This dashboard does not edit the ledger, place bets, or invent odds."
    )
    render_workflow_checklist()
    render_report_buttons()
    render_thursday_best_bets_panel()

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

    ledger_path = MANUAL_DIR / "bet_ledger.csv"
    if ledger_path.exists():
        try:
            ledger = load_bet_ledger(ledger_path)
            overall = summarize_overall(ledger)
            record = f"{overall['wins']}-{overall['losses']}-{overall['pushes']}"
            metric_cols = st.columns(4)
            metric_cols[0].metric("Record", record)
            metric_cols[1].metric("Profit/Loss", f"{overall['profit_units']}u")
            metric_cols[2].metric("ROI", f"{overall['roi']:.1%}")
            metric_cols[3].metric("Pending", int(overall["pending_bets"]))
        except ValueError as exc:
            st.warning(f"The ledger summary could not be calculated yet: {exc}")
            st.info("Run `python scripts/check_bet_ledger.py`, fix the serious ledger issues, then refresh the dashboard.")
    else:
        st.info("No `data/manual/bet_ledger.csv` found yet. Run `python scripts/run_bet_ledger.py` to create the blank ledger files.")

    summary_path = OUTPUTS_DIR / "bet_ledger_summary.md"
    if summary_path.exists():
        with st.expander("Ledger summary report", expanded=False):
            st.markdown(summary_path.read_text(encoding="utf-8"))
    else:
        show_missing_report("data/outputs/bet_ledger_summary.md", "python scripts/run_bet_ledger.py")

    show_output_table("Pending bets", "bet_ledger_pending.csv", "python scripts/run_bet_ledger.py")

    st.subheader("Ledger health check")
    health = read_output_csv("bet_ledger_health_check.csv")
    if health is None:
        show_missing_report("data/outputs/bet_ledger_health_check.csv", "python scripts/check_bet_ledger.py")
    elif health.empty:
        st.success("No ledger health issues found in the latest health check.")
    else:
        st.dataframe(health, width="stretch", hide_index=True)

    show_output_table("Settlement preview", "bet_settlement_preview.csv", "python scripts/settle_bet_ledger.py")
    show_output_table("CLV by market", "clv_by_market.csv", "python scripts/run_backtest.py")

    st.subheader("Profit breakdowns")
    breakdown_tabs = st.tabs(["Market", "Selection", "Team"])
    with breakdown_tabs[0]:
        show_output_table("Profit by market", "bet_ledger_by_market.csv", "python scripts/run_bet_ledger.py")
    with breakdown_tabs[1]:
        show_output_table("Profit by selection", "bet_ledger_by_selection.csv", "python scripts/run_bet_ledger.py")
    with breakdown_tabs[2]:
        show_output_table("Profit by team", "bet_ledger_by_team.csv", "python scripts/run_bet_ledger.py")


st.set_page_config(page_title="EPL Betting Lab", layout="wide")
st.title("EPL Betting Lab")
st.caption("Starter model for EPL betting strategies: goals projections, value checks, backtesting, and weekly card generation.")

with st.sidebar:
    st.header("Settings")
    min_edge = st.slider("Minimum edge", 0.0, 0.15, float(MIN_EDGE), 0.005)
    max_juice = st.number_input("Max default juice", value=int(MAX_DEFAULT_JUICE), step=5)
    recent_matches = st.number_input("Recent matches per team for model fit", value=38, min_value=10, max_value=100, step=2)

try:
    matches = load_matches()
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()

model = PoissonGoalsModel().fit(matches, last_n_matches_per_team=int(recent_matches))

model_tab, ledger_tab, backtest_tab = st.tabs(["Model & weekly card", "Betting ledger", "Backtest"])

with model_tab:
    st.subheader("Recent form table")
    st.dataframe(simple_form_table(matches, last_n=6), width="stretch", hide_index=True)

    st.subheader("Upcoming fixtures and projections")
    try:
        fixtures = load_upcoming_fixtures()
        projections = model.project_fixtures(fixtures)
        projections_show = projections.drop(columns=["top_scores"], errors="ignore")
        st.dataframe(projections_show, width="stretch", hide_index=True)
    except FileNotFoundError as exc:
        st.warning(str(exc))
        fixtures = pd.DataFrame()
        projections = pd.DataFrame()

    if not fixtures.empty:
        st.subheader("Promoted team review spots")
        st.dataframe(flag_promoted_team_spots(fixtures), width="stretch", hide_index=True)

    st.subheader("Value board")
    try:
        odds = load_current_odds()
        if projections.empty:
            st.info("Add upcoming fixtures before generating a value board.")
        else:
            candidates = pd.concat([
                evaluate_1x2_value(projections, odds, min_edge=min_edge, max_juice=int(max_juice)),
                evaluate_total_25(projections, odds, min_edge=min_edge, max_juice=int(max_juice), matches=matches),
                evaluate_btts(projections, odds, min_edge=min_edge, max_juice=int(max_juice)),
            ], ignore_index=True)
            st.dataframe(candidates.sort_values("edge", ascending=False), width="stretch", hide_index=True)
            card = build_weekly_card(candidates)
            st.subheader("Weekly card")
            st.markdown(card_to_markdown(card))
    except FileNotFoundError as exc:
        st.warning(str(exc))

with ledger_tab:
    render_betting_ledger_tab()

with backtest_tab:
    st.subheader("Backtest outputs")
    st.write("Run `python scripts/run_backtest.py` to create `data/outputs/backtest_bets.csv` and `data/outputs/backtest_summary.csv`.")
    try:
        bets = pd.read_csv(OUTPUTS_DIR / "backtest_bets.csv")
        st.dataframe(summarize_backtest(bets), width="stretch", hide_index=True)
    except Exception:
        st.info("No backtest results found yet.")
