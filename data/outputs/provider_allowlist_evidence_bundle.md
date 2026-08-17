# Provider Allowlist PR Evidence Bundle

**Nothing was applied.** This checksum-bound report only gathers and verifies existing review evidence. It does not edit provider policy, allowlist a provider, promote staging, run providers, generate picks, place bets, or enable cron.

## Bundle verdict

- **Missing required evidence**
- Provider: **the_odds_api** (`odds_api`)
- Bundle ID: `odds_api-allowlist-evidence-a7c07f43eeccf893`
- Bundle SHA-256: `a7c07f43eeccf89376f7daf2181c9f0fe530973b5959eb9820a2cfb18777f2de`
- Included checksum entries: **5**

## Review decisions

- Preview verdict: **Blocked**
- Conformance verdict: **Not applicable**
- Receipt verification verdict: **Missing evidence**
- Human receipt ID: `Missing`
- Checklist verdict: **Ready for human allowlist review**

## Included evidence and status

| evidence_type                                  | evidence_path                                                    | required   | expected_checksum_sha256                                         | current_checksum_sha256                                          | status         | verdict                          | generated_at              | details                                                                                                                                                                                                                                                                                                                                                                                              |
|:-----------------------------------------------|:-----------------------------------------------------------------|:-----------|:-----------------------------------------------------------------|:-----------------------------------------------------------------|:---------------|:---------------------------------|:--------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| provider_allowlist_pr_preview                  | data/outputs/provider_allowlist_pr_preview.json                  | Yes        |                                                                  | 606c716557072566e10367de0e8bd96acb4c962437fa4b00e4e91a707c85f575 | Stale          | Blocked                          | 2026-08-17T15:14:10-04:00 | Preview is not Ready for a separate allowlist PR. Ready preview is missing recommended PR text.                                                                                                                                                                                                                                                                                                      |
| provider_human_acceptance_receipt_verification | data/outputs/provider_human_acceptance_receipt_verification.json | Yes        | b054f130f1042667641fa6252c330ae37d36eecc5d247ba71855e01d98278241 | b054f130f1042667641fa6252c330ae37d36eecc5d247ba71855e01d98278241 | Stale          | Missing evidence                 | 2026-08-12T15:02:15-04:00 | Human receipt verification is not Verified for allowlist PR review. Receipt verification does not record approval. Receipt verification does not record a Ready acceptance checklist.                                                                                                                                                                                                                |
| provider_human_acceptance_receipt              | data/outputs/provider_human_acceptance_receipt.json              | Yes        |                                                                  |                                                                  | Missing        |                                  |                           | receipt is missing.                                                                                                                                                                                                                                                                                                                                                                                  |
| provider_acceptance_checklist                  | data/outputs/provider_acceptance_checklist.json                  | Yes        |                                                                  | 7aa6af6017dcf0b243fa43add16307df4877d77f8b079aa0d9ac9e324331dd98 | Stale          | Ready for human allowlist review | 2026-08-17T15:17:20-04:00 | Human receipt does not bind the checklist checksum. Human receipt references a different checklist file.                                                                                                                                                                                                                                                                                             |
| reviewed_shadow_archives                       | data/outputs/archive/provider_shadow_runs                        | Yes        |                                                                  |                                                                  | Missing        |                                  |                           | The human receipt does not bind any reviewed shadow archive.                                                                                                                                                                                                                                                                                                                                         |
| provider_shadow_run_comparison                 | data/outputs/provider_shadow_run_comparison.json                 | Yes        |                                                                  | bd726c676cc3a63e1ec9fe283881febbedd08b04513abf4d6e2c2aacce0d081f | Stale          | Needs more shadow runs           | 2026-08-04T11:59:59-04:00 | Human receipt does not bind the comparison checksum. Human receipt did not bind a shadow comparison. Human receipt references a different comparison file. Shadow comparison is not stable enough for review. Human receipt records a different comparison verdict. Shadow comparison does not identify the newest two reviewed live archives. No reviewed shadow archives are bound by the receipt. |
| provider_allowlist_pr_conformance              | data/outputs/provider_allowlist_pr_conformance.json              | No         |                                                                  |                                                                  | Not applicable |                                  |                           | No policy change has been checked yet; conformance is optional before PR review.                                                                                                                                                                                                                                                                                                                     |
| staging_provider_policy                        | data/manual/staging_provider_policy.json                         | Yes        | 23d88241a66c9cc86b59d4278694b4e1522fd48048c268e0744dd217020b21d3 | 23d88241a66c9cc86b59d4278694b4e1522fd48048c268e0744dd217020b21d3 | Stale          |                                  |                           | Human receipt did not bind the provider policy. Human receipt references a different provider policy file. Evidence references a different provider policy file.                                                                                                                                                                                                                                     |

## Checksum manifest

```json
[
  {
    "checksum_sha256": "23d88241a66c9cc86b59d4278694b4e1522fd48048c268e0744dd217020b21d3",
    "path": "data/manual/staging_provider_policy.json"
  },
  {
    "checksum_sha256": "7aa6af6017dcf0b243fa43add16307df4877d77f8b079aa0d9ac9e324331dd98",
    "path": "data/outputs/provider_acceptance_checklist.json"
  },
  {
    "checksum_sha256": "606c716557072566e10367de0e8bd96acb4c962437fa4b00e4e91a707c85f575",
    "path": "data/outputs/provider_allowlist_pr_preview.json"
  },
  {
    "checksum_sha256": "b054f130f1042667641fa6252c330ae37d36eecc5d247ba71855e01d98278241",
    "path": "data/outputs/provider_human_acceptance_receipt_verification.json"
  },
  {
    "checksum_sha256": "bd726c676cc3a63e1ec9fe283881febbedd08b04513abf4d6e2c2aacce0d081f",
    "path": "data/outputs/provider_shadow_run_comparison.json"
  }
]
```

## Recommended provider allowlist PR

- Title: Not available
- Description:

Generate a Ready allowlist PR preview before opening a policy PR.

## Decision boundary

A ready bundle proves which evidence bytes were reviewed; it does not make the policy change. Provider allowlisting remains a separate PR, and cron remains disabled until a later independent review explicitly enables it.