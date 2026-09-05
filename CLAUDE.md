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

The Claude routines — two are live, **EPL CARD** and **EPL WATCH** (formerly
EPL Model) — are optional and read the **`card-feed` branch**, not email and
not the filesystem. Every run publishes `latest_card_comment.md` and
`latest_status.json` there, and the routine presents the card in Claude with a
PushNotification. A routine that did not run is not the card failing; the two
are independent and only the workflow is load-bearing. Never tell Cooper to
open a terminal to get a card.

Every session, in this order. They replace chat history as project memory, so no
prior conversation and no ChatGPT is needed to operate this repo.

1. `CLAUDE.md` (this file) — hard rules, which override everything.
2. `docs/claude_autonomy_operating_model.md` — how Claude works autonomously,
   what a hard stop means, and how to problem-solve instead of giving up.
3. `docs/epl_scheduled_tasks_bridge.md` — the Claude routines (EPL CARD and
   EPL WATCH), and why they are a reading layer rather than how the card is
   made.
4. `docs/no_terminal_operations.md` — doing things from a browser.
5. `README.md` — full command reference.
6. Latest `data/outputs/` reports, then GitHub PRs, Actions runs, and the
   **“EPL Betting Lab — Claude Operating Home”** issue:
   <https://github.com/cooperross399/epl-betting-lab/issues/135>

**Never route Cooper to ChatGPT** for memory, next steps, status, or debugging.
Use the repo, the reports, and GitHub.

## Current operating state

- Provider **The Odds API is allowlisted for all eight priced markets** —
  `1x2`, `btts`, `total_2_5`, `double_chance`, `draw_no_bet`, `corners_1x2`,
  `corners_total_9_5`, `corners_total_10_5` — approved by Cooper on
  2026-08-21 (PR #224, receipt
  `odds_api-20260821T114655-0400-20ffa5677988`). The approval was made with
  the measurement evidence in view and against its recommendation; the next
  bullet is why that matters.
- `total_2_5` was excluded on 2026-08-17 and **reopened on 2026-08-19**. The
  original finding — that the complete 2.5 line existed only at William Hill,
  Betsson and Nordic Bet — was true of the bulk `totals` market, the only one
  examined. It was never true of `alternate_totals`, where BetRivers and
  FanDuel each carry 2.5 on every fixture. The market is sourced from there.
  - The lesson worth keeping: "no book offers this" was really "no book offers
    this *in the market we looked at*". Check coverage per bookmaker with
    `Provider Market Discovery` → `line_coverage` before concluding a market is
    unreachable.
- **Every market has now been measured against real prices** — the unpriced ones
  were bought per event. Not one interval excludes zero, `double_chance` is
  negative, `draw_no_bet`'s positive number rests on thirteen bets, and
  `corners_1x2` can never be measured because the provider does not retain it
  historically. The measurement recommended enabling nothing; Cooper reviewed
  that evidence and enabled all eight markets anyway on 2026-08-21. Both the
  evidence and the decision stand on the record — say so plainly when asked
  what the card's picks rest on: `docs/every_market_measured.md`.
- **No market in this system has a demonstrated edge.** 1X2 measures +5.3% over
  500 bets (95% interval −3.4% to +14.1%); BTTS measures +15.0% over 51 bets
  (−12.4% to +42.5%). Both intervals include zero. Separating a true +5% edge
  from zero would take about 1,537 bets — roughly twelve seasons at the rate
  this system bets. Say this plainly when asked whether it works:
  `docs/what_we_can_and_cannot_claim.md`.
