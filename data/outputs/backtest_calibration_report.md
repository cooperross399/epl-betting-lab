# EPL Betting Lab Backtest Calibration Report

This report compares model probabilities to settled historical backtest results. It does not use live odds, fabricate prices, or place bets.

Status note: the current backtest only logs plays that passed the old `BETTABLE` filter, so this is calibration for fired bets only.

## Quick answers

- Worst probability bucket: 70% or higher won 44.9% vs 74.9% expected, 29.9% below model.
- Worst market: 1x2 won 43.6% vs 75.2% expected, 31.6% below model.
- Worst side/type: away side won 30.4% vs 64.4% expected, 34.0% below model.
- Big-edge read: 12% or higher won 36.8% vs 57.0% expected, 20.2% below model.
- Shrink extreme probabilities? Yes. High-confidence or big-edge plays are winning less often than their model probabilities, so the next model change should test shrinking extreme probabilities toward the market or a historical baseline before betting them.

## Probability buckets

| probability_bucket   | status   |   bets |   wins |   actual_win_rate |   avg_model_prob |   calibration_gap |   avg_book_implied |   avg_edge |   profit_units |    roi |
|:---------------------|:---------|-------:|-------:|------------------:|-----------------:|------------------:|-------------------:|-----------:|---------------:|-------:|
| 40% to 50%           | BETTABLE |    294 |     98 |             0.333 |            0.452 |            -0.119 |              0.365 |     0.087  |         -28.21 | -0.096 |
| 50% to 60%           | BETTABLE |    348 |    154 |             0.443 |            0.552 |            -0.11  |              0.464 |     0.0889 |         -18.34 | -0.053 |
| 60% to 70%           | BETTABLE |    306 |    164 |             0.536 |            0.64  |            -0.104 |              0.54  |     0.1007 |          -0.52 | -0.002 |
| 70% or higher        | BETTABLE |     69 |     31 |             0.449 |            0.749 |            -0.299 |              0.554 |     0.1946 |         -14.18 | -0.206 |
| under 40%            | BETTABLE |    416 |     93 |             0.224 |            0.288 |            -0.065 |              0.215 |     0.073  |          -5.47 | -0.013 |

## Market calibration

| market    | probability_bucket   | status   |   bets |   wins |   actual_win_rate |   avg_model_prob |   calibration_gap |   avg_book_implied |   avg_edge |   profit_units |    roi |
|:----------|:---------------------|:---------|-------:|-------:|------------------:|-----------------:|------------------:|-------------------:|-----------:|---------------:|-------:|
| 1x2       | 40% to 50%           | BETTABLE |    178 |     60 |             0.337 |            0.446 |            -0.109 |              0.35  |     0.0961 |         -10.43 | -0.059 |
| 1x2       | 50% to 60%           | BETTABLE |    122 |     55 |             0.451 |            0.549 |            -0.098 |              0.435 |     0.1136 |           3.29 |  0.027 |
| 1x2       | 60% to 70%           | BETTABLE |     95 |     45 |             0.474 |            0.643 |            -0.169 |              0.514 |     0.1282 |          -8.79 | -0.093 |
| 1x2       | 70% or higher        | BETTABLE |     39 |     17 |             0.436 |            0.752 |            -0.316 |              0.554 |     0.1977 |          -9.5  | -0.244 |
| 1x2       | under 40%            | BETTABLE |    393 |     86 |             0.219 |            0.284 |            -0.065 |              0.21  |     0.0743 |          -4.95 | -0.013 |
| total_2_5 | 40% to 50%           | BETTABLE |    116 |     38 |             0.328 |            0.461 |            -0.133 |              0.388 |     0.073  |         -17.78 | -0.153 |
| total_2_5 | 50% to 60%           | BETTABLE |    226 |     99 |             0.438 |            0.554 |            -0.116 |              0.479 |     0.0756 |         -21.63 | -0.096 |
| total_2_5 | 60% to 70%           | BETTABLE |    211 |    119 |             0.564 |            0.639 |            -0.075 |              0.551 |     0.0883 |           8.27 |  0.039 |
| total_2_5 | 70% or higher        | BETTABLE |     30 |     14 |             0.467 |            0.744 |            -0.278 |              0.554 |     0.1906 |          -4.68 | -0.156 |
| total_2_5 | under 40%            | BETTABLE |     23 |      7 |             0.304 |            0.358 |            -0.054 |              0.308 |     0.05   |          -0.52 | -0.023 |

## Side and price calibration

