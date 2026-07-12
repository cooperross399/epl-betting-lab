# EPL Betting Lab

A starter Python project for building, testing, and using English Premier League betting strategies for the 2026/27 season.

This is built for a practical betting workflow:

- Pull historical EPL data
- Fit a simple goals model
- Compare model probabilities to betting prices
- Avoid heavy juice by default
- Backtest strategy rules before trusting them
- Generate a weekly betting card
- Review which markets are actually working

> Responsible betting note: this project is for research and tracking. It does not guarantee profit. Use small stakes, record every play, and treat model output as a decision aid rather than an auto-bet system.

---

## Data sources

The starter project is designed around these public data sources:

- **Football-Data.co.uk** for historical EPL results, match stats, and odds CSVs.
- **ClubElo** for team strength ratings.
- **Manual odds entry** at first, because sportsbook lines vary by state/book and change constantly.

The included `data/manual/upcoming_fixtures.csv` is a starter fixture sheet for early 2026/27 EPL matches. Fixtures and times can change, so update it before betting.

---

## Setup on Mac

From Terminal:

```bash
cd ~/Downloads/epl-betting-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

---

## Fetch historical EPL data

```bash
python scripts/fetch_data.py --seasons 2122 2223 2324 2425 2526
```

This creates:

```text
data/processed/epl_historical_matches.csv
```

Season code examples:

```text
2122 = 2021/22
2223 = 2022/23
2324 = 2023/24
2425 = 2024/25
2526 = 2025/26
```

---

## Run the first backtest

```bash
python scripts/run_backtest.py
```

This creates:

```text
data/outputs/backtest_bets.csv
data/outputs/backtest_summary.csv
```

The starter backtest tests:

- 1X2 moneyline-style markets
- Over/under 2.5 goals
- Basic model-vs-book edge logic
- Your default no-heavy-juice rule: pass on odds worse than about `-160`

---

## Add current odds

Copy the template:

```bash
cp data/manual/current_odds_template.csv data/manual/current_odds.csv
```

Then replace the example odds with real book prices.

Expected format:

```csv
date,home_team,away_team,market,selection,american_odds,closing_american_odds,book,notes
2026-08-21,Arsenal,Coventry,total_2_5,under,110,,DraftKings,
```

Supported starter markets:

```text
1x2 selections: home, draw, away
total_2_5 selections: over, under
btts selections: yes, no
```

`american_odds` is the price used when the model makes the decision.
`closing_american_odds` is optional. Leave it blank before matches, then paste
the closing price after the market closes. If it is blank, CLV stays missing
instead of being guessed.

---

## Generate a weekly card

```bash
python scripts/generate_weekly_card.py
```

This creates:

```text
data/outputs/weekly_card.csv
data/outputs/weekly_card.md
```

The weekly card includes:

- Matchup
- Market
- Selection
- American odds
- Model probability
- Book implied probability
- Edge
- Fair price
- Suggested unit size

## Generate Thursday best bets

Every Wednesday or Thursday, update:

```text
data/manual/current_odds.csv
```

Use real sportsbook prices only. If the file does not exist yet, create a fresh
odds-entry template from upcoming fixtures:

```bash
python scripts/create_current_odds_template.py
```

This fills in dates, teams, markets, and selections. You still need to enter
`american_odds` and `book`. To prefill a book name:

```bash
python scripts/create_current_odds_template.py --book FanDuel
```

If `data/manual/current_odds.csv` already exists, the script stops safely. To
replace it intentionally:

```bash
python scripts/create_current_odds_template.py --overwrite
```

To convert a sportsbook or odds-site CSV export with different column names,
save it as `data/manual/sportsbook_export.csv`, then run:

```bash
python scripts/diagnose_odds_export.py --source data/manual/sportsbook_export.csv
```

The read-only diagnostic compares the export columns with every profile in
`data/manual/odds_import_profiles.json`. It shows the best profile, missing
required mappings, ignored extra columns, a small normalized sample, and market
or selection values the safe importer may reject. It writes:

```text
data/outputs/odds_export_profile_diagnostic.csv
data/outputs/odds_export_profile_diagnostic.md
```

If there is no full match, update the closest profile or add a new one before
converting. The diagnostic never creates an import file or edits odds. The
dashboard button `Diagnose odds export profile` runs the same read-only check.

After choosing a profile, preview the conversion:

```bash
python scripts/convert_odds_export.py --profile generic --source data/manual/sportsbook_export.csv
```

The `generic` mapping in `data/manual/odds_import_profiles.json` converts
`game_date`, `home`, `away`, `bet_type`, `pick`, `odds`, and `sportsbook` into
the standard import columns. You can add another named profile for a different
export without changing Python code. The converter writes:

```text
data/manual/current_odds_import.csv
data/outputs/odds_export_conversion_preview.csv
data/outputs/odds_export_conversion_report.md
```

It only copies supplied values; it does not fetch or guess prices. Invalid
American odds are excluded. If `current_odds_import.csv` already exists, it is
preserved unless you intentionally add `--overwrite-import`. The dashboard
button `Preview odds export conversion` only writes the preview reports and
never creates, replaces, or applies an import file.

After conversion, run `python scripts/import_current_odds.py`. That existing
safe importer still performs team normalization, fixture matching,
market/selection validation, duplicate checks, and the normal preview gate.
Applying remains a separate Terminal-only step with backups and audit history.

To enter several real sportsbook prices without an export profile, create the
import file from its safe template:

```bash
cp data/manual/current_odds_import_template.csv data/manual/current_odds_import.csv
```

Fill in `date`, `home_team`, `away_team`, `market`, `selection`,
`american_odds`, and `book`. `closing_american_odds` and `notes` are optional.
Then preview the import:

```bash
python scripts/import_current_odds.py
```

The preview normalizes familiar team/market labels, flags invalid or duplicate
rows, and shows which rows would be added or updated. It writes:

```text
data/outputs/current_odds_import_preview.csv
data/outputs/current_odds_import_report.md
```

Preview mode never edits `current_odds.csv`. After reviewing the report, apply
only valid rows from Terminal:

```bash
python scripts/import_current_odds.py --apply
```

Apply mode creates a timestamped backup before modifying an existing odds
file, preserves extra columns and blank optional fields, and skips every invalid
or duplicate import row. The dashboard only offers `Preview current odds
import`; it has no apply button.

Every `--apply` attempt also prints a unique import batch ID and writes audit
history:

```text
data/outputs/current_odds_import_audit.csv
data/outputs/current_odds_import_audit.md
data/outputs/archive/current_odds_imports/BATCH_ID/current_odds_import_audit.csv
data/outputs/archive/current_odds_imports/BATCH_ID/current_odds_import_audit.md
```

Each batch records the source file and SHA-256 checksum, backup path, row
counts, six-field matching key, skipped issues, and before/after values for
updates. Preview mode does not create an apply audit. The dashboard shows recent
batch summaries and read-only audit details after the first Terminal apply.

If the odds file already has prices and you only want to add missing fixtures
or market rows, preview maintenance first:

```bash
python scripts/maintain_current_odds.py
```

This writes:

```text
data/outputs/current_odds_maintenance_preview.csv
data/outputs/current_odds_maintenance_report.md
```

The preview does not edit `data/manual/current_odds.csv`. If the preview looks
right, apply the missing rows:

```bash
python scripts/maintain_current_odds.py --apply
```

Existing `american_odds`, `closing_american_odds`, `book`, `notes`, and any
extra columns are preserved. Before applying, the helper backs up the current
odds file in:

```text
data/manual/backups/current_odds_YYYYMMDD_HHMMSS.csv
```

To prefill the book only on newly added rows:

```bash
python scripts/maintain_current_odds.py --book FanDuel --apply
```

After your rows exist, check whether any prices are still missing:

```bash
python scripts/check_current_odds_completeness.py
```

This writes:

```text
data/outputs/current_odds_completeness.csv
data/outputs/current_odds_completeness.md
```

The completeness report shows blank odds, non-numeric odds, missing book names,
duplicate market/selection rows, and expected fixture/market rows that are
missing. It also shows a completion percentage: rows with numeric odds divided
by existing rows plus any expected rows that are missing.

Validate the odds file before generating the report:

```bash
python scripts/validate_current_odds.py
```

This creates:

```text
data/outputs/current_odds_validation.csv
data/outputs/current_odds_validation.md
```

Fix serious issues before trusting the Thursday card. Warnings, like missing
book names, heavy juice, or total_2_5 under caution, are review notes.

Then run:

```bash
python scripts/generate_thursday_best_bets.py
```

If serious validation issues exist, this command stops before creating a card.
Fix the issues in `data/manual/current_odds.csv`, then run it again. For a rare
intentional preview only, you can run:

```bash
python scripts/generate_thursday_best_bets.py --force
```

Or open the dashboard and use `Create current odds template`, `Preview current
odds import`, `Preview current odds maintenance`, `Check odds entry
completeness`, then `Generate Thursday best-bets report`, on the `Betting
ledger` tab. The dashboard can preview imports and missing odds rows and show
incomplete entries, but it does not apply imports or maintenance, overwrite an
existing odds file, edit odds, or force generation.

Once `data/manual/current_odds.csv` exists, you can also click `Run Thursday
readiness refresh`. That one safe button runs odds completeness, current odds
validation, and Thursday best-bets generation in order. If validation finds a
serious blocker, it stops before trusting the card and does not force
generation.

After a new Thursday best-bets archive is created, click `Run post-refresh
Thursday review`. That safe review button compares the latest archived card
against the previous archived card, then creates the Thursday decision queue.
If there are not at least two archived cards yet, it stops with a friendly
message and does not try to build the queue.

The dashboard shows a current-odds status badge:

- `Ready`: no serious issues or warnings.
- `Warnings only`: review warnings before trusting the card.
- `Blocked`: fix serious issues before generating best bets.
- `Needs refresh`: `current_odds.csv` changed after validation.
- `Not checked`: run validation first.

The Thursday panel also has a compact readiness row before the full reports.
It shows odds completion percentage, incomplete matches, serious validation
issues, validation warnings, and whether the Thursday workflow is ready,
blocked, stale, or not checked.

This creates:

```text
data/outputs/thursday_best_bets.csv
data/outputs/thursday_best_bets.md
```

Each successful run also saves a dated archive snapshot:

```text
data/outputs/archive/thursday_best_bets/YYYY-MM-DD/HHMMSS_thursday_best_bets.csv
data/outputs/archive/thursday_best_bets/YYYY-MM-DD/HHMMSS_thursday_best_bets.md
data/outputs/archive/thursday_best_bets/YYYY-MM-DD/HHMMSS_thursday_best_bets_metadata.json
```

The archive lets you review old Thursday cards later. If two reports are
generated in the same second, the second snapshot gets a safe suffix instead
of replacing the first one. The dashboard shows recent archived Thursday
reports in the `Betting ledger` tab. Only use `--overwrite-archive` from
Terminal if you intentionally want to replace a timestamp collision.

After you have at least two archived Thursday reports, compare the newest two:

```bash
python scripts/compare_thursday_best_bets.py
```

This creates:

```text
data/outputs/thursday_best_bets_comparison.csv
data/outputs/thursday_best_bets_comparison.md
```

The comparison shows plays added or removed, status changes, confidence tier
changes, ranking score movement, odds movement, calibrated edge changes, and
suggested unit changes. It also labels each row with a movement category and
importance score so the markdown report can show the biggest recommendation
moves first, such as `Became BETTABLE`, `Became PASS/Avoid`, `Tier upgraded`,
`Edge improved`, or `Odds moved against us`. The report also adds an
`action_needed` label, such as `Review price`, `Candidate upgrade`, `Likely
remove from card`, `Watch only`, `Recheck odds`, `Recheck validation`, or
`No action`, so you know what kind of manual review to do next. If there are
not two archived reports yet, it writes a beginner-friendly message instead of
guessing.

The comparison report and dashboard also show which archive pair is being
reviewed, such as `Comparing: 2026-07-09 12:30:00 vs 2026-07-08 11:00:00`.
The label uses archive metadata when it is available and falls back to the
archived CSV filename timestamp if metadata is missing.
Open `Archive history details` in the dashboard to see the latest and previous
archive paths, validation status, best/lean/pass counts, total rows, and notes
when metadata is missing or a file cannot be read.
The dashboard and comparison report also show a compact card count-change note
for best bets, leans, passes, and total rows before you open the full
comparison.
The count-change risk flag is conservative: a best-bet drop of 2+, pass/lean
increase of 5+, total-candidate move of 5+, or incomplete archive data gets
called out for review.
The comparison and dashboard also show a `Top card movement reason`, such as
`Mostly odds movement`, `Mostly tier/status changes`, `Mostly new/removed
plays`, `Mostly edge movement`, `Mostly unit-size changes`, or `Possible
missing odds/data issue`. This is a quick explanation of why the card changed;
it is not a bet recommendation.
The dashboard, comparison report, and decision queue also show a `Recommended
next action` banner. It puts data/odds problems first, then likely removals,
price reviews, and candidate upgrades. It is a manual review prompt only; it
does not edit odds, edit the ledger, or place bets.

To turn that comparison into a compact review queue grouped by what you should
look at first, run:

```bash
python scripts/generate_thursday_decision_queue.py
```

This creates:

```text
data/outputs/thursday_decision_queue.csv
data/outputs/thursday_decision_queue.md
```

The decision queue groups changed plays by `action_needed` in this order:
`Candidate upgrade`, `Review price`, `Likely remove from card`, `Recheck odds`,
`Recheck validation`, `Watch only`, then `No action`. Within each group, the
most important changes appear first. If the comparison report does not exist
yet, the queue report tells you to run
`python scripts/compare_thursday_best_bets.py` first.

From the dashboard, you can use `Run post-refresh Thursday review` to run the
comparison and decision queue together after a new archive exists. It does not
edit odds, edit the ledger, force Thursday generation, or place bets.

The report separates best bets, leans, and passes/notable avoids. It uses
calibrated probabilities, respects the default max-juice rule around `-160`,
and keeps the totals protections. It also adds a transparent ranking score and
confidence tier:

```text
A = strongest best-bet profile, up to 0.5u
B = playable, 0.25u
C = lean/watchlist only, 0.10u max
Pass/Avoid = 0u
```

The ranking rewards calibrated edge, calibrated probability, BETTABLE status,
and more trusted markets. It penalizes heavy juice, plus-money variance,
totals, totals unders, and goal-environment under warnings.

---

## Track actual bets in the ledger

The model card is research. If you actually place a bet yourself, record it in:

```text
data/manual/bet_ledger.csv
```

The repo also includes a blank template:

```text
data/manual/bet_ledger_template.csv
```

Use one row per bet. Keep `stake_units` as the main tracker. You can leave
`closing_american_odds`, `profit_units`, `profit_dollars`, and
`clv_probability_points` blank at first.

Important fields:

```text
result = win, loss, push, or pending
american_odds = the price you actually bet
closing_american_odds = optional closing price after the market closes
stake_units = your unit stake, such as 0.5 or 1
book = sportsbook name for your notes
```

Run the ledger report:

```bash
python scripts/run_bet_ledger.py
```

This creates:

```text
data/outputs/bet_ledger_summary.md
data/outputs/bet_ledger_by_market.csv
data/outputs/bet_ledger_by_selection.csv
data/outputs/bet_ledger_by_team.csv
data/outputs/bet_ledger_pending.csv
```

Pending bets do not count toward profit/loss or ROI. Pushes count as 0.
Missing closing odds stay blank instead of being guessed.

To review how confidence tiers are performing mid-season, run:

```bash
python scripts/generate_tier_performance_report.py
```

This creates:

```text
data/outputs/tier_performance_summary.csv
data/outputs/tier_performance_by_market.csv
data/outputs/tier_performance_by_team.csv
data/outputs/tier_performance_by_odds_range.csv
data/outputs/tier_performance_by_clv.csv
data/outputs/tier_performance_report.md
```

Settled ledger bets count toward wins, losses, pushes, units, and ROI.
Archived Thursday recommendations that were not entered as actual bets are
tracked separately as recommendation-only rows. The dashboard button `Generate
tier performance report` runs the same read-only report.

To save typing after you generate the weekly card, you can pre-fill draft
ledger rows from `data/outputs/weekly_card.csv`:

```bash
python scripts/prefill_bet_ledger.py
```

By default this adds only `BETTABLE` and `LEAN` model rows, marks them
`pending`, leaves `closing_american_odds` blank, and skips rows that are
already in your ledger. To include pass rows for review:

```bash
python scripts/prefill_bet_ledger.py --include-pass
```

After pre-filling, delete any rows you did not actually bet or leave a note
that they were not placed.

Before settling or reviewing profit/loss, run the ledger health check:

```bash
python scripts/check_bet_ledger.py
```

This creates:

```text
data/outputs/bet_ledger_health_check.csv
data/outputs/bet_ledger_health_check.md
```

The health check is read-only. It flags serious issues like duplicate bet IDs,
missing odds, invalid markets, invalid results, and missing team names. It also
flags optional cleanup like missing closing lines for CLV.

After matches finish and the processed EPL results are updated, preview
settlements for pending ledger rows:

```bash
python scripts/settle_bet_ledger.py
```

This creates:

```text
data/outputs/bet_settlement_preview.csv
data/outputs/bet_settlement_preview.md
```

Review the preview first. It supports `1x2`, `total_2_5`, and `btts`.
Rows marked `unmatched` are not changed. To apply confident win/loss/push
suggestions to the ledger:

```bash
python scripts/settle_bet_ledger.py --apply
```

---

## Open the dashboard

```bash
streamlit run app.py
```

The dashboard shows:

- Recent form table
- Upcoming fixture projections
- Promoted-team review spots
- Value board
- Weekly card
- Backtest summary, after you run the backtest
- Betting ledger tab, after you run the ledger scripts

For the ledger tab, run these as needed before opening or refreshing the
dashboard:

```bash
python scripts/run_bet_ledger.py
python scripts/check_bet_ledger.py
python scripts/settle_bet_ledger.py
python scripts/run_backtest.py
```

The ledger tab also has buttons for the safe report actions:

```text
Run Thursday readiness refresh
Run post-refresh Thursday review
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

