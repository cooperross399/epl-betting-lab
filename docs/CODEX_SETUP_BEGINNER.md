# Beginner Setup: Using Codex as the EPL Betting Lab Agent

This guide is for using Codex as the agent that keeps editing and improving this project during the EPL season.

## What Codex does here

Codex should be treated like a coding teammate. It can read the project, edit files, run commands, fix errors, add features, and propose changes.

Codex should not be treated like a sportsbook bot. It should not place bets, invent live odds, or guarantee winners.

## Step 1 — Put this project in GitHub

Codex works best when the project is in a GitHub repository.

Beginner version:

1. Go to GitHub.
2. Create a new private repository called `epl-betting-lab`.
3. Upload the contents of this folder.
4. Commit the files.

Recommended repo settings:

- Keep it private.
- Do not commit sportsbook login info.
- Do not commit API keys.
- Use `.env` locally for secrets.

## Step 2 — Connect GitHub to ChatGPT/Codex

In ChatGPT/Codex, connect your GitHub account and give Codex access to the `epl-betting-lab` repo.

After it is connected, Codex can inspect the codebase and make edits in a branch or pull request.

## Step 3 — Give Codex the first task

Use this prompt:

```text
You are working in my `epl-betting-lab` repo. Read `AGENTS.md` first and follow it. Make the project more ready for the 2026/27 EPL season. Start by running tests and compile checks. Then inspect the current model and suggest the next 3 highest-impact improvements for in-season betting strategy tracking. Do not fabricate odds or results.
```

## Step 4 — Weekly update prompt

After each matchweek, use this:

```text
Read `AGENTS.md`. Update the EPL Betting Lab using the latest available Football-Data EPL results. Rebuild the processed dataset, run the backtest, run the weekly agent brief, and inspect whether recent form or team-specific bias suggests a model improvement. If code changes are justified, make the smallest useful change, add/update tests, and summarize what changed. Do not invent sportsbook odds.
```

## Step 5 — When you paste odds

Before a matchweek, paste or enter odds into:

```text
data/manual/current_odds.csv
```

Use `american_odds` for the price available when you run the model. Leave
`closing_american_odds` blank until after the market closes, then paste the
closing price there for CLV tracking. Missing closing odds are not guessed.

Then tell Codex:

```text
I updated `data/manual/current_odds.csv` with current odds. Run the model, generate the weekly card, and tell me the best smart plays, leans, avoids, and sneaky/fun angles. Respect my max juice rule around -160.
```

Before a Thursday best-bets report, create the manual odds file from upcoming
fixtures if it does not exist yet:

```bash
python scripts/create_current_odds_template.py
```

This fills in dates, teams, markets, and selections. You still need to enter
`american_odds` and `book`. If you want to prefill a book name:

```bash
python scripts/create_current_odds_template.py --book FanDuel
```

If `data/manual/current_odds.csv` already exists, the script stops safely. Only
replace it intentionally with:

```bash
python scripts/create_current_odds_template.py --overwrite
```

If your odds file already has real prices and you only need to add missing
fixtures or market rows, preview the maintenance helper:

```bash
python scripts/maintain_current_odds.py
```

This writes `data/outputs/current_odds_maintenance_preview.csv` and
`data/outputs/current_odds_maintenance_report.md` without editing your odds
file. If the preview looks right, apply it:

```bash
python scripts/maintain_current_odds.py --apply
```

The helper preserves prices, closing odds, book names, notes, and extra columns
already in `data/manual/current_odds.csv`. Before it applies changes, it writes
a backup in `data/manual/backups/`. To fill a book name only on newly added
rows, use:

```bash
python scripts/maintain_current_odds.py --book FanDuel --apply
```

Then check whether any odds entries are still incomplete:

```bash
python scripts/check_current_odds_completeness.py
```

Read `data/outputs/current_odds_completeness.md`. It groups missing or bad odds
by match, market, selection, and book when available. It flags blank odds,
non-numeric odds, missing books, duplicate rows, and expected market rows that
are missing. The completion percentage is numeric odds filled divided by
existing rows plus any expected rows that are missing.

Then validate your manual odds file:

```bash
python scripts/validate_current_odds.py
```

Read `data/outputs/current_odds_validation.md`. Fix serious issues before
trusting the card. Warnings, like missing book names, heavy juice, or totals
under caution, are review notes.

Then run:

```bash
python scripts/generate_thursday_best_bets.py
```

If serious validation issues exist, this stops before creating a card. Fix the
odds file and run it again. For a rare intentional preview only, run:

```bash
python scripts/generate_thursday_best_bets.py --force
```

You can also open the dashboard and click `Create current odds template`,
`Preview current odds maintenance`, `Check odds entry completeness`, `Validate
current odds`, then `Generate Thursday best-bets report`, on the `Betting
ledger` tab. The dashboard only previews maintenance and shows report tables.
It does not overwrite an existing odds file, apply maintenance, edit odds, or
force generation.

The dashboard badge means:

