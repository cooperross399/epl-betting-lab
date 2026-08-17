# CLAUDE.md — EPL Betting Lab Operating Instructions

This repository is the source of truth for the EPL Betting Lab / EPL Model.
Claude operates this repo directly; the older `AGENTS.md` and `codex/` files are
legacy ChatGPT/Codex material. When they conflict with this file, this file wins.

## Main commands

```bash
# Main weekly command (the primary operating flow)
python scripts/run_epl_weekly_pipeline.py

# Week 1 setup command
python scripts/run_week1_launch_readiness.py

# Claude Thursday handoff packet (runs the safe weekly pipeline by default;
# add --read-latest to reuse the latest pipeline summary)
python scripts/run_claude_thursday_epl_model.py

# Dashboard
streamlit run app.py

# Tests
PYTHONPATH=src python -m pytest -q

# Compile smoke check after structural changes
python -m compileall -q src scripts app.py
```

## Hard rules (never break these)

- **Never fabricate odds.** If prices are missing, report it and ask the user
  for real sportsbook prices or the manual odds CSV workflow.
- **Never place bets** or automate betting in any form.
- **Never bypass validation.** The gates exist so a bad card is not generated.
- **Never use force mode** (`--force` or equivalent) unless the user explicitly
  requests it in this conversation.
- **Never enable cron** or any automatic scheduling unless explicitly requested.
- **Never run live providers** (`--live` provider modes, odds APIs) unless
  explicitly requested.
- **Never edit protected manual files** unless the requested workflow
  explicitly allows it (for example, a Terminal-only `--apply` step the user
  asked for). Protected files:
  - `data/manual/current_odds.csv`
  - `data/manual/current_odds_import.csv`
  - `data/manual/bet_ledger.csv`
  - `data/manual/odds_import_profiles.json`
  - `data/manual/staging_provider_policy.json`

## Operating flow

The weekly pipeline (`python scripts/run_epl_weekly_pipeline.py`) is the main
operating flow. It checks data freshness, validates and completeness-checks
current odds, generates and archives the gated Thursday card, compares runs,
builds the decision queue, refreshes ledger reports, and seals/verifies its
own archive receipts. It is report-only and never edits manual files.

If `data/manual/current_odds.csv` is missing or incomplete, the pipeline stops
with `Needs odds`. Report that clearly and do **not** generate or invent picks.
The fix is always a human entering real sportsbook prices.

## Model and betting discipline

- The model uses calibrated probabilities and protects totals unders.
- The user avoids heavy juice, roughly worse than `-160`, and prefers alternate
  angles (DNB/PK, team totals, corners, shots/SOT, BTTS, win + under/over,
  plus-money props) instead of forcing heavy prices.
- Never present a model edge as a guaranteed winner. Separate best bets, leans,
  and passes/avoids.
- Do not change model logic because one slate lost; require backtest evidence.

## Provider automation

Provider automation is **not trusted yet** unless the provider policy
(`data/manual/staging_provider_policy.json`), acceptance checklist, and human
acceptance receipt system say it is. The default policy is manual-only. Shadow
runs, checklists, receipts, evidence bundles, and the PR gate are evidence for
a human decision — none of them allowlist a provider, promote staging, or
enable cron on their own.

## Where to look

- `docs/project_status_for_claude.md` — current project status and priorities.
- `docs/claude_thursday_task_prompt.md` — the standing Thursday task prompt.
- `README.md` — full command reference for every workflow.
