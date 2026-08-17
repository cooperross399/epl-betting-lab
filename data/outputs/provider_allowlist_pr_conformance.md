# Provider Allowlist PR Conformance Check

**Read-only check: nothing was applied.** This report compares the current provider policy with an existing reviewed preview. It does not edit policy, allowlist a provider, promote staging, run providers, generate picks, place bets, or enable cron.

## Verdict

- **Conforms to preview**
- Provider: `the_odds_api` (`odds_api`)
- Preview: `data/outputs/provider_allowlist_pr_preview.json`
- Preview status: **Ready for separate allowlist PR**
- Policy checked: `data/manual/staging_provider_policy.json`

## Evidence checks

- Preview SHA-256: `caebfa6c6939ef903d36dfabd5d4de8bcd447aba39bbdeca888d9e723bf5b4db`
- Bound verification SHA-256: `22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a`
- Current verification SHA-256: `22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a`
- Verification checksum status: **Match**
- Current policy SHA-256: `5b591c6f034bedae31d9a3e6517dc0beb818b53ea6332321abc482d51c4d7eb9`

## Check totals

- Match: 25

## Blockers

- None.

## Warnings

- None.

## Expected vs actual checks

| category                 | field                                                                       | baseline                 | expected                                                                                                                                                                                                                                                                                | actual                                                                                                                                                                                                                                                                                  | status   | details                                                               |
|:-------------------------|:----------------------------------------------------------------------------|:-------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------|:----------------------------------------------------------------------|
| Preview evidence         | preview_file                                                                |                          | Readable preview JSON                                                                                                                                                                                                                                                                   | data/outputs/provider_allowlist_pr_preview.json                                                                                                                                                                                                                                         | Match    | The checker reads the existing preview and does not regenerate it.    |
| Preview evidence         | preview_status                                                              |                          | Ready for separate allowlist PR; proposed allowlist status Allowed                                                                                                                                                                                                                      | Ready for separate allowlist PR; Allowed                                                                                                                                                                                                                                                | Match    | Only a Ready, verified preview can define the expected policy change. |
| Provider identity        | provider_key                                                                |                          | odds_api                                                                                                                                                                                                                                                                                | odds_api                                                                                                                                                                                                                                                                                | Match    | The requested provider must match the preview exactly.                |
| Provider identity        | provider_name                                                               |                          | the_odds_api                                                                                                                                                                                                                                                                            | the_odds_api                                                                                                                                                                                                                                                                            | Match    | The requested provider must match the preview exactly.                |
| Provider identity        | provider_type                                                               |                          | odds_api                                                                                                                                                                                                                                                                                | odds_api                                                                                                                                                                                                                                                                                | Match    | The requested provider must match the preview exactly.                |
| Preview evidence         | verification_report_checksum_sha256                                         |                          | 22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a                                                                                                                                                                                                                        | 22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a                                                                                                                                                                                                                        | Match    | The checker re-hashes the verification report bound by the preview.   |
| Policy                   | policy_file                                                                 |                          | data/manual/staging_provider_policy.json                                                                                                                                                                                                                                                | data/manual/staging_provider_policy.json                                                                                                                                                                                                                                                | Match    | The policy is read and hashed; it is never edited by this checker.    |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.allowlist_status                    | Missing                  | allowed                                                                                                                                                                                                                                                                                 | allowed                                                                                                                                                                                                                                                                                 | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.approved_at                         | Missing                  | 2026-08-17T16:03:07-04:00                                                                                                                                                                                                                                                               | 2026-08-17T16:03:07-04:00                                                                                                                                                                                                                                                               | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.cutoff_policy.day                   | Missing                  | Thursday                                                                                                                                                                                                                                                                                | Thursday                                                                                                                                                                                                                                                                                | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.cutoff_policy.time                  | Missing                  | 10:00                                                                                                                                                                                                                                                                                   | 10:00                                                                                                                                                                                                                                                                                   | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.cutoff_policy.timezone              | Missing                  | America/New_York                                                                                                                                                                                                                                                                        | America/New_York                                                                                                                                                                                                                                                                        | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.evidence_receipt_id                 | Missing                  | odds_api-20260817T160307-0400-20fb55e75c14                                                                                                                                                                                                                                              | odds_api-20260817T160307-0400-20fb55e75c14                                                                                                                                                                                                                                              | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.known_limitations                   | Missing                  | ["`total_2_5` is not allowlisted: the reviewed evidence did not find it eligible. Its prices remain unavailable or incomplete and must never be fabricated.", "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."] | ["`total_2_5` is not allowlisted: the reviewed evidence did not find it eligible. Its prices remain unavailable or incomplete and must never be fabricated.", "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."] | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.max_provider_run_age_hours          | Missing                  | 12.0                                                                                                                                                                                                                                                                                    | 12.0                                                                                                                                                                                                                                                                                    | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.provider_key                        | Missing                  | odds_api                                                                                                                                                                                                                                                                                | odds_api                                                                                                                                                                                                                                                                                | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.provider_name                       | Missing                  | the_odds_api                                                                                                                                                                                                                                                                            | the_odds_api                                                                                                                                                                                                                                                                            | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.provider_type                       | Missing                  | odds_api                                                                                                                                                                                                                                                                                | odds_api                                                                                                                                                                                                                                                                                | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.required_markets                    | Missing                  | ["1x2", "btts"]                                                                                                                                                                                                                                                                         | ["1x2", "btts"]                                                                                                                                                                                                                                                                         | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.reviewed_at                         | Missing                  | 2026-08-17T16:03:08-04:00                                                                                                                                                                                                                                                               | 2026-08-17T16:03:08-04:00                                                                                                                                                                                                                                                               | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.reviewer_name                       | Missing                  | cooperross399                                                                                                                                                                                                                                                                           | cooperross399                                                                                                                                                                                                                                                                           | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.verification_report_checksum_sha256 | Missing                  | 22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a                                                                                                                                                                                                                        | 22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a                                                                                                                                                                                                                        | Match    | Required provider fields must match the preview exactly.              |
| Proposed provider fields | provider_allowlist_entries.the_odds_api.verification_report_path            | Missing                  | data/outputs/provider_human_acceptance_receipt_verification.json                                                                                                                                                                                                                        | data/outputs/provider_human_acceptance_receipt_verification.json                                                                                                                                                                                                                        | Match    | Required provider fields must match the preview exactly.              |
| Expected policy changes  | allowed_provider_names                                                      | ["manual_reviewed"]      | ["manual_reviewed", "the_odds_api"]                                                                                                                                                                                                                                                     | ["manual_reviewed", "the_odds_api"]                                                                                                                                                                                                                                                     | Match    | This is an intended policy change recorded by the preview.            |
| Safety                   | cron_or_automation_enablement                                               | No newly enabled setting | No newly enabled setting                                                                                                                                                                                                                                                                | No newly enabled setting detected                                                                                                                                                                                                                                                       | Match    | Allowlisting and cron remain separate decisions.                      |

