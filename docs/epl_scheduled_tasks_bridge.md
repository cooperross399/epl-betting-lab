# EPL Scheduled Tasks Bridge

> **API-first mode.** Odds come from The Odds API, not from a hand-filled
> template. `data/manual/current_odds.csv` is no longer the active source and
> **no manual odds entry is required**. See
> [API-first odds workflow](#api-first-odds-workflow) below.

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

## API-first odds workflow

The manual odds-entry job is gone. Odds are derived from provider staging
evidence and written **outside** `data/manual/`.

```text
live provider shadow/staging fetch
  -> staging validation + team normalization
  -> per-market eligibility (data/outputs/automated_card_input.json)
  -> provider-derived card input (data/staging/automated_card_current_odds.csv)
  -> EPL Model / EPL CARD bridges
```

Build the card input:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_api_first_card_workflow.py
```

The writer **refuses** any path under `data/manual/` and raises
`ProtectedPathError` rather than touching a protected file.

### Market eligibility

Eligibility is decided **per market**, so one absent market no longer blocks the
whole card:

| State | Meaning | Used for picks? |
|:------|:--------|:----------------|
| `eligible` | Provider covers every fixture in the window; mapping, validation and freshness pass | ✅ Yes |
| `incomplete` | Provider covers only some fixtures | ❌ Excluded (not partially used) |
| `unavailable` | Provider returned no rows at all (BTTS today) | ❌ Excluded |
| `disabled` | Deliberately excluded from automated picks | ❌ Excluded |

**BTTS is disabled by default** (`DEFAULT_DISABLED_MARKETS`) because the featured
endpoint does not return it. Requiring it would reintroduce a manual entry job.

> An excluded market is **never** a pass, a lean, an avoid, or a "no value"
> call. It is reported as unavailable/incomplete/disabled, and no price is ever
> invented to fill the gap.

Current Week 1 state: **1X2 eligible** (10/10 fixtures), **totals incomplete**
(8/10), **BTTS disabled** — so the automated card is 1X2-only, which is exactly
the intended behaviour when only some markets are complete.

### Price selection

Where several bookmakers priced the same selection, the **best real quote** is
taken (lowest implied probability) and the source book is preserved. That is a
choice among real prices — never an average, a synthetic line, or a fabricated
number.

---

## Market discovery: why a market is excluded

A market is only excluded once it is **shown** to be unavailable or incomplete —
never because the first integration missed it, and never for profitability.

```bash
# Free: analyses the archived raw response, no network request
PYTHONPATH=src .venv/bin/python scripts/run_provider_market_discovery.py

# Paid: queries the per-event endpoint (cost reported before spending)
PYTHONPATH=src .venv/bin/python scripts/run_provider_market_discovery.py \
    --check-event-markets --regions us --markets btts
```

Outputs `data/outputs/provider_market_discovery.{md,json}`.

### Two endpoints, deliberately kept separate

| Endpoint | Serves | Notes |
|:---|:---|:---|
| `/v4/sports/{sport}/odds` (bulk/featured) | `h2h`, `spreads`, `totals` | Additional markets are **never** returned here, whatever regions or bookmakers you request |
| `/v4/sports/{sport}/events/{id}/odds` | additional markets incl. `btts` | Costs `markets × regions` **per event** |

Conflating these is what produced the earlier wrong conclusion. BTTS missing
from the bulk response is **expected** and is *not* evidence the provider lacks
BTTS — the report now says so explicitly and reports `not_checked` rather than
`unavailable` until the event endpoint has actually been queried.

### Quota

`/events` listing is free. Odds requests cost `markets × regions`; the event
endpoint charges that per event. The script prints the estimate **before**
making any paid call, and paid calls are opt-in via `--check-event-markets`.

### Fetching event markets into staging

`--include-event-markets` on the provider entry points merges per-event BTTS
into the bulk payload before normalisation. The merged payload is re-serialised
as the archived raw evidence so the checksum pair still matches. A per-event
failure records a warning and leaves the market **missing** — never fabricated.

---

## Provider trust / allowlist path

```bash
PYTHONPATH=src .venv/bin/python scripts/build_provider_trust_packet.py
```

Produces `data/outputs/provider_trust_packet.{md,json}` consolidating the
acceptance checklist, coverage by scope, market eligibility, quota, and safety
flags, plus the exact approval still needed.

The existing acceptance process is used, not bypassed: it requires **3 completed
live shadow runs**. Allowlisting is a human edit to
`data/manual/staging_provider_policy.json`; no script in this repository makes
that change.

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
