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

### Provider staging files

A future permitted odds/fixtures provider should write standard CSVs to a
holding area first, not directly into your manual files:

```text
data/staging/current_odds_staging.csv
data/staging/upcoming_fixtures_staging.csv
data/staging/staging_provenance.json
```

For the first controlled provider, copy the source templates and fill them with
real, reviewed data:

```bash
cp data/staging/source_current_odds_template.csv data/staging/source_current_odds.csv
cp data/staging/source_upcoming_fixtures_template.csv data/staging/source_upcoming_fixtures.csv
python scripts/run_manual_staging_provider.py
```

The command writes only the three staging outputs and provider run reports. It
records who supplied the data and SHA-256 checksums, but never guesses odds.
If staging outputs already exist, it stops. Use `--overwrite-staging` only
after reviewing them and deciding to replace the whole bundle. Provider writes
remain Terminal-only.

You can also preview the shared provider framework without calling an API or
writing staging files:

```bash
python scripts/run_provider_staging.py --provider manual --dry-run
python scripts/run_provider_staging.py --provider odds_api --dry-run
```

The `odds_api` option is the first real-provider skeleton. It is offline by
default. Live mode is an intentional Terminal step and reads its key only from
the environment:

```bash
export EPL_ODDS_API_KEY='your-secret-key'
python scripts/run_provider_staging.py --provider odds_api --live
```

Never paste the key into a CSV, JSON file, notes field, command argument, or
Git commit. The provider report shows only whether a key was configured. A live
run archives the raw response under `data/staging/raw/`, records checksums, and
prepares normalized source/staging CSVs. It never invents a missing price.

The first skeleton may return only 1X2 and totals from the featured endpoint.
If BTTS or another required row is absent, that is expected to block staging
completeness. Do not fill the gap with a guessed price. The default policy also
keeps `the_odds_api` disallowed until you have reviewed real output and
deliberately approved the provider name.

Before making any allowlist decision, run a shadow verification. Start with the
safe no-network mode:

```bash
python scripts/run_provider_shadow_verification.py --provider odds_api --dry-run
```

Seeing `Blocked` in the dry-run report is expected. The command checked its safe
setup, but it deliberately did not fetch evidence that could prove readiness.

When you intentionally want to test real provider output and have set
`EPL_ODDS_API_KEY` in your environment, run:

```bash
python scripts/run_provider_shadow_verification.py --provider odds_api --live
```

Read `data/outputs/provider_shadow_verification.md`. It explains team-name,
fixture, bookmaker, market, BTTS, completeness, checksum, provider-age, policy,
and safe quota results. A `Shadow ready for review` verdict is still not
permission to generate picks automatically. The report does not edit the
provider policy or protected files, and live mode is not available in the
dashboard. Use GitHub Secrets rather than committed files if credentials are
added to a future manual GitHub workflow.

Each shadow report is kept as a dated snapshot in
`data/outputs/archive/provider_shadow_runs/`. Run the provider several times on
different slates or refreshes, then compare the newest two snapshots:

```bash
python scripts/compare_provider_shadow_runs.py --provider odds_api
```

Open `data/outputs/provider_shadow_run_comparison.md`, or use the read-only
history area on the Odds Import dashboard. Check that team and fixture mapping,
bookmakers, 1X2/totals/BTTS coverage, completeness, checksum proof, staging
verdicts, and quota behavior remain understandable. Two stable runs still get
`Needs more shadow runs`; three or more consistent runs can become
`Stable enough for review`, which still requires a person to decide what comes
next. The tool never edits the provider allowlist or enables cron.

Once you have at least three completed live shadow runs, generate the
read-only provider acceptance checklist:

```bash
python scripts/generate_provider_acceptance_checklist.py --provider odds_api
```

