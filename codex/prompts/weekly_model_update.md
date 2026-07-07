# Codex Prompt — Weekly EPL Model Update

Read `AGENTS.md` and follow it.

Task:
Update the EPL Betting Lab for the latest matchweek.

Steps:

1. Check whether current-season EPL data is available in the project.
2. If the current season is available, rebuild the dataset with the current season included.
3. Run:
   - `python -m compileall -q src scripts app.py`
   - `python -m pytest`
   - `python scripts/run_backtest.py`
   - `python scripts/agent_weekly_brief.py --current-season 2627 --recent-matches 6`
4. Review `data/outputs/agent_weekly_brief.md`.
5. Identify whether the model appears biased toward or against any teams, markets, promoted teams, or totals.
6. Make only small, explainable code improvements that are supported by the evidence.
7. Do not fabricate odds. If `data/manual/current_odds.csv` is missing or stale, say that odds need to be updated before generating a real card.
8. Summarize:
   - What changed.
   - Which commands passed/failed.
   - What the current model likes.
   - What still needs manual odds/news input.
