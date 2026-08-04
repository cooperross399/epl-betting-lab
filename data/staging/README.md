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

The shared provider command also includes an offline-first odds API skeleton:

```bash
python scripts/run_provider_staging.py --provider odds_api --dry-run
```

Dry-run makes no network request and writes no staging files. Live mode must be
run intentionally from Terminal with `EPL_ODDS_API_KEY` set in the environment:

```bash
export EPL_ODDS_API_KEY='your-secret-key'
python scripts/run_provider_staging.py --provider odds_api --live
```

Never store the key in this folder. A live run can add raw JSON evidence under
`data/staging/raw/` and normalized source/staging CSVs with checksums. It copies
only returned prices; missing markets remain missing for validation to flag.
The default policy does not allow `the_odds_api` until real output is reviewed.

It stops if any output already exists. Review the existing bundle first and use
`--overwrite-staging` only when replacing all three outputs is intentional.
The generated provenance identifies both source files and their SHA-256
checksums plus both copied staging files and their checksums; it must never
contain credentials. The provider command is Terminal-only and does not
validate or promote data.

The policy at `data/manual/staging_provider_policy.json` controls allowed
providers, maximum provider-run and receipt ages, and the Thursday cutoff. Run
`python scripts/validate_staging_inputs.py` after the adapter and before
considering these files for the GitHub runner handoff.

Validation recalculates all four checksums and verifies each source/staging
pair. Any mismatch, missing file, unreadable file, or missing required checksum
blocks handoff. Missing provenance is also blocked unless the reviewed provider
policy explicitly allows it. The provider `generated_at` must be timezone-aware,
not in the future, and within the provider-run age limit; this timestamp is
created by the provider and should never be edited just to pass validation.

Validation is read-only. It does not copy staging files into `data/manual/`,
promote inputs, enable cron, or place bets.
