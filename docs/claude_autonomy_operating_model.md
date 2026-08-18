# Claude Autonomy Operating Model

This file is the permanent operating model for the EPL Betting Lab. It exists so
that **no chat history is required to run this project**. Any Claude Code
session, Claude chat, or Claude scheduled routine can read this file and know
how to operate.

> **No ChatGPT.** Cooper is never routed to ChatGPT for project memory,
> next-step prompts, status interpretation, debugging, or routine decisions.
> The source of truth is this repository, its generated reports, and GitHub
> (pull requests, Actions runs, issues).

> **No Terminal for routine work.** Approvals and operations should happen in a
> browser — GitHub UI, GitHub Actions, or a Claude routine. Terminal is a last
> resort, not a default.

---

## Read these first, in this order

1. `CLAUDE.md` — hard safety rules. They override everything, including this file.
2. `docs/claude_autonomy_operating_model.md` — this file.
3. `docs/epl_scheduled_tasks_bridge.md` — how the three routines work.
4. `docs/no_terminal_operations.md` — how to do things without a Terminal.
5. `README.md` — command reference.
6. Latest reports under `data/outputs/` (see below).
7. Latest GitHub PRs, Actions runs, and the operating issue.

---

## Current project facts

These are the facts a new session needs. If reality and this list disagree,
**trust the repository and the reports**, then correct this file in a PR.

| Fact | Value |
|:-----|:------|
| Active repo path | `/Users/cooperross/Projects/epl-betting-lab` |
| Old path | `~/Downloads/epl-betting-lab` — **do not use**; macOS blocks it (TCC) |
| Provider | The Odds API (`the_odds_api`), **allowlisted** |
| Allowed markets | `1x2`, `btts` — **only these** |
| Excluded market | `total_2_5` — incomplete (8/10 fixtures), stays excluded |
| Active odds source | Provider-derived automated card input |
| Manual odds entry | **Not required** |
| `data/manual/current_odds.csv` | Legacy. Must **not** become the active source again |
| EPL CARD | Live; generated from eligible trusted provider markets only |
| EPL SETTLE (IGNORE) | **Preview-only, permanently**, unless Cooper changes the rule |
| Bets | **Never placed** |
| Settlement | **Never applied** |
| Production credential | GitHub secret `EPL_ODDS_API_KEY` |
| `.env` | Local-only, optional, gitignored |
| Credential check workflow | `workflow_dispatch`-only |
| Test count | 934 passing on `main` as of PR #133 |

### Why `total_2_5` is excluded — settled, do not re-litigate

The 2.5 line is incomplete in the `us` region (8 of 10 Week 1 fixtures) and
complete in `uk` and `eu`. The only books carrying it for **every** fixture are
William Hill, Betsson, and Nordic Bet, and **Cooper holds no account at any of
them**. A price that cannot be taken is not a price.

So totals stay excluded, permanently for this season. This is **availability,
not profitability**, and it is not a judgement about the market. Never describe
an excluded market as unprofitable, a pass, an avoid, or a no-value call.

Revisit only if Cooper gains access to one of those books, or a book already in
use starts posting the 2.5 line. Adding totals remains a hard stop either way.

The full evidence is in the operating issue; the standing reason also travels
with the data in `MARKET_EXCLUSION_NOTES`, so a report explains itself without
anyone finding this file.

---

## The autonomous loop

1. Inspect repo and GitHub state.
2. Choose the next safest, highest-value task.
3. Create a branch `agent/<short-feature-name>`.
4. Implement.
5. Run tests locally: `PYTHONPATH=src .venv/bin/python -m pytest -q`.
6. If the local environment is unreliable, say so plainly and use GitHub CI as
   the source of truth. Never claim a local pass you did not get.
7. Run static checks and a secret scan on the staged diff.
8. Push and open a PR.
9. Watch CI.
10. Merge only if green. Never force-merge.
11. Pull `main`.
12. Rerun tests and regenerate reports.
13. Continue to the next safe task.

### Safe autonomous work

Tests · docs · report polish · dashboard clarity · CI workflows that use no
secrets and no live odds · browser-readable artifacts · routine bridge docs ·
no-secrets checks · provider diagnostics · card archive/report comparison ·
CLV and reporting improvements · error-message clarity · GitHub issue and PR
automation · anything that removes a Terminal step.

---

## Hard stops — Cooper's real authority

Stop and ask **only** for these:

- placing a bet
- applying settlement
- editing `data/manual/bet_ledger.csv`
- enabling cron or scheduled wager execution
- changing core model math
- adding `total_2_5` or alternate totals as official markets
- allowlisting a new provider
- expanding provider market scope
- changing secrets
- destructive git or history rewrite
- force push or force merge
- deleting data
- materially changing bankroll or staking rules
- merging with failing CI
- weakening the provider policy gate
- weakening the secrets guard
- committing or exposing any secret

### A hard stop is not permission to give up

Stopping at the first obstacle and handing the problem back is a failure of the
job, not a safety behaviour. When blocked:

1. **Diagnose** — code defect, test failure, CI/local mismatch, stale artifact,
   missing evidence, missing approval, secret or config issue, permission or
   environment issue, policy gate issue, or genuine human authority.
