# Provider Trust Packet

Consolidated evidence for the provider allowlist decision. This report cannot edit policy, allowlist a provider, generate picks, or place bets.

## Decision

- Provider: **the_odds_api**
- Currently allowlisted: **No**
- Ready for human approval: **Yes**

## Acceptance progress

- Checklist verdict: **Ready for human allowlist review**
- Completed live runs: **5/3** (0 remaining)

## Coverage summary

- Team mapping: **Verified**
- Unmapped teams: none

| Scope | Status | Covered | Coverage |
|:------|:-------|:--------|:---------|
| `provider_returned` | Complete | 10/10 | 100.0% |
| `selected_week1_window` | Complete | 10/10 | 100.0% |
| `full_upcoming_fixtures` | Incomplete | 10/20 | 50.0% |

## Market eligibility summary

- Included: **['1x2', 'btts']**
- Excluded: **['total_2_5']**
- Unavailable: none
- Incomplete: ['total_2_5']
- Disabled: none
- BTTS: **Available**
- Provider-derived card input rows: **50**
- Manual odds entry required: **No**

## Quota

- Status: **Available**
- Used: 76
- Remaining: 424

## Safety flags

- Secrets written or printed: **No**
- Manual or production files edited: **No**
- Provider policy edited: **No**
- Staging promoted: **No**
- Trusted picks generated: **No**
- Bets placed: **No**
- Cron enabled: **No**

## Outstanding requirements

- Explicit human approval to add `the_odds_api` to `allowed_provider_names` in `data/manual/staging_provider_policy.json`.

## Exact approval needed

Add `"the_odds_api"` to `allowed_provider_names` in `data/manual/staging_provider_policy.json`. This packet does not and cannot make that edit; it requires your explicit approval.
