# EPL Scheduled Tasks Bridge

This document connects the three Claude scheduled tasks/routines to concrete
repository outputs:

| Routine | Command | Outputs |
|:--------|:--------|:--------|
| **EPL Model** | `scripts/run_epl_model_task.py` | `data/outputs/epl_model_task.{md,json}` |
| **EPL CARD** | `scripts/run_epl_card_task.py` | `data/outputs/epl_card_task.{md,json}` |
| **EPL SETTLE (IGNORE)** | `scripts/run_epl_settle_preview_task.py` | `data/outputs/epl_settle_preview_task.{md,json}` |

All three are **read-only status bridges**. They read report JSON that other
commands already produced. None of them fetches odds, runs a provider, edits a
protected manual file, places a bet, applies settlement, or enables cron.

> **Scheduling is not configured from this repository.** These scripts do not
> create, edit, or enable any schedule. Claude Code did not modify your
> scheduled tasks; the prompts below are for you to paste manually.

---

## Running them

```bash
PYTHONPATH=src .venv/bin/python scripts/run_epl_model_task.py
PYTHONPATH=src .venv/bin/python scripts/run_epl_card_task.py
PYTHONPATH=src .venv/bin/python scripts/run_epl_settle_preview_task.py
```

Exit codes: `0` = ready / no blockers, `2` = blocked (this is the normal state
until the gates pass), `1` = runtime failure.

Each bridge reads whatever evidence currently exists on disk. Refresh the
upstream reports first when you want current answers:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_week1_launch_readiness.py
```

**Stale evidence is reported as missing, never as passing.** If a report is
absent or unreadable, the bridge emits a blocker rather than assuming the gate
passed.

---

## EPL Model

**Question it answers:** is the model ready, and may EPL CARD run?

Reads `week1_launch_readiness.json` and `provider_shadow_verification.json`.

Reports:

- model readiness
- fixture freshness
- selected slate/window
- odds status (completeness, missing rows, validation warnings)
- provider/shadow status (verdict, handoff eligibility, policy)
- mapping coverage (and which team names are unmapped)
- market coverage — core 1X2/totals **separately** from BTTS
- blockers
- exact next action
- whether EPL CARD is ready

`epl_card_ready` is the field the EPL CARD routine should gate on.

---

## EPL CARD

**Question it answers:** may the card publish selections?

The card carries selections **only** when every gate passes. While blocked it
returns empty lists — `best_bets`, `leans`, `passes_or_avoids`,
`unit_suggestions` — and sets `picks_suppressed: true`.

> An empty card here means **blocked**, not "no value found". The markdown says
> `withheld` explicitly so the two cannot be confused.

When `handoff_eligible` is false the card reports named blockers from this fixed
vocabulary:

- `Needs odds`
- `Needs mapping`
- `Needs BTTS`
- `Needs validation`
- `Provider not trusted`
- `Needs fixtures`

**EPL CARD only pushes picks when validation passes.** There is no override
flag, and provider output is never used as a pick source while it is shadow-only.

---

## EPL SETTLE (IGNORE)

**Preview only.** It reads `data/manual/bet_ledger.csv` and reports row counts,
open bets, and settled bets. `would_settle_count` is always `0`.

It never:

- applies settlement
- edits `bet_ledger.csv`
- uses force mode
- places bets

This is enforced structurally, not by a default: `build_epl_settle_preview_task`
has **no** `apply`, `force`, `settle`, or `write` parameter, and a test asserts
those parameter names do not exist. The ledger is opened read-only.

---

## Exact routine prompts

Claude Code does not edit your scheduled tasks. Paste these into the routine
definitions yourself.

### EPL Model

```text
Run the EPL Model readiness bridge in ~/Downloads/epl-betting-lab.

Command:
PYTHONPATH=src .venv/bin/python scripts/run_epl_model_task.py

Rules:
- Do not generate official picks.
- Do not run live providers.
- Do not allowlist the provider.
- Do not edit protected manual files.
- Do not apply settlement or place bets.
- Do not enable cron.

Report: model readiness, fixture freshness, selected slate/window, odds status,
provider/shadow status, mapping coverage, market coverage (core vs BTTS),
blockers, exact next action, and whether EPL CARD is ready.
```

### EPL CARD

```text
Run the EPL CARD bridge in ~/Downloads/epl-betting-lab.

Command:
PYTHONPATH=src .venv/bin/python scripts/run_epl_card_task.py

Rules:
- If card_ready is false, do NOT invent or publish any pick, lean, or stake.
- Report blockers instead: Needs odds / Needs mapping / Needs BTTS /
  Needs validation / Provider not trusted.
- Do not run live providers.
- Do not allowlist the provider.
- Do not edit protected manual files.
- Do not place bets.

Report: card status, best bets / leans / passes only if the card is actually
ready, unit suggestions only if ready, validation warnings, odds completeness,
provider/source used, blockers, and the exact next action.
```

### EPL SETTLE (IGNORE)

```text
Run the EPL settle PREVIEW bridge in ~/Downloads/epl-betting-lab.

Command:
PYTHONPATH=src .venv/bin/python scripts/run_epl_settle_preview_task.py

Rules:
- Preview only.
- Never apply settlement.
- Never edit bet_ledger.csv.
- Never use force mode.
- Never place bets.

Report: ledger rows, open bets, settled bets, would-settle count (always 0),
blockers, and the exact next action.
```

---

## Safe vs unsafe actions

| Safe (automated) | Unsafe (ask a human first) |
|:-----------------|:---------------------------|
| Running the three bridge commands | Filling official odds |
| Re-running Week 1 readiness | Generating picks while `handoff_eligible` is false |
| Dry-run provider commands | Editing any protected manual file |
| Reading reports under `data/outputs/` | Allowlisting the provider |
| Reporting blockers | Enabling cron or scheduled workflows |
| | Applying settlement |
| | Changing core model logic |
| | Using force / overwrite modes |

Protected manual files — never edited by these bridges:

```text
data/manual/current_odds.csv
data/manual/current_odds_import.csv
data/manual/bet_ledger.csv
data/manual/odds_import_profiles.json
data/manual/staging_provider_policy.json
```

---

## Provider trust status

**Provider odds remain shadow/untrusted until the allowlist policy passes.**

A completed provider run is not approval. The sequence is:

1. Shadow verification passes its technical gates (mapping, coverage,
   checksums, provenance, age).
2. You review repeated shadow evidence manually across several runs.
3. You deliberately edit `data/manual/staging_provider_policy.json` to allow
   `the_odds_api`. No script does this for you.
4. Only then can `handoff_eligible` become true and the card use provider data.

Until step 3, `epl_card_task.json` reports
`provider_source.source_used: "none (provider output is shadow-only and
untrusted)"` and `trusted: false`.

BTTS deserves its own note: when the provider returns zero BTTS rows, that is
reported as `Unavailable`, never as trusted and never as a zero price. The
recommended action is manual BTTS odds or a provider/market configuration
change — never a fabricated number. Core 1X2/totals coverage is reported
separately so a BTTS gap does not hide otherwise-usable coverage.
