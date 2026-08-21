# Provider Shadow Verification

A shadow run evaluates provider staging evidence without generating trusted picks, promoting files, changing policy, enabling cron, or placing bets.

## Verdict

- **Shadow ready for review**
- Mode: **Live shadow run**
- Reason: The live bundle passed current technical gates; manual review is still required.
- Next step: Review raw evidence and repeat several manual shadow runs before any provider allowlist or scheduling decision.

## Provider and evidence

- Provider: **the_odds_api** (odds_api)
- Provider run status: **Completed**
- Network request made: **Yes**
- Raw evidence: **Created** | ['data/staging/raw/20260821T154335Z_9ed629a2fed4_odds_api_response.json']
- Raw evidence checksum: **Verified**
- Provider age: **Fresh**
- Provenance: **Verified**

## Coverage

- Team mapping: **Verified** | 20/20 mapped
- Unmapped teams: none
- Fixture matching: **Verified** | 15/15 matched
- Markets: 1X2 345 rows; totals 180 rows; BTTS 176 rows
- Missing market coverage: none
- Core markets (1X2 + totals): **Complete** | 525 rows
- BTTS availability: **Available** | 176 rows | trusted: No
- Odds completeness: 100.0%
- Bookmakers (11): ['BetMGM', 'BetOnline.ag', 'BetRivers', 'BetUS', 'Bovada', 'Caesars', 'DraftKings', 'FanDuel', 'Fanatics', 'LowVig.ag', 'MyBookie.ag']

## Fixture coverage by scope

Each row uses a different denominator. A high percentage against provider-returned fixtures does **not** mean the slate is covered.

| Scope | Denominator | Status | Covered | Coverage |
|:------|:------------|:-------|:--------|:---------|
| `provider_returned` | fixtures the provider actually returned in this run | **Complete** | 15/15 | 100.0% |
| `selected_week1_window` | fixtures inside the selected Week 1 window (2026-08-21 through 2026-08-24) | **Complete** | 10/10 | 100.0% |
| `full_upcoming_fixtures` | every fixture in data/manual/upcoming_fixtures.csv | **Incomplete** | 14/20 | 70.0% |

- Selected Week 1 window: **2026-08-21 through 2026-08-24**
- Fixtures in the selected window without provider odds: none

## BTTS availability

- Status: **Available** (176 rows)
- Treated as trusted: **No**
- Any price fabricated: **No**
- Recommended action: none; BTTS rows were returned.
- Core 1X2/totals coverage is reported separately: **Complete** (525 rows)

## Existing gates

- Staging validation: **Ready for handoff**
- Handoff eligible: **Yes**
- Provider policy: **Provider allowed**
- Provider currently allowed: **Yes**
- This report never edits the allowlist.

## Safe API usage

- Quota status: **Available**
- Requests remaining: 6518
- Requests used: 13482
- Last request cost: 2
- Credentials are never included in this report.

## Blockers

- None.

## Warnings

- The provider repeated 20 `corners_total_10_5` row(s) for the same fixture, selection and book. The first price was kept and the repeats ignored; no price was guessed.
- The provider repeated 22 `corners_total_9_5` row(s) for the same fixture, selection and book. The first price was kept and the repeats ignored; no price was guessed.
- The provider repeated 32 `total_2_5` row(s) for the same fixture, selection and book. The first price was kept and the repeats ignored; no price was guessed.
- Staging validation was not run automatically. The checked-in provider policy must explicitly allow `the_odds_api` before this bundle can become Ready for handoff.
- Current odds validation found 489 warning(s). Review them before trusting the card.
- `upcoming_fixtures.csv` holds 20 fixtures but the selected Week 1 window holds only 10. Coverage percentages differ by scope.

## Check table

