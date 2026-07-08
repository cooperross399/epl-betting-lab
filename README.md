# EPL Betting Lab

A starter Python project for building, testing, and using English Premier League betting strategies for the 2026/27 season.

This is built for a practical betting workflow:

- Pull historical EPL data
- Fit a simple goals model
- Compare model probabilities to betting prices
- Avoid heavy juice by default
- Backtest strategy rules before trusting them
- Generate a weekly betting card
- Review which markets are actually working

> Responsible betting note: this project is for research and tracking. It does not guarantee profit. Use small stakes, record every play, and treat model output as a decision aid rather than an auto-bet system.

---

## Data sources

The starter project is designed around these public data sources:

- **Football-Data.co.uk** for historical EPL results, match stats, and odds CSVs.
- **ClubElo** for team strength ratings.
- **Manual odds entry** at first, because sportsbook lines vary by state/book and change constantly.

The included `data/manual/upcoming_fixtures.csv` is a starter fixture sheet for early 2026/27 EPL matches. Fixtures and times can change, so update it before betting.

---

## Setup on Mac

From Terminal:

```bash
cd ~/Downloads/epl-betting-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

---

## Fetch historical EPL data

```bash
python scripts/fetch_data.py --seasons 2122 2223 2324 2425 2526
```

This creates:

```text
data/processed/epl_historical_matches.csv
```

Season code examples:

```text
2122 = 2021/22
2223 = 2022/23
2324 = 2023/24
2425 = 2024/25
2526 = 2025/26
```

---

## Run the first backtest

```bash
python scripts/run_backtest.py
```

This creates:

```text
data/outputs/backtest_bets.csv
data/outputs/backtest_summary.csv
```

The starter backtest tests:

- 1X2 moneyline-style markets
- Over/under 2.5 goals
- Basic model-vs-book edge logic
- Your default no-heavy-juice rule: pass on odds worse than about `-160`

---

## Add current odds

Copy the template:

```bash
cp data/manual/current_odds_template.csv data/manual/current_odds.csv
```

Then replace the example odds with real book prices.

Expected format:

```csv
date,home_team,away_team,market,selection,american_odds,closing_american_odds,book,notes
2026-08-21,Arsenal,Coventry,total_2_5,under,110,,DraftKings,
```

Supported starter markets:

```text
1x2 selections: home, draw, away
total_2_5 selections: over, under
btts selections: yes, no
```

`american_odds` is the price used when the model makes the decision.
`closing_american_odds` is optional. Leave it blank before matches, then paste
the closing price after the market closes. If it is blank, CLV stays missing
instead of being guessed.

---

## Generate a weekly card

```bash
python scripts/generate_weekly_card.py
```

This creates:

```text
data/outputs/weekly_card.csv
data/outputs/weekly_card.md
```

The weekly card includes:

- Matchup
- Market
- Selection
- American odds
- Model probability
- Book implied probability
- Edge
- Fair price
- Suggested unit size

## Generate Thursday best bets

Every Wednesday or Thursday, update:

```text
data/manual/current_odds.csv
```

Use real sportsbook prices only. If the file does not exist yet:

```bash
cp data/manual/current_odds_template.csv data/manual/current_odds.csv
```

Then run:

```bash
python scripts/generate_thursday_best_bets.py
```

This creates:

```text
data/outputs/thursday_best_bets.csv
data/outputs/thursday_best_bets.md
```

The report separates best bets, leans, and passes/notable avoids. It uses
calibrated probabilities, respects the default max-juice rule around `-160`,
and keeps the totals protections.

---

## Track actual bets in the ledger

The model card is research. If you actually place a bet yourself, record it in:

```text
data/manual/bet_ledger.csv
```

The repo also includes a blank template:

```text
data/manual/bet_ledger_template.csv
```

Use one row per bet. Keep `stake_units` as the main tracker. You can leave
`closing_american_odds`, `profit_units`, `profit_dollars`, and
`clv_probability_points` blank at first.

Important fields:

```text
result = win, loss, push, or pending
american_odds = the price you actually bet
closing_american_odds = optional closing price after the market closes
stake_units = your unit stake, such as 0.5 or 1
book = sportsbook name for your notes
```

Run the ledger report:

```bash
python scripts/run_bet_ledger.py
```

This creates:

```text
data/outputs/bet_ledger_summary.md
data/outputs/bet_ledger_by_market.csv
data/outputs/bet_ledger_by_selection.csv
data/outputs/bet_ledger_by_team.csv
data/outputs/bet_ledger_pending.csv
```

Pending bets do not count toward profit/loss or ROI. Pushes count as 0.
Missing closing odds stay blank instead of being guessed.

To save typing after you generate the weekly card, you can pre-fill draft
ledger rows from `data/outputs/weekly_card.csv`:

```bash
python scripts/prefill_bet_ledger.py
```

By default this adds only `BETTABLE` and `LEAN` model rows, marks them
`pending`, leaves `closing_american_odds` blank, and skips rows that are
already in your ledger. To include pass rows for review:

```bash
python scripts/prefill_bet_ledger.py --include-pass
```

After pre-filling, delete any rows you did not actually bet or leave a note
that they were not placed.

Before settling or reviewing profit/loss, run the ledger health check:

```bash
python scripts/check_bet_ledger.py
```

This creates:

```text
data/outputs/bet_ledger_health_check.csv
data/outputs/bet_ledger_health_check.md
```

The health check is read-only. It flags serious issues like duplicate bet IDs,
missing odds, invalid markets, invalid results, and missing team names. It also
flags optional cleanup like missing closing lines for CLV.

After matches finish and the processed EPL results are updated, preview
settlements for pending ledger rows:

```bash
python scripts/settle_bet_ledger.py
```

This creates:

```text
data/outputs/bet_settlement_preview.csv
data/outputs/bet_settlement_preview.md
```

Review the preview first. It supports `1x2`, `total_2_5`, and `btts`.
Rows marked `unmatched` are not changed. To apply confident win/loss/push
suggestions to the ledger:

```bash
python scripts/settle_bet_ledger.py --apply
```

---

## Open the dashboard

```bash
streamlit run app.py
```

The dashboard shows:

- Recent form table
- Upcoming fixture projections
- Promoted-team review spots
- Value board
- Weekly card
- Backtest summary, after you run the backtest
- Betting ledger tab, after you run the ledger scripts

For the ledger tab, run these as needed before opening or refreshing the
dashboard:

```bash
python scripts/run_bet_ledger.py
python scripts/check_bet_ledger.py
python scripts/settle_bet_ledger.py
python scripts/run_backtest.py
```

The ledger tab also has buttons for the safe report actions:

```text
Run bet ledger report
Run ledger health check
Run settlement preview
Run backtest reports
Refresh dashboard data
```

These buttons do not edit `data/manual/bet_ledger.csv`, do not apply
settlements, do not place bets, and do not invent missing odds.

The ledger tab also includes a weekly workflow checklist. It shows whether key
files are `Complete`, `Missing`, or `Needs refresh`, when they were last
modified, and the command to run when something is missing or stale.

---

## Project structure

```text
epl-betting-lab/
├── app.py
├── requirements.txt
├── pyproject.toml
├── README.md
├── data/
│   ├── manual/
│   │   ├── upcoming_fixtures.csv
│   │   ├── current_odds_template.csv
│   │   ├── bet_ledger_template.csv
│   │   ├── bet_ledger.csv
│   │   └── mock_current_odds.csv
│   ├── raw/
│   ├── processed/
│   └── outputs/
├── scripts/
│   ├── fetch_data.py
│   ├── run_backtest.py
│   └── generate_weekly_card.py
└── src/epl_betting_lab/
    ├── config.py
    ├── data/
    ├── models/
    ├── strategies/
    ├── backtest/
    └── reports/