Read `data/outputs/provider_acceptance_checklist.md`, or use **Generate provider
acceptance checklist** under Odds Import. The default checklist reviews the
latest five live runs and requires three completed runs. Dry runs do not count.
It checks mappings, fixtures, books, market coverage, staging results, age,
checksums, quota headers, policy state, and blockers. `Ready for human allowlist
review` does not add the provider to the policy. A person must still inspect the
evidence and make any policy edit separately. Cron remains disabled.

When the checklist says `Ready for human allowlist review`, preview a human
decision receipt from Terminal:

```bash
python scripts/create_provider_human_acceptance_receipt.py \
  --provider odds_api \
  --reviewer-name "Cooper Ross" \
  --decision approved_for_allowlist_pr \
  --notes "Reviewed the checklist and its shadow archives."
```

Nothing is written during preview. Read the evidence paths, checksums, verdict,
and warnings in Terminal. If they match what you reviewed, rerun the exact
command printed by the script; it adds `--write-receipt`. The receipt records the
checklist, reviewed archive bundles, latest matching comparison when available,
provider policy when available, reviewer, decision, and notes. It writes JSON,
Markdown, and CSV files and a dated archive. The Odds Import dashboard can show
the latest receipt, but it cannot create or approve one.

Choices are `approved_for_allowlist_pr`, `rejected`, or
`needs_more_shadow_runs`. Approval is blocked when the checklist is not ready.
There is a clearly recorded Terminal-only override for exceptional documentation,
but using it still does not allowlist the provider. Any policy edit needs a
separate reviewed PR, and cron remains disabled.

Before opening that separate PR, verify that none of the reviewed files changed:

```bash
python scripts/verify_provider_human_acceptance_receipt.py --provider odds_api
```

Read `data/outputs/provider_human_acceptance_receipt_verification.md`, or click
**Verify latest human acceptance receipt** under Odds Import. The checker reads
the latest receipt by default and recalculates every bound evidence checksum. A
checksum mismatch means the file no longer matches what the reviewer approved;
regenerate the checklist and receipt after reviewing the current evidence. The
best verdict, `Verified for allowlist PR review`, still only supports a later
human-reviewed policy PR. It does not allowlist the provider or enable cron.

Next, preview that possible policy PR without changing the policy:

```bash
python scripts/preview_provider_allowlist_pr.py --provider odds_api
```

Read `data/outputs/provider_allowlist_pr_preview.md`, or click **Preview provider
allowlist PR** under Odds Import. A Ready preview shows the exact current and
proposed JSON, the diff, reviewed markets and limitations, receipt evidence,
and suggested PR title/description. A blocked preview tells you which receipt,
verification, or policy evidence needs attention. The preview cannot edit the
policy or allowlist anything. A person must still open and review a separate
policy PR, and cron remains disabled.

After the separate policy PR changes `staging_provider_policy.json`, compare it
with the reviewed preview:

```bash
python scripts/check_provider_allowlist_pr_conformance.py --provider odds_api
```

You can also click **Check provider allowlist PR conformance** under Odds Import.
Read `data/outputs/provider_allowlist_pr_conformance.md`. `Conforms to preview`
means the full policy matches the previewed result exactly. Missing fields,
changed values, extra provider-policy edits, changed verification evidence, or
new cron/automation settings fail closed. Extra policy edits are risky because
they were not covered by the human-reviewed preview. This check only reviews
files; it does not edit policy, allowlist the provider, or enable cron.

After the Ready preview, gather the exact evidence into one checksum-bound
package. Before the policy PR, conformance is `Not applicable`; during PR
review, run conformance and build the bundle again:

```bash
python scripts/build_provider_allowlist_evidence_bundle.py --provider odds_api
```

You can also click **Build provider allowlist evidence bundle** under Odds
Import. Read `data/outputs/provider_allowlist_evidence_bundle.md` first. A ready
bundle includes the preview, human receipt and verification, acceptance
checklist, matching shadow comparison, every reviewed shadow archive file,
provider policy, and conformance report when one exists. Each file is re-hashed,
and the combined paths and checksums produce the bundle ID. Missing, changed, or
non-ready evidence blocks the ready verdict. Dated copies are kept under
`data/outputs/archive/provider_allowlist_evidence_bundles/` for PR review. This
button only writes reports; it cannot change policy or enable cron.