| category   | check                            | status                  | value                                                                                                                                  | details                                                                                                                                                                                                                                                                                                                       |
|:-----------|:---------------------------------|:------------------------|:---------------------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Shadow run | shadow_verdict                   | Shadow ready for review | Live shadow run                                                                                                                        | The live bundle passed current technical gates; manual review is still required.                                                                                                                                                                                                                                              |
| Provider   | provider_run_status              | Completed               | True                                                                                                                                   | Network request made is reported without exposing credentials.                                                                                                                                                                                                                                                                |
| Evidence   | raw_evidence                     | Created                 | ["data/staging/raw/20260821T154335Z_9ed629a2fed4_odds_api_response.json"]                                                              | Raw evidence checksum: Verified.                                                                                                                                                                                                                                                                                              |
| Evidence   | source_odds_checksum_status      | Verified                | Verified                                                                                                                               | Status comes from the existing staging provenance verifier.                                                                                                                                                                                                                                                                   |
| Evidence   | source_fixtures_checksum_status  | Verified                | Verified                                                                                                                               | Status comes from the existing staging provenance verifier.                                                                                                                                                                                                                                                                   |
| Evidence   | staging_odds_checksum_status     | Verified                | Verified                                                                                                                               | Status comes from the existing staging provenance verifier.                                                                                                                                                                                                                                                                   |
| Evidence   | staging_fixtures_checksum_status | Verified                | Verified                                                                                                                               | Status comes from the existing staging provenance verifier.                                                                                                                                                                                                                                                                   |
| Evidence   | odds_checksum_pair_status        | Verified                | Verified                                                                                                                               | Status comes from the existing staging provenance verifier.                                                                                                                                                                                                                                                                   |
| Evidence   | fixtures_checksum_pair_status    | Verified                | Verified                                                                                                                               | Status comes from the existing staging provenance verifier.                                                                                                                                                                                                                                                                   |
| Provider   | provider_age                     | Fresh                   | 0.005                                                                                                                                  | Provider run is 0.0 minute(s) old; policy allows up to 12 hour(s).                                                                                                                                                                                                                                                            |
| Coverage   | team_name_mapping                | Verified                | 1.0                                                                                                                                    | Unmapped teams: none.                                                                                                                                                                                                                                                                                                         |
| Coverage   | fixture_matching                 | Verified                | 1.0                                                                                                                                    | Unmatched odds: none; fixtures without odds: none.                                                                                                                                                                                                                                                                            |
| Coverage   | slate_provider_returned          | Complete                | 1.0                                                                                                                                    | Denominator: fixtures the provider actually returned in this run; covered 15/15; missing: none.                                                                                                                                                                                                                               |
| Coverage   | slate_selected_week1_window      | Complete                | 1.0                                                                                                                                    | Denominator: fixtures inside the selected Week 1 window (2026-08-21 through 2026-08-24); covered 10/10; missing: none.                                                                                                                                                                                                        |
| Coverage   | slate_full_upcoming_fixtures     | Incomplete              | 0.7                                                                                                                                    | Denominator: every fixture in data/manual/upcoming_fixtures.csv; covered 14/20; missing: ['2026-08-28: crystal palace vs man city', '2026-08-29: aston villa vs arsenal', '2026-08-29: coventry vs hull', "2026-08-29: liverpool vs nott'm forest", '2026-08-30: man united vs ipswich', '2026-08-30: sunderland vs fulham']. |
| Coverage   | btts_availability                | Available               | 176                                                                                                                                    | Trusted: False; fabricated: False. BTTS rows were returned.                                                                                                                                                                                                                                                                   |
| Coverage   | core_market_coverage             | Complete                | 525                                                                                                                                    | 1X2 and totals coverage only. BTTS availability is reported separately and is never inferred from these markets.                                                                                                                                                                                                              |
| Coverage   | market_1x2                       | Returned                | 345                                                                                                                                    | No missing price is inferred or fabricated.                                                                                                                                                                                                                                                                                   |
| Coverage   | market_total_2_5                 | Returned                | 180                                                                                                                                    | No missing price is inferred or fabricated.                                                                                                                                                                                                                                                                                   |
| Coverage   | market_btts                      | Returned                | 176                                                                                                                                    | No missing price is inferred or fabricated.                                                                                                                                                                                                                                                                                   |
| Coverage   | bookmaker_coverage               | Available               | ["BetMGM", "BetOnline.ag", "BetRivers", "BetUS", "Bovada", "Caesars", "DraftKings", "FanDuel", "Fanatics", "LowVig.ag", "MyBookie.ag"] | Rows by bookmaker: {'BetMGM': 160, 'BetOnline.ag': 91, 'BetRivers': 190, 'BetUS': 36, 'Bovada': 187, 'Caesars': 110, 'DraftKings': 190, 'FanDuel': 250, 'Fanatics': 148, 'LowVig.ag': 36, 'MyBookie.ag': 91}.                                                                                                                 |
| Validation | odds_completeness                | Complete                | 1.0                                                                                                                                    | Incomplete matches: 0.                                                                                                                                                                                                                                                                                                        |
| Validation | staging_validation_verdict       | Ready for handoff       | True                                                                                                                                   | The existing staging and GitHub handoff gates remain authoritative.                                                                                                                                                                                                                                                           |
| Policy     | provider_allowed                 | Allowed                 | Provider allowed                                                                                                                       | The shadow verifier never changes the provider policy.                                                                                                                                                                                                                                                                        |
| Provider   | api_quota                        | Available               | {"requests_last": "2", "requests_remaining": "6518", "requests_used": "13482", "status": "Available"}                                  | Only the provider's safe request-usage headers are included.                                                                                                                                                                                                                                                                  |

## Verdict meanings

- **Shadow ready for review:** technical checks passed; manual review still comes first.
- **Needs mapping fixes:** provider team or fixture identities need reviewed mappings.
- **Needs market coverage review:** required prices, including BTTS when absent, remain incomplete.
- **Needs provider policy review:** data passed, but the provider is not allowlisted.
- **Blocked:** a safety, evidence, age, validation, or credential gate stopped the run.
- **Failed:** a runtime/reporting failure prevented verification.

Cron remains disabled, and this report cannot generate or approve a bet.