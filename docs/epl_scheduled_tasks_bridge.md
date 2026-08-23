# EPL Scheduled Tasks Bridge

> **API-first mode.** Odds come from The Odds API, not from a hand-filled
> template. `data/manual/current_odds.csv` is no longer the active source and
> **no manual odds entry is required**. See
> [API-first odds workflow](#api-first-odds-workflow) below.

This document connects the Claude scheduled tasks/routines to concrete
repository outputs. Two routines are live — **EPL CARD** and **EPL WATCH**
(the routine formerly named EPL Model; scripts and outputs keep the old
name):

| Routine | Command | Outputs |
|:--------|:--------|:--------|
| **EPL WATCH** (formerly EPL Model) | `scripts/run_epl_model_task.py` | `data/outputs/epl_model_task.{md,json}` |
| **EPL CARD** | `scripts/run_epl_card_task.py` | `data/outputs/epl_card_task.{md,json}` |
| **EPL SETTLE (IGNORE)** — not currently deployed | `scripts/run_epl_settle_preview_task.py` | `data/outputs/epl_settle_preview_task.{md,json}` |

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

## EPL WATCH (formerly EPL Model)

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

## These routines are no longer how the card gets made

Read this before pasting anything below.

The card is produced by **GitHub Actions**
(`.github/workflows/matchday-refresh.yml`), ten triggers a week across five
matchdays, on GitHub's
infrastructure. It fetches results, fetches prices, rebuilds every report, and
renders the card on the run page. It needs no laptop, no terminal, and nothing
from these routines. That is the self-sustaining path and it is proven end to
end.

The routines below are a **reading layer**, and they have a hard limitation
worth stating plainly rather than discovering on a Thursday: their prompts run
commands against a local checkout at `/Users/cooperross/Projects/epl-betting-lab`.
That requires a Claude session with filesystem access to that machine, and the
machine being awake. **With the laptop closed they cannot run**, and a routine
that cannot run is not a quiet no-op — it is a scheduled item that appears to
be covering something and is not.

So:

* **To get the card:** open Actions → Matchday Refresh → the latest run. Nothing
  else is required, ever.
* **These routines:** optional. They add a plain-English reading of what is
  already on disk, and only when the machine they point at is on.

Do not treat a routine failing to run as the card failing. The two are
independent, and only one of them is load-bearing.

---

## Exact routine prompts

Claude Code does not edit your scheduled tasks. Paste these into the routine
definitions yourself, and re-paste them when this file changes — a routine is
text living in another system, and it does not update itself.

**These prompts read email, not the filesystem.** The card is built by GitHub
Actions and posted to issue #162, *EPL Card — this week's picks*, which
mentions Cooper so GitHub always emails it. A routine reading that mail works
from anywhere with the laptop shut and needs only the Gmail connector. Earlier
versions ran commands against a local checkout, so they silently could not run
whenever the machine was off — the exact situation a scheduled routine is for.

**One email can be either a card or a failure.** Both arrive from the same
issue. A card leads with *"Selections changed"*; a failure leads with
*"Something went wrong"* and lists what broke before showing whatever card
could still be built. Read the first line before reading the tables.

**A card arrives once a day, and silence means a missed run.** The schedule
fires ten times a week — Thursday through Monday, twice a day — and the first
run of each day that produces a card sends it, whether or not the selections
moved. Later runs the same day stay quiet unless something changed or broke.

So a matchday with no message at all means a run did not happen, which is a
sharper signal than the old rule of "mail only when the picks move". That rule
was right for a person reading an inbox and wrong for a routine reading daily:
the first routine run read a message from the previous day and reported it as
the state of play.

**A search is not a sort.** The first routine run read a message from the
previous day and reported it as the current state, missing a card issued that
morning. Ask for newest by date, and say which timestamp you read, so a stale
answer is visible as one.

**Every run says how it started — but only in the issue message.** Its heading
ends "— scheduled run" or "— manual run". A message with neither predates
labelling and is old, which is itself worth knowing. GitHub's own "Run failed" notifications carry no such label and
no error text either, so they cannot tell you whether the schedule is healthy.
Judge that from the issue #162 messages, which are labelled, and treat raw
Actions failure mail as a pointer to look rather than as evidence.

This matters more than it sounds. Every failure this project has recorded was a
manual dispatch; the only scheduled run so far succeeded. Two health checks in a
row concluded the pipeline was broken by counting failure notifications that
were all someone testing.

---

### EPL CARD

```text
Search Gmail for GitHub notifications for issue #162, "EPL Card — this week's
picks", in cooperross399/epl-betting-lab. Sort by date and take the newest.
Do not rely on search relevance: the first result is often not the latest.

Start by stating the timestamp of the message you are reading, which is in its
first line. If it is more than 24 hours old, say so before anything else — a
newer one probably exists and you have the wrong message.

Report two things separately, because they are often different messages:
- the newest message of any kind, and what it says
- the newest actual CARD, meaning one whose first line says "Selections
  changed". A degraded run can arrive after the last good card, and the card is
  still the current advice.

A message whose subject starts "EPL Card bridge copy" is a verbatim relay
of the newest issue #162 comment, sent by a local bridge task because
GitHub's notification email is broken: treat the comment it quotes exactly
as you would a GitHub card email, using the posted timestamp it names.

Read the first line of each before the tables. "Selections changed" means it is
a card. "Something went wrong" means the run was degraded: say what broke
first, then report whatever card was still built and note it may rest on stale
prices. A heading ending "— manual run" means someone started it by hand rather
than the schedule. Say so — it says nothing about whether the *schedule* is
healthy — but the card itself is real: manual and scheduled runs use the same
reviewed configuration, so a manual card is still the current advice until a
newer card replaces it.

Then tell me, in plain English:

- whether a card was produced, or whether it was blocked and why
- the best bets: market, selection, tier, edge, price, book, suggested units
- the leans, separately, and say plainly that they carry no stake
- the Player props section, if one appears: player, market, selection,
  price, book, units
- what changed since the previous card: added, dropped, or moved section
- which markets were included and excluded

Rules:
- Report only what the email says. Do not compute, adjust, or invent a
  selection, a price, or an edge. If something is missing, say it is missing.
- A blocked card means nothing was generated. It never means "no value found",
  and it is never a reason to suggest a bet.
- A lean is information, not a bet. It fires at a 1.5% modelled edge, which is
  below this model's own error and below a book's margin; measured, leans
  returned about -9% over 150 bets. Never present one as a play.
- A zero-unit row is not a small bet, it is no bet. Anything under "Ranked but
  not stakeable" is in that category, whatever its edge looks like.
- Prices longer than +600 are refused by design. The model overstates long
  prices, and the band above +900 went 0 for 12 in the backtest. If I ask about
  a big price that is not on the card, that is why.
- No market in this project has a demonstrated edge. Every measured interval
  includes zero. If I ask whether it works, say exactly that.
- A Player props section appears only when a prop pick cleared a bar set
  above every match-level bar; every prop pick carries 0.1 units, the
  smallest stake the card uses, and the props measurement demonstrates no
  edge. A missing props section means props are held by policy or nothing
  qualified — never a judgement either way.
- Place no bets. Apply no settlement. Suggest no stake beyond the units shown.
- Never tell me to open a Terminal or to ask ChatGPT. If something looks wrong,
  say what, and point me at the Actions run linked in the email.

A card is sent once a day while the schedule runs. If the newest message is
from before today and today is a matchday (Thursday through Monday), there
are two possible causes and email alone cannot tell them apart: a run was
missed, or GitHub stopped emailing while the pipeline stayed healthy — that
second one really happened on 19 August, when four days of cards posted to
issue #162 with zero emails delivered. Say both possibilities, and point me
at the issue itself and the Actions page to settle it:
https://github.com/cooperross399/epl-betting-lab/issues/162 and
Actions -> Matchday Refresh. Never present the stale card's prices as
current.
```

---

### EPL WATCH (formerly EPL Model)

```text
You are running a weekly health check on the EPL betting model pipeline for
Cooper (cooperross399@gmail.com). Do NOTHING that writes. This routine only
checks the machinery is alive and reports the state of play.

STEP 1 — Search Gmail (via the connector) for notifications for the repository
cooperross399/epl-betting-lab from the last seven days for:
1. GitHub Actions failure notifications for the workflow "Matchday Refresh".
2. Any notification for issue #162 ("EPL Card — this week's picks") whose
   first line says "Something went wrong".
3. The most recent notification for issue #162 of any kind.

STEP 2 — Judge schedule health ONLY from issue #162 messages, ignoring any
whose heading ends "— manual run": a manual run says nothing about whether the
schedule works. GitHub's own "Run failed" notifications carry no trigger label
and no error text, so counting them is not evidence — two health checks in a
row once concluded the pipeline was broken by counting them. The issue #162
headings say how each run started; trust those and nothing else.

Say which of these is true:
- A message within the last four days and no non-manual failures: the schedule
  is running.
- No messages at all for more than four days: either a run was missed or
  GitHub stopped emailing while the pipeline stayed healthy — the second
  one really happened on 19 August. Say both, and tell Cooper to check the
  issue itself and Actions -> Matchday Refresh rather than concluding from
  the empty inbox: https://github.com/cooperross399/epl-betting-lab/issues/162
- A non-manual failure: say which run, when, and what the error line says.
- Only manual failures: say the schedule looks healthy and that someone was
  testing, and do not describe the pipeline as broken.

If you cannot tell whether a failure came from the schedule, say you cannot
tell rather than assuming it did.

STEP 3 — From the most recent card email, report:
- Whether the latest card was ready, blocked, or degraded.
- Which markets are included and excluded.
- How much provider quota remains and how many runs that buys.

A card from a manual run is a real card: manual and scheduled runs use the
same reviewed configuration, so it is the current advice until a newer card
replaces it. Say it was manual — that is about schedule health, not about the
card — and do not call it a test.

FACTS ABOUT THE MARKETS — state these rather than guessing:
- All eight priced markets are enabled since 2026-08-21: 1x2, btts, total_2_5,
  double_chance, draw_no_bet, corners_1x2, corners_total_9_5,
  corners_total_10_5. Cooper approved the scope on PR #224, bound to human
  acceptance receipt odds_api-20260821T114655-0400-20ffa5677988. A card
  carrying all eight markets is the normal card, not a test.
- Every market has been measured against real historical prices. Not one
  interval excludes zero. double_chance measured negative; draw_no_bet's
  positive number rests on thirteen bets; corners_1x2 can never be measured
  because the provider does not retain it historically.
- The measurement recommended enabling nothing new. Cooper reviewed that
  evidence and enabled all eight anyway; both the evidence and the decision
  are on the record, and if he asks whether the picks rest on a demonstrated
  edge, the honest answer is still no.
- total_2_5 was excluded on 2026-08-17 on a finding that was true of the
  bulk `totals` market and silent about alternate_totals, where BetRivers
  and FanDuel carry the 2.5 line on every fixture; reopened on 2026-08-19; enabled with
  the rest on 2026-08-21. Do not re-run that investigation, and do not repeat
  the stale answer.
- Player props (shots, shots on target, assists, anytime scorer) are fully
  built and measured as of 2026-08-22: prices confirmed live and historical,
  a calibrated player model, and a held-out measurement showing good
  calibration and no demonstrated edge — about two qualifying picks a month.
  They are held by the reviewed policy allowlist; if Cooper ever approves
  them on a policy PR, a Player props section appears in card emails at 0.1
  units. Held is the normal state, not a fault.

HARD RULES — follow exactly:
- Generate no picks. Place no bets. Apply no settlement. Never edit the bet
  ledger, record a result, or compute a profit or loss.
- Do not propose enabling or disabling a market. Scope changes are reviewed
  decisions behind the policy gate, not something a health check suggests.
- Report only what the emails say; if something is missing, say it is missing.
- Never tell Cooper to open a Terminal or to ask ChatGPT.

Within a single day, no card email does not mean the system is broken; it
can mean the picks did not move. A gap of more than four days means either
a missed run or dead email delivery — settle it from the issue and Actions
pages, never from the inbox alone.
```

---

### EPL SETTLE (IGNORE) — not currently deployed

```text
Do nothing that writes. This routine only checks that the machinery is alive.

Search Gmail in cooperross399/epl-betting-lab for, in the last seven days:
1. GitHub Actions failure notifications for "Matchday Refresh"
2. any notification for issue #162 whose first line says "Something went wrong"
3. the most recent notification for issue #162 of any kind

Judge schedule health ONLY from issue #162 messages, ignoring any whose heading
ends "— manual run". GitHub's "Run failed" notifications carry no trigger label
and no error text, so counting them is not evidence: every failure this project
has recorded was a manual dispatch, and two health checks in a row concluded the
pipeline was broken by counting them.

Then say which of these is true:
- A message within the last four days and no non-manual failures: the schedule
  is running.
- No messages at all for more than four days: a run was probably missed. Tell me
  to check Actions → Matchday Refresh, and say the workflow may need enabling.
- A non-manual failure: tell me which run, when, and what the error line says.
- Only manual failures: say the schedule looks healthy and that someone was
  testing, and do not describe the pipeline as broken.

If you cannot tell whether a failure came from the schedule, say you cannot tell
rather than assuming it did.

Rules:
- Settlement is preview-only in this project and has no write path. Never apply
  settlement, never edit the bet ledger, never record a result, and never
  compute a profit or loss.
- Place no bets and suggest none.
- Never tell me to open a Terminal or to ask ChatGPT.
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
