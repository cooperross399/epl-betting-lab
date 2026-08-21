# Provider Human Acceptance Receipt

This receipt documents a human review decision and the exact evidence reviewed. It does **not** allowlist the provider, enable cron, promote staging, generate picks, or place bets.

## Human decision

- Receipt ID: `odds_api-20260821T114655-0400-20ffa5677988`
- Created at: **2026-08-21T11:46:55-04:00**
- Provider: **the_odds_api** (`odds_api`)
- Reviewer: **cooperross399**
- Decision: **approved_for_allowlist_pr**
- Checklist verdict: **Ready for human allowlist review**
- Approval gate: **Passed**
- Gate note: Checklist was ready for human allowlist review.
- Reviewer notes: Approved in GitHub UI on PR #224 by cooperross399 via comment at 2026-08-21T15:46:30+00:00. Markets: 1x2, btts, corners_1x2, corners_total_10_5, corners_total_9_5, double_chance, draw_no_bet, total_2_5. Excluded: .

## Bound evidence

| receipt_id                                 | provider_key   | reviewer_name   | decision                  | created_at                | evidence_type                  | evidence_path                                                        | checksum_sha256                                                  | evidence_status   | evidence_verdict                 | evidence_generated_at     | details                                                                |
|:-------------------------------------------|:---------------|:----------------|:--------------------------|:--------------------------|:-------------------------------|:---------------------------------------------------------------------|:-----------------------------------------------------------------|:------------------|:---------------------------------|:--------------------------|:-----------------------------------------------------------------------|
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | acceptance_checklist           | data/outputs/provider_acceptance_checklist.json                      | 865d4e6ec1c4d1535a96966bba04df89ce3a0643e288cde36a3c5b643aac4b69 | Bound             | Ready for human allowlist review | 2026-08-21T11:44:26-04:00 |                                                                        |
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-21/154335_odds_api | 6b2842cbc84eddbecbd3ca435a652bc900f47c2b00999985ce398c47059aa866 | Bound             | Shadow ready for review          | 2026-08-21T15:43:35+00:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-21/154222_odds_api | 539a2672fc06e78616e8235fecd39d85a9c67d697350547a6a20f80d0c197c28 | Bound             | Shadow ready for review          | 2026-08-21T15:42:22+00:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-21/154019_odds_api | 9525c7de23a88ac19b34b9e812e68b6caa156d5d3483f9360b12edfc3c262935 | Bound             | Shadow ready for review          | 2026-08-21T15:40:19+00:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-21/153908_odds_api | 0e0aae3c2da51bf78bd25991ad100e5421195356ff9f3fa8bc2c8c1bae411398 | Bound             | Shadow ready for review          | 2026-08-21T15:39:08+00:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | reviewed_shadow_archive        | data/outputs/archive/provider_shadow_runs/2026-08-21/153816_odds_api | 30f6c1ad63ccda5181ff5fd39a9f9f474e6f0630041d22b3c84b37cd4b564491 | Bound             | Shadow ready for review          | 2026-08-21T15:38:16+00:00 | 9 file(s); checklist integrity Verified; current integrity Verified    |
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | latest_live_shadow_archive_set | data/outputs/archive/provider_shadow_runs                            |                                                                  | Verified          |                                  |                           | The checklist reviewed the current latest live shadow-run archive set. |
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | latest_shadow_comparison       | data/outputs/provider_shadow_run_comparison.json                     | 81a23e87f4e585b8b1e7b3d25d80a5ad6ff7427f806563d98e22dff2785474e5 | Bound             | Stable enough for review         | 2026-08-21T11:44:26-04:00 |                                                                        |
| odds_api-20260821T114655-0400-20ffa5677988 | odds_api       | cooperross399   | approved_for_allowlist_pr | 2026-08-21T11:46:55-04:00 | provider_policy                | data/manual/staging_provider_policy.json                             | 1a16ba8a70d96ec81ddc6aabd4e7f0e61b0e50982b7893dcc19f178139466dbb | Bound             |                                  |                           |                                                                        |

Archive bundle checksums cover each reviewed archive's filenames and current file checksums in deterministic order.

## Warnings

No evidence-binding warnings.

## Decision boundary

- `approved_for_allowlist_pr` means only that a separate allowlist PR may be considered.
- A separate human-reviewed PR is still required to edit `staging_provider_policy.json`.
- Cron remains disabled and requires its own later review.
- This receipt never edits protected manual files or runs a provider.

No provider was allowlisted and cron remains disabled.