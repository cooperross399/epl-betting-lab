# GitHub Runner Odds and Fixtures Handoff

This is the safe staging-receipt input method for the manual Thursday GitHub
Action. It uses real odds and fixtures that you prepare, validate, review, and
commit with their Ready receipt to the branch you select when starting the
Action.

The runner does not fetch sportsbook prices, fill blank prices, edit the input
files, use `--force`, or place bets.

Provider-produced files should first pass the separate read-only staging gate:

```bash
python scripts/validate_staging_inputs.py
```

That gate reads `data/staging/current_odds_staging.csv` and
`data/staging/upcoming_fixtures_staging.csv`. A `Ready for handoff` verdict
means the existing freshness, validation, completeness, and runner handoff
checks passed. It does not copy or promote the files. The manual Action binds
its selected files to `data/outputs/staging_input_validation.json`, then runs
the normal gates again.

## What to prepare

The default Action input paths are:

```text
data/staging/current_odds_staging.csv
data/staging/upcoming_fixtures_staging.csv
data/outputs/staging_input_validation.json
```

Create the two staging CSVs from their templates, enter only real prices, and
keep the fixture file limited to the upcoming slate you want the runner to
analyze.

```bash
cp data/staging/current_odds_staging_template.csv data/staging/current_odds_staging.csv
cp data/staging/upcoming_fixtures_staging_template.csv data/staging/upcoming_fixtures_staging.csv
python scripts/validate_staging_inputs.py
```

Before committing:

1. Fill every supported market row with a real numeric `american_odds` value.
2. Fill `book` when known.
3. Remove or archive every odds row tied to a past match.
4. Keep only today/future rows in the prepared fixtures file.
5. Fix blank or malformed dates.
6. Make sure completeness is 100% for the prepared fixture slate.
7. Review heavy juice around or worse than `-160` and totals-under warnings.

Confirm `data/outputs/staging_input_validation.md` says `Ready for handoff`.
Commit both unchanged staging CSVs and the matching JSON receipt to a
short-lived weekly branch, then push that branch. Never put sportsbook
passwords, API keys, account numbers, or other secrets in either CSV.
Repository files and generated artifacts may be visible to anyone who can
access the repository.

## Optional checksum confirmation

The Action always calculates and reports SHA-256 checksums. You can also enter
the expected checksums when starting the workflow:

```bash
shasum -a 256 data/staging/current_odds_staging.csv
shasum -a 256 data/staging/upcoming_fixtures_staging.csv
```

Copy only the 64-character checksum into the matching optional workflow field.
A mismatch blocks the card.

## Run the manual Action

1. Open the repository on GitHub.
2. Open **Actions**, then **Manual Thursday Workflow**.
3. Select **Run workflow**.
4. Select the weekly branch containing the prepared files.
5. Confirm the repository-relative odds, fixtures, and staging receipt paths.
6. Optionally enter the two expected SHA-256 values.
7. Run the workflow.

The path fields accept only regular `.csv` files inside the checked-out
repository. Absolute paths, paths that escape the repository, directories, and
symbolic links are blocked.

## What the runner proves

The Action summary and these artifact files record the handoff:

```text
data/outputs/github_runner_input_handoff.json
data/outputs/github_runner_input_handoff.md
data/outputs/scheduled_thursday_workflow_summary.json
data/outputs/scheduled_thursday_workflow_summary.md
data/outputs/github_manual_thursday_run_verification.csv
data/outputs/github_manual_thursday_run_verification.md
```

They show:

- selected GitHub ref and commit SHA
- staging receipt path, verdict, generated timestamp, and receipt checksum
- receipt path, input checksum, and row-count match status
- exact repository-relative odds and fixture paths
- calculated file SHA-256 checksums
- optional checksum match status
- odds and fixture date freshness
- current-odds validation status and issue counts
- odds completion percentage and incomplete-match count
- whether Thursday card generation was allowed

This gives you a reviewable receipt without exposing made-up prices because the
runner never invents missing data.

## Verify a completed manual run

The Action runs this read-only verification automatically after the scheduled
runner:

```bash
python scripts/verify_github_manual_thursday_run.py
```

You can run the same command after placing a downloaded artifact's reports in
`data/outputs/`. It compares the standalone handoff proof with the copy inside
the scheduled summary and verifies the Git ref/SHA, exact input paths and
checksums, freshness, validation, completeness, card permission, workflow
status, and every output file the runner says it created.

The verdict is one of:

- `Verified ready run`: trusted evidence and expected card files are present.
- `Verified blocked run`: the safety gate stopped generation as intended.
- `Incomplete run artifacts`: expected report files are missing.
- `Missing handoff proof`: the input identity receipt is absent.
- `Missing scheduled workflow summary`: the workflow receipt is absent.
- `Failed/untrusted run`: evidence is malformed, inconsistent, or unsafe.

The dashboard shows the latest verification report under
`Tools / Diagnostics`. Verification only reads report artifacts; it never
changes odds, fixtures, imports, ledger rows, profiles, or model behavior.

## Fail-closed rules

Card generation is blocked when:

- the staging receipt is missing, unreadable, malformed, or outside the repository
- the receipt verdict is not `Ready for handoff`
- selected paths do not match the receipt or are not inside `data/staging`
- either staging file checksum or row count changed after validation
- the receipt does not record acceptable freshness, validation, and completeness
- either file is missing, unreadable, empty, outside the repository, or not CSV
- an optional expected checksum does not match
- odds or fixtures contain any past-match rows
- dates are blank, malformed, or contain no today/future rows
- current-odds validation finds a serious issue
- odds completeness is below 100%
- an expected fixture, market, or selection row is missing

Warnings such as missing books, heavy juice, or totals-under caution remain
visible. A blocked input run does not use `--force`. The Action still uploads
the available reports so you can read why it stopped.

## Why cron is still off

The handoff is intentionally manual. A person still has to source real prices,
validate and review the staging receipt, commit the files, choose the correct
branch, and review warnings. Before enabling a Thursday schedule, the project
still needs:

- a trusted and permitted automated odds source
- an automated fixture refresh with date checks
- secure credentials that are never written to artifacts or logs
- an agreed Thursday timezone and cutoff time
- ownership for reviewing warnings and blocked runs
- evidence that the automated source maps teams, markets, and selections
  correctly

Until those pieces exist, `workflow_dispatch` remains the only trigger.
