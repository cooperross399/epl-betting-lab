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

If your sportsbook or odds site gives you a CSV export with different column
names, save it as `data/manual/sportsbook_export.csv`, then run:

```bash
python scripts/diagnose_odds_export.py --source data/manual/sportsbook_export.csv
```

Open `data/outputs/odds_export_profile_diagnostic.md`. It compares every
configured profile, shows the closest match and missing source columns, lists
extra columns, and previews how market and selection names would normalize.
If no profile fully matches, update `data/manual/odds_import_profiles.json` and
run the diagnostic again. Nothing is imported or applied by this step.

The dashboard button `Diagnose odds export profile` performs the same safe,
read-only check and displays both the report and comparison table.

If no existing profile fully matches, create a review-only draft:

```bash
python scripts/suggest_odds_export_profile.py --source data/manual/sportsbook_export.csv --profile-name example_book
```

Open `data/outputs/odds_export_profile_suggestion.md`. High confidence means a
source header exactly matched a known alias. Medium confidence means it matched
only after spaces or separators were removed. `REVIEW_NEEDED` means the helper
did not make a safe choice. Optional fields may remain blank.

The JSON and markdown outputs are drafts only. The helper does not edit
`odds_import_profiles.json`, `current_odds.csv`, or `current_odds_import.csv`.
After checking every confidence note, validate the draft against the export:

```bash
python scripts/validate_odds_export_profile_suggestion.py
```

The validator normally reads the source path stored in the draft. To choose a
different source explicitly, add `--source data/manual/sportsbook_export.csv`.
Read `data/outputs/odds_export_profile_suggestion_validation.md` and its CSV
preview. It flags unresolved required mappings, missing source columns, empty
required outputs, bad odds, market/selection normalization problems, and
duplicate converted rows.

The verdicts are:

- `Ready for manual profile review`: conversion checks passed, but you must
  still inspect every mapping.
- `Needs edits before profile review`: fix the listed mappings or source rows.
- `Invalid draft suggestion`: regenerate or repair the draft first.

The validation is read-only and never creates `current_odds_import.csv`. The
dashboard buttons `Suggest odds export profile` and `Validate suggested odds
profile` provide the same safe flow.

Next, preview the exact registry change without installing anything:

```bash
python scripts/preview_install_odds_profile.py
```

Read `data/outputs/odds_profile_install_preview.md`. It shows the profile name,
whether that name already exists, profile counts before and after, the exact
JSON block, validation verdict, and warnings. The dashboard button `Preview
odds profile install` runs this same read-only preview.

Only after reviewing the preview should you install from Terminal:

```bash
python scripts/preview_install_odds_profile.py --apply
```

Additional safety flags are required in riskier cases:

- `--replace-existing` replaces a duplicate profile name.
- `--allow-needs-edits` explicitly accepts a Needs-edits verdict, invalid
  validation rows, or remaining `REVIEW_NEEDED` fields.
- `--allow-missing-validation` explicitly accepts missing validation.

An `Invalid draft suggestion` verdict can never be overridden. A successful
install first backs up the registry under `data/manual/backups/`, then writes
`data/outputs/odds_profile_install_audit.csv` and its markdown report. There is
no dashboard apply button.

After installation, verify that the installed profile still works against the
original export:

```bash
python scripts/verify_installed_odds_profile.py --profile example_book --source data/manual/sportsbook_export.csv
```

Read `data/outputs/odds_profile_post_install_verification.md` and its CSV. The
check is read-only and covers required mappings, missing/blank outputs, American
odds, market and selection normalization, duplicate rows, and converted sample
rows. The dashboard button `Verify installed odds profile` runs the same check
without writing an import file.

If verification finds a problem, use the backup path from the install preview
or audit to preview rollback:

```bash
python scripts/rollback_odds_profile_registry.py --backup-path data/manual/backups/BACKUP.json
```

The preview shows current and backup profile counts plus names that would be
added, removed, or changed. It clearly warns that apply replaces the registry.
If the backup already matches the current registry, nothing happens.

Apply rollback only from Terminal:

```bash
python scripts/rollback_odds_profile_registry.py --backup-path data/manual/backups/BACKUP.json --apply
```

Apply first creates a new backup of the current registry, restores the selected
backup, and writes `data/outputs/odds_profile_rollback_audit.csv` and its
markdown report. The dashboard displays the latest rollback preview but has no
rollback apply button.

When the report identifies the right profile, convert the export:

```bash
python scripts/convert_odds_export.py --profile generic --source data/manual/sportsbook_export.csv
```

The example `generic` profile expects `game_date`, `home`, `away`, `bet_type`,
`pick`, `odds`, and `sportsbook`. It maps them to the safe standard import
format using `data/manual/odds_import_profiles.json`. Add another named profile
there when a site uses different headers; no model code needs to change.