Right before a provider-policy PR is approved, verify that its archived review
bundle and every evidence file are still unchanged:

```bash
python scripts/verify_provider_allowlist_evidence_bundle.py --provider odds_api
```

You can also click **Verify provider allowlist evidence bundle** under Odds
Import. Read
`data/outputs/provider_allowlist_evidence_bundle_verification.md`. A verdict of
`Evidence bundle verified for PR approval review` confirms that all bound
checksums and the deterministic bundle ID still match. A missing file or
checksum mismatch means the reviewed evidence changed, so stop and rebuild the
bundle after reviewing the new evidence. The verifier only writes its JSON,
Markdown, and CSV reports. It does not apply the policy change, allowlist the
provider, or enable cron. It can later become a PR-only CI check after that
separate workflow is reviewed.

Provider-policy PRs are also checked automatically by the PR-only **Provider
Policy PR Gate** workflow. Before opening that PR, run:

```bash
python scripts/check_provider_policy_pr_gate.py --provider odds_api
```

If `staging_provider_policy.json` did not change, `Not applicable` is a normal
passing result. If it did change, commit the Ready preview, verified receipt
report, conforming policy report, rebuilt evidence bundle/archive, and verified
bundle report reviewed for that exact policy. The Action reruns the read-only
checks and blocks missing, stale, mismatched, nonconforming, or automation-
enabling evidence. Reports are available in `provider_policy_pr_gate.md` and
the GitHub Actions artifact. The **Check provider policy PR gate** button under
Odds Import only regenerates this local report. Neither the button nor Action
edits policy, uses secrets, runs a provider, allowlists anything, or enables
cron.

For a real policy change, look for receipt binding **Bound** and a Gate receipt
ID in the report or Action summary. That ID is a fingerprint of the exact PR
base/head commits, changed files and contents, before/after policy, evidence
reports, and final verdict. The generation time is not included, so an
unchanged rerun keeps the same ID. A different file, policy, evidence report,
or compared commit changes the ID. **Missing Git context**, **Missing
changed-file digest**, **Missing evidence digest**, or **Digest mismatch**
blocks a policy-changing PR. The Odds Import page shows the latest ID,
base/head SHAs, changed-files digest, and binding status without changing any
file. This proves what was checked; it still does not apply the policy,
allowlist a provider, or enable cron.

Before approving that policy PR, verify the saved gate receipt one more time:

```bash
python scripts/verify_provider_policy_pr_gate_receipt.py --provider odds_api
```

Read
`data/outputs/provider_policy_pr_gate_receipt_verification.md`, or click
**Verify provider policy PR gate receipt** under Odds Import. The checker uses
the recorded PR base/head commits to rebuild the changed-file list and hashes,
then re-hashes the policy and every evidence report before recalculating the
receipt ID. `Gate receipt verified for PR approval` means those exact inputs
still match. If Git context is missing, a file changed, evidence changed, the
policy changed, or the original gate did not pass, stop and rerun/review the PR
gate. `--diagnostic` is for troubleshooting only and cannot approve a receipt.
The Action and dashboard remain read-only; neither can apply policy, allowlist a
provider, or enable cron.

Then validate the generated staging files:

```bash
python scripts/validate_staging_inputs.py
```

Read `data/outputs/staging_input_validation.md`. `Ready for handoff` means the
staging paths, schema, dates, odds, fixture matching, provider allowlist,
receipt age/cutoff, validation, completeness, and existing GitHub handoff gate
passed. It also means both source files and both staging files still match the
checksums written by the provider, and each source/staging pair matches. A
missing, unreadable, or changed file blocks the receipt. The provider
`generated_at` must be timezone-aware, cannot be in the future, and must be no
older than the policy's provider-run limit. `Needs fixes`,
`Blocked`, or `Missing staging inputs` means the files are not eligible. The
command never copies the files into `data/manual/` or generates picks.

