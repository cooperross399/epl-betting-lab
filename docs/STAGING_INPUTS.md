# Trusted Provider Staging Inputs

The staging folder is a holding area between a future permitted provider and
the GitHub Thursday handoff. Provider data is checked there before it can be
considered for analysis.

## Expected files

```text
data/staging/current_odds_staging.csv
data/staging/upcoming_fixtures_staging.csv
```

Start with the header-only templates:

```bash
cp data/staging/current_odds_staging_template.csv data/staging/current_odds_staging.csv
cp data/staging/upcoming_fixtures_staging_template.csv data/staging/upcoming_fixtures_staging.csv
```

Enter or import only real provider prices. Never guess a missing price.

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
- exact repository-relative odds and fixture paths
- SHA-256 checksums and row counts for both files
- odds and fixture date freshness
- current-odds validation and completeness status
- whether the existing GitHub handoff gate allowed card generation

After reviewing a Ready result, commit these exact files to the same weekly
branch:

```text
data/staging/current_odds_staging.csv
data/staging/upcoming_fixtures_staging.csv
data/outputs/staging_input_validation.json
```

In **Actions > Manual Thursday Workflow**, select that branch and keep the
three matching workflow paths. The runner rechecks the receipt and all normal
freshness, validation, and completeness gates. If a staging CSV changes after
validation, its checksum and possibly its row count no longer match, so card
generation is blocked. Run validation again and review the replacement receipt
instead of bypassing the gate.

The receipt does not promote or copy staging data into `data/manual/`. The
scheduled runner reads the selected staging CSVs directly for that report-only
run.

## Dashboard

Open `Odds Import`, then use `Validate staging inputs`. The dashboard shows the
verdict plus expandable markdown and CSV details. This button is read-only.

## Why cron remains disabled

The project still needs a trusted and permitted provider, secure credential
handling, verified provider mappings, a chosen Thursday timezone/cutoff, and
reliable automated staging refreshes. Until those pieces exist, the GitHub
workflow remains manual-only and no cron trigger is enabled.
