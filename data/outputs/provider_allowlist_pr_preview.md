# Provider Allowlist PR Readiness Preview

**Preview only: nothing was applied.** This report does not edit `staging_provider_policy.json`, allowlist a provider, promote staging, run a provider, generate picks, place bets, or enable cron.

## Status

- **Ready for separate allowlist PR**
- Provider: `the_odds_api` (`odds_api`)
- Current allowlist status: **Allowed**
- Proposed allowlist status: **Allowed**

## Evidence used

- Verification verdict: **Verified for allowlist PR review**
- Verification report: `data/outputs/provider_human_acceptance_receipt_verification.json`
- Verification SHA-256: `a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd`
- Human receipt ID: `odds_api-20260821T114655-0400-20ffa5677988`
- Reviewer: **cooperross399**
- Reviewed at: 2026-08-21T11:47:03-04:00
- Approved at: 2026-08-21T11:46:55-04:00
- Current policy: `data/manual/staging_provider_policy.json`
- Current policy SHA-256: `1a16ba8a70d96ec81ddc6aabd4e7f0e61b0e50982b7893dcc19f178139466dbb`

## Blockers

- None.

## Warnings

- None.

## Exact proposed provider fields

```json
{
  "allowlist_status": "allowed",
  "approved_at": "2026-08-21T11:46:55-04:00",
  "cutoff_policy": {
    "day": "Thursday",
    "time": "10:00",
    "timezone": "America/New_York"
  },
  "evidence_receipt_id": "odds_api-20260821T114655-0400-20ffa5677988",
  "known_limitations": [
    "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
  ],
  "max_provider_run_age_hours": 12.0,
  "provider_key": "odds_api",
  "provider_name": "the_odds_api",
  "provider_type": "odds_api",
  "required_markets": [
    "1x2",
    "total_2_5",
    "btts",
    "double_chance",
    "draw_no_bet",
    "corners_1x2",
    "corners_total_9_5",
    "corners_total_10_5"
  ],
  "reviewed_at": "2026-08-21T11:47:03-04:00",
  "reviewer_name": "cooperross399",
  "verification_report_checksum_sha256": "a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd",
  "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
}
```

## Change table

| category          | field                                                                       | before                                                                 | after                                                                                                                      | change                          | status                          | details                                                                          |
|:------------------|:----------------------------------------------------------------------------|:-----------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------|:--------------------------------|:--------------------------------|:---------------------------------------------------------------------------------|
| Evidence          | receipt_verification_verdict                                                | Verified for allowlist PR review                                       | Verified for allowlist PR review                                                                                           | Required gate                   | Verified                        | An existing verified receipt report is required; this preview does not rerun it. |
| Evidence          | verification_report_checksum_sha256                                         | a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd       | a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd                                                           | Bound evidence                  | Verified                        | The proposed policy entry binds the exact verification report bytes.             |
| Policy            | allowed_provider_names                                                      | ["manual_reviewed", "the_odds_api"]                                    | ["manual_reviewed", "the_odds_api"]                                                                                        | Add provider name               | Ready for separate allowlist PR | Proposed canonical provider name: `the_odds_api`.                                |
| Policy            | allowed_provider_types                                                      | ["manual_upload", "sportsbook_export", "odds_api", "fixture_provider"] | ["manual_upload", "sportsbook_export", "odds_api", "fixture_provider"]                                                     | Ensure provider type is allowed | Ready for separate allowlist PR | Provider type: `odds_api`.                                                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_key                        | Not present                                                            | odds_api                                                                                                                   | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_name                       | Not present                                                            | the_odds_api                                                                                                               | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_type                       | Not present                                                            | odds_api                                                                                                                   | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.allowlist_status                    | Not present                                                            | allowed                                                                                                                    | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.max_provider_run_age_hours          | Not present                                                            | 12.0                                                                                                                       | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.cutoff_policy                       | Not present                                                            | {"day": "Thursday", "time": "10:00", "timezone": "America/New_York"}                                                       | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.required_markets                    | Not present                                                            | ["1x2", "total_2_5", "btts", "double_chance", "draw_no_bet", "corners_1x2", "corners_total_9_5", "corners_total_10_5"]     | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.known_limitations                   | Not present                                                            | ["Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."] | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.evidence_receipt_id                 | Not present                                                            | odds_api-20260821T114655-0400-20ffa5677988                                                                                 | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.verification_report_path            | Not present                                                            | data/outputs/provider_human_acceptance_receipt_verification.json                                                           | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.verification_report_checksum_sha256 | Not present                                                            | a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd                                                           | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.reviewer_name                       | Not present                                                            | cooperross399                                                                                                              | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.reviewed_at                         | Not present                                                            | 2026-08-21T11:47:03-04:00                                                                                                  | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.approved_at                         | Not present                                                            | 2026-08-21T11:46:55-04:00                                                                                                  | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |

