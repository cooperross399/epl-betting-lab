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
| `pr:` missing | Refused |
| `pr:` naming a different PR | Refused |
| A review in state DISMISSED, CHANGES_REQUESTED, PENDING or COMMENTED | Refused, by name |
| A review with no state at all | Refused |
| A later `REVOKED_FOR_ALLOWLIST_PR` from you | Refused |
| The approval block appearing only inside a `>` quotation | Refused |
| Approval older than 72 hours | Refused |
| A caller asking for a window longer than 72 hours | Refused |
| Approval timestamp in the future | Refused |
| Evidence regenerated *after* you approved | Refused |
| Any expected evidence artifact absent or unreadable | Refused |
| Review approved a commit that has since been superseded | Refused |
| No evidence artifacts to bind to | Refused |
| No `gh` at a trusted absolute location | Refused |

Approving and then pushing a new commit, or approving and then re-running the
provider verification, both invalidate the approval — you approved a specific
state, and the state changed.

`pr:` is required rather than optional. Without it the block bound to whichever
pull request the verifier was pointed at, so one approval could be spent on a
pull request nobody had read.

An expected evidence artifact that is missing is a refusal, not a narrower
binding. Deleting two of the four used to produce an approval bound to two,
with nothing saying so.

---

## Withdrawing an approval

Leave a comment or review containing:

```
REVOKED_FOR_ALLOWLIST_PR
```

A revocation from an allowed reviewer that is newer than — or the same age as —
the approval refuses the approval outright. Before this token existed, only the
newest comment *carrying the approval phrase* was read, so a plain-English
withdrawal was invisible and the withdrawn approval kept verifying until it
aged out.

Do not quote the approval block while withdrawing it. A quoted block is not
read at all now, which is the fix for the worse version of the same problem: a
comment reading "REVOKED. Ignore this: > APPROVED_FOR_ALLOWLIST_PR …" used to
parse as a brand new approval, because `> ` was stripped like a bullet marker.

---

## What the card checks when it builds

The provider policy file is a committed record of a decision. It is not the
decision. Every card build re-reads
`data/outputs/provider_human_acceptance_receipt.json` and refuses any market
the receipt does not actually approve — checking the reviewer against the
allow-list in the source, the receipt id the policy names, the recorded review
state, that every expected artifact is bound, and that
`provider_acceptance_checklist.json` still hashes to what the receipt printed.

A market the policy claims and the receipt does not is disabled, and the reason
is printed in the card input report. Editing the policy is not approving
anything.

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
    --decision rejected --write-receipt
```

The GitHub flow is not merely the better attestation of the two; it is now the
only one. `--reviewer-name` is typed by whoever runs the command, while a
GitHub review is authenticated as you, so the Terminal command no longer offers
`--decision approved_for_allowlist_pr` at all.

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

`--activity-json` replays a saved API response through the rules offline. It
cannot be combined with `--write-receipt`: a saved file is indistinguishable
from a fetched one, so a receipt is only ever written from activity this command
fetched from GitHub itself, through a `gh` resolved at a trusted absolute
location rather than through `PATH`.