- **The model has better ratings available, and the live card does not use
  them yet — on purpose.** Opponent-adjusted attack/defence, a 365-day
  half-life on match age, and ratings fitted on 70% Understat xG / 30% goals
  (`RatingConfig`, `src/epl_betting_lab/models/poisson_goals.py`) beat the old
  goals-ratio ratings on every threshold-free measure: 1X2 log loss 1.0014 →
  0.9835 against the market's 0.9654. The card still runs `CARD_RATINGS =
  RatingConfig.legacy()` because its bet rule was tuned to the old model and,
  under that rule, the new one bets draws and long-priced away sides for −74
  units. Do not switch the card's ratings without rebuilding the rule and
  passing a held-out-season test: `docs/no_edge_out_of_sample.md`.
- **1X2 is off the card (2026-08-28).** With rules chosen on 2021/22–2024/25
  and read on 2025/26–2026/27, every configuration of both models loses, and
  training-season CLV is negative in every cell. The historical +34 units was
  created by the calibration filter removing 272 of 774 raw bets, and the
  filter was tuned on the same pass. Cooper directed the removal in chat after
  being told it was his market-scope call; `CARD_DISABLED_MARKETS` records
  it. Put it back only with new held-out evidence, never on a single-pass
  profit figure.
- **The card's ranking takes no reliability nudge from the backtest.**
  `_market_reliability_from_backtest` returns `{}`. It used to scale each
  market's in-sample ROI into a ±12 band, which handed `total_2_5` the maximum
  +12 from FIVE bets at +40.8% and `1x2` a bonus from the +34.41u that
  `docs/no_edge_out_of_sample.md` repudiates — while the markets that actually
  carry the card (corners 23 of the first 42 best bets, draw_no_bet and
  double_chance another 12) appeared in that file not at all. The mechanism and
  `MINIMUM_BETS_FOR_MARKET_RELIABILITY` remain for the day a forward record can
  fill it; at 33 settled selections it cannot.
- **The 2.5 line runs on `TOTALS_RATINGS` under the market-anchored rule
  (`evaluate_total_25_anchored`, weight 0.5, lift 0.03), capped at tier C.**
  Note the second gate: the card zeroes any row whose edge against the posted
  price is not positive, so the live rule is tighter than lift alone. That was
  an accident, and it is now the measured rule too — `score_rule` applies the
  price gate by default. Held out at the live setting: 95 bets, ROI +7.5%, CLV
  **−0.138 points**. Positive profit and negative closing-line value on 95 bets
  is not an edge, it is too small a sample for either proxy to speak.
  Held out by season it sits at zero CLV — no edge shown, none ruled out — so
  the stake stays at 0.1u until the forward CLV record says otherwise. The
  parameters were fixed before the test seasons were read; do not re-tune
  them on the test seasons. The matchday workflow fetches Understat xG each
  run (soft: a match without xG is rated on goals).
- **Closing odds and CLV are real now.** `AvgCH/AvgCD/AvgCA/AvgC>2.5/AvgC<2.5`
  are kept from Football-Data and reach every backtested bet; before
  2026-08-28 they were dropped at build time and every CLV figure was blank.
  `scripts/run_out_of_sample.py` regenerates the season-split tables.
- **Calibration is a precondition, not a goal.** It can rule a model out; it
  cannot rule one in. Never ship a model change on calibration evidence alone
  where a price-based backtest is available — Football-Data ships historical
  odds for 1X2 and the 2.5 line, so for those it always is. A change that
  improved calibration on every market cost about 140 units in the backtest:
  `docs/why_better_calibration_lost_money.md`.
- **BTTS's nine-point bias is measured out (2026-09-02), by the ratings rather
  than by a patch.** It runs on `BTTS_RATINGS` — the same opponent-adjusted,
  365-day, xG-blended configuration as the 2.5 line. Walk-forward over 1,540
  matches the overall gap goes +4.2 → −0.7 points and Brier and log loss
  improve with it, which is what separates this from the shrinkage that cost
  140 units: that improved calibration by saying less. It also bets fewer, not
  more. `docs/the_btts_bias_was_a_ratings_problem.md`,
  `scripts/run_btts_calibration.py`.
- **BTTS *can* be profit-backtested, and the claim that it never could was
  false (2026-09-02).** The provider serves historical `btts` — along with
  `draw_no_bet`, `double_chance` and `alternate_totals_corners` — at BetMGM,
  BetRivers, Bovada, DraftKings and FanDuel, all bettable books, verified by
  dispatching `Provider Capability Probe`. The tool to buy them has been in
  this repo the whole time, is *named after BTTS*, and had bought corners and
  player props and never one BTTS price. It could not: what counted as
  "already bought" was a fixture with no market in the key, so a BTTS harvest
  over the window already bought for corners skipped all 150 fixtures, spent
  nothing, and printed a green "already hold 150 fixtures". Fixed in
  `providers/historical_btts.holding_key`, with a misses ledger so a
  fixture/market pair that genuinely has no price is not re-bought forever.
  This is the same shape as every other fault found here: **a run that reports
  fine while nothing lands**. Before writing "no source this project can reach
  has X", dispatch the probe and read the answer.
- **BTTS does not produce most of the picks.** That was carried here for weeks
  and is false: from the `card-feed` branch, BTTS is 4 of the first 42 best
  bets and corners are 23. Check the feed, not `data/outputs/`, before making
  a claim about what the card stakes — the working tree holds stale runs.
- **Player props are built, measured, and calibration-corrected — not
  enabled.** The provider prices eight prop markets live and retains them
  historically (probed 2026-08-22). The pipeline has a player-data source
  (Understat match logs), a per-player Poisson model, a fitted Platt
  correction, a live staging fetch into its own file
  (`data/staging/player_props_staging.csv`, invisible to the card), and a
  walk-forward measurement with an honest split
  (`data/outputs/player_props_backtest.md`). Held out entirely, April–May
  2026 replicated the raw model's overconfidence (63.7% predicted, 52.7%
  happened) and the correction — fitted only on February–March — straightened
  every volume bucket (24.3 predicted vs 24.5 happened; 34.4 vs 34.9). The
  corrected model clears an 8% edge bar four times in two months: it almost
  never disagrees with the one-sided market prices by that much, no edge is
  demonstrated, and none can be at this sample size. Props reach the card
  only through the player/line-aware card integration (not built) and a
  reviewed policy approval, and the measurement above is what that review
  should weigh.
- **The card's fixture window moves with the calendar.** It is the round still
  to be played, derived in `src/epl_betting_lab/selected_slate.py` from the
  fixtures in hand, not a pair of dates written down. It used to be hardcoded
  to the opening round (2026-08-21 through 2026-08-24), which was correct for
  one week: after that every provider price fell outside it, every market read
  `unavailable`, and every card came back **Blocked** while the fetch, the
  mapping and the completeness checks all passed. A green run with no card is
  the signature of that class of fault — check the selected window in
  `data/outputs/automated_card_input.md` first.
- `data/manual/upcoming_fixtures.csv` is **fetched, not typed**. Every run
  refreshes it from Football-Data's public fixtures feed
  (`scripts/refresh_upcoming_fixtures.py`), so the slate advances on its own.
  Deliberately not sourced from the odds provider: this file is the denominator
  the shadow verifier uses to ask whether the provider covered the slate, and a
  provider checked against itself always passes. A failed fetch leaves the
  previous slate in place and marks the run degraded rather than emptying it.
  An *empty* feed is different: Football-Data lists only the coming round and
  goes empty around an international break, which is a quiet week, not a
  fault — the script then takes the provider's staged fixtures (noted as such
  in the file) so the card is not blocked against a stale committed slate,
  and the workflow runs it a second time after the price fetch because that
  staging does not exist on a fresh runner before it. That blocked the card on
  2026-09-01 with 160 `fixture_not_found` rows.
- **All four derived markets are now profit-backtested against real offered
  prices, and none of them shows an edge (2026-09-02).** A full 2025/26 season
  bought from the provider at T-3h, filtered to books Cooper can actually bet,
  run through the card's own `evaluate_*` rules walk-forward:
  `data/outputs/derived_market_backtest.md`,
  `scripts/run_derived_market_backtest.py`. **273 bets, ROI -0.35%, 95%
  interval -14.7% to +15.6%.** Per market: `draw_no_bet` +8.2% over 68 (18 of
  them pushes), `corners_total_9_5` +7.6% over 74, `btts` +0.7% over 31,
  `double_chance` -6.5% over 52, `corners_total_10_5` -18.8% over 48. Every
  interval includes zero.
  - The count is capped at the card's real limit of
    `MAX_BEST_BETS_DEFAULT` = 8 per round. Counting every BETTABLE row
    measured a population the card would never have bet - a median of ten a
    week, a maximum of twenty-four, over the cap in 24 weeks of 36. Even 273
    is an upper bound, because `total_2_5` competes for the same slots and is
    not in this backtest.
  - The half-season read +1.8% and the full season reads -1.51%. That is what
    213 bets buys you, and it is the reason to quote the interval and never
    the point.
  - Two numbers here were wrong for a few hours on 2026-09-02 and an
    adversarial review caught both. The runner passed `load_matches()`, and
    `PoissonGoalsModel` silently serves pure goals when `home_xg` is absent,
    so BTTS was measured on a model the card does not bet and read -1.5%
    instead of -10.6%; `build_backtest` now refuses a frame without xG rather
    than degrading quietly. And drawn draw-no-bets were dropped instead of
    counted as pushes, removing 33 of 115 bets from the denominator and
    reporting +7.1% for a rule that returned +5.1%. **A push is a bet.**
  - Two corner lines of the same market with the same model disagree by 17
    points of ROI. Treat that as the noise floor of a 370-bet sample, not as a
    reason to bet 9.5 and fade 10.5.
  - There is **no CLV here**: one snapshot per fixture means no close to
    compare against. Profit is the weaker instrument. `live_clv_report.md` is
    still where a market earns a bigger stake.
- **The corner markets are measured, and they are well calibrated.** Walk-forward
  gaps of -0.0, 0.0 and 0.0 points overall (`scripts/run_count_calibration.py`,
  `data/outputs/count_calibration.md`), which matters because corners are 23 of
  the first 42 best bets and their whole prior validation was synthetic unit
  tests plus six `@needs_dataset` checks that never ran in CI (since replaced
  by checks on a generated league that run everywhere). Good calibration
  is a precondition and cannot license a stake; a bad number there would be a
  reason to stake less, never a licence to fit the model until it moves.
- **Each pick carries a "bet down to" price, and the card shows it instead of
  the tier.** `_bet_down_to` in `reports/thursday_best_bets.py`: the price at
  which the edge falls to that market's own bar, so the line can drift that far
  and the bet still stands. It is NOT the fair price — fair is break-even, and
  taking a bet there is paying the vig for a coin flip. The tier column was
  dropped from the table because every bet is the same size, so it printed the
  same letter on every row.
- **The card may only price a bet at a book on `books.BETTABLE_BOOKS`, and the
  filter runs BEFORE market eligibility.** `bettable_only` fails closed — a
  frame with no `book` column returns empty, because "I cannot tell whose price
  this is" must never mean "price it anyway". Filtering only at pricing let
  eligibility certify a market at 10 of 10 fixtures while the card quietly
  priced fewer, since uncovered selections just produce no row: demonstrated
  2026-09-02, eligibility said 2/2 and the card priced 1. The anchored totals
  consensus is filtered too, or an unusable book would move the anchor and
  change which bets fire. `_best_quote` keeps its own check as defence in
  depth. A price that cannot be taken is
  worse than no price, because on the card it looks like the ones that can.
  Bookmakers the provider returns that are not on the list are NAMED in the
  card input report rather than dropped quietly — if one is a book Cooper can
  use, adding it is a decision about where he holds money, not a heuristic.
- **Every bet on the card is the same size: 0.1 units.**
  `PROFIT_BACKTESTABLE_MARKETS` is `{1x2, total_2_5}` — the only two
  Football-Data ships odds for — and `1x2` is off the card while the anchored
  rule caps `total_2_5` at C anyway. Tier A was never reached across 162
  archived best bets, so `UNVERIFIABLE_MARKET_TIER` is a **floor**, not the
  "one tier down, ranking still moves the stake" an earlier commit of mine
  claimed. The tier orders the card; it does not size the bet, and the card
  now prints a line saying so above the table. NOT a calibration judgement —
  see the bullet above — it is that no market here can be profit-backtested,
  so none has earned more. `live_clv_report.md` is where one earns its way
  back to a bigger stake.
- **Fading the public was tested and is not in the static prices.**
  Football-Data ships Pinnacle on 1,730 matches. Held out by date, fading the
  public returns −34.6% and *following* it −41.4% — a signal and its inverse
  both losing means the sample has nothing to say — and a fair-probability
  disagreement over two points fires on **0.0%** of selections: once each
  margin is removed properly the bookmaker average already sits on the sharpest
  book. Two dead ends are recorded in `docs/fading_the_public.md` because both
  looked like findings: normalising the margin away manufactures longshot
  edges, and "the best price beats a sharp book" is true of 93% of selections
  and so measures nothing. The live signal worth testing is reverse line
  movement, which needs the price feed to accumulate.
- **Pinnacle IS reachable: `bookmakers=pinnacle` overrides `regions`
  (2026-09-02).** Probed live — 20 events, one credit, Pinnacle returned. The
  repo said for weeks that `--regions us` does not return it and treated the
  sharp reference as out of reach; that was never tested against the provider.
  Pinnacle is a reference book, NOT on `BETTABLE_BOOKS`: it anchors and
  measures, and the card may never price a bet at it.
- **Every backtest breakdown is stamped `in_sample_backtest_not_evidence_of_edge`.**
  `backtest_market_breakdown.csv` carried `1x2 ... +34.41 units` for weeks and
  the ranking scaled it into a bonus. The ranking no longer reads those files;
  the stamp is for whoever opens one anyway.
- **The Closing Snapshot workflow is watched, twice.** The weekly check fails
  when it has not run in 14 days, and `live_clv_report.md` shouts when fewer
  than half of played picks have a price captured — because a snapshot that
  never fires and one that always fires late look identical in the record, and
  only the first leaves a missing run.
- **Live closing-line value is real from 2026-09-02, and empty until the feed
  fills.** Every CLV figure before that date came from `run_backtest.py`
  measuring backtested bets against Football-Data closes — in-sample, and a
  different population from the card. The live card's `closing_american_odds`
  is written as `""` by its only producer and 0 of 448 staged rows ever carried
  one. Now every run appends its observed prices to `refs/heads/price-feed`
  (`reports/price_feed.py`), the **Closing Snapshot** workflow adds readings
  ~20 minutes before each kick-off slot, and `reports/live_clv.py` scores the
  card's own picks against them. Read `data/outputs/live_clv_report.md`, not
  `clv_report.md`, for anything about the live card.
  - Live CLV is the only *closing-line* feedback corners have — but it is no
    longer their only feedback at all. "No source retains their historical
    prices" was false: the provider sells them, they have been bought for a
    full season, and `data/outputs/derived_market_backtest.md` measures the
    corner rule against money. Corners are 23 of the first 42 best bets, so
    this mattered more than any other wrong claim here.
  - The 42 picks archived before this date carry no kickoff or event id and
    report as `kickoff unknown` forever. Information not captured on the day is
    not recoverable.
  - A late snapshot is safe: `live_clv` only reads observations strictly before
    kick-off, so a delayed cron is ignored rather than trusted.
- **Card delivery is the `card-feed` branch, and no email.** Each run publishes
  `latest_card_comment.md` + `latest_status.json` there; the issue #162 comment
  remains as the written record but mentions nobody, and the repository's
  notifications are set to ignored. Changed 2026-08-28 at Cooper's request
  ("i dont want emails anymore"). An @mention overrides an ignored
  subscription, so putting one back into the comment would resume the emails.
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
python -m compileall -q -f src scripts app.py
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
  `tests/test_no_secrets_committed.py` enforces this; do not weaken it. It
  scans every tracked path, symlink target and body — no file is exempt for
  what it is called — and it lists the shapes it still cannot see in
  `test_the_gaps_this_guard_still_has_are_the_ones_written_down`.
- **Never delete, rename, narrow around, or run around a hard-rule guard.**
  `tests/test_the_guards_exist.py` names them (the secrets guard, the
  sibling-import guard, `tests/test_workflows.py`, and itself) and
  `tests/conftest.py` ends any run in which one of them contributed no test.
  `tests/conftest.py` also ends any run that SKIPPED anything — including a
  module-level `pytest.skip` or `importorskip`, which arrive as collection
  reports and never reach a test-report hook — and any run pytest parsed a
  `-k`, `-m`, `--deselect`, `--ignore` or an `addopts` into while a guard was
  enforced. The floor is per TEST, not per module: deselecting one guard test
  is as red as deleting the file.
  `tests/test_workflows.py` parses and executes `.github/workflows/tests.yml`,
  and the list of what it refuses is in that module's docstring — a renamed
  job, `needs:`/`strategy:` on the gate, an `if:` on any other job in the
  file, a pytest argument outside the whitelist, a missing `PYTHONSAFEPATH`,
  a bound `PYTEST_ADDOPTS`, a filtered trigger, a secret, a condition, a
  swallowed failure. What no test here covers: branch protection itself is a
  repository setting, a commit that deletes the guards and the conftest
  together is green, and a plugin in `requirements.txt` loads before the
  guards are counted.
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
