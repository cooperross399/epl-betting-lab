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
- Verification SHA-256: `db780554963c79ef24ba2c489ec35a641c82ef63af8490afda3b89184e39615e`
- Human receipt ID: `odds_api-20261019T064821+0000-5e5248a72a82`
- Reviewer: **cooperross399**
- Reviewed at: 2026-10-19T06:48:28+00:00
- Approved at: 2026-10-19T06:48:21+00:00
- Current policy: `data/manual/staging_provider_policy.json`
- Current policy SHA-256: `7a01454f6fc252f39bbe110c8f864fc99d90421876d8c2cb5d22a1d0e68fee3f`

## Blockers

- None.

## Warnings

- None.

## Exact proposed provider fields

```json
{
  "allowlist_status": "allowed",
  "approved_at": "2026-10-19T06:48:21+00:00",
  "cutoff_policy": {
    "day": "Thursday",
    "time": "10:00",
    "timezone": "America/New_York"
  },
  "evidence_receipt_id": "odds_api-20261019T064821+0000-5e5248a72a82",
  "known_limitations": [
    "Player props carry no demonstrated edge: the held-out measurement (data/outputs/player_props_backtest.md) found the corrected model well calibrated and clearing its edge bar about twice a month, and books reprice on the team sheet after the card is built. Approving them approves that trade-off.",
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
    "corners_total_10_5",
    "player_assists",
    "player_goal_scorer_anytime",
    "player_shots",
    "player_shots_on_target"
  ],
  "reviewed_at": "2026-10-19T06:48:28+00:00",
  "reviewer_name": "cooperross399",
  "verification_report_checksum_sha256": "db780554963c79ef24ba2c489ec35a641c82ef63af8490afda3b89184e39615e",
  "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
}
```

## Change table

