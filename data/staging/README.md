# Provider staging inputs

This folder is a holding area for real provider odds and current fixture data.
For the controlled manual provider, first copy the source templates:

```bash
cp data/staging/source_current_odds_template.csv data/staging/source_current_odds.csv
cp data/staging/source_upcoming_fixtures_template.csv data/staging/source_upcoming_fixtures.csv
```

Fill those two source files with reviewed, real provider data, then run:

```bash
python scripts/run_manual_staging_provider.py
```

The adapter copies the source bytes without inventing or normalizing data and
writes these expected validation inputs:

- `current_odds_staging.csv`
- `upcoming_fixtures_staging.csv`
- `staging_provenance.json`

It stops if any output already exists. Review the existing bundle first and use
`--overwrite-staging` only when replacing all three outputs is intentional.
The generated provenance identifies both source files and their SHA-256
checksums plus both copied staging files and their checksums; it must never
contain credentials. The provider command is Terminal-only and does not
validate or promote data.

The policy at `data/manual/staging_provider_policy.json` controls allowed
providers, the maximum receipt age, and the Thursday cutoff. Run
`python scripts/validate_staging_inputs.py` after the adapter and before
considering these files for the GitHub runner handoff.

Validation recalculates all four checksums and verifies each source/staging
pair. Any mismatch, missing file, unreadable file, or missing required checksum
blocks handoff. Missing provenance is also blocked unless the reviewed provider
policy explicitly allows it.

Validation is read-only. It does not copy staging files into `data/manual/`,
promote inputs, enable cron, or place bets.