- `Ready`: no serious issues or warnings.
- `Warnings only`: review warnings before trusting the card.
- `Blocked`: fix serious issues before generating best bets.
- `Needs refresh`: `current_odds.csv` changed after validation.
- `Not checked`: run validation first.

The Thursday panel also shows a quick readiness row before the full reports:
odds completion percentage, incomplete matches, serious validation issues,
validation warnings, and Thursday status. Use that row first, then open the
details only when something looks missing or blocked.

This reads only `data/manual/current_odds.csv` and writes:

```text
data/outputs/thursday_best_bets.md
data/outputs/thursday_best_bets.csv
```

Before running it each Wednesday or Thursday, update the real book prices in
`american_odds`, fill in `book`, and leave `closing_american_odds` blank until
after the market closes.

## Step 6 — Track actual bets

The weekly card is not a bet slip. If you decide to place a bet yourself, log
it in:

```text
data/manual/bet_ledger.csv
```

Use one row per bet. The safest fields to fill right away are:

```text
bet_id
date
season
match
home_team
away_team
market
selection
model_recommendation_status
american_odds
stake_units
result
book
notes
```

Use `pending` until the match is graded. Later change `result` to `win`,
`loss`, or `push`. If you paste `closing_american_odds` after the market
closes, the report will calculate CLV. If closing odds are blank, CLV stays
blank.

Run:

```bash
python scripts/run_bet_ledger.py
```

Then read:

```text
data/outputs/bet_ledger_summary.md
```

To create draft ledger rows from the weekly card instead of copying each play
by hand, run this after `python scripts/generate_weekly_card.py`:

```bash
python scripts/prefill_bet_ledger.py
```

This adds `BETTABLE` and `LEAN` rows from `data/outputs/weekly_card.csv` to
`data/manual/bet_ledger.csv`. It uses a stable `bet_id`, so running it twice
does not create duplicates. The rows are drafts: `result` stays `pending`,
`closing_american_odds` stays blank, and you still need to confirm which bets
you actually placed.

If you want to review pass rows too:

```bash
python scripts/prefill_bet_ledger.py --include-pass
```

Before you settle bets or trust profit/loss, run the ledger health check:

```bash
python scripts/check_bet_ledger.py
```

Then read:

```text
data/outputs/bet_ledger_health_check.md
```

Fix serious issues first, such as duplicate `bet_id`, missing odds, invalid
markets, invalid results, or missing team names. Missing closing odds are
optional cleanup for CLV tracking, not a blocker.

After matches finish, update the processed EPL results and preview settlement:

```bash
python scripts/settle_bet_ledger.py
```

Read:

```text
data/outputs/bet_settlement_preview.md
```

The preview suggests `win`, `loss`, `push`, `pending`, or `unmatched` for
pending ledger rows. It does not edit your ledger by default. If the preview
looks right, apply the confident settlements:

```bash
python scripts/settle_bet_ledger.py --apply
```

Rows marked `unmatched` are left alone so you can fix team names, dates, or
missing results by hand.

## Step 7 — View the ledger dashboard tab

After you run the ledger scripts, open the dashboard:

```bash
streamlit run app.py
```

Use the `Betting ledger` tab to see your record, profit/loss, ROI, pending
bets, health check issues, settlement preview, CLV summary, and market/team
breakdowns in one place. The dashboard is read-only for now, so it will not
edit `data/manual/bet_ledger.csv`.

The ledger tab has buttons to run safe report actions:

```text
Run bet ledger report
Run ledger health check
Run settlement preview
Create current odds template
Preview current odds maintenance
Check odds entry completeness
Validate current odds
Generate Thursday best-bets report
Run backtest reports
Refresh dashboard data
```

The tab also shows the current odds validation report and Thursday report
writeup/table when their files exist.

These buttons only regenerate reports. They do not apply settlements, confirm
actual bets, edit the ledger, edit `data/manual/current_odds.csv`, place bets,
or invent missing odds.

At the top of the tab, the weekly workflow checklist shows which files are
ready, missing, or stale. If something says `Missing` or `Needs refresh`, use
the command shown in that row.

## Step 8 — What to approve and what to reject

Approve Codex changes when:

- Tests pass.
- The code is simpler or more useful.
- The change improves backtest discipline.
- The output is easier to understand.
- It does not fake odds or overclaim confidence.

Reject or ask for revisions when:

- It removes your betting rules.
- It adds complicated code without clear improvement.
- It changes thresholds based on one bad or good week.
- It pretends missing data is real.

## Good first agent tasks

1. Add a recent-form weighting toggle.
2. Add home/away split projections.
3. Add market ROI by season and by team.
4. Add promoted-team tracking dashboard.
5. Add closing-line-value tracking.
6. Add corners model using Football-Data corner columns.
7. Add shots/SOT model using Football-Data shot columns.

## Important reminder

This is a research tool. The final decision should still be manual. The best use is to find smarter prices for a game script, not to blindly bet every model edge.
