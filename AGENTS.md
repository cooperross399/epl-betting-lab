# AGENTS.md — EPL Betting Lab Codex Instructions

You are the coding agent for `epl-betting-lab`, a Python/Streamlit project that researches English Premier League betting strategies.

## Mission

Keep the project useful during the 2026/27 EPL season by improving the model with fresh in-season evidence, better stats, cleaner backtests, and clearer weekly betting outputs.

The project should help the user answer:

- What is the likely match script?
- Which market best expresses that script?
- Is the sportsbook price still playable?
- Is there a smarter alternate angle than eating heavy juice?

## User betting preferences

Honor these by default unless the user explicitly overrides them:

- Avoid lines worse than about `-160`.
- Prefer alternate ways to attack the same game script: DNB/PK, team totals, corners, shots/SOT, BTTS, win + under/over, and plus-money props.
- Track all standard bet profit/loss in one ledger.
- Do not count bonus-bet profit/loss unless the user explicitly says to count it.
- Always separate `smart play`, `lean`, and `fun/sneaky` angles.
- Never present a model edge as a guaranteed winner.

## Non-negotiables

- Do not fabricate live sportsbook odds. If odds are missing, ask the user to paste odds or use the manual odds CSV template.
- Do not place bets or automate betting.
- Do not claim profitability without a backtest and clear sample-size warnings.
- Do not overwrite raw data without a `--force` option or clear reason.
- Run tests after code changes: `python -m pytest`.
- Run a smoke compile check after structural changes: `python -m compileall -q src scripts app.py`.
- Keep beginner-friendly commands in `README.md` and `docs/`.

## Preferred workflow for Codex tasks

When asked to improve the project:

1. Inspect the current codebase.
2. Identify the smallest useful feature or fix.
3. Edit the code.
4. Add or update tests when practical.
5. Run tests and compile checks.
6. Summarize exactly what changed, what passed, and what still needs manual input.

## In-season weekly update workflow

After each EPL matchweek, use this order:

1. Pull the latest public EPL result data from Football-Data if available.
2. Rebuild `data/processed/epl_historical_matches.csv`.
3. Run `scripts/agent_weekly_brief.py` to summarize recent form and model blind spots.
4. Run the backtest.
5. Review the value model thresholds.
6. Suggest code improvements only if the evidence supports them.
7. Do not change model logic just because one slate lost.

## Strategy areas to keep improving

Prioritize these modules/features:

- Recent form weighting and last-6/last-10 team trends.
- Promoted-team tracking: Coventry City, Hull City, Ipswich Town.
- Big-six European hangover spots.
- Rest disadvantage / fixture congestion.
- Corners model.
- Player shots and shots-on-target model.
- Closing-line value tracking.
- Market-specific ROI reports.
- Team-specific model bias reports.

## Project commands

Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Fetch data:

```bash
python scripts/fetch_data.py --seasons 2122 2223 2324 2425 2526
```

During the 2026/27 season, once Football-Data publishes current-season rows:

```bash
python scripts/fetch_data.py --seasons 2122 2223 2324 2425 2526 2627
```

Backtest:

```bash
python scripts/run_backtest.py
```

Agent weekly brief:

```bash
python scripts/agent_weekly_brief.py --current-season 2627 --recent-matches 6
```

Dashboard:

```bash
streamlit run app.py
```

Tests:

```bash
python -m pytest
python -m compileall -q src scripts app.py
```

## Weekly betting card style

The final output should be readable for betting decisions, not just data science. Prefer this structure:

```text
EPL Matchweek X Betting Lab

Best value:
- Match: Arsenal vs Coventry
- Play: Coventry team total under 0.5 / Arsenal win + under 4.5 / etc.
- Model probability:
- Book implied probability:
- Edge:
- Fair price:
- Suggested units:
- Why it fits the game script:

Avoid:
- Market too juiced, no edge, or model disagrees.

Sneaky/fun:
- Smaller plus-money angle, clearly labeled.
```

## Model discipline

Soccer is high variance. Do not overfit to a tiny sample.

When improving the model, prefer additions that are explainable:

- Recent form weights.
- Home/away splits.
- Rest days.
- Fixture congestion.
- Shot volume and shots on target.
- Corners for/against.
- Team-specific attack/defense adjustments.

Avoid black-box changes unless the backtest clearly improves and the code explains why.
