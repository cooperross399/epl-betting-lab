# Provider staging inputs

This folder is a holding area for real provider odds and current fixture data.
The validator reads these expected files:

- `current_odds_staging.csv`
- `upcoming_fixtures_staging.csv`

Start from the two header-only templates in this folder. Do not invent or fill
missing sportsbook prices. Run `python scripts/validate_staging_inputs.py`
before considering either file for the GitHub runner handoff.

Validation is read-only. It does not copy staging files into `data/manual/`,
promote inputs, enable cron, or place bets.