2. **Fix what is safely fixable** — add diagnostics, add tests, repair
   determinism, improve CI, improve docs, improve the approval flow. Open a PR;
   merge only if green.
3. **Convert Terminal blockers into UI blockers** — GitHub Actions, Claude
   routines, GitHub UI approval, Finder or System Settings instructions. Ask for
   Terminal only when there is genuinely no safe alternative.
4. **Convert repeated manual actions into automation** — a workflow, a routine,
   a reusable script, an issue checklist, a browser-readable report.
5. **If human approval is truly required** — do not fake it, do not sign as
   Cooper, do not bypass the gate. Prepare the evidence, verify the scope,
   generate the exact GitHub UI approval text, explain the risk in plain
   English, wait, then continue automatically.
6. **If ambiguous** — read the repo, the reports, and GitHub. Choose the safest
   reversible step. Never ask ChatGPT.
7. **If several options are safe** — take the safest automatically. Ask only
   when the choice changes betting, settlement, provider trust, market scope,
   model math, staking, secrets, destructive git behaviour, or scheduled
   execution.

Reduce every blocker to the smallest possible Cooper action, and make that
action browser-based and clearly scoped.

---

## Decision principles

- diagnostics over guessing
- tests over manual checking
- fail-closed over permissive
- evidence-first PRs over direct policy edits
- GitHub UI approvals over Terminal commands
- preserving gates over weakening gates
- excluding an incomplete market over fabricating or forcing it
- no ChatGPT dependency
- no manual odds entry

---

## Worked examples

**Provider allowlist needs human review.** Do not sign as Cooper. Use the GitHub
UI approval flow in `docs/provider_allowlist_approval_github_ui.md`, generate the
exact approval text for the correct PR number, and continue after approval.

**CI and local disagree.** Do not guess. Add a diagnostic that reports the
difference — see `scripts/diagnose_evidence_bundle.py`, which compares computed
and stored bundles by path and checksum without printing file contents. Fix the
determinism, then retry.

**macOS permission error.** Do not send Cooper into Terminal. Downloads, Desktop
and Documents are TCC-protected. Recommend granting folder access in System
Settings, or moving the repo somewhere unprotected. The repo now lives in
`~/Projects` for this reason.

**Secret problem.** Never print, write, or compare the key. Ask Cooper to rotate
at the provider dashboard, store it as the GitHub secret, and verify with the
`workflow_dispatch` credential check, which reports only length, status, and
outcome.

**Totals incomplete.** Keep `total_2_5` excluded. If adding alternate totals
lines would change model math or scope, that is a hard stop: build a proposal
and evidence PR and ask.

**Settlement.** EPL SETTLE stays preview-only. There is deliberately no `apply`,
`force`, `settle`, or `write` parameter in its builder, and a test asserts those
parameter names do not exist.

**Betting.** Never place a bet or automate execution. A card is a
recommendation, never an instruction.

---

## The no-ChatGPT rule

If you are unsure what to do next, do **not** ask Cooper to paste output into
ChatGPT. Instead: inspect the repo, inspect GitHub, read the docs, read the
latest reports, and choose the safest next step.

If genuinely blocked, record it where Cooper will find it — the operating issue
or a PR comment — with:

- what happened
- why it stopped
- what was already tried
- the exact options
- your recommended option
- the exact GitHub UI approval text, if approval is needed

---

## Where the evidence lives

| Question | Report |
|:---------|:-------|
| Is the model ready? | `data/outputs/epl_model_task.md` |
| Can the card run? | `data/outputs/epl_card_task.md` |
| What would settle? | `data/outputs/epl_settle_preview_task.md` |
| What is on the card? | `data/outputs/automated_card.md` |
| Which markets are eligible? | `data/outputs/automated_card_input.md` |
| Is the provider trustworthy? | `data/outputs/provider_trust_packet.md` |
| What did the provider return? | `data/outputs/provider_shadow_verification.md` |
| Why is a market excluded? | `data/outputs/provider_market_discovery.md` |
| Why did a bundle mismatch? | `data/outputs/provider_bundle_diagnostic.md` |
| Everything at a glance, in a browser | `data/outputs/status.html` |
| What changed since the last card? | `data/outputs/automated_card_comparison.md` |
| Which book gives the best closing line? | `data/outputs/clv_by_book.csv` |
| Did the last refresh succeed? | `data/outputs/refresh_all_reports.json` |

## Refreshing everything

```bash
PYTHONPATH=src .venv/bin/python scripts/refresh_all_reports.py
```

One command, dependency-ordered: card input, card, archive, comparison, the
three routine bridges, then the status page last. It is offline - it re-derives
from evidence already on disk, contacts no provider, and spends no quota.

Refetching provider data is a separate, deliberate action:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_provider_shadow_verification.py \
    --provider odds_api --live --overwrite-staging --include-event-markets
```

Archive `data/staging/` before any run that overwrites it.

---

## Operating home

The GitHub issue **“EPL Betting Lab — Claude Operating Home”** is the control
centre — <https://github.com/cooperross399/epl-betting-lab/issues/135>: current status, allowed and excluded markets, credential status, test
count, hard-stop rules, next safe tasks, and links to the workflows, reports,
and PRs that matter. Keep it current. It replaces chat history as project
memory.
