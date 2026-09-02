# Derived market backtest

The first time corners, BTTS, draw-no-bet and double chance have been judged against prices that were really offered, at books that can really be bet.

One snapshot per fixture at a fixed lead before kick-off, so there is **no closing line here and no CLV** — only profit, which is the weaker instrument. Read the interval, not the point estimate: an interval that includes zero has not demonstrated an edge, whatever the ROI says.

| market             |   bets |   win_rate |   units |   roi_pct |   ci_low_pct |   ci_high_pct |   p_above_zero |
|:-------------------|-------:|-----------:|--------:|----------:|-------------:|--------------:|---------------:|
| btts               |     46 |       45.7 |   -0.71 |     -1.54 |        -33.7 |          29.3 |           0.46 |
| corners_total_10_5 |     83 |       41   |   -8.97 |    -10.81 |        -34.8 |          13.1 |           0.2  |
| corners_total_9_5  |     82 |       58.5 |    5.3  |      6.46 |        -13.2 |          25.9 |           0.76 |
| double_chance      |     77 |       42.9 |   -4.22 |     -5.48 |        -31.3 |          21.1 |           0.34 |
| draw_no_bet        |     82 |       36.6 |    5.86 |      7.14 |        -26.9 |          43.6 |           0.64 |
| ALL                |    370 |       44.9 |   -2.75 |     -0.74 |        -14.8 |          14.5 |           0.47 |

Scored candidates: 3972. Bets the card rule would have taken: 370.

## What was dropped, and why

- Dropped 29021 row(s) with no book — a cross-book maximum cannot be shown to have been takeable.
