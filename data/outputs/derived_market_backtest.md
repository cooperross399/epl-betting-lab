# Derived market backtest

The first time corners, BTTS, draw-no-bet and double chance have been judged against prices that were really offered, at books that can really be bet.

One snapshot per fixture at a fixed lead before kick-off, so there is **no closing line here and no CLV** — only profit, which is the weaker instrument. Read the interval, not the point estimate: an interval that includes zero has not demonstrated an edge, whatever the ROI says.

`pushes` are bets that returned the stake — a drawn draw-no-bet, a corner total landing on the line. They are bets, so they sit in the denominator at zero profit; dropping them once removed 33 of 115 draw-no-bet selections and reported +7.1% for a rule that returned +5.1%. `win_rate` is therefore over all bets, pushes included.

| market             |   bets |   pushes |   win_rate |   units |   roi_pct |   ci_low_pct |   ci_high_pct |   p_above_zero |
|:-------------------|-------:|---------:|-----------:|--------:|----------:|-------------:|--------------:|---------------:|
| btts               |     37 |        0 |       45.9 |   -3.92 |    -10.61 |        -42.9 |          19.1 |           0.24 |
| corners_total_10_5 |     83 |        0 |       41   |   -8.97 |    -10.81 |        -34.8 |          13.1 |           0.2  |
| corners_total_9_5  |     82 |        0 |       58.5 |    5.3  |      6.46 |        -13.2 |          25.9 |           0.76 |
| double_chance      |     77 |        0 |       42.9 |   -4.22 |     -5.48 |        -31.3 |          21.1 |           0.34 |
| draw_no_bet        |    115 |       33 |       26.1 |    5.86 |      5.09 |        -17.6 |          30.9 |           0.65 |
| ALL                |    394 |       33 |       41.1 |   -5.96 |     -1.51 |        -14.8 |          11.2 |           0.39 |

Scored candidates: 4180. Bets the card rule would have taken: 394.

## What was dropped, and why

- Dropped 29021 row(s) with no book — a cross-book maximum cannot be shown to have been takeable.
