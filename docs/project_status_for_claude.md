# Project Status for Claude

A summary of where the EPL Betting Lab stands so Claude can operate the repo
without rediscovering it. Read `CLAUDE.md` first for the hard safety rules.

## Core model, backtesting, and calibration

- Transparent Poisson goals model (`src/epl_betting_lab/models/`) producing
  1X2, over/under 2.5, and BTTS probabilities plus likely scorelines.
- Value logic compares calibrated model probabilities to book implied
  probabilities with a minimum edge (`MIN_EDGE = 0.035`) and a max-juice guard
  (`MAX_DEFAULT_JUICE = -160`).
- Backtest (`python scripts/run_backtest.py`) writes market, team, odds-range,
  season, and calibration breakdowns, plus totals diagnostics. Calibration
  reports feed the card's calibrated probabilities, and totals unders carry
  extra protections (goal-environment warnings, ranking penalties).

## Thursday card workflow

- Real odds live in `data/manual/current_odds.csv` (protected; humans fill it).
- `python scripts/validate_current_odds.py` and
  `python scripts/check_current_odds_completeness.py` gate the card.
- `python scripts/generate_thursday_best_bets.py` generates the card only when
  validation passes; it archives every successful card under
  `data/outputs/archive/thursday_best_bets/`.
- Comparison (`compare_thursday_best_bets.py`) and the decision queue
  (`generate_thursday_decision_queue.py`) explain what changed between cards.
- Cards separate best bets (tier A/B), leans (tier C), and passes/avoids, with
  ranking scores, risk flags, and suggested units.

## Weekly pipeline workflow (main operating flow)

- `python scripts/run_epl_weekly_pipeline.py` runs everything in order:
  freshness → odds validation → completeness → gated card generation and
  archive → comparison → decision queue → ledger health → ledger summary →
  tier performance → sealed archive receipt → receipt verification →
  verification sidecar → sidecar verification → sidecar-verification archive.
- Final statuses: `Ready for card review`, `Card generated with warnings`,
  `Needs odds`, `Needs odds fixes`, `Needs data refresh`, `Blocked`, `Failed`.
- Report-only: it never uses force mode, edits manual files, applies
  settlement, runs providers, enables cron, fabricates odds, or places bets.
- The Claude handoff packet builds on this:
  `python scripts/run_claude_thursday_epl_model.py` (add `--read-latest` to
  reuse the latest summary without rerunning the pipeline).

## Week 1 launch readiness workflow

- `python scripts/check_upcoming_fixture_slate.py` is the read-only fixture
  slate confirmation check: duplicate fixtures, double-booked teams, unknown
  team spellings, date problems, partial matchweeks, and slate/odds drift,
  plus a manual confirmation checklist against the official schedule.
- `python scripts/trim_upcoming_fixtures.py` previews (and, with a
  confirmation ID, applies) deferring later matchweek groups out of the slate
  when their odds are not posted yet, with backups and a deferred-fixtures
  archive. Nothing is deleted.
- `python scripts/run_week1_launch_readiness.py` checks the Week 1 fixture
  slate and the odds file. If `current_odds.csv` does not exist and fixtures
  are usable, it creates a blank seven-market template per fixture — with all
  `american_odds` left blank for a human to fill with real prices.
- `--overwrite-template` (Terminal-only) is the only way to replace an
  existing odds file; never use it unless the user explicitly asks.

## Bet ledger and CLV tracking

- Actual bets are recorded by the human in `data/manual/bet_ledger.csv`
  (protected). `run_bet_ledger.py` builds profit/ROI breakdowns;
  `check_bet_ledger.py` is the read-only health check;
  `settle_bet_ledger.py` previews settlement (apply is Terminal-only and
  user-requested); `prefill_bet_ledger.py` drafts pending rows from the card.
- CLV: closing odds are optional and never guessed. When present, CLV
  probability points are computed and reported by market, selection, team,
  odds range, and edge bucket (`clv_*.csv`, `clv_report.md`), plus
  tier-performance-by-CLV.

## Provider automation safety gates

Provider automation is not trusted yet. The chain is deliberately long, and
every step is evidence for a human decision, not the decision itself:
staging provider run → staging validation (`Ready for handoff`) → shadow
verification runs → shadow run comparison → acceptance checklist → human
acceptance receipt (Terminal-only `--write-receipt`) → receipt verification →
allowlist PR preview → PR conformance check → evidence bundle → bundle
verification → provider policy PR gate with checksum-bound gate receipt →
gate receipt verification → archived verification. The default policy in
`data/manual/staging_provider_policy.json` is manual-only, and cron is
disabled everywhere.

## Current safety rules

- Never fabricate odds; missing prices mean `Needs odds`, not guesses.
- Never place bets; never apply settlement unless the user explicitly asks.
- Never bypass validation; never use `--force` unless explicitly requested.
- Never enable cron; never run live providers unless explicitly requested.
- Never edit the protected manual files (`current_odds.csv`,
  `current_odds_import.csv`, `bet_ledger.csv`, `odds_import_profiles.json`,
  `staging_provider_policy.json`) unless the requested workflow explicitly
  allows it.
- Respect the max-juice guard around `-160`; prefer alternate angles.

## Current commands

```bash
python scripts/run_epl_weekly_pipeline.py          # main weekly command
python scripts/run_week1_launch_readiness.py       # Week 1 setup
python scripts/run_claude_thursday_epl_model.py    # Claude handoff packet
python scripts/run_backtest.py                     # backtest + calibration
python scripts/run_bet_ledger.py                   # ledger reports
python scripts/check_bet_ledger.py                 # ledger health check
streamlit run app.py                               # dashboard
PYTHONPATH=src python -m pytest -q                 # tests
python -m compileall -q src scripts app.py         # compile smoke check
```

## Current priority

1. Confirm the Week 1 fixture slate in `data/manual/upcoming_fixtures.csv`.
2. Create/fill `data/manual/current_odds.csv` with real sportsbook odds
   (`run_week1_launch_readiness.py` creates the blank template; a human fills
   the prices).
3. Run the weekly pipeline: `python scripts/run_epl_weekly_pipeline.py`.
4. Review the card, comparison, and decision queue manually.
5. Track placed bets in the ledger and enter closing odds for CLV.
6. Only later revisit provider automation/cron, and only through the full
   policy/checklist/receipt evidence chain.
