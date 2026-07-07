# EPL Betting Lab Backtest Bias Report

This report uses settled historical backtest bets only. It does not use live odds, does not fabricate prices, and does not place bets.

Status note: the current backtest only settles plays that passed the old `BETTABLE` filter. The CSVs keep a `status` column so future candidate logs can also compare leans and passes.

## Quick answers

- Worst market: total_2_5 lost -36.34 units across 606 bets.
- Worst odds range: +101 to +200 lost -48.05 units across 568 bets.
- Favorite vs underdog read: underdog / plus money lost -56.54 units across 1046 bets.
- Small-edge read: 8% to 12% lost -36.52 units across 358 bets.
- Threshold check: A stricter edge cutoff of 3.5% had the best ROI among already-bettable historical plays: -4.7% over 1433 bets.

## Favorite vs underdog

| favorite_bucket       | status   |   bets |   wins |   losses |   win_rate |   profit_units |    roi |   avg_american_odds |   avg_edge |
|:----------------------|:---------|-------:|-------:|---------:|-----------:|---------------:|-------:|--------------------:|-----------:|
| underdog / plus money | BETTABLE |   1046 |    331 |      715 |      0.316 |         -56.54 | -0.054 |                 266 |     0.0935 |
| favorite / juiced     | BETTABLE |    383 |    207 |      176 |      0.54  |         -10.18 | -0.027 |                -127 |     0.0863 |
| even money            | BETTABLE |      4 |      2 |        2 |      0.5   |           0    |  0     |                 100 |     0.0564 |

## Edge buckets

| edge_bucket   | status   |   bets |   wins |   losses |   win_rate |   profit_units |    roi |   avg_american_odds |   avg_edge |
|:--------------|:---------|-------:|-------:|---------:|-----------:|---------------:|-------:|--------------------:|-----------:|
| 8% to 12%     | BETTABLE |    358 |    135 |      223 |      0.377 |         -36.52 | -0.102 |                 135 |     0.0991 |
| 12% or higher | BETTABLE |    307 |    113 |      194 |      0.368 |         -19.24 | -0.063 |                 157 |     0.1738 |
| 5% to 8%      | BETTABLE |    456 |    170 |      286 |      0.373 |         -16.09 | -0.035 |                 159 |     0.0634 |
| 3.5% to 5%    | BETTABLE |    312 |    122 |      190 |      0.391 |           5.13 |  0.016 |                 195 |     0.0428 |

## Teams most associated with losses

| team           | team_role   | bet_on_team   |   bets |   wins |   losses |   win_rate |   profit_units |    roi |   avg_american_odds |   avg_edge |
|:---------------|:------------|:--------------|-------:|-------:|---------:|-----------:|---------------:|-------:|--------------------:|-----------:|
| Bournemouth    | away        | False         |     56 |     17 |       39 |      0.304 |         -20.45 | -0.365 |                  69 |     0.0974 |
| Man United     | home        | False         |    115 |     31 |       84 |      0.27  |         -20.41 | -0.177 |                 255 |     0.103  |
| Bournemouth    | home        | False         |     69 |     22 |       47 |      0.319 |         -19.26 | -0.279 |                 126 |     0.0995 |
| Aston Villa    | home        | False         |     54 |     13 |       41 |      0.241 |         -19.11 | -0.354 |                 169 |     0.0842 |
| Newcastle      | away        | False         |     36 |     12 |       24 |      0.333 |         -12.9  | -0.358 |                  25 |     0.0798 |
| Brighton       | away        | False         |     45 |     14 |       31 |      0.311 |         -12.83 | -0.285 |                 105 |     0.0772 |
| Man City       | home        | False         |     42 |      8 |       34 |      0.19  |         -12.29 | -0.293 |                 482 |     0.1084 |
| Crystal Palace | home        | False         |     34 |     11 |       23 |      0.324 |         -12.07 | -0.355 |                  55 |     0.0769 |
| Brentford      | home        | False         |     30 |      9 |       21 |      0.3   |         -11.48 | -0.383 |                   8 |     0.0721 |
| Newcastle      | away        | True          |     36 |     10 |       26 |      0.278 |         -11.32 | -0.314 |                 168 |     0.1003 |

## Threshold check

This section only tests stricter cutoffs on bets the old rules already fired. It does not prove the model would have found every possible pass or lean.

|   min_edge_threshold |   bets |   wins |   losses |   win_rate |   profit_units |    roi |
|---------------------:|-------:|-------:|---------:|-----------:|---------------:|-------:|
|                0.035 |   1433 |    540 |      893 |      0.377 |         -66.72 | -0.047 |
|                0.05  |   1121 |    418 |      703 |      0.373 |         -71.85 | -0.064 |
|                0.08  |    665 |    248 |      417 |      0.373 |         -55.76 | -0.084 |
|                0.1   |    473 |    177 |      296 |      0.374 |         -31.95 | -0.068 |
|                0.12  |    307 |    113 |      194 |      0.368 |         -19.24 | -0.063 |
|                0.15  |    179 |     63 |      116 |      0.352 |         -12.67 | -0.071 |