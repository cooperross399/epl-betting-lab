# Provider Policy PR Gate

**Read-only PR check: nothing was applied.** This gate only reads Git change metadata, committed evidence reports, archived evidence, and the provider policy. It writes report outputs only.

## Verdict

- **Provider policy PR gate passed**
- Provider: **the_odds_api** (`odds_api`)
- Policy changed: **Yes**
- Gate mode: `local_worktree`
- Generated at: `2026-08-17T16:05:24-04:00`
- Detection source: Local Git diff against default branch
- Base ref: `origin/main`
- Head ref: `HEAD`
- Base SHA: `a2648d68a853edf657c7bff48ee522c0b8d45c3c`
- Head SHA: `a2648d68a853edf657c7bff48ee522c0b8d45c3c`
- Merge base SHA: `a2648d68a853edf657c7bff48ee522c0b8d45c3c`

## Gate receipt

- Receipt binding: **Bound**
- Comparison context: **Bound**
- Gate receipt ID: `odds_api-provider-policy-gate-19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0`
- Gate receipt SHA-256: `19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0`
- Changed-files digest: `8bd72883253dfbe756681e35e7284d24379016c30d27adaceab86b403e304967`
- Evidence digest: `1c3fa0a773ff419c704f35933d26055a9d14a3ae319ab7b074d6fce17b59d93f`
- Policy-change digest: `2ad20e03ae455270ada512a21bcab74a9bc68784c83ef0147c6d9355100469bf`
- Binding note: The exact Git comparison, changed-file contents, current policy, and required evidence reports are checksum-bound.

## Changed files

- `data/manual/staging_provider_policy.json`
- `data/outputs/provider_allowlist_evidence_bundle.json`
- `data/outputs/provider_allowlist_evidence_bundle.md`
- `data/outputs/provider_allowlist_evidence_bundle_verification.json`
- `data/outputs/provider_allowlist_evidence_bundle_verification.md`

## Changed-file content digests

- `data/manual/staging_provider_policy.json`: `5b591c6f034bedae31d9a3e6517dc0beb818b53ea6332321abc482d51c4d7eb9` (Hashed, working tree)
- `data/outputs/provider_allowlist_evidence_bundle.json`: `3de3890eb0e73db23920751ee1ae8ac3ef2fb641002f4254742c29929680501c` (Hashed, working tree)
- `data/outputs/provider_allowlist_evidence_bundle.md`: `45a25f99d05e07b3b1089beed716a78bfda3512826965545d6871cd945e4a196` (Hashed, working tree)
- `data/outputs/provider_allowlist_evidence_bundle_verification.json`: `10ff27d53438245d06a6f2a473b35a1412daf0108151168cd55b7a6126c0c2ba` (Hashed, working tree)
- `data/outputs/provider_allowlist_evidence_bundle_verification.md`: `9576c7a5c046f822ff5621573588f7e0993773538a6310c17013656b47ad735f` (Hashed, working tree)

## Evidence report digests

- `data/outputs/provider_allowlist_pr_conformance.json`: `646647836148fbbf332f264e81600a15e7575eccaa0098e1ee05c3a79e383d25` (Included)
- `data/outputs/provider_allowlist_evidence_bundle_verification.json`: `10ff27d53438245d06a6f2a473b35a1412daf0108151168cd55b7a6126c0c2ba` (Included)
- `data/outputs/provider_allowlist_pr_preview.json`: `caebfa6c6939ef903d36dfabd5d4de8bcd447aba39bbdeca888d9e723bf5b4db` (Included)
- `data/outputs/provider_human_acceptance_receipt_verification.json`: `22fa32fb6d0316128d6b89c53736ad943d787c6be2828b25c87d0c9982da653a` (Included)

## Blockers

- None.

## Gate checks