The policy is `data/manual/staging_provider_policy.json`. By default, receipts
must be no more than 12 hours old and generated by 10:00 AM New York time on
Thursday. Provider runs must also be no more than 12 hours old. Unknown
providers are blocked. If you change the policy after validation, validate
again so the receipt records the new policy checksum.
Missing provenance is also blocked by default; the
`allow_missing_provenance` exception must be deliberately enabled in policy and
will remain visible as a warning.

For a manual GitHub run, commit the two unchanged staging CSVs, provenance
file, provider policy, and `data/outputs/staging_input_validation.json` to the
same weekly branch. The JSON is the receipt that binds the Action to the exact
paths, checksums, provider policy, row counts, and Ready validation you
reviewed. Editing either CSV or the policy after validation blocks the run
until you validate again and use the new receipt.

The first step under dashboard `Odds Import` is `Validate provider staging`.
It runs the same report-only check and shows the latest odds API provider report
without running the provider. Full instructions are in `docs/STAGING_INPUTS.md`.

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

### One safe Thursday Terminal command

To run the whole report-only Thursday package in the correct order:

```bash
python scripts/run_scheduled_thursday_workflow.py
```

It runs:

1. Home/data freshness check.
2. Current odds validation.
3. Odds completeness check.
4. Thursday best-bets generation through the existing validation gate.
5. A dated Thursday archive when generation succeeds.
6. Latest-archive comparison when at least two archives exist.
7. The Thursday decision queue when comparison succeeds.
8. Tier performance from available ledger/archive data.

Read the combined receipt here:

```text
data/outputs/scheduled_thursday_workflow_summary.md
data/outputs/scheduled_thursday_workflow_summary.json
```

The status will be `Ready`, `Warnings only`, `Blocked`, `Partial`, or `Failed`.
`Partial` commonly means there is only one archive, so comparison must wait for
another refresh. `Blocked` means serious current-odds issues stopped the card.
The script never forces generation and never edits protected manual files or
applies an import, settlement, archive, rollback, or profile change.
Open `Tools / Diagnostics` to read the latest scheduled workflow summary in a
collapsed dashboard expander. This display is read-only; run the command from
Terminal when you intentionally want to refresh the package.

### Run it manually from GitHub

First prepare and validate the staging files the GitHub runner will read:

```bash
cp data/staging/source_current_odds_template.csv data/staging/source_current_odds.csv
cp data/staging/source_upcoming_fixtures_template.csv data/staging/source_upcoming_fixtures.csv
python scripts/run_manual_staging_provider.py
python scripts/validate_staging_inputs.py
```

Enter only real sportsbook prices. Keep the fixture staging file limited to the
upcoming slate, with no past or malformed dates. The staging verdict must say
`Ready for handoff`. Fill in the provenance file, then commit both unchanged
staging CSVs, the provenance file, `data/manual/staging_provider_policy.json`,
and `data/outputs/staging_input_validation.json` to a short-lived weekly
branch. Do not put passwords, API keys, or sportsbook account details in these
files.

1. Open `cooperross399/epl-betting-lab` on GitHub.
2. Click the **Actions** tab.
3. Click **Manual Thursday Workflow** in the workflow list.
4. Click **Run workflow** and select the weekly branch containing your prepared
   odds and fixture files.
5. Confirm the odds, fixtures, staging receipt, and provider policy paths. You
   may also paste optional SHA-256 checksums from `shasum -a 256 FILE` for an
   extra check.
6. Open the run when it finishes and read the job summary.
7. Scroll to **Artifacts** and download
   `scheduled-thursday-reports-RUN_NUMBER-RUN_ATTEMPT`.

The Action checks its own evidence before it finishes. Downloaded artifacts
include:

```text
data/outputs/github_manual_thursday_run_verification.csv
data/outputs/github_manual_thursday_run_verification.md
```

Open `Tools / Diagnostics` to read the verification verdict, or place the
downloaded reports in `data/outputs/` and run:

```bash
python scripts/verify_github_manual_thursday_run.py
```

`Verified ready run` means the handoff passed and the expected card files were
found. `Verified blocked run` means the safety gate stopped the card as
intended. Missing, incomplete, or inconsistent proof must be fixed before you
trust any recommendation from that run.

The artifact contains whichever `data/outputs/` reports the safe runner could
create and remains downloadable for 14 days. A `Blocked` run, commonly caused
by missing current odds on the fresh GitHub runner, is shown as a warning and
can finish successfully so its summary is still downloadable. A compile,
test, runtime, unexpected-exit, verification, or artifact-upload failure makes
the Action fail.

The job summary proves which inputs were used by showing the selected Git ref
and commit, staging receipt path/verdict/time, provider name/type, receipt age,
policy/cutoff status, receipt binding status, odds and fixture paths,
calculated SHA-256 checksums, freshness, validation, completeness, and whether
card generation was allowed. A missing or non-Ready receipt, changed file or
policy, unapproved provider, old/after-cutoff receipt, path mismatch, past row,
invalid date, serious validation issue, checksum mismatch, or completeness
below 100% blocks the card. The runner never fills blank odds.

The complete handoff guide is in
`docs/GITHUB_RUNNER_INPUT_HANDOFF.md`.

This workflow has only `workflow_dispatch`; it has no cron schedule. Automatic
Thursday scheduling must wait for a trusted permitted source that can refresh
real odds and fixtures without manual commits. You also need secure credential
handling, verified provider mappings, reliable refreshes before the configured
cutoff, and ownership of warnings/blocked runs. The workflow never guesses
sportsbook prices, uses `--force`, edits protected manual files, applies
changes, or places bets.

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
the exact detail section to review after you read the recommended action. Click
its `Open ...` button to switch sections safely; it does not run reports or
change files. It
also shows affected-play counts from `thursday_decision_queue.csv` when that
file is current, or a short generate/refresh message when it is not usable.

Home also shows the stale-odds archive confirmation receipt:

- `Ready` shows the confirmation ID and points you to the Terminal command in
  `Tools / Diagnostics`.
- `Odds changed after preview` tells you to run the stale odds archive preview
  again before applying.
- `Missing receipt` stays informational when no stale rows exist, but becomes a
  warning when stale odds need attention.
- Invalid receipts and missing or unreadable current odds show a clear warning
  or error.

When stale rows are known to exist and the receipt is missing, invalid,
invalidated by newer odds, or linked to an unreadable odds file, `Open this
next` points to `Tools / Diagnostics: stale odds archive preview and
confirmation status`. Clicking its button only opens that portal section.
Review the two read-only controls there; nothing runs until you choose one,
and archive apply remains Terminal-only.

This Home line only reads existing files. It never runs preview, applies an
archive, or edits odds. The same status is repeated inside `Data freshness
details`.

The Home page `Data freshness` area shows how many important files are `Fresh`,
`Stale`, `Missing`, `Needs refresh`, or `Not checked`. Follow its plain-English
recommendation first. Open `Data freshness details` only when you need the exact
file paths, source paths, local timestamps, notes, and refresh commands. The
fixture row also shows the earliest and latest match dates plus past,
today/future, and invalid-date counts. If every listed match is before today,
fixtures show `Needs refresh`. Blank, malformed, or unreadable dates show `Not
checked`. The freshness check never changes a file.

The `Current odds` row also checks match dates. If every odds row is before
today, it shows `Needs refresh`. If today/future rows exist alongside old rows,
current odds stay `Fresh` and show a warning so valid prices are not blocked.
The details table shows earliest/latest odds dates plus past, today/future, and
invalid-date row counts. The check only reads `current_odds.csv`.

To list the exact rows behind that freshness warning, run:

```bash
python scripts/report_stale_current_odds.py
```

