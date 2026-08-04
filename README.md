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

### Validate provider staging inputs

Future odds/fixtures providers should write their prepared standard CSVs to:

```text
data/staging/current_odds_staging.csv
data/staging/upcoming_fixtures_staging.csv
data/staging/staging_provenance.json
```

The first controlled provider adapter prepares that bundle from two local
source files. Copy the source templates, enter only reviewed real data, and run
the Terminal-only adapter:

```bash
cp data/staging/source_current_odds_template.csv data/staging/source_current_odds.csv
cp data/staging/source_upcoming_fixtures_template.csv data/staging/source_upcoming_fixtures.csv
python scripts/run_manual_staging_provider.py
```

The adapter records source/staging SHA-256 checksums and provenance but does not
judge whether the odds or fixtures are valid. It stops rather than replacing an
existing staging bundle. After reviewing the old bundle, intentional replacement
requires `python scripts/run_manual_staging_provider.py --overwrite-staging`.
There is no dashboard provider-run button.

The shared provider registry also includes an offline-first The Odds API
skeleton. Its default command is a no-network dry-run:

```bash
python scripts/run_provider_staging.py --provider manual --dry-run
python scripts/run_provider_staging.py --provider odds_api --dry-run
```

Live odds API mode is Terminal-only and explicit. Put the key in the
`EPL_ODDS_API_KEY` environment variable (or a future GitHub Secret), never in a
CSV, JSON file, command argument, or commit:

```bash
export EPL_ODDS_API_KEY='your-secret-key'
python scripts/run_provider_staging.py --provider odds_api --live
```

The provider copies only returned prices. It writes normalized source/staging
CSVs, `staging_provenance.json`, raw JSON evidence under `data/staging/raw/`,
and `data/outputs/odds_api_staging_provider_report.*`. The first skeleton asks
the featured endpoint for 1X2 and totals. If BTTS or another required row is not
returned, it stays missing and staging completeness blocks the bundle rather
than guessing a price. Existing staging files still require the explicit
`--overwrite-staging` flag.

The default provider policy remains manual-only. Add `the_odds_api` to the
allowlist only after reviewing real provider output, team names, market mapping,
raw evidence, and repeated validation results. A completed provider run is not
approval for handoff.

Next, review `data/manual/staging_provider_policy.json` and run the independent
eligibility gate:

```bash
python scripts/validate_staging_inputs.py
```

The validator restricts inputs to safe CSV paths inside `data/staging`, records
SHA-256 checksums, checks required columns and today/future dates, validates
teams/markets/selections and fixture matching, rejects duplicate odds rows,
enforces provider/receipt-age/Thursday-cutoff policy, and reuses the existing
odds validation, 100% completeness, freshness, and GitHub runner handoff gates.
It also re-hashes both provider source files and both staging files, compares
them with `staging_provenance.json`, and confirms each source/staging pair still
matches byte-for-byte. A missing file, unreadable file, absent checksum, or
checksum mismatch blocks `Ready for handoff`. Missing provenance is blocked by
default through `allow_missing_provenance: false` in the provider policy. The
provider's timezone-aware `generated_at` must also be present, not in the
future, and no older than `max_provider_run_age_hours` (12 hours by default).
This is separate from the age of the validation receipt itself.
It writes:

```text
data/outputs/staging_input_validation.csv
data/outputs/staging_input_validation.md
data/outputs/staging_input_validation.json
```

Only `Ready for handoff` means the files passed all blocking gates. Validation
does not copy staging files into `data/manual/`, generate a card, or enable
cron. The `Odds Import` dashboard section has the same read-only button and
report display, plus a read-only view of the latest odds API provider report.
The dashboard never runs a live provider. See
[docs/STAGING_INPUTS.md](docs/STAGING_INPUTS.md) for the full workflow.

The JSON output is the staging receipt used by the manual GitHub Action. It
records the exact staging paths, SHA-256 checksums, row counts, freshness,
validation, and completeness state. After a `Ready for handoff` result, commit
the two unchanged staging CSVs and that JSON receipt to the same short-lived
weekly branch. If either CSV changes afterward, the Action blocks the card
until you validate again and use the new receipt.

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

To create a conservative draft for an unmatched export, run:

```bash
python scripts/suggest_odds_export_profile.py --source data/manual/sportsbook_export.csv --profile-name example_book
```

The suggestion uses only known column aliases. Exact matches receive high
confidence, compact spelling matches receive medium confidence, and ambiguous
or unknown required fields remain `REVIEW_NEEDED`. It writes:

```text
data/outputs/odds_export_profile_suggestion.json
data/outputs/odds_export_profile_suggestion.md
```

These are review-only drafts. The helper never edits
`data/manual/odds_import_profiles.json`, either odds CSV, or the ledger. Review
the confidence notes and unmapped columns, then validate the draft in memory:

```bash
python scripts/validate_odds_export_profile_suggestion.py
```

The validator uses the source path stored in the suggestion. Override it when
needed with `--source data/manual/sportsbook_export.csv`. It checks required
outputs, unresolved mappings, missing source columns, odds values,
market/selection normalization, and duplicate converted rows. It writes:

```text
data/outputs/odds_export_profile_suggestion_validation.csv
data/outputs/odds_export_profile_suggestion_validation.md
```

The verdict is `Ready for manual profile review`, `Needs edits before profile
review`, or `Invalid draft suggestion`. Even a ready verdict still requires
manual review. The validator never creates `current_odds_import.csv` or edits
the profile registry or odds files.

Before installing a reviewed profile, preview the exact registry change:

```bash
python scripts/preview_install_odds_profile.py
```

Preview mode shows whether the profile name already exists, profile counts
before/after, the exact JSON block, validation verdict, and safety warnings. It
writes:

```text
data/outputs/odds_profile_install_preview.json
data/outputs/odds_profile_install_preview.md
```

Preview never edits the registry. Installation is Terminal-only and requires:

```bash
python scripts/preview_install_odds_profile.py --apply
```

A ready, new profile needs no extra flag beyond `--apply`. Existing names need
`--replace-existing`; Needs-edits or `REVIEW_NEEDED` drafts need
`--allow-needs-edits`; missing validation needs `--allow-missing-validation`.
An invalid draft verdict is always refused. Successful installation creates a
timestamped backup under `data/manual/backups/` and writes
`odds_profile_install_audit.csv` plus `odds_profile_install_audit.md` in
`data/outputs/`.

The dashboard buttons `Suggest odds export profile`, `Validate suggested odds
profile`, and `Preview odds profile install` are report-only. There is no
dashboard apply button.

After a Terminal installation, verify the installed profile against the export:

```bash
python scripts/verify_installed_odds_profile.py --profile example_book --source data/manual/sportsbook_export.csv
```

Verification loads the installed registry entry and converts the source only
in memory. It checks required mappings and values, American odds,
market/selection normalization, duplicates, and sample rows. It writes:

```text
data/outputs/odds_profile_post_install_verification.csv
data/outputs/odds_profile_post_install_verification.md
```

The dashboard button `Verify installed odds profile` runs this read-only check.
It never creates an import file or edits odds.

If verification exposes a problem, preview a registry rollback using the
backup path recorded by installation:

```bash
python scripts/rollback_odds_profile_registry.py --backup-path data/manual/backups/BACKUP.json
```

The rollback preview compares profile counts and lists names that would be
added, removed, or changed. It does not modify the registry. To restore the
selected backup from Terminal:

```bash
python scripts/rollback_odds_profile_registry.py --backup-path data/manual/backups/BACKUP.json --apply
```

Apply first backs up the current registry, then restores the selected backup
and writes `odds_profile_rollback_audit.csv` plus its markdown report in
`data/outputs/`. An equivalent backup produces no changes. The dashboard can
display the latest rollback preview but has no rollback apply button.

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

Or open the dashboard. Use `Odds Import` for export/import previews and
`Thursday Card` for completeness, validation, and best-bets generation. The
dashboard can preview imports and missing odds rows, but it does not apply
imports or maintenance, overwrite an existing odds file, edit odds, or force
generation.

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

For one Terminal command that creates the full safe Thursday report package,
run:

```bash
python scripts/run_scheduled_thursday_workflow.py
```

The command checks Home/data freshness, validates current odds, checks odds
completeness, generates and archives the Thursday card through the existing
validation gate, compares the latest two archives when available, builds the
decision queue when comparison succeeds, and refreshes tier performance. It
never uses `--force`. Missing prerequisites are skipped or blocked with a
plain-English explanation.

Every run writes:

```text
data/outputs/scheduled_thursday_workflow_summary.md
data/outputs/scheduled_thursday_workflow_summary.json
```

