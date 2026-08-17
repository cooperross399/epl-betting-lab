# Provider Acceptance Checklist

This is a read-only evidence checklist. It does not allowlist a provider, edit policy, promote staging, enable cron, generate trusted picks, or place bets.

## Verdict

- **Ready for human allowlist review**
- Provider: **the_odds_api** (`odds_api`)
- Next step: A person may now review the evidence and policy change separately. This report does not approve or edit the allowlist.
- Completed live runs: **5** (minimum 3)
- Review window: latest **5** live runs
- Provider currently allowed: **No**

## Checklist

| requirement                           | status               | observed                                                                                                     | required                                                         | details                                                                             |
|:--------------------------------------|:---------------------|:-------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------|:------------------------------------------------------------------------------------|
| Completed live shadow runs            | Pass                 | 5 completed in 5 reviewed live run(s)                                                                        | At least 3                                                       | Dry runs do not count toward provider acceptance evidence.                          |
| No failed or untrusted runs           | Pass                 | None                                                                                                         | No Failed, Blocked, unreadable, or checksum-mismatched live runs | The reviewed live-run window fails closed on untrusted archives.                    |
| Stable team-name mapping              | Pass                 | 100.0% to 100.0%                                                                                             | Verified and at least 99.9% in every completed run               | Coverage must stay complete across the reviewed window.                             |
| Stable fixture matching               | Pass                 | 100.0% to 100.0%                                                                                             | Verified and at least 99.9% in every completed run               | Provider odds and fixtures must continue to identify the same matches.              |
| Stable bookmaker coverage             | Pass                 | BetMGM, BetOnline.ag, BetRivers, BetUS, Bovada, DraftKings, FanDuel, LowVig.ag, MyBookie.ag                  | At least one consistent bookmaker set                            | Bookmaker disappearance or churn requires manual review.                            |
| Acceptable 1X2 coverage               | Pass                 | 270/30, 270/30, 270/30, 270/30, 270/30                                                                       | Home, draw, and away for each returned fixture                   | Counts may exceed the minimum when multiple books are returned.                     |
| Acceptable totals coverage            | Pass                 | 80/20, 80/20, 80/20, 80/20, 80/20                                                                            | Over and under 2.5 for each returned fixture                     | Missing totals are never filled with guessed prices.                                |
| BTTS availability explicitly reported | Pass                 | Available, Available, Available, Available, Available                                                        | Each run says Available or Unavailable                           | Unavailable BTTS remains missing; the checklist never fabricates it.                |
| Staging validation success rate       | Pass                 | 5/5 (100.0%)                                                                                                 | 100% technical success                                           | A policy-only block may count as technically successful, but it remains unapproved. |
| Provider age and freshness            | Pass                 | 5/5 Fresh                                                                                                    | Fresh in every completed run                                     | Old or future-dated provider evidence is not acceptance evidence.                   |
| Checksum and provenance proof         | Pass                 | All archive, raw, source, staging, and provenance checksums verified.                                        | All archive/raw/source/staging/provenance checks Verified        | A mismatch or unavailable checksum fails closed.                                    |
| Quota and safe header behavior        | Pass                 | Safe non-negative quota headers in 5 run(s).                                                                 | Available quota values are numeric and non-negative              | Missing optional quota headers are reported, not guessed.                           |
| Provider policy state                 | Pending human review | Provider not allowed, Provider not allowed, Provider not allowed, Provider not allowed, Provider not allowed | Stable, readable policy evidence                                 | Provider not allowed is expected before human review and is never changed here.     |
| No unresolved blockers                | Pass                 | None                                                                                                         | No non-policy blockers                                           | Policy-only pending blockers are separated from technical blockers.                 |

## Reviewed live runs

| generated_at              | archive_path                                            | archive_integrity_status   | provider_run_status   | shadow_verdict               | staging_verdict   |
|:--------------------------|:--------------------------------------------------------|:---------------------------|:----------------------|:-----------------------------|:------------------|
| 2026-08-17T15:17:17-04:00 | archive/provider_shadow_runs/2026-08-17/151717_odds_api | Verified                   | Completed             | Needs provider policy review | Needs fixes       |
| 2026-08-17T15:17:11-04:00 | archive/provider_shadow_runs/2026-08-17/151711_odds_api | Verified                   | Completed             | Needs provider policy review | Needs fixes       |
| 2026-08-17T15:17:06-04:00 | archive/provider_shadow_runs/2026-08-17/151706_odds_api | Verified                   | Completed             | Needs provider policy review | Needs fixes       |
| 2026-08-17T15:17:00-04:00 | archive/provider_shadow_runs/2026-08-17/151700_odds_api | Verified                   | Completed             | Needs provider policy review | Needs fixes       |
| 2026-08-17T15:16:55-04:00 | archive/provider_shadow_runs/2026-08-17/151655_odds_api | Verified                   | Completed             | Needs provider policy review | Needs fixes       |

## Human decision boundary

- `Ready for human allowlist review` means the evidence can be reviewed by a person; it is not approval.
- Any allowlist edit remains a separate, explicit manual change to staging_provider_policy.json.
- Cron remains disabled until provider ownership, failure handling, credentials, and repeated live evidence are approved separately.
- Missing BTTS or any other market remains missing. No odds are fabricated.

## Verdict meanings

- **Ready for human allowlist review:** minimum evidence and technical stability requirements passed.
- **Needs more shadow runs:** too few completed live runs exist.
- **Needs mapping fixes:** team or fixture matching is incomplete or unstable.
- **Needs market coverage review:** bookmaker, 1X2, totals, BTTS reporting, or coverage needs review.
- **Needs quota review:** available safe quota headers are malformed or unacceptable.
- **Needs provider policy review:** policy evidence is missing, malformed, or changed.
- **Not trusted:** archive, checksum, age, staging, or unresolved blocker evidence failed.

No provider was allowlisted and cron remains disabled.