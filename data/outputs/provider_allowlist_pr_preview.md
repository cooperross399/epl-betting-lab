# Provider Allowlist PR Readiness Preview

**Preview only: nothing was applied.** This report does not edit `staging_provider_policy.json`, allowlist a provider, promote staging, run a provider, generate picks, place bets, or enable cron.

## Status

- **Ready for separate allowlist PR**
- Provider: `the_odds_api` (`odds_api`)
- Current allowlist status: **Not allowed**
- Proposed allowlist status: **Allowed**

## Evidence used

- Verification verdict: **Verified for allowlist PR review**
- Verification report: `data/outputs/provider_human_acceptance_receipt_verification.json`
- Verification SHA-256: `837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee`
- Human receipt ID: `odds_api-20260817T155217-0400-8204291a2b19`
- Reviewer: **cooperross399**
- Reviewed at: 2026-08-17T15:52:18-04:00
- Approved at: 2026-08-17T15:52:17-04:00
- Current policy: `data/manual/staging_provider_policy.json`
- Current policy SHA-256: `23d88241a66c9cc86b59d4278694b4e1522fd48048c268e0744dd217020b21d3`

## Blockers

- None.

## Warnings

- None.

## Exact proposed provider fields

```json
{
  "allowlist_status": "allowed",
  "approved_at": "2026-08-17T15:52:17-04:00",
  "cutoff_policy": {
    "day": "Thursday",
    "time": "10:00",
    "timezone": "America/New_York"
  },
  "evidence_receipt_id": "odds_api-20260817T155217-0400-8204291a2b19",
  "known_limitations": [
    "BTTS is not requested by the current provider adapter. Missing BTTS prices remain unavailable and must never be fabricated.",
    "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
  ],
  "max_provider_run_age_hours": 12.0,
  "provider_key": "odds_api",
  "provider_name": "the_odds_api",
  "provider_type": "odds_api",
  "required_markets": [
    "1x2",
    "total_2_5"
  ],
  "reviewed_at": "2026-08-17T15:52:18-04:00",
  "reviewer_name": "cooperross399",
  "verification_report_checksum_sha256": "837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee",
  "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
}
```

## Change table

| category          | field                                                                       | before                                                                 | after                                                                                                                                                                                                                                                     | change                          | status                          | details                                                                          |
|:------------------|:----------------------------------------------------------------------------|:-----------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------|:--------------------------------|:---------------------------------------------------------------------------------|
| Evidence          | receipt_verification_verdict                                                | Verified for allowlist PR review                                       | Verified for allowlist PR review                                                                                                                                                                                                                          | Required gate                   | Verified                        | An existing verified receipt report is required; this preview does not rerun it. |
| Evidence          | verification_report_checksum_sha256                                         | 837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee       | 837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee                                                                                                                                                                                          | Bound evidence                  | Verified                        | The proposed policy entry binds the exact verification report bytes.             |
| Policy            | allowed_provider_names                                                      | ["manual_reviewed"]                                                    | ["manual_reviewed", "the_odds_api"]                                                                                                                                                                                                                       | Add provider name               | Ready for separate allowlist PR | Proposed canonical provider name: `the_odds_api`.                                |
| Policy            | allowed_provider_types                                                      | ["manual_upload", "sportsbook_export", "odds_api", "fixture_provider"] | ["manual_upload", "sportsbook_export", "odds_api", "fixture_provider"]                                                                                                                                                                                    | Ensure provider type is allowed | Ready for separate allowlist PR | Provider type: `odds_api`.                                                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_key                        | Not present                                                            | odds_api                                                                                                                                                                                                                                                  | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_name                       | Not present                                                            | the_odds_api                                                                                                                                                                                                                                              | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_type                       | Not present                                                            | odds_api                                                                                                                                                                                                                                                  | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.allowlist_status                    | Not present                                                            | allowed                                                                                                                                                                                                                                                   | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.max_provider_run_age_hours          | Not present                                                            | 12.0                                                                                                                                                                                                                                                      | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.cutoff_policy                       | Not present                                                            | {"day": "Thursday", "time": "10:00", "timezone": "America/New_York"}                                                                                                                                                                                      | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.required_markets                    | Not present                                                            | ["1x2", "total_2_5"]                                                                                                                                                                                                                                      | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.known_limitations                   | Not present                                                            | ["BTTS is not requested by the current provider adapter. Missing BTTS prices remain unavailable and must never be fabricated.", "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."] | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.evidence_receipt_id                 | Not present                                                            | odds_api-20260817T155217-0400-8204291a2b19                                                                                                                                                                                                                | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.verification_report_path            | Not present                                                            | data/outputs/provider_human_acceptance_receipt_verification.json                                                                                                                                                                                          | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.verification_report_checksum_sha256 | Not present                                                            | 837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee                                                                                                                                                                                          | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.reviewer_name                       | Not present                                                            | cooperross399                                                                                                                                                                                                                                             | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.reviewed_at                         | Not present                                                            | 2026-08-17T15:52:18-04:00                                                                                                                                                                                                                                 | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.approved_at                         | Not present                                                            | 2026-08-17T15:52:17-04:00                                                                                                                                                                                                                                 | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |

## Current policy

```json
{
  "allow_missing_provenance": false,
  "allow_unknown_providers": false,
  "allowed_provider_names": [
    "manual_reviewed"
  ],
  "allowed_provider_types": [
    "manual_upload",
    "sportsbook_export",
    "odds_api",
    "fixture_provider"
  ],
  "max_provider_run_age_hours": 12,
  "max_receipt_age_hours": 12,
  "thursday_cutoff_time": "10:00",
  "timezone": "America/New_York"
}
```

## Proposed policy

```json
{
  "allow_missing_provenance": false,
  "allow_unknown_providers": false,
  "allowed_provider_names": [
    "manual_reviewed",
    "the_odds_api"
  ],
  "allowed_provider_types": [
    "manual_upload",
    "sportsbook_export",
    "odds_api",
    "fixture_provider"
  ],
  "max_provider_run_age_hours": 12,
  "max_receipt_age_hours": 12,
  "provider_allowlist_entries": {
    "the_odds_api": {
      "allowlist_status": "allowed",
      "approved_at": "2026-08-17T15:52:17-04:00",
      "cutoff_policy": {
        "day": "Thursday",
        "time": "10:00",
        "timezone": "America/New_York"
      },
      "evidence_receipt_id": "odds_api-20260817T155217-0400-8204291a2b19",
      "known_limitations": [
        "BTTS is not requested by the current provider adapter. Missing BTTS prices remain unavailable and must never be fabricated.",
        "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
      ],
      "max_provider_run_age_hours": 12.0,
      "provider_key": "odds_api",
      "provider_name": "the_odds_api",
      "provider_type": "odds_api",
      "required_markets": [
        "1x2",
        "total_2_5"
      ],
      "reviewed_at": "2026-08-17T15:52:18-04:00",
      "reviewer_name": "cooperross399",
      "verification_report_checksum_sha256": "837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee",
      "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
    }
  },
  "thursday_cutoff_time": "10:00",
  "timezone": "America/New_York"
}
```

## Diff preview

```diff
--- data/manual/staging_provider_policy.json (current)
+++ data/manual/staging_provider_policy.json (proposed)
@@ -2,7 +2,8 @@
   "allow_missing_provenance": false,
   "allow_unknown_providers": false,
   "allowed_provider_names": [
-    "manual_reviewed"
+    "manual_reviewed",
+    "the_odds_api"
   ],
   "allowed_provider_types": [
     "manual_upload",
@@ -12,6 +13,34 @@
   ],
   "max_provider_run_age_hours": 12,
   "max_receipt_age_hours": 12,
+  "provider_allowlist_entries": {
+    "the_odds_api": {
+      "allowlist_status": "allowed",
+      "approved_at": "2026-08-17T15:52:17-04:00",
+      "cutoff_policy": {
+        "day": "Thursday",
+        "time": "10:00",
+        "timezone": "America/New_York"
+      },
+      "evidence_receipt_id": "odds_api-20260817T155217-0400-8204291a2b19",
+      "known_limitations": [
+        "BTTS is not requested by the current provider adapter. Missing BTTS prices remain unavailable and must never be fabricated.",
+        "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
+      ],
+      "max_provider_run_age_hours": 12.0,
+      "provider_key": "odds_api",
+      "provider_name": "the_odds_api",
+      "provider_type": "odds_api",
+      "required_markets": [
+        "1x2",
+        "total_2_5"
+      ],
+      "reviewed_at": "2026-08-17T15:52:18-04:00",
+      "reviewer_name": "cooperross399",
+      "verification_report_checksum_sha256": "837ec2d2bb6b0796a66f1714f3168c9f971256b5221d78602bbe1690498a77ee",
+      "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
+    }
+  },
   "thursday_cutoff_time": "10:00",
   "timezone": "America/New_York"
 }
```

## Recommended separate PR

- Title: Allowlist the_odds_api staging provider
- Description:

Adds `the_odds_api` (`odds_api`) to the reviewed staging provider allowlist for 1x2, total_2_5. Binds the policy entry to human acceptance receipt `odds_api-20260817T155217-0400-8204291a2b19` and its verified evidence. Known limitations: BTTS is not requested by the current provider adapter. Missing BTTS prices remain unavailable and must never be fabricated. Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates. This policy-only proposal does not promote staging, run a provider, generate picks, place bets, or enable cron.

## Decision boundary

A Ready preview is evidence for a separate human-reviewed policy PR. It is not an apply command and does not make the provider eligible by itself. Cron remains disabled and requires another separate decision.