The ledger tab also displays `data/outputs/current_odds_completeness.md`,
`data/outputs/current_odds_validation.md`,
`data/outputs/current_odds_validation.csv`, `data/outputs/thursday_best_bets.md`,
`data/outputs/thursday_best_bets.csv`,
`data/outputs/thursday_best_bets_comparison.md`, and
`data/outputs/thursday_best_bets_comparison.csv`,
`data/outputs/thursday_decision_queue.md`, and
`data/outputs/thursday_decision_queue.csv` when they exist.

At the top of the Thursday panel, the dashboard shows a command center card
with Thursday status, odds completion, serious current-odds issues, warnings,
the latest archive pair, count-change risk, top movement reason, and the
recommended next manual action. The detailed readiness row and full reports
remain below the card. An `Open this next` cue points to the validation,
archive, comparison, or decision-queue section that matches that action. When
the decision queue is current, the cue also shows how many plays are in the
relevant review group. Missing, stale, or unreadable queues show a refresh note.

These buttons do not edit `data/manual/bet_ledger.csv`, do not edit
`data/manual/current_odds.csv`, do not apply settlements, do not place bets,
do not force Thursday generation, and do not invent missing odds.

The ledger tab also includes a weekly workflow checklist. It shows whether key
files are `Complete`, `Missing`, or `Needs refresh`, when they were last
modified, and the command to run when something is missing or stale.

