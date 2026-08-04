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

## Provider adapter framework and odds API skeleton

`scripts/run_provider_staging.py` is the shared entry point for registered
providers. It requires `--provider` and defaults to dry-run:

```bash
python scripts/run_provider_staging.py --provider manual --dry-run
python scripts/run_provider_staging.py --provider odds_api --dry-run
```

Dry-run writes only a provider report under `data/outputs/`. It makes no API
request and writes no staging files. The registered provider code lives in:

```text
src/epl_betting_lab/providers/base.py
src/epl_betting_lab/providers/provider_registry.py
src/epl_betting_lab/providers/odds_api_staging_provider.py
```

The first real-provider skeleton follows The Odds API v4 EPL event/odds shape.
Live mode requires an environment-only key:

```bash
export EPL_ODDS_API_KEY='your-secret-key'
python scripts/run_provider_staging.py --provider odds_api --live
```

Do not put the key in a command argument, `.csv`, provenance JSON, notes, or a
commit. A future GitHub run must receive it through GitHub Secrets. The adapter
never prints or writes the key.

An intentional live run can write only provider evidence under `data/staging/`
and its generated report under `data/outputs/`:

```text
data/staging/source_current_odds.csv
data/staging/source_upcoming_fixtures.csv
data/staging/current_odds_staging.csv
data/staging/upcoming_fixtures_staging.csv
data/staging/staging_provenance.json
data/staging/raw/TIMESTAMP_CHECKSUM_odds_api_response.json
data/outputs/odds_api_staging_provider_report.json
data/outputs/odds_api_staging_provider_report.md
```

The normalized source CSVs and staging CSVs are byte-identical so the existing
checksum-pair gate still works. Provenance also records the provider name/type,
generated timestamp, source URL without credentials, raw response checksum,
normalized/staging checksums, generator, and notes.

The skeleton requests featured 1X2 and totals data and parses BTTS only when it
is present in provider evidence. It never fills a missing market. Missing BTTS,
unsupported team naming, partial fixtures, malformed responses, or empty odds
remain visible and can block the separate staging validator. The checked-in
provider policy intentionally does not allow `the_odds_api` yet; review real
output before deliberately adding that provider name.

Provider network/writes stay Terminal-only. The Odds Import dashboard displays
the latest report but cannot fetch, overwrite staging, expose a secret, validate
automatically, promote data, or place a bet.

## Controlled live shadow verification

A shadow run asks, "Can this provider produce a technically usable bundle?"
It does not ask the model for picks and does not approve the provider. Start
with the no-network dry-run:

```bash
python scripts/run_provider_shadow_verification.py --provider odds_api --dry-run
```

The dry-run command itself exits successfully when the preview works, but its
report verdict remains `Blocked`: no live evidence was fetched, so provider
usability cannot honestly be proven yet.

For an intentional live shadow run, set the key only in your local environment:

```bash
export EPL_ODDS_API_KEY='your-secret-key'
python scripts/run_provider_shadow_verification.py --provider odds_api --live
```

A future GitHub runner must receive the same variable through GitHub Secrets;
never commit the key or pass it as a command argument. If staging evidence
already exists, the provider blocks replacement. Review it first, then use
`--overwrite-staging` only when replacing the whole staging bundle is
intentional.

Live shadow mode runs the registered provider, writes only staging/evidence and
provider reports, then calls the existing staging validation and handoff gates.
It creates:

```text
data/outputs/provider_shadow_verification.json
data/outputs/provider_shadow_verification.md
data/outputs/provider_shadow_verification.csv
```

The report covers raw evidence, source/staging checksums, provider age, exact
team-name reference coverage, fixture matching, bookmakers, 1X2/totals/BTTS
coverage, missing selections, odds completeness, provider policy status, and
safe quota headers when the provider returns them. BTTS remains missing when it
is unavailable; the verifier never invents a price.

Shadow verdicts are:

- `Shadow ready for review`: technical gates passed, but manual review remains.
- `Needs mapping fixes`: team or fixture identities need reviewed mappings.
- `Needs market coverage review`: required market rows are incomplete.
- `Needs provider policy review`: data passed but the provider is not allowed.
- `Blocked`: a credential, evidence, age, validation, or safety gate stopped it.
- `Failed`: a runtime/reporting failure prevented verification.

The `Odds Import` dashboard displays the latest markdown and CSV reports. It
does not expose a live-run button. Repeated successful shadow runs, reviewed
team mappings, acceptable market coverage, understood quota behavior, and a
clear owner for failures are still required before allowlisting or cron.

## Shadow-run history and comparison

Every shadow verification archives its JSON, markdown, CSV, available provider
report, available staging validation report, and safe SHA-256 metadata under:

```text
data/outputs/archive/provider_shadow_runs/YYYY-MM-DD/HHMMSS_PROVIDER/
```

Archive names are collision-safe, so a second run in the same second creates a
new folder instead of replacing reviewed evidence. Compare the latest two runs
for one provider with:

```bash
python scripts/compare_provider_shadow_runs.py --provider odds_api
```

The outputs are `data/outputs/provider_shadow_run_comparison.json`, `.md`, and
`.csv`. They compare verdicts, exact team and fixture coverage, bookmakers,
1X2/totals/BTTS rows, completeness, source/staging checksum proof, policy,
staging validation, safe quota headers, and warnings/blockers added or removed.
Comparison verdicts are `Stable enough for review`, `Needs more shadow runs`,
`Coverage changed`, `Mapping issue`, `Market coverage issue`,
`Provider policy issue`, and `Failed/untrusted`.

The Odds Import dashboard shows recent snapshots and a report-only comparison
button. It cannot run a live provider, allowlist one, promote staging, expose a
secret, or enable cron. Treat three consistent runs as a minimum review cue,
not automatic provider approval.

## Provider acceptance checklist

The acceptance checklist applies the minimum-run and stability policy across
archived live shadow runs:

```bash
python scripts/generate_provider_acceptance_checklist.py --provider odds_api
```

Defaults are three completed live runs inside the latest five live-run
archives. Change them only for an intentional review:

```bash
python scripts/generate_provider_acceptance_checklist.py \
  --provider odds_api --minimum-runs 5 --review-window 5
```

Dry runs never count. The report evaluates failed/untrusted history, mapping and
fixture stability, bookmaker consistency, 1X2 and totals coverage, explicit
BTTS availability, staging technical success, provider freshness,
archive/source/staging/provenance checksums, safe quota headers, policy state,
and unresolved blockers. It writes:

```text
data/outputs/provider_acceptance_checklist.json
data/outputs/provider_acceptance_checklist.md
data/outputs/provider_acceptance_checklist.csv
```

The possible verdicts are `Ready for human allowlist review`, `Needs more
shadow runs`, `Needs mapping fixes`, `Needs market coverage review`, `Needs
quota review`, `Needs provider policy review`, and `Not trusted`. A consistently
disallowed provider may become ready for **human review** because that is the
question the report answers. It never changes `staging_provider_policy.json` or
approves the provider itself.

The Odds Import dashboard button only regenerates these report files. Live
provider runs, policy edits, staging promotion, and cron remain unavailable in
the dashboard. Cron stays disabled until a person reviews repeated live
evidence, credentials, ownership, failure handling, and the policy change.

## Human provider acceptance receipt

Create this receipt only after a person has read a provider acceptance checklist
and the reviewed shadow-run evidence. Start with a preview:

```bash
python scripts/create_provider_human_acceptance_receipt.py \
  --provider odds_api \
  --reviewer-name "Cooper Ross" \
  --decision approved_for_allowlist_pr \
  --notes "Reviewed the bound provider evidence."
```

The supported decisions are `approved_for_allowlist_pr`, `rejected`, and
`needs_more_shadow_runs`. Preview mode writes nothing. After checking the
provider, decision, checklist verdict, evidence paths, and warnings shown in
Terminal, intentionally write the receipt:

```bash
python scripts/create_provider_human_acceptance_receipt.py \
  --provider odds_api \
  --reviewer-name "Cooper Ross" \
  --decision approved_for_allowlist_pr \
  --notes "Reviewed the bound provider evidence." \
  --write-receipt
```

Approval is refused unless the checklist verdict is `Ready for human allowlist
review`. A rare, intentional exception requires the Terminal-only
`--allow-not-ready-approval` flag and is recorded as an override in the receipt.
The receipt binds these exact inputs:

- acceptance checklist path, verdict, generated time, and SHA-256 checksum
- every reviewed shadow archive path and deterministic archive-bundle checksum
- latest matching shadow comparison path and checksum when available
- provider policy path and checksum when available
- reviewer, decision, notes, and receipt timestamp

Written reports are:

```text
data/outputs/provider_human_acceptance_receipt.json
data/outputs/provider_human_acceptance_receipt.md
data/outputs/provider_human_acceptance_receipt.csv
data/outputs/archive/provider_acceptance_receipts/YYYY-MM-DD/
```

The Odds Import dashboard displays the latest receipt and evidence table only.
It has no create, approval, allowlist, promotion, or cron control. Even an
`approved_for_allowlist_pr` receipt only says a separate human-reviewed policy PR
may be considered; it does not edit `staging_provider_policy.json`.

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
plus expandable markdown and CSV details. The latest odds API staging provider
report is display-only below it. No provider live/dry-run button is exposed.
These dashboard controls are read-only.

## Why cron remains disabled

The provider adapter is still a manually triggered skeleton. Its real team and
market mappings, BTTS coverage, quota behavior, secret injection, failure
alerts, and pre-cutoff reliability need repeated review before automation. The
policy defines a cutoff; it does not fetch fresh inputs. Until those pieces work
reliably over repeated manual runs, the GitHub workflow remains manual-only and
no cron trigger is enabled.