```

---

## How the model works right now

The starter model uses a transparent Poisson goals approach:

```text
Home expected goals = league home scoring average × home attack strength × away defensive weakness
Away expected goals = league away scoring average × away attack strength × home defensive weakness
```

From there it estimates:

```text
Home win probability
Draw probability
Away win probability
Over/under 2.5 probability
BTTS yes/no probability
Most likely scorelines
```

Then it compares those probabilities to sportsbook odds.

A play is usually only marked `BETTABLE` when:

```text
model probability - book implied probability >= minimum edge
expected value > 0
odds are not worse than the default max juice threshold
```

---

## Strategy ideas to expand next

Good next modules:

- Corners model
- Shots on target props
- Anytime goal scorer model
- Cards/fouls model
- European hangover spots
- Promoted-team fade tracker
- Closing-line value tracker
- Line movement tracker
- Bankroll ledger
- Twitter/X thread generator for matchweek previews

---

## Team naming note

The starter fixture file uses Football-Data-style names where possible, such as:

```text
Man United
Man City
Nott'm Forest
Tottenham
Newcastle
```

If your fixtures use `Manchester United` but the historical data uses `Man United`, the model will treat them as different teams. Keep names consistent.

---

## Using Codex as the season-long agent

This project is now Codex-ready.

Important files:

```text
AGENTS.md                                  # Rules/instructions Codex should follow
codex/prompts/weekly_model_update.md       # Weekly update prompt
codex/prompts/add_corners_model.md         # Future corners-model prompt
codex/prompts/add_shots_sot_model.md       # Future shots/SOT prompt
docs/CODEX_SETUP_BEGINNER.md               # Beginner Codex setup guide
scripts/agent_weekly_brief.py              # Creates an in-season brief for the agent
```

After each matchweek, once current-season data is available, run:

```bash
python scripts/fetch_data.py --seasons 2122 2223 2324 2425 2526 2627
python scripts/run_backtest.py
python scripts/agent_weekly_brief.py --current-season 2627 --recent-matches 6
```

This creates:

```text
data/outputs/agent_weekly_brief.md
data/outputs/agent_team_recent_form.csv
data/outputs/agent_team_market_profile.csv
```

Give Codex this weekly instruction:

```text
Read AGENTS.md. Use data/outputs/agent_weekly_brief.md, the latest backtest outputs, and the current codebase to decide whether the model needs a small, explainable improvement. Do not fabricate odds. Respect the max-juice rule around -160. Run tests before summarizing changes.
```

For full beginner instructions, open:

```text
docs/CODEX_SETUP_BEGINNER.md
```
