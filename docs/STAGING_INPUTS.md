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

Start with the header-only templates:

```bash
cp data/staging/current_odds_staging_template.csv data/staging/current_odds_staging.csv
cp data/staging/upcoming_fixtures_staging_template.csv data/staging/upcoming_fixtures_staging.csv
cp data/staging/staging_provenance_template.json data/staging/staging_provenance.json
```

Enter or import only real provider prices. Never guess a missing price.

In `staging_provenance.json`, identify the source without putting credentials
in the file. Supported provider types are `manual_upload`, `sportsbook_export`,
`odds_api`, `fixture_provider`, and `unknown`. Set `source_file_path` to a file
inside `data/staging/`; a blank source checksum is calculated during validation.

The checked-in policy at `data/manual/staging_provider_policy.json` controls:

- allowed provider names and provider types
- whether an unknown provider is allowed
- maximum receipt age (12 hours by default)
- policy timezone (`America/New_York` by default)
- Thursday automation cutoff (10:00 AM by default)

The policy is fail-closed. A missing or malformed policy cannot produce a Ready
receipt.

## Run validation

```bash
python scripts/validate_staging_inputs.py
```

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
- SHA-256 checksums are recorded for later identity review
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
and all normal freshness, validation, and completeness gates. If a staging CSV
or policy changes after validation, its checksum no longer matches, so card
generation is blocked. A receipt that becomes older than the policy limit is
also blocked. Run validation again and review the replacement receipt instead
of bypassing the gate.

The receipt does not promote or copy staging data into `data/manual/`. The
scheduled runner reads the selected staging CSVs directly for that report-only
run.

## Dashboard

Open `Odds Import`, then use `Validate staging inputs`. The dashboard shows the
verdict plus expandable markdown and CSV details. This button is read-only.

## Why cron remains disabled

The project still needs a trusted and permitted automated provider, secure
credential handling, verified provider mappings, reliable pre-cutoff staging
refreshes, and ownership for blocked runs. The policy defines a cutoff; it does
not fetch fresh inputs. Until those pieces work reliably over repeated manual
runs, the GitHub workflow remains manual-only and no cron trigger is enabled.