## Current policy

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
      "approved_at": "2026-08-17T16:03:07-04:00",
      "cutoff_policy": {
        "day": "Thursday",
        "time": "10:00",
        "timezone": "America/New_York"
      },
      "evidence_receipt_id": "odds_api-20260817T160307-0400-20fb55e75c14",
      "known_limitations": [
        "No market in this system has a demonstrated edge: every measured interval includes zero, `double_chance` measured negative, and `draw_no_bet`'s positive number rests on thirteen bets. Enablement is a reviewed human decision made with that evidence in view, not on it.",
        "`corners_1x2` can never be profit-backtested: the provider does not retain its history. `btts` carries a known, unfixed calibration bias of roughly nine points and cannot be profit-backtested either.",
        "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
      ],
      "max_provider_run_age_hours": 12.0,
      "provider_key": "odds_api",
      "provider_name": "the_odds_api",
      "provider_type": "odds_api",
      "required_markets": [
        "1x2",
        "btts",
        "total_2_5",
        "double_chance",
        "draw_no_bet",
        "corners_1x2",
        "corners_total_9_5",
        "corners_total_10_5"
      ],
      "reviewed_at": "2026-08-17T16:03:08-04:00",
      "reviewer_name": "cooperross399",
      "verification_report_checksum_sha256": "22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a",
      "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
    }
  },
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
      "approved_at": "2026-08-21T11:46:55-04:00",
      "cutoff_policy": {
        "day": "Thursday",
        "time": "10:00",
        "timezone": "America/New_York"
      },
      "evidence_receipt_id": "odds_api-20260821T114655-0400-20ffa5677988",
      "known_limitations": [
        "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
      ],
      "max_provider_run_age_hours": 12.0,
      "provider_key": "odds_api",
      "provider_name": "the_odds_api",
      "provider_type": "odds_api",
      "required_markets": [
        "1x2",
        "total_2_5",
        "btts",
        "double_chance",
        "draw_no_bet",
        "corners_1x2",
        "corners_total_9_5",
        "corners_total_10_5"
      ],
      "reviewed_at": "2026-08-21T11:47:03-04:00",
      "reviewer_name": "cooperross399",
      "verification_report_checksum_sha256": "a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd",
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
@@ -16,16 +16,14 @@
   "provider_allowlist_entries": {
     "the_odds_api": {
       "allowlist_status": "allowed",
-      "approved_at": "2026-08-17T16:03:07-04:00",
+      "approved_at": "2026-08-21T11:46:55-04:00",
       "cutoff_policy": {
         "day": "Thursday",
         "time": "10:00",
         "timezone": "America/New_York"
       },
-      "evidence_receipt_id": "odds_api-20260817T160307-0400-20fb55e75c14",
+      "evidence_receipt_id": "odds_api-20260821T114655-0400-20ffa5677988",
       "known_limitations": [
-        "No market in this system has a demonstrated edge: every measured interval includes zero, `double_chance` measured negative, and `draw_no_bet`'s positive number rests on thirteen bets. Enablement is a reviewed human decision made with that evidence in view, not on it.",
-        "`corners_1x2` can never be profit-backtested: the provider does not retain its history. `btts` carries a known, unfixed calibration bias of roughly nine points and cannot be profit-backtested either.",
         "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
       ],
       "max_provider_run_age_hours": 12.0,
@@ -34,17 +32,17 @@
       "provider_type": "odds_api",
       "required_markets": [
         "1x2",
+        "total_2_5",
         "btts",
-        "total_2_5",
         "double_chance",
         "draw_no_bet",
         "corners_1x2",
         "corners_total_9_5",
         "corners_total_10_5"
       ],
-      "reviewed_at": "2026-08-17T16:03:08-04:00",
+      "reviewed_at": "2026-08-21T11:47:03-04:00",
       "reviewer_name": "cooperross399",
-      "verification_report_checksum_sha256": "22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a",
+      "verification_report_checksum_sha256": "a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd",
       "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
     }
   },
```

## Recommended separate PR

- Title: Update the the_odds_api allowlisted market scope
- Description:

Updates the reviewed allowlist entry for `the_odds_api` (`odds_api`) to cover 1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5. Binds the policy entry to human acceptance receipt `odds_api-20260821T114655-0400-20ffa5677988` and its verified evidence. Known limitations: Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates. This policy-only proposal does not promote staging, run a provider, generate picks, place bets, or enable cron.

## Decision boundary

A Ready preview is evidence for a separate human-reviewed policy PR. It is not an apply command and does not make the provider eligible by itself. Cron remains disabled and requires another separate decision.