## Expected policy

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
        "`total_2_5` is not allowlisted: the reviewed evidence did not find it eligible. Its prices remain unavailable or incomplete and must never be fabricated.",
        "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
      ],
      "max_provider_run_age_hours": 12.0,
      "provider_key": "odds_api",
      "provider_name": "the_odds_api",
      "provider_type": "odds_api",
      "required_markets": [
        "1x2",
        "btts"
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

## Actual policy

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
        "`total_2_5` is not allowlisted: the reviewed evidence did not find it eligible. Its prices remain unavailable or incomplete and must never be fabricated.",
        "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
      ],
      "max_provider_run_age_hours": 12.0,
      "provider_key": "odds_api",
      "provider_name": "the_odds_api",
      "provider_type": "odds_api",
      "required_markets": [
        "1x2",
        "btts"
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

## Expected/actual diff

```diff
No differences. The current policy matches the previewed policy.
```

## Baseline/current diff

```diff
--- preview baseline staging_provider_policy.json
+++ current staging_provider_policy.json
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
+      "approved_at": "2026-08-17T16:03:07-04:00",
+      "cutoff_policy": {
+        "day": "Thursday",
+        "time": "10:00",
+        "timezone": "America/New_York"
+      },
+      "evidence_receipt_id": "odds_api-20260817T160307-0400-20fb55e75c14",
+      "known_limitations": [
+        "`total_2_5` is not allowlisted: the reviewed evidence did not find it eligible. Its prices remain unavailable or incomplete and must never be fabricated.",
+        "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
+      ],
+      "max_provider_run_age_hours": 12.0,
+      "provider_key": "odds_api",
+      "provider_name": "the_odds_api",
+      "provider_type": "odds_api",
+      "required_markets": [
+        "1x2",
+        "btts"
+      ],
+      "reviewed_at": "2026-08-17T16:03:08-04:00",
+      "reviewer_name": "cooperross399",
+      "verification_report_checksum_sha256": "22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a",
+      "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
+    }
+  },
   "thursday_cutoff_time": "10:00",
   "timezone": "America/New_York"
 }
```

## What the verdict means

`Conforms to preview` means the complete policy document matches the reviewed after-policy exactly and no automation change was detected. Any missing field, changed value, extra policy edit, stale verification evidence, or automation enablement must be resolved before merge.

Allowlisting and cron remain separate decisions. Passing this checker does not enable a provider for scheduled runs and does not authorize any automated betting action.