Possible overall statuses are `Ready`, `Warnings only`, `Blocked`, `Partial`,
and `Failed`. `Blocked` or `Failed` returns a non-zero Terminal exit code so a
future GitHub Actions job can alert you. This script is safe to schedule later:
it only generates reports and archives. It does not edit manual odds/import
files, the ledger, or profile settings; apply imports, settlements, archives,
rollbacks, or profile installs; fabricate odds; or place bets.
The latest markdown summary is also available as a read-only expander under
`Tools / Diagnostics`; the dashboard does not run the scheduled command.

### Run the Thursday package manually in GitHub Actions

The repository includes a manual-only workflow at
`.github/workflows/manual-thursday-workflow.yml`.

The safe handoff uses a reviewed `Ready for handoff` staging receipt. Before
starting the Action:

1. Put real provider prices in `data/staging/source_current_odds.csv` and the
   matching slate in `data/staging/source_upcoming_fixtures.csv`.
2. Run `python scripts/run_manual_staging_provider.py` to create the staging
   bundle and provenance without touching manual production files.
3. Review `data/manual/staging_provider_policy.json`. The default policy allows
   named, reviewed sources, limits receipts to 12 hours, and requires creation
   by 10:00 AM `America/New_York` on Thursday.
4. Run `python scripts/validate_staging_inputs.py` near the Thursday run.
5. Confirm the verdict is `Ready for handoff` and review its warnings.
6. Commit both unchanged staging CSVs, the provenance declaration, the provider
   policy, plus
   `data/outputs/staging_input_validation.json` to one short-lived weekly
   branch, then push it.

Then:

1. Open the repository on GitHub and select **Actions**.
2. Select **Manual Thursday Workflow**.
3. Select **Run workflow** and choose the weekly branch containing the prepared
   files.
4. Confirm the repository-relative odds, fixtures, staging receipt, and provider
   policy paths. Optional SHA-256 fields provide an additional identity check.
5. Open the finished run and read its job summary.
6. Download `scheduled-thursday-reports-RUN_NUMBER-RUN_ATTEMPT` from the
   **Artifacts** section.

The Action also creates a read-only verification receipt inside the artifact:

```text
data/outputs/github_manual_thursday_run_verification.csv
data/outputs/github_manual_thursday_run_verification.md
```

After downloading an artifact into the project's `data/outputs/` folder, you
can regenerate the same check locally with:

```bash
python scripts/verify_github_manual_thursday_run.py
```

The report cross-checks the standalone input handoff against the handoff copy
inside the scheduled summary, then checks the Git ref/SHA, input paths and
checksums, freshness, validation, completeness, card permission, workflow
status, and claimed output files. Read it under `Tools / Diagnostics` in the
dashboard. A ready or safely blocked run is verified; missing or inconsistent
evidence is not trusted.

The artifact contains the available `data/outputs/` reports and is retained for
14 days. A missing or blocked odds setup still uploads the validation and
scheduled-workflow summaries when possible. `Blocked` is shown as a warning
and is allowed to finish successfully so you can download the explanation.
Compile failures, test failures, runtime failures, unexpected exit codes,
untrusted/incomplete verification, or artifact-upload failures make the Action
fail.

The runner accepts only regular staging CSVs, a regular JSON receipt, and a
valid provider policy inside the checked-out repository. It records the
selected Git ref and commit, exact paths, receipt timestamp and age, provider
name/type, source provenance, calculated SHA-256 checksums, policy checksum,
cutoff status, date freshness, validation results, completeness, and whether
card generation was allowed. A missing or non-Ready receipt, changed staging
file or provider policy, unapproved/unknown provider, receipt older than the
policy limit, receipt created after the Thursday cutoff, path mismatch, past
odds/fixture row, malformed date, serious validation issue, checksum mismatch,
or completeness below 100% blocks the card without `--force`.

Read [docs/GITHUB_RUNNER_INPUT_HANDOFF.md](docs/GITHUB_RUNNER_INPUT_HANDOFF.md)
for copy/paste setup, optional checksum commands, fail-closed rules, and the
fields shown in the Action receipt. Do not commit credentials or sportsbook
account information.

There is deliberately no Thursday cron trigger. A fresh GitHub runner does not
automatically source permitted real sportsbook odds. This repository-file
handoff still needs a person to prepare and review each weekly input. Before
automatic scheduling, connect a trusted automated odds/fixture source, secure
its credentials, prove that it refreshes staging before the configured cutoff,
verify provider mappings over repeated runs, and assign ownership for blocked
runs and warnings. The Action never guesses missing prices and never uses
`--force`.

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

Use the sidebar to move between seven focused sections:

- `Home / Command Center`: Thursday status, recommended next action, odds
  completion, validation counts, archive movement, ledger units/ROI, and
  pending bets.
- `Thursday Card`: readiness refresh, completeness, validation, and the latest
  best-bets report.
- `Odds Import`: diagnose, suggest, validate, install-preview, verify,
  rollback-preview, conversion-preview, import-preview, and audit history in
  step-by-step order.
- `Performance Reports`: tier performance, backtest summary, CLV, and ledger
  profit breakdowns.
- `Bet Ledger`: record, pending bets, health check, settlement preview, and
  weekly ledger commands.
- `Archives & Comparisons`: archived cards, archive pair, comparison report,
  movement summary, and decision queue.
- `Tools / Diagnostics`: model projections, recent form, promoted-team spots,
  value board, weekly card, maintenance reports, and file status.

Run these as needed before opening or refreshing the ledger and performance
sections:

```bash
python scripts/run_bet_ledger.py
python scripts/check_bet_ledger.py
python scripts/settle_bet_ledger.py
python scripts/run_backtest.py
```

The three most important report buttons are visible on `Home / Command Center`:

```text
Run Thursday readiness refresh
Run post-refresh Thursday review
Generate tier performance report
```

The related sections keep the individual safe actions available:

```text
Run bet ledger report
Run ledger health check
Run settlement preview
Create current odds template
Preview current odds import
Preview current odds maintenance
Report stale current odds
Preview stale odds archive
Check stale odds archive confirmation
Preview stale odds rollback
Refresh backup list report
Check odds entry completeness
Validate current odds
Generate Thursday best-bets report
Compare latest Thursday reports
Generate Thursday decision queue
Run backtest reports
Refresh dashboard data
```

The Home page shows a command center card
with Thursday status, odds completion, serious current-odds issues, warnings,
the latest archive pair, count-change risk, top movement reason, and the
recommended next manual action. It also shows ledger units, ROI, record, and
pending bets when the ledger is available. The `Open this next` cue includes a
safe button that switches directly to the matching portal section without
running a report or editing data. When
the decision queue is current, the cue also shows how many plays are in the
relevant review group. Missing, stale, or unreadable queues show a refresh note.

The same Home card now shows the latest stale-odds archive confirmation status.
A matching receipt shows `Ready` with its confirmation ID. Changed odds show
`Odds changed after preview` and tell you to preview again. A missing receipt
stays low priority when there are no stale rows, but becomes a warning when
stale odds need attention. The status is read-only; archive apply remains a
Terminal-only action documented under `Tools / Diagnostics`. When stale rows
exist and the receipt is missing, invalid, changed, or tied to an unreadable
odds file, Home's `Open this next` button takes you to the stale-odds preview
and confirmation panel in `Tools / Diagnostics`. Navigation only changes the
visible portal section; it does not run either check or edit a file.

Home also includes a compact `Data freshness` area. It checks historical
results, fixtures, current odds, Thursday reports and archives, comparison and
decision reports, tier performance, and the ledger summary. The main view shows
status counts and the most important next refresh step; open `Data freshness
details` for file paths, source paths, local timestamps, notes, and commands.
The fixture check also reads the `date` column: at least one match today or in
the future keeps fixtures fresh, while an all-past slate needs refresh. The
details include the fixture date range and past/future counts. This check is
read-only. Current odds use the same local-date rule: all-past rows need a
refresh, malformed dates cannot be checked, and a mix of past and future rows
stays usable with a warning about the old rows. Odds date ranges and row counts
appear in the details expander. The expander also repeats the stale-odds archive
confirmation status and confirmation ID when available.

To see exactly which odds rows belong to past matches, run:

```bash
python scripts/report_stale_current_odds.py
```

This creates `data/outputs/stale_current_odds_report.csv` and
`data/outputs/stale_current_odds_report.md`. Each source row is marked
`Stale`, `Current`, `Invalid date`, or `Blank date`, with a suggested manual
action. The report is read-only: it never removes, archives, or changes odds.
The same check is available as `Report stale current odds` in `Tools /
Diagnostics`.

To safely preview removing those stale rows, run:

```bash
python scripts/archive_stale_current_odds.py
```

The default command only writes
`data/outputs/stale_current_odds_archive_preview.csv` and
`data/outputs/stale_current_odds_archive_preview.md`, plus a small
`data/outputs/stale_current_odds_archive_preview.json` confirmation receipt.
It shows stale rows that would be archived/removed, current rows that would
stay, and blank or invalid dates that stay for manual fixing. The receipt ties
the confirmation ID to the odds file path, file checksum, and all three row
counts. The dashboard offers the same read-only `Preview stale odds archive`
action under `Tools / Diagnostics`.