| category          | field                                                                       | before                                                                 | after                                                                                                                                                                                                                                                                                                                                                                                                                                 | change                          | status                          | details                                                                          |
|:------------------|:----------------------------------------------------------------------------|:-----------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------|:--------------------------------|:---------------------------------------------------------------------------------|
| Evidence          | receipt_verification_verdict                                                | Verified for allowlist PR review                                       | Verified for allowlist PR review                                                                                                                                                                                                                                                                                                                                                                                                      | Required gate                   | Verified                        | An existing verified receipt report is required; this preview does not rerun it. |
| Evidence          | verification_report_checksum_sha256                                         | db780554963c79ef24ba2c489ec35a641c82ef63af8490afda3b89184e39615e       | db780554963c79ef24ba2c489ec35a641c82ef63af8490afda3b89184e39615e                                                                                                                                                                                                                                                                                                                                                                      | Bound evidence                  | Verified                        | The proposed policy entry binds the exact verification report bytes.             |
| Policy            | allowed_provider_names                                                      | ["manual_reviewed", "the_odds_api"]                                    | ["manual_reviewed", "the_odds_api"]                                                                                                                                                                                                                                                                                                                                                                                                   | Add provider name               | Ready for separate allowlist PR | Proposed canonical provider name: `the_odds_api`.                                |
| Policy            | allowed_provider_types                                                      | ["manual_upload", "sportsbook_export", "odds_api", "fixture_provider"] | ["manual_upload", "sportsbook_export", "odds_api", "fixture_provider"]                                                                                                                                                                                                                                                                                                                                                                | Ensure provider type is allowed | Ready for separate allowlist PR | Provider type: `odds_api`.                                                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_key                        | Not present                                                            | odds_api                                                                                                                                                                                                                                                                                                                                                                                                                              | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_name                       | Not present                                                            | the_odds_api                                                                                                                                                                                                                                                                                                                                                                                                                          | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.provider_type                       | Not present                                                            | odds_api                                                                                                                                                                                                                                                                                                                                                                                                                              | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.allowlist_status                    | Not present                                                            | allowed                                                                                                                                                                                                                                                                                                                                                                                                                               | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.max_provider_run_age_hours          | Not present                                                            | 12.0                                                                                                                                                                                                                                                                                                                                                                                                                                  | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.cutoff_policy                       | Not present                                                            | {"day": "Thursday", "time": "10:00", "timezone": "America/New_York"}                                                                                                                                                                                                                                                                                                                                                                  | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.required_markets                    | Not present                                                            | ["1x2", "total_2_5", "btts", "double_chance", "draw_no_bet", "corners_1x2", "corners_total_9_5", "corners_total_10_5", "player_assists", "player_goal_scorer_anytime", "player_shots", "player_shots_on_target"]                                                                                                                                                                                                                      | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.known_limitations                   | Not present                                                            | ["Player props carry no demonstrated edge: the held-out measurement (data/outputs/player_props_backtest.md) found the corrected model well calibrated and clearing its edge bar about twice a month, and books reprice on the team sheet after the card is built. Approving them approves that trade-off.", "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."] | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.evidence_receipt_id                 | Not present                                                            | odds_api-20261019T064821+0000-5e5248a72a82                                                                                                                                                                                                                                                                                                                                                                                            | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.verification_report_path            | Not present                                                            | data/outputs/provider_human_acceptance_receipt_verification.json                                                                                                                                                                                                                                                                                                                                                                      | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.verification_report_checksum_sha256 | Not present                                                            | db780554963c79ef24ba2c489ec35a641c82ef63af8490afda3b89184e39615e                                                                                                                                                                                                                                                                                                                                                                      | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.reviewer_name                       | Not present                                                            | cooperross399                                                                                                                                                                                                                                                                                                                                                                                                                         | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.reviewed_at                         | Not present                                                            | 2026-10-19T06:48:28+00:00                                                                                                                                                                                                                                                                                                                                                                                                             | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |
| Provider controls | provider_allowlist_entries.the_odds_api.approved_at                         | Not present                                                            | 2026-10-19T06:48:21+00:00                                                                                                                                                                                                                                                                                                                                                                                                             | Add reviewed provider control   | Ready for separate allowlist PR | This field is proposed only and was not written to policy.                       |

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
        "corners_total_10_5",
        "player_shots",
        "player_shots_on_target",
        "player_assists",
        "player_goal_scorer_anytime"
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
      "approved_at": "2026-10-19T06:48:21+00:00",
      "cutoff_policy": {
        "day": "Thursday",
        "time": "10:00",
        "timezone": "America/New_York"
      },
      "evidence_receipt_id": "odds_api-20261019T064821+0000-5e5248a72a82",
      "known_limitations": [
        "Player props carry no demonstrated edge: the held-out measurement (data/outputs/player_props_backtest.md) found the corrected model well calibrated and clearing its edge bar about twice a month, and books reprice on the team sheet after the card is built. Approving them approves that trade-off.",
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
        "corners_total_10_5",
        "player_assists",
        "player_goal_scorer_anytime",
        "player_shots",
        "player_shots_on_target"
      ],
      "reviewed_at": "2026-10-19T06:48:28+00:00",
      "reviewer_name": "cooperross399",
      "verification_report_checksum_sha256": "db780554963c79ef24ba2c489ec35a641c82ef63af8490afda3b89184e39615e",
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
@@ -16,14 +16,15 @@
   "provider_allowlist_entries": {
     "the_odds_api": {
       "allowlist_status": "allowed",
-      "approved_at": "2026-08-21T11:46:55-04:00",
+      "approved_at": "2026-10-19T06:48:21+00:00",
       "cutoff_policy": {
         "day": "Thursday",
         "time": "10:00",
         "timezone": "America/New_York"
       },
-      "evidence_receipt_id": "odds_api-20260821T114655-0400-20ffa5677988",
+      "evidence_receipt_id": "odds_api-20261019T064821+0000-5e5248a72a82",
       "known_limitations": [
+        "Player props carry no demonstrated edge: the held-out measurement (data/outputs/player_props_backtest.md) found the corrected model well calibrated and clearing its edge bar about twice a month, and books reprice on the team sheet after the card is built. Approving them approves that trade-off.",
         "Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates."
       ],
       "max_provider_run_age_hours": 12.0,
@@ -39,14 +40,14 @@
         "corners_1x2",
         "corners_total_9_5",
         "corners_total_10_5",
+        "player_assists",
+        "player_goal_scorer_anytime",
         "player_shots",
-        "player_shots_on_target",
-        "player_assists",
-        "player_goal_scorer_anytime"
+        "player_shots_on_target"
       ],
-      "reviewed_at": "2026-08-21T11:47:03-04:00",
+      "reviewed_at": "2026-10-19T06:48:28+00:00",
       "reviewer_name": "cooperross399",
-      "verification_report_checksum_sha256": "a5b59887648b80bd03f4ee8e04d7e6f68281497a7e18d3beac80bb77fc3a51fd",
+      "verification_report_checksum_sha256": "db780554963c79ef24ba2c489ec35a641c82ef63af8490afda3b89184e39615e",
       "verification_report_path": "data/outputs/provider_human_acceptance_receipt_verification.json"
     }
   },
```

## Recommended separate PR

- Title: Update the the_odds_api allowlisted market scope
- Description:

Updates the reviewed allowlist entry for `the_odds_api` (`odds_api`) to cover 1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5, player_assists, player_goal_scorer_anytime, player_shots, player_shots_on_target. Binds the policy entry to human acceptance receipt `odds_api-20261019T064821+0000-5e5248a72a82` and its verified evidence. Known limitations: Player props carry no demonstrated edge: the held-out measurement (data/outputs/player_props_backtest.md) found the corrected model well calibrated and clearing its edge bar about twice a month, and books reprice on the team sheet after the card is built. Approving them approves that trade-off. Allowlisting does not bypass staging validation, freshness, completeness, checksum, receipt, or Thursday cutoff gates. This policy-only proposal does not promote staging, run a provider, generate picks, place bets, or enable cron.

## Decision boundary

A Ready preview is evidence for a separate human-reviewed policy PR. It is not an apply command and does not make the provider eligible by itself. Cron remains disabled and requires another separate decision.