The report marks each row as `Stale`, `Current`, `Invalid date`, or `Blank
date`. Open `Tools / Diagnostics` and use `Report stale current odds` for the
same safe check from the dashboard. It only writes report files under
`data/outputs/`; it never edits the odds file.

Preview stale-row archiving before changing anything:

```bash
python scripts/archive_stale_current_odds.py
```

The preview lists rows that would be archived/removed and rows that would
stay. Blank and invalid dates always stay for you to fix manually. You can run
the same read-only preview from `Tools / Diagnostics` with `Preview stale odds
archive`. Preview also writes
`data/outputs/stale_current_odds_archive_preview.json`, a small receipt that
connects its confirmation ID to the odds file path, checksum, and row counts.

Check that the receipt still matches before applying:

```bash
python scripts/check_stale_current_odds_archive_confirmation.py
```

The command writes
`data/outputs/stale_current_odds_archive_confirmation_status.csv` and `.md`.
`Ready` means the receipt path, checksum, and row counts still match. `Missing
receipt`, `Invalid receipt`, `Odds changed after preview`, `Missing
current_odds.csv`, and `Unreadable current_odds.csv` tell you what to fix.
When it is not `Ready`, run the archive preview again instead of using the old
confirmation ID.

In `Tools / Diagnostics`, the compact confirmation panel checks the same state
without editing anything. `Check stale odds archive confirmation` only
regenerates the read-only status files. It does not apply an archive.

Only after reviewing the preview, copy the exact apply command shown in its
markdown report. It looks like:

```bash
python scripts/archive_stale_current_odds.py \
  --apply \
  --confirm-id CONFIRM_ID_FROM_PREVIEW
```

Apply first checks that the file path, checksum, and stale/current/date-fix row
counts still match what you reviewed. If anything changed, it stops before
making a backup or editing the odds file; run preview again and use the new
ID. A successful apply creates a full backup under `data/manual/backups/`,
archives stale rows under `data/manual/archive/current_odds_stale/`, verifies
that archive, and then keeps current and date-fix rows in `current_odds.csv`.
Audit files under `data/outputs/` record the confirmation and both preview/apply
states.

The Terminal-only `--allow-unconfirmed-archive` flag exists for a rare case
you have manually inspected. Its use is clearly warned about and saved in the
audit. The dashboard has no apply or override button.

To undo an applied stale-odds archive, preview a selected pre-archive backup
first:

```bash
python scripts/rollback_stale_current_odds_archive.py \
  --backup-path data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv
```

The preview compares the selected backup with the current file and writes
`data/outputs/stale_current_odds_archive_rollback_preview.csv` plus its
markdown report and a `.json` preview receipt. The receipt contains a
confirmation ID tied to the selected paths and the exact checksums of
`current_odds.csv` and the selected backup. The report also shows whether the
backup checksum is `Verified`, `Mismatch`, or `Not available`. No odds are
changed. In the dashboard, open `Tools / Diagnostics`, enter the backup path,
and click `Preview stale odds rollback` for the same read-only check.

After reviewing the preview, copy the exact apply command shown in its markdown
report. It looks like this:

```bash
python scripts/rollback_stale_current_odds_archive.py \
  --backup-path data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv \
  --apply \
  --confirm-id CONFIRM_ID_FROM_PREVIEW
```

Apply checks that the confirmation ID, backup path, current odds checksum, and
backup checksum still match what you reviewed. If anything changed, it stops
before creating a recovery backup or editing odds and tells you to preview
again. Once the confirmation matches, apply saves the current file as a new
timestamped pre-rollback backup, then restores and verifies the selected
backup. It records the operation in
`data/outputs/stale_current_odds_archive_rollback_audit.csv` and `.md`. Empty,
malformed, missing, non-CSV, or same-file backups are blocked. The dashboard
does not offer rollback apply. New archive audit rows record checksums for the
pre-archive backup and stale-row archive. New rollback audit rows record the
selected backup checksum and the pre-rollback recovery backup checksum.

The checksum safety gate behaves conservatively:

- `Verified` backups may be applied normally.
- `Not available` backups may be applied, but the report and audit warn that
  older or missing audit history cannot confirm their original integrity.
- `Mismatch` backups are blocked before `current_odds.csv` or any recovery
  backup is changed.

Only after manually inspecting a mismatched backup may you use the explicit
Terminal-only override:

```bash
python scripts/rollback_stale_current_odds_archive.py \
  --backup-path data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv \
  --apply \
  --confirm-id CONFIRM_ID_FROM_PREVIEW \
  --allow-checksum-mismatch
```

The console, rollback preview, and audit then say `Override used` and warn that
the file may have changed after creation. They record the checksum status,
recorded checksum, current checksum, gate result, and gate note. There is no
dashboard apply or override button.

If the confirmation ID or preview receipt cannot be matched after you manually
inspect both files, the separate Terminal-only override is:

```bash
python scripts/rollback_stale_current_odds_archive.py \
  --backup-path data/manual/backups/TIMESTAMP_current_odds_pre_stale_archive.csv \
  --apply \
  --allow-unconfirmed-rollback
```

Use this only as an exception. The console, preview report, and audit warn that
apply did not match a reviewed preview. They record the confirmation ID status,
the preview and apply checksums for both files, the confirmation gate result,
and its explanation. A known backup checksum mismatch still needs
`--allow-checksum-mismatch` too. The dashboard has no apply or override button.

List the available backups first so you do not need to find and paste paths:

```bash
python scripts/list_stale_current_odds_backups.py
```

The command reads the pre-archive and pre-rollback recovery files under
`data/manual/backups/`. It writes
`data/outputs/stale_current_odds_backup_list.csv` and `.md`, showing each
backup's timestamp, modified time, row count, date range, stale/current/date
issue counts, and whether it is readable and valid. It does not change any
backup or odds file.

The list also checks the archive and rollback audit CSV/markdown reports. A
matched backup shows whether `archive_apply` or `rollback_apply` created it,
when that happened, the operation status, relevant archive path, and available
archived/restored/replaced row counts. `unknown` means there is no matching
creator row yet, or the audit history is missing, unreadable, or malformed. The
backup remains visible so you can review it manually.

The backup list also checks file integrity without editing anything. It hashes
the backup and compares that value with the linked audit checksum. Older audit
rows can use their equivalent source checksum when one was recorded:

- `Verified` means the backup is still an exact byte-for-byte match.
- `Mismatch` means the backup changed after it was created. Do not trust it for
  rollback until you inspect it manually.
- `Not available` means there is no usable recorded checksum. This is normal
  for some older backups, but their integrity is not confirmed.

The output shows the recorded checksum, current checksum, status, and a short
explanation. Generating the list never changes a backup, audit, or odds file.

In the dashboard, open `Tools / Diagnostics` and expand `Available stale odds
backups`. Select a valid backup from the list, then click `Preview stale odds
rollback`. The selected path is used only for preview. Unreadable or malformed
files remain visible for review but are not offered in the selector, and there
is still no dashboard rollback apply button. The compact table and selected
backup note show audit provenance and checksum status without changing any
audit or odds file. A mismatch produces a clear warning to inspect the file.

The selected portal section is also stored in the browser URL. For example,
`?section=odds-import` opens Odds Import and `?section=performance` opens
Performance Reports after a refresh or from a bookmark. Sidebar changes and
the Home `Open ...` button update the URL automatically. Missing or invalid
values safely open Home, and the URL never runs reports or changes data.
Use the compact `Back to Home` button at the top of any other portal section to
return to Home / Command Center. It also changes the URL to `?section=home` and
does not run reports or edit files.
Every portal page also shows a small display-only location breadcrumb, such as
`Home > Thursday Card`. The breadcrumb never runs a report or changes a file.

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

- `Home / Command Center` for Thursday readiness, stale-odds archive
  confirmation, the next action, ledger units/ROI, and pending bets.
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
Report stale current odds
Preview stale odds archive
Check stale odds archive confirmation
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
