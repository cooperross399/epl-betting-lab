# Claude Thursday Task Prompt

Use this standing prompt every Wednesday/Thursday when running the EPL model
with Claude. It assumes `CLAUDE.md` has been read and its hard rules apply.

## The task

Read `CLAUDE.md` and `docs/project_status_for_claude.md`. Then produce this
week's Claude Thursday packet:

```bash
python scripts/run_claude_thursday_epl_model.py
```

That command runs the safe weekly pipeline first and writes:

```text
data/outputs/claude_thursday_epl_packet.json
data/outputs/claude_thursday_epl_packet.md
data/outputs/claude_thursday_epl_packet.csv
```

If the weekly pipeline already ran this session and you only need the packet
rebuilt from its latest summary, use:

```bash
python scripts/run_claude_thursday_epl_model.py --read-latest
```

## How to report the result

- Lead with the weekly pipeline status and whether a card is ready.
- If the status is `Needs odds` (or anything else not card-ready): say clearly
  that **no card is ready**, list the exact blockers, and stop. Do not
  generate, guess, or invent picks or odds. The next step is a human filling
  `data/manual/current_odds.csv` with real sportsbook prices.
- If a card is ready: summarize best bets, leans, and passes/avoids with their
  odds, calibrated edges, tiers, and suggested units. Flag any warnings,
  heavy-juice prices near or worse than `-160`, and totals-under cautions.
- Include odds validation status, odds completeness, the CLV and ledger
  summaries when available, ledger health, the archive receipt ID, the
  archive/sidecar verification verdicts, and the recommended next human
  action from the packet.
- Always close by reminding that this is research: the user confirms live
  prices and decides every bet manually.

## Rules for this task

- Do not change the core model.
- Do not fabricate odds.
- Do not place bets.
- Do not enable cron.
- Do not run live providers.
- Do not edit protected files (`data/manual/current_odds.csv`,
  `current_odds_import.csv`, `bet_ledger.csv`, `odds_import_profiles.json`,
  `staging_provider_policy.json`).
- Do not use force mode.
- Do not apply settlement.
