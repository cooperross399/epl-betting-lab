from __future__ import annotations

import pandas as pd
import streamlit as st

from epl_betting_lab.backtest.walk_forward import summarize_backtest
from epl_betting_lab.config import MAX_DEFAULT_JUICE, MIN_EDGE
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures, load_current_odds
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.models.ratings import simple_form_table
from epl_betting_lab.reports.weekly_card import build_weekly_card, card_to_markdown
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.promoted_fades import flag_promoted_team_spots
from epl_betting_lab.strategies.totals import evaluate_total_25

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

st.subheader("Recent form table")
st.dataframe(simple_form_table(matches, last_n=6), use_container_width=True, hide_index=True)

st.subheader("Upcoming fixtures and projections")
try:
    fixtures = load_upcoming_fixtures()
    projections = model.project_fixtures(fixtures)
    projections_show = projections.drop(columns=["top_scores"], errors="ignore")
    st.dataframe(projections_show, use_container_width=True, hide_index=True)
except FileNotFoundError as exc:
    st.warning(str(exc))
    fixtures = pd.DataFrame()
    projections = pd.DataFrame()

if not fixtures.empty:
    st.subheader("Promoted team review spots")
    st.dataframe(flag_promoted_team_spots(fixtures), use_container_width=True, hide_index=True)

st.subheader("Value board")
try:
    odds = load_current_odds()
    if projections.empty:
        st.info("Add upcoming fixtures before generating a value board.")
    else:
        candidates = pd.concat([
            evaluate_1x2_value(projections, odds, min_edge=min_edge, max_juice=int(max_juice)),
            evaluate_total_25(projections, odds, min_edge=min_edge, max_juice=int(max_juice)),
            evaluate_btts(projections, odds, min_edge=min_edge, max_juice=int(max_juice)),
        ], ignore_index=True)
        st.dataframe(candidates.sort_values("edge", ascending=False), use_container_width=True, hide_index=True)
        card = build_weekly_card(candidates)
        st.subheader("Weekly card")
        st.markdown(card_to_markdown(card))
except FileNotFoundError as exc:
    st.warning(str(exc))

st.subheader("Backtest outputs")
st.write("Run `python scripts/run_backtest.py` to create `data/outputs/backtest_bets.csv` and `data/outputs/backtest_summary.csv`.")
try:
    bets = pd.read_csv("data/outputs/backtest_bets.csv")
    st.dataframe(summarize_backtest(bets), use_container_width=True, hide_index=True)
except Exception:
    st.info("No backtest results found yet.")