The converter creates `data/manual/current_odds_import.csv` plus a conversion
preview CSV and markdown report in `data/outputs/`. It does not fetch or invent
odds. Invalid American prices are excluded, and an existing import file is
preserved unless you deliberately pass `--overwrite-import`.

The dashboard's `Preview odds export conversion` button creates reports only.
It never writes or applies the import file. After a Terminal conversion, run
`python scripts/import_current_odds.py`; team and fixture matching, market and
selection validation, duplicate checks, backups, and audit gates remain in the
existing safe importer.

To import several real sportsbook prices without an export profile, first copy
the beginner template:

```bash
cp data/manual/current_odds_import_template.csv data/manual/current_odds_import.csv
```

Enter the real `american_odds` and `book` for each row. You may leave
`closing_american_odds` and `notes` blank. Preview everything before applying:

```bash
python scripts/import_current_odds.py
```

Read `data/outputs/current_odds_import_report.md`. It shows valid rows, invalid
rows, duplicates, additions, and updates without changing your odds file. When
the preview is correct, apply valid rows from Terminal only:

```bash
python scripts/import_current_odds.py --apply
```

Apply mode backs up an existing `current_odds.csv`, preserves its extra columns
and existing optional values, and skips invalid rows. The dashboard button
`Preview current odds import` cannot apply changes.

Every Terminal `--apply` attempt prints an import batch ID. Read the cumulative
history here:

```text
data/outputs/current_odds_import_audit.md
data/outputs/current_odds_import_audit.csv
```

The project also saves one CSV and markdown snapshot per batch under
`data/outputs/archive/current_odds_imports/BATCH_ID/`. The audit records the
source checksum, backup path, added/updated/unchanged/skipped counts, matching
key, and before/after values. Preview mode creates no apply audit. Recent batch
summaries and details appear read-only in the dashboard after the first apply.

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

You can also open the dashboard. Use `Odds Import` for the export/profile/import
steps, then use `Thursday Card` for odds completeness, validation, and best-bets
generation. `Home / Command Center` keeps the readiness refresh and recommended
next action at the front.
The dashboard only previews imports and maintenance and shows report tables.
It does not overwrite an existing odds file, apply imports or maintenance,
edit odds, or force generation.

After the odds file exists, the easiest path is the dashboard button `Run
Thursday readiness refresh`. It runs odds completeness, current odds
validation, and Thursday best-bets generation in that order. If validation is
blocked, it stops safely and tells you what to fix.

After a new Thursday best-bets archive is created, use `Run post-refresh
Thursday review`. It compares the newest archived card against the previous
archived card, then builds the decision queue. If you do not have at least two
archived Thursday cards yet, it stops and explains that comparison is not
available yet.

The dashboard badge means:

- `Ready`: no serious issues or warnings.
- `Warnings only`: review warnings before trusting the card.
- `Blocked`: fix serious issues before generating best bets.
- `Needs refresh`: `current_odds.csv` changed after validation.
- `Not checked`: run validation first.

The Thursday panel also shows a command center card before the full reports:
Thursday status, odds completion, serious validation issues, warnings, the
latest archive pair, count-change risk, top movement reason, and the
recommended next manual action. Use that card first, then open the details only
when something looks missing or blocked. The `Open this next` line points to
the exact detail section to review after you read the recommended action. It
also shows affected-play counts from `thursday_decision_queue.csv` when that
file is current, or a short generate/refresh message when it is not usable.

This reads only `data/manual/current_odds.csv` and writes:

```text
data/outputs/thursday_best_bets.md
data/outputs/thursday_best_bets.csv
```

Every successful run also saves dated snapshots here:

```text
data/outputs/archive/thursday_best_bets/YYYY-MM-DD/HHMMSS_thursday_best_bets.md
data/outputs/archive/thursday_best_bets/YYYY-MM-DD/HHMMSS_thursday_best_bets.csv
data/outputs/archive/thursday_best_bets/YYYY-MM-DD/HHMMSS_thursday_best_bets_metadata.json
```

These archived reports are read-only history so you can compare old Thursday
cards later. Same-second duplicates get a safe suffix instead of overwriting.
The dashboard lists recent archived Thursday reports on the `Betting ledger`
tab.

After you have at least two archived reports, compare the latest two:

```bash
python scripts/compare_thursday_best_bets.py
```

This writes:

```text
data/outputs/thursday_best_bets_comparison.md
data/outputs/thursday_best_bets_comparison.csv
```

The comparison shows which plays were added or removed, plus changes in status,
confidence tier, ranking score, odds, calibrated edge, and suggested units. It
also adds a movement category and importance score so the top of the markdown
shows the biggest recommendation moves first. The report also adds
`action_needed` and `action_reason` fields, such as `Review price`, `Candidate
upgrade`, `Likely remove from card`, `Watch only`, `Recheck odds`, `Recheck
validation`, or `No action`. If there are not enough archives yet, the report
says comparison is not available yet and tells you to create more Thursday
snapshots first.

