# Trusted Provider Staging Inputs

The staging folder is a holding area between a future permitted provider and
the GitHub Thursday handoff. Provider data is checked there before it can be
considered for analysis.

## Expected files

```text
data/staging/current_odds_staging.csv
data/staging/upcoming_fixtures_staging.csv
data/staging/staging_provenance.json
```

## Prepare them with the manual provider adapter

The first provider is a controlled, Terminal-only adapter. Start with its
header-only source templates:

```bash
cp data/staging/source_current_odds_template.csv data/staging/source_current_odds.csv
cp data/staging/source_upcoming_fixtures_template.csv data/staging/source_upcoming_fixtures.csv
```

Enter or import only real provider prices and fixtures into those source files.
Never guess a missing price. Then run:

```bash
python scripts/run_manual_staging_provider.py
```

The adapter performs only basic path, readability, non-empty-file, and copy
safety checks. It copies the prepared CSV bytes and creates
`staging_provenance.json` with provider identity, source/staging paths, row
counts, SHA-256 checksums, generator, timestamp, and notes. Review:

```text
data/outputs/manual_staging_provider_report.md
data/outputs/manual_staging_provider_report.json
```

If any staging output already exists, the command stops without changing the
bundle. After reviewing the old files, replace all three outputs intentionally
with:

```bash
python scripts/run_manual_staging_provider.py --overwrite-staging
```

There is no dashboard write button. This keeps source-to-staging writes an
intentional Terminal step. The adapter does not validate betting fields, copy
anything into `data/manual/`, generate picks, or enable cron.

If you prepare staging files without the adapter, start from the older staging
templates and complete `staging_provenance_template.json` manually. Never put
credentials in provenance. Supported provider types are `manual_upload`,
`sportsbook_export`, `odds_api`, `fixture_provider`, and `unknown`.

The checked-in policy at `data/manual/staging_provider_policy.json` controls:

- allowed provider names and provider types
- whether an unknown provider is allowed
- whether missing provenance is allowed (`false` by default)
- maximum receipt age (12 hours by default)
- maximum provider-run age (12 hours by default)
- policy timezone (`America/New_York` by default)
- Thursday automation cutoff (10:00 AM by default)

The policy is fail-closed. A missing or malformed policy cannot produce a Ready
receipt.

## Run validation

```bash
python scripts/validate_staging_inputs.py
```

Validation is the actual eligibility gate. A successful provider run by itself
does **not** mean the data is ready for GitHub or Thursday analysis.

This creates:

```text
data/outputs/staging_input_validation.csv
data/outputs/staging_input_validation.md
data/outputs/staging_input_validation.json
```

The validator checks:

- both files exist, are readable CSVs, and contain required columns
- both paths stay inside `data/staging` and do not use symbolic links
- odds and fixture dates are valid and today/future
- every American price is numeric and every expected market row exists
- teams, markets, and selections pass the existing current-odds validator
- odds rows match the staged fixtures
- duplicate odds and duplicate fixture rows are flagged
- the existing GitHub runner handoff gate would allow the inputs
- the current source odds, source fixtures, staging odds, and staging fixtures
  each match the SHA-256 checksum recorded by the provider
- each source file still matches its corresponding staging file byte-for-byte
- provider `generated_at` is present, timezone-aware, not in the future, and
  within `max_provider_run_age_hours`
- provider name/type and source provenance are declared and allowed by policy
- the receipt is within the maximum age policy
- the receipt was generated no later than the Thursday cutoff in the policy

## Verdicts

- `Ready for handoff`: all blocking gates passed. Review any warnings.
- `Needs fixes`: readable inputs have data, freshness, validation, or
  completeness problems.
- `Blocked`: a path, CSV, or schema problem prevented safe validation.
- `Missing staging inputs`: one or both expected files do not exist.

`Ready for handoff` is an eligibility receipt, not a promotion action. The
validator never copies files into `data/manual/`, applies an import, generates
a Thursday card, or places a bet.

## Bind a manual GitHub run to the receipt

The JSON report is a machine-readable receipt. It includes:

- `generated_at` and the `Ready for handoff` verdict
- provider name/type, source path/checksum, generator, and notes
- exact repository-relative odds and fixture paths
- SHA-256 checksums and row counts for both files
- provider policy path/checksum, receipt age limit, timezone, and cutoff status
- odds and fixture date freshness
- current-odds validation and completeness status
- whether the existing GitHub handoff gate allowed card generation
- `Verified`, `Mismatch`, `Not available`, `Missing file`, or `Unreadable file`
  checksum status for all four provider files and both source/staging pairs

The proof is fail-closed. “Provider ran, but source odds changed afterward”
means the prepared source was edited after the adapter recorded it. “Provider
ran, but staging odds changed afterward” means the copied staging output was
edited. Rerun the provider intentionally, then rerun validation; do not edit a
receipt checksum by hand. “No provenance receipt found” also blocks by default.
The policy can explicitly allow no-provenance staging, but that exception is
visible as a warning and should be used only for a reviewed manual process.
Provider age is still required: missing provenance cannot produce a Ready
receipt when there is no provider timestamp to verify.

Provider age has its own status: `Fresh`, `Too old`, `Future timestamp`,
`Missing`, `Invalid`, or `Policy unavailable`. `Fresh` is the only status that
can be eligible for handoff. If it is too old, rerun the manual staging provider
and then validation. Do not edit `generated_at` by hand.

After reviewing a Ready result, commit these exact files to the same weekly
branch:

```text
data/staging/current_odds_staging.csv
data/staging/upcoming_fixtures_staging.csv
data/staging/staging_provenance.json
data/manual/staging_provider_policy.json
data/outputs/staging_input_validation.json
```

In **Actions > Manual Thursday Workflow**, select that branch and keep the
four matching workflow paths. The runner rechecks the receipt, provider policy,
provider-run age, and all normal freshness, validation, and completeness gates.
If a staging CSV or policy changes after validation, its checksum no longer
matches, so card generation is blocked. A receipt that becomes older than the
policy limit is also blocked. A provider run that was Fresh during validation
but becomes too old before the Action starts is blocked too. Rerun the provider
and validation instead of bypassing the gate.

The receipt does not promote or copy staging data into `data/manual/`. The
scheduled runner reads the selected staging CSVs directly for that report-only
run.

## Dashboard

Open `Odds Import`, then use `Validate staging inputs`. The dashboard shows the
verdict, compact provider proof, provider age, and source/staging pair statuses,
plus expandable markdown and CSV details. This button is read-only.

## Why cron remains disabled

The project still needs a trusted and permitted automated provider, secure
credential handling, verified provider mappings, reliable pre-cutoff staging
refreshes, and ownership for blocked runs. The policy defines a cutoff; it does
not fetch fresh inputs. Until those pieces work reliably over repeated manual
runs, the GitHub workflow remains manual-only and no cron trigger is enabled.