| category           | check                                       | evidence_path                                                     | expected                                               | observed                                        | status   | details                                                                                                            | gate_receipt_id                                                                                | base_sha                                 | head_sha                                 | changed_files_digest                                             | evidence_digest                                                  | policy_change_digest                                             | receipt_binding_status   |
|:-------------------|:--------------------------------------------|:------------------------------------------------------------------|:-------------------------------------------------------|:------------------------------------------------|:---------|:-------------------------------------------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------------------|:-----------------------------------------|:-----------------------------------------|:-----------------------------------------------------------------|:-----------------------------------------------------------------|:-----------------------------------------------------------------|:-------------------------|
| Change detection   | Provider policy changed                     | data/manual/staging_provider_policy.json                          | Policy path present in changed files                   | Policy path changed                             | Passed   | Verified provider evidence is required before this PR can pass.                                                    | odds_api-provider-policy-gate-19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0 | a2648d68a853edf657c7bff48ee522c0b8d45c3c | a2648d68a853edf657c7bff48ee522c0b8d45c3c | 8bd72883253dfbe756681e35e7284d24379016c30d27adaceab86b403e304967 | 1c3fa0a773ff419c704f35933d26055a9d14a3ae319ab7b074d6fce17b59d93f | 2ad20e03ae455270ada512a21bcab74a9bc68784c83ef0147c6d9355100469bf | Bound                    |
| Evidence bundle    | Verified allowlist evidence bundle          | data/outputs/provider_allowlist_evidence_bundle_verification.json | Evidence bundle verified for PR approval review        | Evidence bundle verified for PR approval review | Passed   | Stored and current bundle verification are approval-ready and match.                                               | odds_api-provider-policy-gate-19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0 | a2648d68a853edf657c7bff48ee522c0b8d45c3c | a2648d68a853edf657c7bff48ee522c0b8d45c3c | 8bd72883253dfbe756681e35e7284d24379016c30d27adaceab86b403e304967 | 1c3fa0a773ff419c704f35933d26055a9d14a3ae319ab7b074d6fce17b59d93f | 2ad20e03ae455270ada512a21bcab74a9bc68784c83ef0147c6d9355100469bf | Bound                    |
| Preview            | Ready provider allowlist preview            | data/outputs/provider_allowlist_pr_preview.json                   | Ready for separate allowlist PR                        | Ready for separate allowlist PR                 | Passed   | The preview is ready and proposes the reviewed allowlist entry.                                                    | odds_api-provider-policy-gate-19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0 | a2648d68a853edf657c7bff48ee522c0b8d45c3c | a2648d68a853edf657c7bff48ee522c0b8d45c3c | 8bd72883253dfbe756681e35e7284d24379016c30d27adaceab86b403e304967 | 1c3fa0a773ff419c704f35933d26055a9d14a3ae319ab7b074d6fce17b59d93f | 2ad20e03ae455270ada512a21bcab74a9bc68784c83ef0147c6d9355100469bf | Bound                    |
| Human review       | Verified human acceptance receipt           | data/outputs/provider_human_acceptance_receipt_verification.json  | Verified for allowlist PR review                       | Verified for allowlist PR review                | Passed   | Human acceptance evidence remains verified for allowlist PR review.                                                | odds_api-provider-policy-gate-19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0 | a2648d68a853edf657c7bff48ee522c0b8d45c3c | a2648d68a853edf657c7bff48ee522c0b8d45c3c | 8bd72883253dfbe756681e35e7284d24379016c30d27adaceab86b403e304967 | 1c3fa0a773ff419c704f35933d26055a9d14a3ae319ab7b074d6fce17b59d93f | 2ad20e03ae455270ada512a21bcab74a9bc68784c83ef0147c6d9355100469bf | Bound                    |
| Policy conformance | Current policy conforms to reviewed preview | data/outputs/provider_allowlist_pr_conformance.json               | Conforms to preview                                    | Conforms to preview                             | Passed   | Stored and rerun conformance checks match the reviewed preview.                                                    | odds_api-provider-policy-gate-19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0 | a2648d68a853edf657c7bff48ee522c0b8d45c3c | a2648d68a853edf657c7bff48ee522c0b8d45c3c | 8bd72883253dfbe756681e35e7284d24379016c30d27adaceab86b403e304967 | 1c3fa0a773ff419c704f35933d26055a9d14a3ae319ab7b074d6fce17b59d93f | 2ad20e03ae455270ada512a21bcab74a9bc68784c83ef0147c6d9355100469bf | Bound                    |
| Safety             | No cron or automation enablement            | data/manual/staging_provider_policy.json                          | No newly enabled cron, schedule, or automation setting | No unsafe automation change detected            | Passed   | The conformance check found no newly enabled automation setting.                                                   | odds_api-provider-policy-gate-19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0 | a2648d68a853edf657c7bff48ee522c0b8d45c3c | a2648d68a853edf657c7bff48ee522c0b8d45c3c | 8bd72883253dfbe756681e35e7284d24379016c30d27adaceab86b403e304967 | 1c3fa0a773ff419c704f35933d26055a9d14a3ae319ab7b074d6fce17b59d93f | 2ad20e03ae455270ada512a21bcab74a9bc68784c83ef0147c6d9355100469bf | Bound                    |
| Receipt binding    | Deterministic PR comparison receipt         | data/manual/staging_provider_policy.json                          | Bound                                                  | Bound                                           | Bound    | The exact Git comparison, changed-file contents, current policy, and required evidence reports are checksum-bound. | odds_api-provider-policy-gate-19445f63256d300a2af5fb7eb33738b8f0b824fbe0cc74b014dc8bac186377a0 | a2648d68a853edf657c7bff48ee522c0b8d45c3c | a2648d68a853edf657c7bff48ee522c0b8d45c3c | 8bd72883253dfbe756681e35e7284d24379016c30d27adaceab86b403e304967 | 1c3fa0a773ff419c704f35933d26055a9d14a3ae319ab7b074d6fce17b59d93f | 2ad20e03ae455270ada512a21bcab74a9bc68784c83ef0147c6d9355100469bf | Bound                    |

## Safety boundary

Passing this gate confirms only that a provider-policy PR matches the reviewed evidence. It does not edit policy, allowlist a provider by itself, promote staging, run providers, create receipts or previews, generate picks, place bets, require secrets, or enable cron.