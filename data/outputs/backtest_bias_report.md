# EPL Betting Lab Backtest Bias Report

This report uses settled historical backtest bets only. It does not use live odds, does not fabricate prices, and does not place bets.

Status note: these rows use calibrated `BETTABLE` decisions. Raw edge columns are included for before/after comparison.

## Quick answers

- Worst market: total_2_5 lost 1.04 units across 6 bets.
- Worst odds range: +401 or longer lost -15.22 units across 130 bets.
- Favorite vs underdog read: favorite / juiced lost 6.01 units across 70 bets.
- Small-edge read: 5% to 8% lost -20.97 units across 254 bets.
- Threshold check: A stricter edge cutoff of 3.5% had the best ROI among already-bettable historical plays: 2.7% over 552 bets.

## Favorite vs underdog

| favorite_bucket       | status   |   bets |   wins |   losses |   win_rate |   profit_units |   roi |   avg_american_odds |   avg_raw_edge |   avg_calibrated_edge |
|:----------------------|:---------|-------:|-------:|---------:|-----------:|---------------:|------:|--------------------:|---------------:|----------------------:|
| favorite / juiced     | BETTABLE |     70 |     42 |       28 |      0.6   |           6.01 | 0.086 |                -125 |         0.0763 |                0.0551 |
| underdog / plus money | BETTABLE |    482 |    143 |      339 |      0.297 |           8.75 | 0.018 |                 327 |         0.0727 |                0.0487 |

## Edge buckets

| edge_bucket   | status   |   bets |   wins |   losses |   win_rate |   profit_units |    roi |   avg_american_odds |   avg_raw_edge |   avg_calibrated_edge |
|:--------------|:---------|-------:|-------:|---------:|-----------:|---------------:|-------:|--------------------:|---------------:|----------------------:|
| 5% to 8%      | BETTABLE |    254 |     86 |      168 |      0.339 |         -20.97 | -0.083 |                 217 |         0.0817 |                0.0576 |
| 3.5% to 5%    | BETTABLE |    298 |     99 |      199 |      0.332 |          35.73 |  0.12  |                 314 |         0.0659 |                0.0426 |

## Teams most associated with losses

| team           | team_role   | bet_on_team   |   bets |   wins |   losses |   win_rate |   profit_units |    roi |   avg_american_odds |   avg_raw_edge |   avg_calibrated_edge |
|:---------------|:------------|:--------------|-------:|-------:|---------:|-----------:|---------------:|-------:|--------------------:|---------------:|----------------------:|
| Everton        | away        | False         |     17 |      3 |       14 |      0.176 |          -9.44 | -0.555 |                 152 |         0.073  |                0.0523 |
| Crystal Palace | home        | True          |     26 |      7 |       19 |      0.269 |          -9.11 | -0.35  |                 227 |         0.0697 |                0.0504 |
| Arsenal        | home        | False         |     18 |      1 |       17 |      0.056 |          -8.11 | -0.451 |                 629 |         0.0635 |                0.0464 |
| Arsenal        | away        | True          |     11 |      2 |        9 |      0.182 |          -7.46 | -0.678 |                  46 |         0.087  |                0.047  |
| Nott'm Forest  | home        | False         |     22 |      4 |       18 |      0.182 |          -7.28 | -0.331 |                 225 |         0.0748 |                0.0515 |
| Newcastle      | away        | True          |     22 |      6 |       16 |      0.273 |          -6.83 | -0.31  |                 195 |         0.0745 |                0.0489 |
| Brighton       | away        | True          |      9 |      1 |        8 |      0.111 |          -6.46 | -0.718 |                 243 |         0.0819 |                0.0529 |
| Chelsea        | away        | False         |     21 |      5 |       16 |      0.238 |          -6.22 | -0.296 |                 237 |         0.0755 |                0.0525 |
| Liverpool      | home        | False         |     23 |      3 |       20 |      0.13  |          -5.97 | -0.26  |                 633 |         0.0715 |                0.0463 |
| Leeds          | home        | False         |      8 |      1 |        7 |      0.125 |          -5.63 | -0.704 |                 243 |         0.0777 |                0.048  |

## Threshold check

This section tests stricter cutoffs on calibrated bets that fired. It does not prove the model would have found every possible pass or lean.

|   min_edge_threshold |   bets |   wins |   losses |   win_rate |   profit_units |    roi |
|---------------------:|-------:|-------:|---------:|-----------:|---------------:|-------:|
|                0.035 |    552 |    185 |      367 |      0.335 |          14.76 |  0.027 |
|                0.05  |    254 |     86 |      168 |      0.339 |         -20.97 | -0.083 |
|                0.08  |      0 |      0 |        0 |      0     |           0    |  0     |
|                0.1   |      0 |      0 |        0 |      0     |           0    |  0     |
|                0.12  |      0 |      0 |        0 |      0     |           0    |  0     |
|                0.15  |      0 |      0 |        0 |      0     |           0    |  0     |