# EPL Betting Lab Backtest Bias Report

This report uses settled historical backtest bets only. It does not use live odds, does not fabricate prices, and does not place bets.

Status note: these rows use calibrated `BETTABLE` decisions. Raw edge columns are included for before/after comparison.

## Quick answers

- Worst market: total_2_5 lost -36.53 units across 474 bets.
- Worst odds range: +101 to +200 lost -34.4 units across 395 bets.
- Favorite vs underdog read: underdog / plus money lost -25.25 units across 727 bets.
- Small-edge read: 5% to 8% lost -58.34 units across 520 bets.
- Threshold check: A stricter edge cutoff of 3.5% had the best ROI among already-bettable historical plays: -2.2% over 1020 bets.

## Favorite vs underdog

| favorite_bucket       | status   |   bets |   wins |   losses |   win_rate |   profit_units |    roi |   avg_american_odds |   avg_raw_edge |   avg_calibrated_edge |
|:----------------------|:---------|-------:|-------:|---------:|-----------:|---------------:|-------:|--------------------:|---------------:|----------------------:|
| underdog / plus money | BETTABLE |    727 |    233 |      494 |      0.32  |         -25.25 | -0.035 |                 264 |         0.0722 |                0.0499 |
| even money            | BETTABLE |      4 |      2 |        2 |      0.5   |           0    |  0     |                 100 |         0.0564 |                0.0435 |
| favorite / juiced     | BETTABLE |    289 |    161 |      128 |      0.557 |           2.44 |  0.008 |                -126 |         0.0683 |                0.0536 |

## Edge buckets

| edge_bucket   | status   |   bets |   wins |   losses |   win_rate |   profit_units |    roi |   avg_american_odds |   avg_raw_edge |   avg_calibrated_edge |
|:--------------|:---------|-------:|-------:|---------:|-----------:|---------------:|-------:|--------------------:|---------------:|----------------------:|
| 5% to 8%      | BETTABLE |    520 |    199 |      321 |      0.383 |         -58.34 | -0.112 |                 112 |         0.0814 |                0.0587 |
| 3.5% to 5%    | BETTABLE |    500 |    197 |      303 |      0.394 |          35.53 |  0.071 |                 195 |         0.0603 |                0.0428 |

## Teams most associated with losses

| team           | team_role   | bet_on_team   |   bets |   wins |   losses |   win_rate |   profit_units |    roi |   avg_american_odds |   avg_raw_edge |   avg_calibrated_edge |
|:---------------|:------------|:--------------|-------:|-------:|---------:|-----------:|---------------:|-------:|--------------------:|---------------:|----------------------:|
| Brighton       | away        | False         |     37 |     10 |       27 |      0.27  |         -14.49 | -0.392 |                  97 |         0.0696 |                0.0507 |
| Man United     | home        | False         |     71 |     19 |       52 |      0.268 |         -11.73 | -0.165 |                 241 |         0.0742 |                0.0516 |
| Brentford      | home        | False         |     27 |      8 |       19 |      0.296 |         -10.96 | -0.406 |                 -16 |         0.0719 |                0.0502 |
| Newcastle      | away        | False         |     28 |      9 |       19 |      0.321 |         -10.7  | -0.382 |                  19 |         0.0683 |                0.0521 |
| Chelsea        | away        | False         |     44 |     15 |       29 |      0.341 |         -10.08 | -0.229 |                 103 |         0.0686 |                0.0523 |
| Arsenal        | home        | False         |     36 |      9 |       27 |      0.25  |          -9.75 | -0.271 |                 334 |         0.0625 |                0.0473 |
| Everton        | home        | False         |     60 |     22 |       38 |      0.367 |          -9.25 | -0.154 |                  78 |         0.075  |                0.0505 |
| Crystal Palace | home        | True          |     26 |      7 |       19 |      0.269 |          -9.11 | -0.35  |                 227 |         0.0697 |                0.0504 |
| Crystal Palace | home        | False         |     29 |     10 |       19 |      0.345 |          -8.8  | -0.303 |                  41 |         0.0681 |                0.0509 |
| Everton        | away        | False         |     39 |     15 |       24 |      0.385 |          -8.04 | -0.206 |                  46 |         0.0703 |                0.0537 |

## Threshold check

This section tests stricter cutoffs on calibrated bets that fired. It does not prove the model would have found every possible pass or lean.

|   min_edge_threshold |   bets |   wins |   losses |   win_rate |   profit_units |    roi |
|---------------------:|-------:|-------:|---------:|-----------:|---------------:|-------:|
|                0.035 |   1020 |    396 |      624 |      0.388 |         -22.81 | -0.022 |
|                0.05  |    520 |    199 |      321 |      0.383 |         -58.34 | -0.112 |
|                0.08  |      0 |      0 |        0 |      0     |           0    |  0     |
|                0.1   |      0 |      0 |        0 |      0     |           0    |  0     |
|                0.12  |      0 |      0 |        0 |      0     |           0    |  0     |
|                0.15  |      0 |      0 |        0 |      0     |           0    |  0     |