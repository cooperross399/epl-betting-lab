from __future__ import annotations

import pandas as pd
import streamlit as st

from epl_betting_lab.backtest.walk_forward import summarize_backtest
from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, MIN_EDGE, OUTPUTS_DIR
from epl_betting_lab.dashboard_actions import (
    run_bet_ledger_report,
    run_ledger_health_check,
    run_settlement_preview,
)
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures, load_current_odds
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.models.ratings import simple_form_table
from epl_betting_lab.reports.bet_ledger import load_bet_ledger, summarize_overall
from epl_betting_lab.reports.weekly_card import build_weekly_card, card_to_markdown
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.promoted_fades import flag_promoted_team_spots
from epl_betting_lab.strategies.totals import evaluate_total_25
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
    except Exception as exc:
        st.error(f"{label} failed.")
        st.exception(exc)
    else:
        st.success(f"{label} finished. Refreshing dashboard data.")
        st.rerun()


def render_report_buttons() -> None:
    st.subheader("Report controls")
    st.caption(
        "These buttons only regenerate reports. They do not place bets, confirm bets, edit odds, or apply settlements."
    )
    button_cols = st.columns(5)
    if button_cols[0].button("Run bet ledger report", width="stretch"):
        run_dashboard_action("Bet ledger report", run_bet_ledger_report)
    if button_cols[1].button("Run ledger health check", width="stretch"):
        run_dashboard_action("Ledger health check", run_ledger_health_check)
    if button_cols[2].button("Run settlement preview", width="stretch"):
        run_dashboard_action("Settlement preview", run_settlement_preview)
    if button_cols[3].button("Run backtest reports", width="stretch"):
        run_dashboard_action("Backtest reports", run_backtest.main)
    if button_cols[4].button("Refresh dashboard data", width="stretch"):
        st.rerun()


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
