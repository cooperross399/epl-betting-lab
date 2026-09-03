# Derived market backtest

Corners, BTTS, draw-no-bet and double chance judged against prices that were really offered, at books that can really be bet. Which of them this particular run actually covered is in the Coverage table at the bottom — read that before the ROI column.

One snapshot per fixture at a fixed lead before kick-off, so there is **no closing line here and no CLV** — only profit, which is the weaker instrument. Read the interval, not the point estimate: an interval that includes zero has not demonstrated an edge, whatever the ROI says.

`pushes` are bets that returned the stake — a drawn draw-no-bet, a corner total landing on the line. They are bets, so they sit in the denominator at zero profit; dropping them once removed 33 of 115 draw-no-bet selections and reported +7.1% for a rule that returned +5.1%. `win_rate` is therefore over all bets, pushes included.

| market             |   bets |   pushes |   win_rate |   units |   roi_pct |   ci_low_pct |   ci_high_pct |   p_above_zero |
|:-------------------|-------:|---------:|-----------:|--------:|----------:|-------------:|--------------:|---------------:|
| btts               |     31 |        0 |       51.6 |    0.21 |      0.66 |        -34.2 |          34.7 |           0.5  |
| corners_total_10_5 |     48 |        0 |       37.5 |   -9.03 |    -18.82 |        -47   |          11.7 |           0.11 |
| corners_total_9_5  |     74 |        0 |       59.5 |    5.62 |      7.6  |        -12.5 |          28.6 |           0.77 |
| double_chance      |     52 |        0 |       44.2 |   -3.36 |     -6.47 |        -34.8 |          23.4 |           0.33 |
| draw_no_bet        |     68 |       18 |       27.9 |    5.6  |      8.24 |        -22.4 |          43.9 |           0.67 |
| ALL                |    273 |       18 |       44   |   -0.96 |     -0.35 |        -14.7 |          15.6 |           0.47 |

Scored candidates: 4180. Bets the card rule would have taken: 273.

## Coverage

| market | scored | bets |
|---|---:|---:|
| btts | 760 | 31 |
| corners_total_9_5 | 760 | 74 |
| corners_total_10_5 | 760 | 48 |
| double_chance | 1140 | 52 |
| draw_no_bet | 760 | 68 |

## What was dropped, and why

- Dropped 29021 row(s) with no book — a cross-book maximum cannot be shown to have been takeable.
- 121 BETTABLE selection(s) ranked below the card's 8-per-round limit and could never have appeared on a card, so they are not counted as bets. The real card is tighter again: `total_2_5` competes for the same slots and is not in this backtest.
