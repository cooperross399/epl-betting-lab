# Beginner Setup: Using Codex as the EPL Betting Lab Agent

This guide is for using Codex as the agent that keeps editing and improving this project during the EPL season.

## What Codex does here

Codex should be treated like a coding teammate. It can read the project, edit files, run commands, fix errors, add features, and propose changes.

Codex should not be treated like a sportsbook bot. It should not place bets, invent live odds, or guarantee winners.

## Step 1 — Put this project in GitHub

Codex works best when the project is in a GitHub repository.

Beginner version:

1. Go to GitHub.
2. Create a new private repository called `epl-betting-lab`.
3. Upload the contents of this folder.
4. Commit the files.

Recommended repo settings:

- Keep it private.
- Do not commit sportsbook login info.
- Do not commit API keys.
- Use `.env` locally for secrets.

## Step 2 — Connect GitHub to ChatGPT/Codex

In ChatGPT/Codex, connect your GitHub account and give Codex access to the `epl-betting-lab` repo.

After it is connected, Codex can inspect the codebase and make edits in a branch or pull request.

## Step 3 — Give Codex the first task

Use this prompt:

```text
You are working in my `epl-betting-lab` repo. Read `AGENTS.md` first and follow it. Make the project more ready for the 2026/27 EPL season. Start by running tests and compile checks. Then inspect the current model and suggest the next 3 highest-impact improvements for in-season betting strategy tracking. Do not fabricate odds or results.
```

## Step 4 — Weekly update prompt

After each matchweek, use this:

```text
Read `AGENTS.md`. Update the EPL Betting Lab using the latest available Football-Data EPL results. Rebuild the processed dataset, run the backtest, run the weekly agent brief, and inspect whether recent form or team-specific bias suggests a model improvement. If code changes are justified, make the smallest useful change, add/update tests, and summarize what changed. Do not invent sportsbook odds.
```

## Step 5 — When you paste odds

Before a matchweek, paste or enter odds into:

```text
data/manual/current_odds.csv
```

Use `american_odds` for the price available when you run the model. Leave
`closing_american_odds` blank until after the market closes, then paste the
closing price there for CLV tracking. Missing closing odds are not guessed.

Then tell Codex:

```text
I updated `data/manual/current_odds.csv` with current odds. Run the model, generate the weekly card, and tell me the best smart plays, leans, avoids, and sneaky/fun angles. Respect my max juice rule around -160.
```

## Step 6 — Track actual bets

The weekly card is not a bet slip. If you decide to place a bet yourself, log
it in:

```text
data/manual/bet_ledger.csv
```

Use one row per bet. The safest fields to fill right away are:

```text
bet_id
date
season
match
home_team
away_team
market
selection
model_recommendation_status
american_odds
stake_units
result
book
notes
```

Use `pending` until the match is graded. Later change `result` to `win`,
`loss`, or `push`. If you paste `closing_american_odds` after the market
closes, the report will calculate CLV. If closing odds are blank, CLV stays
blank.

Run:

```bash
python scripts/run_bet_ledger.py
```

Then read:

```text
data/outputs/bet_ledger_summary.md
```

## Step 7 — What to approve and what to reject

Approve Codex changes when:

- Tests pass.
- The code is simpler or more useful.
- The change improves backtest discipline.
- The output is easier to understand.
- It does not fake odds or overclaim confidence.

Reject or ask for revisions when:

- It removes your betting rules.
- It adds complicated code without clear improvement.
- It changes thresholds based on one bad or good week.
- It pretends missing data is real.

## Good first agent tasks

1. Add a recent-form weighting toggle.
2. Add home/away split projections.
3. Add market ROI by season and by team.
4. Add promoted-team tracking dashboard.
5. Add closing-line-value tracking.
6. Add corners model using Football-Data corner columns.
7. Add shots/SOT model using Football-Data shot columns.

## Important reminder

This is a research tool. The final decision should still be manual. The best use is to find smarter prices for a game script, not to blindly bet every model edge.
