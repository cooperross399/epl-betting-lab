# Provider staging inputs

This folder is a holding area for real provider odds and current fixture data.
The validator reads these expected files:

- `current_odds_staging.csv`
- `upcoming_fixtures_staging.csv`
- `staging_provenance.json`

Start from the CSV templates and `staging_provenance_template.json` in this
folder. Do not invent or fill missing sportsbook prices. The provenance file
identifies the provider/source but must never contain credentials. The policy
at `data/manual/staging_provider_policy.json` controls allowed providers, the
maximum receipt age, and the Thursday cutoff. Run
`python scripts/validate_staging_inputs.py` before considering these files for
the GitHub runner handoff.

Validation is read-only. It does not copy staging files into `data/manual/`,
promote inputs, enable cron, or place bets.