| selection_context   | favorite_bucket       | odds_range     | status   |   bets |   wins |   actual_win_rate |   avg_model_prob |   calibration_gap |   avg_book_implied |   avg_edge |   profit_units |    roi |
|:--------------------|:----------------------|:---------------|:---------|-------:|-------:|------------------:|-----------------:|------------------:|-------------------:|-----------:|---------------:|-------:|
| away side           | favorite / juiced     | -120 to +100   | BETTABLE |     23 |      7 |             0.304 |            0.644 |            -0.34  |              0.525 |     0.1195 |          -9.57 | -0.416 |
| away side           | favorite / juiced     | -160 to -121   | BETTABLE |     34 |     17 |             0.5   |            0.696 |            -0.196 |              0.582 |     0.1141 |          -5    | -0.147 |
| away side           | underdog / plus money | +101 to +200   | BETTABLE |    167 |     60 |             0.359 |            0.516 |            -0.157 |              0.403 |     0.1129 |         -19.31 | -0.116 |
| away side           | underdog / plus money | +201 to +400   | BETTABLE |    170 |     48 |             0.282 |            0.364 |            -0.082 |              0.265 |     0.0994 |           9.13 |  0.054 |
| away side           | underdog / plus money | +401 or longer | BETTABLE |    129 |     18 |             0.14  |            0.236 |            -0.096 |              0.148 |     0.0884 |         -16.3  | -0.126 |
| draw                | underdog / plus money | +201 to +400   | BETTABLE |     28 |      7 |             0.25  |            0.298 |            -0.048 |              0.239 |     0.0598 |           0.07 |  0.002 |
| draw                | underdog / plus money | +401 or longer | BETTABLE |     33 |      7 |             0.212 |            0.219 |            -0.007 |              0.16  |     0.0588 |           8.71 |  0.264 |
| home side           | favorite / juiced     | -120 to +100   | BETTABLE |     26 |     16 |             0.615 |            0.625 |            -0.009 |              0.53  |     0.0948 |           4.25 |  0.163 |
| home side           | favorite / juiced     | -160 to -121   | BETTABLE |     25 |     18 |             0.72  |            0.691 |             0.029 |              0.585 |     0.1057 |           5.77 |  0.231 |
| home side           | underdog / plus money | +101 to +200   | BETTABLE |    103 |     44 |             0.427 |            0.51  |            -0.082 |              0.414 |     0.0951 |           3.31 |  0.032 |
| home side           | underdog / plus money | +201 to +400   | BETTABLE |     71 |     20 |             0.282 |            0.366 |            -0.084 |              0.272 |     0.0934 |           0.82 |  0.012 |
| home side           | underdog / plus money | +401 or longer | BETTABLE |     18 |      1 |             0.056 |            0.212 |            -0.156 |              0.151 |     0.0611 |         -12.26 | -0.681 |
| total over          | even money            | -120 to +100   | BETTABLE |      1 |      1 |             1     |            0.555 |             0.445 |              0.5   |     0.0549 |           1    |  1     |
| total over          | favorite / juiced     | -120 to +100   | BETTABLE |     50 |     30 |             0.6   |            0.611 |            -0.011 |              0.527 |     0.0835 |           7.1  |  0.142 |
| total over          | favorite / juiced     | -160 to -121   | BETTABLE |     97 |     54 |             0.557 |            0.65  |            -0.093 |              0.579 |     0.0706 |          -3.5  | -0.036 |
| total over          | underdog / plus money | +101 to +200   | BETTABLE |     40 |     21 |             0.525 |            0.561 |            -0.036 |              0.477 |     0.0834 |           3.81 |  0.095 |
| total under         | even money            | -120 to +100   | BETTABLE |      3 |      1 |             0.333 |            0.557 |            -0.224 |              0.5   |     0.0569 |          -1    | -0.333 |
| total under         | favorite / juiced     | -120 to +100   | BETTABLE |     63 |     34 |             0.54  |            0.597 |            -0.057 |              0.525 |     0.0719 |           1.6  |  0.025 |
| total under         | favorite / juiced     | -160 to -121   | BETTABLE |     65 |     31 |             0.477 |            0.665 |            -0.188 |              0.576 |     0.0889 |         -10.83 | -0.167 |
| total under         | underdog / plus money | +101 to +200   | BETTABLE |    258 |     96 |             0.372 |            0.516 |            -0.144 |              0.428 |     0.0884 |         -35.86 | -0.139 |
| total under         | underdog / plus money | +201 to +400   | BETTABLE |     29 |      9 |             0.31  |            0.413 |            -0.102 |              0.297 |     0.1156 |           1.34 |  0.046 |

## Edge calibration

| edge_bucket   | status   |   bets |   wins |   actual_win_rate |   avg_model_prob |   calibration_gap |   avg_book_implied |   avg_edge |   profit_units |    roi |
|:--------------|:---------|-------:|-------:|------------------:|-----------------:|------------------:|-------------------:|-----------:|---------------:|-------:|
| 12% or higher | BETTABLE |    307 |    113 |             0.368 |            0.57  |            -0.202 |              0.396 |     0.1738 |         -19.24 | -0.063 |
| 3.5% to 5%    | BETTABLE |    312 |    122 |             0.391 |            0.422 |            -0.031 |              0.379 |     0.0428 |           5.13 |  0.016 |
| 5% to 8%      | BETTABLE |    456 |    170 |             0.373 |            0.451 |            -0.078 |              0.388 |     0.0634 |         -16.09 | -0.035 |
| 8% to 12%     | BETTABLE |    358 |    135 |             0.377 |            0.504 |            -0.126 |              0.404 |     0.0991 |         -36.52 | -0.102 |