---

## Project structure

```text
epl-betting-lab/
├── app.py
├── requirements.txt
├── pyproject.toml
├── README.md
├── data/
│   ├── manual/
│   │   ├── upcoming_fixtures.csv
│   │   ├── current_odds_template.csv
│   │   ├── current_odds_import_template.csv
│   │   ├── odds_import_profiles.json
│   │   ├── bet_ledger_template.csv
│   │   ├── bet_ledger.csv
│   │   └── mock_current_odds.csv
│   ├── raw/
│   ├── processed/
│   └── outputs/
├── scripts/
│   ├── fetch_data.py
│   ├── diagnose_odds_export.py
│   ├── convert_odds_export.py
│   ├── import_current_odds.py
│   ├── run_backtest.py
│   └── generate_weekly_card.py
└── src/epl_betting_lab/
    ├── config.py
    ├── data/
    ├── models/
    ├── strategies/
    ├── backtest/
    └── reports/
```

---

## How the model works right now

The starter model uses a transparent Poisson goals approach:

```text
Home expected goals = league home scoring average × home attack strength × away defensive weakness
Away expected goals = league away scoring average × away attack strength × home defensive weakness
```

From there it estimates:

```text
Home win probability
Draw probability
Away win probability
Over/under 2.5 probability
BTTS yes/no probability
Most likely scorelines
```

