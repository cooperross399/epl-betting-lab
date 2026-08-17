# Provider Human Acceptance Receipt

This receipt documents a human review decision and the exact evidence reviewed. It does **not** allowlist the provider, enable cron, promote staging, generate picks, or place bets.

## Human decision

- Receipt ID: `odds_api-20260817T155217-0400-8204291a2b19`
- Created at: **2026-08-17T15:52:17-04:00**
- Provider: **the_odds_api** (`odds_api`)
- Reviewer: **cooperross399**
- Decision: **approved_for_allowlist_pr**
- Checklist verdict: **Ready for human allowlist review**
- Approval gate: **Passed**
- Gate note: Checklist was ready for human allowlist review.
- Reviewer notes: Approved in GitHub UI on PR #124 by cooperross399 via review at 2026-08-17T19:46:41+00:00. Markets: 1x2, btts. Excluded: total_2_5.

## Bound evidence

| receipt_id                                 | provider_key   | reviewer_name   | decision                  | created_at                | evidence_type                  | evidence_path                                                        | checksum_sha256                                                  | evidence_status   | evidence_verdict                 | evidence_generated_at     | details                                                                |
|:-------------------------------------------|:---------------|:----------------|:--------------------------|:--------------------------|:-------------------------------|:---------------------------------------------------------------------|:-----------------------------------------------------------------|:------------------|:---------------------------------|:--------------------------|:-----------------------------------------------------------------------|
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | acceptance_checklist           | data/outputs/provider_acceptance_checklist.json                      | 7aa6af6017dcf0b243fa43add16307df4877d77f8b079aa0d9ac9e324331dd98 | Bound             | Ready for human allowlist review | 2026-08-17T15:17:20-04:00 |                                                                        |
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-17/151717_odds_api | 350e8968939101ed4f96b65b40abea897318695fc14494007cbcaa7d5065af96 | Bound             | Needs provider policy review     | 2026-08-17T15:17:17-04:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-17/151711_odds_api | 9548e60f62463182766da19fabfb5228a473fe395bc167abea691aad335fd735 | Bound             | Needs provider policy review     | 2026-08-17T15:17:11-04:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-17/151706_odds_api | 03e810ba7a46d193774e99f05e8f67cf21dfae96caa64b767577a951377c50df | Bound             | Needs provider policy review     | 2026-08-17T15:17:06-04:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-17/151700_odds_api | 1fd4711908ca3ccc01d0144ef30064250bddb1ba9de18877ea9222e1aa14e760 | Bound             | Needs provider policy review     | 2026-08-17T15:17:00-04:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-17/151655_odds_api | 68478b7192e7004b4e7426223e39e06d7074b3704681c5072409669ec9432471 | Bound             | Needs provider policy review     | 2026-08-17T15:16:55-04:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | latest_live_shadow_archive_set | data/outputs/archive/provider_shadow_runs                            |                                                                  | Verified          |                                  |                           | The checklist reviewed the current latest live shadow-run archive set. |
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | latest_shadow_comparison       | data/outputs/provider_shadow_run_comparison.json                     | 17bd99391c54fcb732f1be6e4350b1cd2f30ec15b7dc32677e01299ca665211d | Bound             | Stable enough for review         | 2026-08-17T15:51:40-04:00 |                                                                        |
| odds_api-20260817T155217-0400-8204291a2b19 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-17T15:52:17-04:00 | provider_policy                | data/manual/staging_provider_policy.json                             | 23d88241a66c9cc86b59d4278694b4e1522fd48048c268e0744dd217020b21d3 | Bound             |                                  |                           |                                                                        |

Archive bundle checksums cover each reviewed archive's filenames and current file checksums in deterministic order.

## Warnings

No evidence-binding warnings.

## Decision boundary

- `approved_for_allowlist_pr` means only that a separate allowlist PR may be considered.
- A separate human-reviewed PR is still required to edit `staging_provider_policy.json`.
- Cron remains disabled and requires its own later review.
- This receipt never edits protected manual files or runs a provider.

No provider was allowlisted and cron remains disabled.