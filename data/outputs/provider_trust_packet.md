# Provider Trust Packet

Consolidated evidence for the provider allowlist decision. This report cannot edit policy, allowlist a provider, generate picks, or place bets.

## Decision

- Provider: **odds_api**
- Currently allowlisted: **No**
- Ready for human approval: **No**

## Acceptance progress

- Checklist verdict: **Ready for human allowlist review**
- Completed live runs: **5/3** (0 remaining)

## Coverage summary

- Team mapping: **Verified**
- Unmapped teams: none

| Scope | Status | Covered | Coverage |
|:------|:-------|:--------|:---------|
| `provider_returned` | Complete | 15/15 | 100.0% |
| `selected_week1_window` | Complete | 10/10 | 100.0% |
| `full_upcoming_fixtures` | Incomplete | 14/20 | 70.0% |

## Market eligibility summary

- Included: **1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5**
- Excluded: **none**
- Unavailable: none
- Incomplete: none
- Disabled: none
- BTTS: **Available**
- Provider-derived card input rows: **190**
- Manual odds entry required: **No**

## Quota

- Status: **Available**
- Used: 13482
- Remaining: 6518

## Safety flags

- Secrets written or printed: **No**
- Manual or production files edited: **No**
- Provider policy edited: **No**
- Staging promoted: **No**
- Trusted picks generated: **No**
- Bets placed: **No**
- Cron enabled: **No**

## Outstanding requirements

- Acceptance checklist verdict is `Ready for human allowlist review`; resolve its listed failures. The checklist reviews a window of past runs and fails closed on any that failed, were blocked, or predate a fix.
- Explicit human approval to add `odds_api` to `allowed_provider_names` in `data/manual/staging_provider_policy.json`.

## Exact approval needed

Add `"odds_api"` to `allowed_provider_names` in `data/manual/staging_provider_policy.json`. This packet does not and cannot make that edit; it requires your explicit approval.
