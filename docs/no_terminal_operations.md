# Operating without a Terminal

Everything routine in this project can be done from a browser. This file lists
how, and what the remaining exceptions are.

The design goal: **Cooper approves and reads; Claude does the work.** A Terminal
step is treated as a defect to be engineered away, not a normal cost of running
the project.

---

## What Cooper actually does

| Task | Where | How |
|:-----|:------|:----|
| Approve a provider allowlist PR | GitHub UI | Paste the approval block into a PR review or comment |
| See card status | GitHub / report | `data/outputs/epl_card_task.md` or the routine output |
| See model readiness | GitHub / report | `data/outputs/epl_model_task.md` |
| Check the API credential | GitHub Actions | Run **Provider Credential Check** → *Run workflow* |
| See what changed | GitHub | PR list and Actions runs |
| Track the project | GitHub Issues | “EPL Betting Lab — Claude Operating Home” |

None of these require a command line.

---

## Approving a provider allowlist PR

Full detail in `docs/provider_allowlist_approval_github_ui.md`. In short: open
the PR, review the evidence, and leave a review or comment containing the
approval block:

```text
APPROVED_FOR_ALLOWLIST_PR
pr: <PR NUMBER>
provider: the_odds_api
markets: 1x2, btts
```

The approval binds to PR number, provider, and market scope, so it cannot be
reused elsewhere or silently widened. Submitting it re-triggers the gate, which
verifies the approval and transcribes it into the receipt.

The automation **cannot** author an approval — the reviewer identity comes from
GitHub's API. That is the point: the attestation stays genuinely Cooper's.

---

## Checking the API credential

**GitHub → Actions → Provider Credential Check → Run workflow.**

It reports whether the provider accepted the credential. It never prints,
writes, or compares the key; only its length appears, as a bare integer. It
calls the sports-list endpoint, so it costs **0 quota** and fetches **no odds**.

A healthy run looks like:

```text
Credential present: Yes
Credential length: 32
Endpoint: https://api.the-odds-api.com/v4/sports (quota cost 0)
Authenticated: Yes
HTTP status: 200
Outcome: The provider accepted the credential.
```

If it reports rejected, rotate the key at the Odds API dashboard and update the
repository secret `EPL_ODDS_API_KEY` in **Settings → Secrets and variables →
Actions**. No Terminal involved.

---

## macOS folder permissions

`~/Downloads`, `~/Desktop`, and `~/Documents` are protected by macOS privacy
controls (TCC). A process without permission gets `Operation not permitted` on
reads that look like they should work, with normal-looking file permissions.

That is why the repo lives at `/Users/cooperross/Projects/epl-betting-lab`.
**Do not move it back into a protected folder.**

If a permission error appears anyway, fix it in the GUI:

**System Settings → Privacy & Security → Files and Folders** → enable folder
access for the app running Claude Code. If it is not listed, use **Full Disk
Access** instead. Restart the app afterwards.

---

## What still needs a Terminal, and why

| Action | Why it is not browser-based yet |
|:-------|:--------------------------------|
| Running the local test suite | Fast local feedback; CI covers it on every PR |
| Regenerating reports locally | Convenience; the routines can do it instead |
| Live provider shadow runs | Consumes quota and writes staging evidence, so it stays deliberate |

None of these are required of Cooper. Claude runs them. If Claude's local
environment breaks, CI is the source of truth and the work continues.

---

## Turning a Terminal step into a browser step

The standing pattern when a manual step appears:

1. Can a GitHub workflow do it? Prefer `workflow_dispatch` so it stays
   deliberate rather than scheduled.
2. Can a Claude scheduled routine do it and write a report?
3. Can it become a committed artifact Cooper simply reads?
4. Can it become a GitHub issue checklist?

Only if all four fail should a Terminal command be suggested — and then with the
exact command, and an explanation of why nothing safer works.

---

## What is deliberately not automated

Some things stay manual because automating them would remove a judgement that
should be human:

- **Placing bets.** Never automated. The card is a recommendation.
- **Applying settlement.** EPL SETTLE is preview-only and has no write path.
- **Allowlisting a provider.** Requires a real GitHub approval from Cooper.
- **Adding a market.** Scope changes are reviewed, never inferred from data.
- **Scheduled execution of wagers.** Not enabled, and not to be enabled.

These are not gaps in the automation. They are the boundary of it.