The comparison report and dashboard show the exact archive pair being reviewed,
such as `Comparing: 2026-07-09 12:30:00 vs 2026-07-08 11:00:00`. The project
uses archive metadata for that label when available and falls back to the
archived CSV filename timestamp if metadata is missing.
Open `Archive history details` in the dashboard to see the latest and previous
archive paths, validation status, best/lean/pass counts, total rows, and notes
when metadata is missing or a file cannot be read.
The dashboard and comparison report also show a quick card count-change note
for best bets, leans, passes, and total rows before you open the full
comparison.
The count-change risk flag is conservative: a best-bet drop of 2+, pass/lean
increase of 5+, total-candidate move of 5+, or incomplete archive data gets
called out for review.
The comparison and dashboard also show a `Top card movement reason`, such as
`Mostly odds movement`, `Mostly tier/status changes`, `Mostly new/removed
plays`, `Mostly edge movement`, `Mostly unit-size changes`, or `Possible
missing odds/data issue`. This is only a quick explanation of why the card
changed; it does not recommend or place a bet.
The dashboard, comparison report, and decision queue also show a `Recommended
next action` banner. It puts data/odds problems first, then likely removals,
price reviews, and candidate upgrades. It is only a manual review prompt; it
does not edit odds, edit your ledger, or place bets.

After the comparison exists, create a compact decision queue:

```bash
python scripts/generate_thursday_decision_queue.py
```

This writes:

```text
data/outputs/thursday_decision_queue.md
data/outputs/thursday_decision_queue.csv
```

The decision queue groups plays by `action_needed` so the biggest manual review
items are easier to scan: `Candidate upgrade`, `Review price`, `Likely remove
from card`, `Recheck odds`, `Recheck validation`, `Watch only`, then
`No action`. Inside each group, higher `importance_score` rows come first. If
the comparison file is missing, the queue report tells you to run
`python scripts/compare_thursday_best_bets.py` first.

From the dashboard, `Run post-refresh Thursday review` runs the comparison and
decision queue together after the Thursday report has been refreshed. It does
not edit odds, edit your ledger, force report generation, or place bets.

The Thursday report ranks plays with a simple score and tier:

```text
A = strongest best-bet profile, up to 0.5u
B = playable, 0.25u
C = lean/watchlist only, 0.10u max
Pass/Avoid = 0u
```

The ranking rewards calibrated edge, calibrated probability, BETTABLE status,
and more trusted markets. It penalizes heavy juice, plus-money variance,
totals, totals unders, and goal-environment under warnings.

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

To review whether A, B, C, LEAN, and PASS/Avoid tiers are actually performing,
run:

```bash
python scripts/generate_tier_performance_report.py
```

This writes `data/outputs/tier_performance_report.md` plus CSV breakdowns by
tier, market, team, odds range, and CLV when closing odds are available.
Settled ledger bets count toward profit/loss. Archived Thursday recommendations
that were not bet are tracked separately as recommendation-only rows. The
dashboard has a safe `Generate tier performance report` button for the same
read-only report.

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

## Step 7 — Open the betting portal

After you run the ledger scripts, open the dashboard:

```bash
streamlit run app.py
```

Use the sidebar sections:

- `Home / Command Center` for Thursday readiness, the next action, ledger
  units/ROI, and pending bets.
- `Thursday Card` for odds completeness, validation, and best bets.
- `Odds Import` for the safe profile and import preview sequence.
- `Performance Reports` for tiers, backtests, CLV, and profit breakdowns.
- `Bet Ledger` for record, pending bets, health checks, and settlement preview.
- `Archives & Comparisons` for saved cards, comparisons, and decision queue.
- `Tools / Diagnostics` for projections, form, model views, and file checks.

The three main Home buttons are:

```text
Run Thursday readiness refresh
Run post-refresh Thursday review
Generate tier performance report
```

The related sections keep the individual safe report actions:

```text
Run bet ledger report
Run ledger health check
Run settlement preview
Create current odds template
Preview current odds import
Preview current odds maintenance
Check odds entry completeness
Validate current odds
Generate Thursday best-bets report
Compare latest Thursday reports
Generate Thursday decision queue
Run backtest reports
Refresh dashboard data
```

`Thursday Card` shows the current odds validation report and Thursday report
writeup/table when their files exist. `Archives & Comparisons` shows the latest
snapshot comparison after you run `python scripts/compare_thursday_best_bets.py`
or click `Compare latest Thursday reports`. It also shows the decision queue after you run
`python scripts/generate_thursday_decision_queue.py` or click
`Generate Thursday decision queue`.

These buttons only regenerate reports. They do not apply settlements, confirm
actual bets, edit the ledger, edit `data/manual/current_odds.csv`, place bets,
force Thursday generation, or invent missing odds.

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
