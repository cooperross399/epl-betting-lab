# CLAUDE.md — EPL Betting Lab Operating Instructions

This repository is the source of truth for the EPL Betting Lab / EPL Model.
Claude operates this repo directly; the older `AGENTS.md` and `codex/` files are
legacy ChatGPT/Codex material. When they conflict with this file, this file wins.

**Active repo path: `/Users/cooperross/Projects/epl-betting-lab`.** The old
`~/Downloads/epl-betting-lab` path is dead: macOS privacy controls (TCC) block
reads there and produce confusing `Operation not permitted` errors. Do not use
it.

## Read these first

**The card is produced by GitHub Actions, not by anything on Cooper's machine.**
`.github/workflows/matchday-refresh.yml` runs five times a week — Thursday plus
every day that can hold a match — and fetches results, fetches prices, rebuilds
every report, and renders the card on the run page. It needs no laptop, no
terminal, and no Claude routine. Read it at Actions → Matchday Refresh → latest
run.

The three Claude routines are optional and only work when the machine they point
at is on. A routine that did not run is not the card failing; the two are
independent and only the workflow is load-bearing. Never tell Cooper to open a
terminal to get a card.

Every session, in this order. They replace chat history as project memory, so no
prior conversation and no ChatGPT is needed to operate this repo.

1. `CLAUDE.md` (this file) — hard rules, which override everything.
2. `docs/claude_autonomy_operating_model.md` — how Claude works autonomously,
   what a hard stop means, and how to problem-solve instead of giving up.
3. `docs/epl_scheduled_tasks_bridge.md` — the three Claude routines, and why
   they are a reading layer rather than how the card is made.
4. `docs/no_terminal_operations.md` — doing things from a browser.
5. `README.md` — full command reference.
6. Latest `data/outputs/` reports, then GitHub PRs, Actions runs, and the
   **“EPL Betting Lab — Claude Operating Home”** issue:
   <https://github.com/cooperross399/epl-betting-lab/issues/135>

**Never route Cooper to ChatGPT** for memory, next steps, status, or debugging.
Use the repo, the reports, and GitHub.

## Current operating state

- Provider **The Odds API is allowlisted**, scoped to `1x2` and `btts` only.
- `total_2_5` was excluded on 2026-08-17 and **reopened on 2026-08-19**. The
  original finding — that the complete 2.5 line existed only at William Hill,
  Betsson and Nordic Bet — was true of the bulk `totals` market, the only one
  examined. It was never true of `alternate_totals`, where BetRivers and
  FanDuel each carry 2.5 on every fixture. The market is sourced from there now
  and awaits policy approval like any other.
  - The lesson worth keeping: "no book offers this" was really "no book offers
    this *in the market we looked at*". Check coverage per bookmaker with
    `Provider Market Discovery` → `line_coverage` before concluding a market is
    unreachable.
- **Calibration is a precondition, not a goal.** It can rule a model out; it
  cannot rule one in. Never ship a model change on calibration evidence alone
  where a price-based backtest is available — Football-Data ships historical
  odds for 1X2 and the 2.5 line, so for those it always is. A change that
  improved calibration on every market cost about 140 units in the backtest:
  `docs/why_better_calibration_lost_money.md`.
- BTTS has a known, measured, **unfixed** calibration bias of roughly nine
  points, and cannot be profit-backtested because no historical BTTS prices
  exist. It produces most of the picks on a card. Say so rather than patching
  it.
- The active odds source is the **provider-derived automated card input**.
  Manual odds entry is not required.
- `data/manual/current_odds.csv` is **legacy** and must not become active again.
- **EPL CARD is live**, generated from eligible trusted markets only.
- **EPL SETTLE (IGNORE) is preview-only, permanently.**
- Production credential is the GitHub secret `EPL_ODDS_API_KEY`. `.env` is
  local-only and optional.

## Main commands

```bash
# API-first card flow (current)
PYTHONPATH=src .venv/bin/python scripts/run_api_first_card_workflow.py
PYTHONPATH=src .venv/bin/python scripts/run_automated_card.py

# Scheduled-routine bridges
PYTHONPATH=src .venv/bin/python scripts/run_epl_model_task.py
PYTHONPATH=src .venv/bin/python scripts/run_epl_card_task.py
PYTHONPATH=src .venv/bin/python scripts/run_epl_settle_preview_task.py

# Legacy weekly command (manual-odds era; kept for reference)
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

- **Never fabricate odds.** A missing price stays missing. An incomplete market
  is excluded, and an excluded market is never described as a pass, an avoid, or
  a no-value call.
- **Never place bets** or automate betting in any form.
- **Never bypass validation.** The gates exist so a bad card is not generated.
- **Never use force mode** (`--force` or equivalent) unless the user explicitly
  requests it in this conversation.
- **Never enable cron** or any automatic scheduling unless explicitly requested.
- **Never run live providers** (`--live` provider modes, odds APIs) unless
  explicitly requested.
- **Never add `total_2_5` or alternate totals** as official markets without a
  separate reviewed approval.
- **Never print, write, compare, or commit an API key.** The secrets guard in
  `tests/test_no_secrets_committed.py` enforces this; do not weaken it.
- **Never weaken the Provider Policy PR Gate** or sign a human acceptance
  receipt on Cooper's behalf.
- **Never merge with failing CI**, and never force-merge or force-push.
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
