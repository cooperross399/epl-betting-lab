# Approving a provider allowlist PR from the GitHub UI

Allowlisting a provider needs a human acceptance receipt. This document is the
terminal-free way to produce one: you approve in the GitHub UI, and the
Provider Policy PR Gate transcribes your approval into the receipt.

> **The approval is yours, not the automation's.** The reviewer identity comes
> from GitHub's API, so the tooling can verify an approval but cannot author
> one. There is no flag that makes it sign on your behalf.

---

## Steps

### 1. Open the PR

Go to the pull request that changes `data/manual/staging_provider_policy.json`.

### 2. Review the evidence

Before approving, read these from the PR's **Checks** tab or the repository's
`data/outputs/` reports:

| Artifact | What to confirm |
|:---------|:----------------|
| `provider_acceptance_checklist.md` | Verdict is `Ready for human allowlist review` |
| `provider_trust_packet.md` | Coverage, quota, and safety flags look right |
| `automated_card_input.md` | Included markets are the ones you intend |
| `provider_shadow_verification.md` | Mapping verified, no failed runs |

Check specifically that the **included** markets are the ones you intend.
The reviewed scope is whatever the PR's proposed policy lists in
`required_markets` — the gate reads it from the PR head, and your approval
must name exactly that scope. (`total_2_5` was excluded until 2026-08-19,
when the line was found complete in `alternate_totals`; it is approvable
like any other market now.)

### 3. Approve with the approval block

Leave either a **PR review** (Files changed → Review changes → Approve) or a
**PR comment**, containing exactly this:

```text
APPROVED_FOR_ALLOWLIST_PR
pr: <PR NUMBER>
provider: the_odds_api
markets: 1x2, btts
```

All four lines matter:

- `APPROVED_FOR_ALLOWLIST_PR` — the phrase that marks the comment as an approval
- `pr:` — binds the approval to one PR, so it cannot be reused elsewhere
- `provider:` — binds it to one provider
- `markets:` — binds it to a market scope

Markdown bullets and different capitalisation are tolerated
(`- PR: 115`, `* Provider: The_Odds_API` both parse).

### 4. Wait for checks

Submitting the review re-triggers **Provider Policy PR Gate**. It will:

1. regenerate the acceptance checklist and evidence bundle
2. read your review/comment from the GitHub API
3. verify the approval and write the receipt
4. run the existing conformance, bundle, and receipt verifications
5. pass or fail on the real gate result

If it passes, the PR is mergeable. If it fails, the log names the reason.

---

## What gets refused

Every one of these fails closed and produces **no receipt**:

| Condition | Result |
|:----------|:-------|
| Approval phrase missing | Refused |
| Author is not an allowed reviewer | Refused |
| Someone else quotes your approval text | Refused |
| `provider:` missing or naming another provider | Refused |
| `markets:` missing | Refused |
| `markets:` naming a market the project cannot price | Refused |
| Market scope narrower or wider than the PR's proposed `required_markets` | Refused |
| `pr:` naming a different PR | Refused |
| Approval older than 72 hours | Refused |
| Approval timestamp in the future | Refused |
| Evidence regenerated *after* you approved | Refused |
| Review approved a commit that has since been superseded | Refused |
| No evidence artifacts to bind to | Refused |

The last two matter most in practice. Approving and then pushing a new commit,
or approving and then re-running the provider verification, both invalidate the
approval — you approved a specific state, and the state changed.

---

## What the receipt records

Your approval is bound into the receipt, so the audit trail shows where the
human act happened rather than merely asserting that one occurred:

- PR number and repository
- your GitHub login
- whether it was a review or a comment, and its ID
- the approval timestamp and age
- the PR head SHA and the reviewed commit
- provider, approved markets, excluded markets
- SHA-256 of every evidence artifact at approval time

---

## If you would rather use the terminal

The original command still exists and is unchanged:

```bash
PYTHONPATH=src .venv/bin/python scripts/create_provider_human_acceptance_receipt.py \
    --provider odds_api --reviewer-name "Your Name" \
    --decision approved_for_allowlist_pr --write-receipt
```

The GitHub flow is the better attestation of the two: `--reviewer-name` is
typed by whoever runs the command, while a GitHub review is authenticated as
you.

---

## Verifying without approving

To check what the verifier sees, or to print the exact text to paste:

```bash
# print the approval block for a PR
PYTHONPATH=src .venv/bin/python scripts/create_receipt_from_github_approval.py \
    --pr 115 --print-template

# verify an existing approval without writing a receipt
PYTHONPATH=src .venv/bin/python scripts/create_receipt_from_github_approval.py \
    --pr 115 --repository cooperross399/epl-betting-lab
```

Neither writes anything without `--write-receipt`.
