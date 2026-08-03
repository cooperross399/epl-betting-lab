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

## Dashboard

Open `Odds Import`, then use `Validate staging inputs`. The dashboard shows the
verdict plus expandable markdown and CSV details. This button is read-only.

## Why cron remains disabled

The project still needs a trusted and permitted provider, secure credential
handling, verified provider mappings, a chosen Thursday timezone/cutoff, and an
explicitly reviewed staging-to-handoff promotion design. Until those pieces
exist, the GitHub workflow remains manual-only and no cron trigger is enabled.