To check whether that receipt still matches the latest odds file, run:

```bash
python scripts/check_stale_current_odds_archive_confirmation.py
```

This creates
`data/outputs/stale_current_odds_archive_confirmation_status.csv` and
`data/outputs/stale_current_odds_archive_confirmation_status.md`. Status is
`Ready` only when the receipt is valid and its path, SHA-256 checksum, stale
row count, current row count, and manual-review row count all still match.
Other statuses explain whether the receipt is missing or invalid, odds changed
after preview, or `current_odds.csv` is missing or unreadable. A date change
that changes stale-row classification also invalidates the old receipt.

`Tools / Diagnostics` shows the same result in a compact read-only panel and
offers `Check stale odds archive confirmation` to regenerate the two status
files. It never applies the archive or edits an odds file.

After reviewing the preview, copy its exact Terminal-only apply command:

```bash
python scripts/archive_stale_current_odds.py \
  --apply \
  --confirm-id CONFIRM_ID_FROM_PREVIEW
```

Before changing anything, apply verifies that the confirmation ID, canonical
odds path, current file checksum, stale-row count, current-row count, and
manual-review-row count still match the preview. If the file changed, apply
stops and asks you to preview again. A successful apply first backs up the full
odds file under `data/manual/backups/`, then writes stale rows under
`data/manual/archive/current_odds_stale/`, verifies the archive, and keeps
today/future plus date-fix rows in `current_odds.csv`. It also writes
`stale_current_odds_archive_audit.csv` and `.md` under `data/outputs/`, including
the preview/apply checksums, counts, confirmation status, and gate result.

For a rare manually inspected emergency, Terminal has
`--allow-unconfirmed-archive`. This bypass is prominently recorded in the
report and audit. There is no dashboard apply or override button.

If you need to undo an applied stale-odds archive, first choose the matching
pre-archive backup and preview the rollback:

```bash
python scripts/rollback_stale_current_odds_archive.py \
  --backup-path data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv
```

Preview writes `stale_current_odds_archive_rollback_preview.csv`, `.md`, and
`.json` under `data/outputs/`. It shows the current and backup row counts, rows
that would return, rows that would be replaced, and the selected backup's
checksum safety status. The JSON file is a small preview receipt containing a
confirmation ID tied to the selected paths and both file checksums. It does not
edit either CSV. The `Preview stale odds rollback` button under `Tools /
Diagnostics` runs this same read-only check after you enter a backup path.

After reviewing the report, copy its exact Terminal-only apply command. It will
look like this:

```bash
python scripts/rollback_stale_current_odds_archive.py \
  --backup-path data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv \
  --apply \
  --confirm-id CONFIRM_ID_FROM_PREVIEW
```

Apply first checks that the confirmation ID, selected backup path,
`current_odds.csv` checksum, and selected backup checksum still match the
reviewed preview. A missing or invalid ID, changed file, changed path, or
malformed preview receipt stops before a recovery backup is created. When the
confirmation matches, apply creates another timestamped backup ending in
`current_odds_pre_stale_archive_rollback.csv`, restores the selected backup
atomically, and writes
`stale_current_odds_archive_rollback_audit.csv` and `.md` under
`data/outputs/`. Future rollback rows record the selected backup checksum and
the newly created `recovery_backup_checksum_sha256`. Missing, empty,
malformed, non-CSV, or same-file backups are blocked. There is no dashboard
rollback apply button.

Rollback apply also uses a checksum safety gate:

- `Verified`: apply is allowed because the backup matches its creator audit.
- `Not available`: apply is allowed with a warning because older or unmatched
  audit history cannot confirm the backup's original checksum.
- `Mismatch`: apply is blocked before any recovery backup or odds replacement.

After manually inspecting a known mismatch, the only override is explicit and
Terminal-only:

```bash
python scripts/rollback_stale_current_odds_archive.py \
  --backup-path data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv \
  --apply \
  --confirm-id CONFIRM_ID_FROM_PREVIEW \
  --allow-checksum-mismatch
```

The console, preview report, and rollback audit clearly record `Override used`
and warn that the backup may have changed after creation. Preview and audit
outputs include `checksum_status`, `recorded_checksum_sha256`,
`current_checksum_sha256`, `checksum_gate_result`, and `checksum_gate_note`.
The dashboard has no apply or checksum-override button.