Then it compares those probabilities to sportsbook odds.

A play is usually only marked `BETTABLE` when:

```text
model probability - book implied probability >= minimum edge
expected value > 0
odds are not worse than the default max juice threshold
```

---

## Strategy ideas to expand next

Good next modules:

- Corners model
- Shots on target props
- Anytime goal scorer model
- Cards/fouls model
- European hangover spots
- Promoted-team fade tracker
- Closing-line value tracker
- Line movement tracker
- Bankroll ledger
- Twitter/X thread generator for matchweek previews

---

## Team naming note

The starter fixture file uses Football-Data-style names where possible, such as:

```text
Man United
Man City
Nott'm Forest
Tottenham
Newcastle
```

If your fixtures use `Manchester United` but the historical data uses `Man United`, the model will treat them as different teams. Keep names consistent.

---

## Using Codex as the season-long agent

This project is now Codex-ready.

Important files:

```text
AGENTS.md                                  # Rules/instructions Codex should follow
codex/prompts/weekly_model_update.md       # Weekly update prompt
codex/prompts/add_corners_model.md         # Future corners-model prompt
codex/prompts/add_shots_sot_model.md       # Future shots/SOT prompt
docs/CODEX_SETUP_BEGINNER.md               # Beginner Codex setup guide
scripts/agent_weekly_brief.py              # Creates an in-season brief for the agent
```

After each matchweek, once current-season data is available, run:

```bash
python scripts/fetch_data.py --seasons 2122 2223 2324 2425 2526 2627
python scripts/run_backtest.py
python scripts/agent_weekly_brief.py --current-season 2627 --recent-matches 6
```

This creates:

```text
data/outputs/agent_weekly_brief.md
data/outputs/agent_team_recent_form.csv
data/outputs/agent_team_market_profile.csv
```

Give Codex this weekly instruction:

```text
Read AGENTS.md. Use data/outputs/agent_weekly_brief.md, the latest backtest outputs, and the current codebase to decide whether the model needs a small, explainable improvement. Do not fabricate odds. Respect the max-juice rule around -160. Run tests before summarizing changes.
```

For full beginner instructions, open:

```text
docs/CODEX_SETUP_BEGINNER.md
```