If a preview cannot be matched after manual inspection, the separate
Terminal-only confirmation override is:

```bash
python scripts/rollback_stale_current_odds_archive.py \
  --backup-path data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv \
  --apply \
  --allow-unconfirmed-rollback
```

This is not the normal workflow. The console, preview report, and audit warn
that apply did not match a reviewed preview. Confirmation outputs record
`confirm_id`, `confirm_id_status`, both preview/apply checksums,
`confirmation_gate_result`, and `confirmation_gate_note`. If the backup also
has a known checksum mismatch, both explicit Terminal-only overrides are
required. The dashboard remains preview-only and offers neither override.

To list available stale-odds backups without searching the backup folder
manually, run:

```bash
python scripts/list_stale_current_odds_backups.py
```

This scans only these established backup types:

```text
data/manual/backups/*_current_odds_pre_stale_archive.csv
data/manual/backups/*_current_odds_pre_stale_archive_rollback.csv
```

It writes `data/outputs/stale_current_odds_backup_list.csv` and `.md`. For
each file, the report shows its path, parsed filename timestamp, modified time,
row count, odds date range, stale/current/date-fix counts, and whether it is
readable and valid for rollback preview. Unreadable files, malformed CSVs, and
malformed filename timestamps stay visible with clear warnings.

When audit history exists, the same report links each backup to the operation
that created it. Archive backups match the `backup_path` recorded in
`stale_current_odds_archive_audit.csv`; rollback recovery backups match the
`pre_rollback_backup_path` in
`stale_current_odds_archive_rollback_audit.csv`. The list then shows
`archive_apply`, `rollback_apply`, or `unknown`, plus the audit timestamp,
operation status, archive path, archived/restored/replaced row counts, audit
file paths, and a plain-English note. Missing, unreadable, or malformed audit
history never hides a backup and never stops the list from running.

The picker also calculates each backup's current SHA-256 checksum. It compares
that value with the explicit checksum in newer audits, or the equivalent
source checksum in older audits when available:

- `Verified`: the backup still matches the recorded checksum byte for byte.
- `Mismatch`: the file changed after creation. Do not trust it for rollback
  unless you inspect it manually.
- `Not available`: no usable recorded checksum exists, or the file could not
  be checksummed. Older backups commonly have this status.

The CSV and markdown include `recorded_checksum_sha256`,
`current_checksum_sha256`, `checksum_status`, and `checksum_note`. Running the
picker only reads backup and audit files; it never modifies them.

In `Tools / Diagnostics`, open `Available stale odds backups`. Readable backups
can be selected directly and their full path is shown for copying. The selected
path feeds only `Preview stale odds rollback`; it never applies a rollback or
edits an odds file. A manual path remains available when a valid backup lives
outside the standard folder. The dashboard uses a compact provenance view and
shows checksum status beside each backup. A selected mismatch displays a clear
warning beneath the path, but the dashboard still has no rollback apply action.

Portal sections are bookmarkable with the `section` query parameter:

```text
?section=home
?section=thursday-card
?section=odds-import
?section=performance
?section=bet-ledger
?section=archives
?section=tools
```

The sidebar and Home `Open ...` button keep this value synchronized. A missing,
unknown, repeated, or malformed section value safely opens Home. The parameter
only controls the visible portal section and never runs a report.
Every non-Home section also has a compact `Back to Home` button near the top;
it returns to Home and updates the URL to `?section=home` without running a report.
Each page also shows a compact display-only breadcrumb, such as
`Home > Odds Import`, so you can quickly confirm where you are in the portal.

These buttons do not edit `data/manual/bet_ledger.csv`, do not edit
`data/manual/current_odds.csv`, do not apply settlements, do not place bets,
do not force Thursday generation, and do not invent missing odds.

The weekly workflow checklist is available from the Home page and `Tools /
Diagnostics`. It shows whether key files are `Complete`, `Missing`, or `Needs
refresh`, when they were last modified, and the command to run when something
is missing or stale.

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
│   ├── suggest_odds_export_profile.py
│   ├── validate_odds_export_profile_suggestion.py
│   ├── preview_install_odds_profile.py
│   ├── verify_installed_odds_profile.py
│   ├── rollback_odds_profile_registry.py
│   ├── convert_odds_export.py
│   ├── import_current_odds.py
│   ├── run_backtest.py
│   └── generate_weekly_card.py
└── src/epl_betting_lab/
    ├── config.py
    ├── dashboard_portal.py
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
