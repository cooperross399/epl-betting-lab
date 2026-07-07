# EPL Betting Lab — Agent Weekly Brief

**Data basis:** No `2627` matches found yet. Using the latest 380 completed matches as preseason baseline.

## League market trends

- Completed matches in basis: 380
- Average goals per match: 2.75
- Home win rate: 42.6%
- Draw rate: 27.4%
- Away win rate: 30.0%
- Over 2.5 rate: 55.0%
- BTTS rate: 56.1%

## Teams to review manually

Use these lists as prompts for model review, not automatic bets.

### Strong recent form

| team          |   matches |   points |   wins |   draws |   losses |   goals_for |   goals_against |   goal_diff |   points_per_match |   gf_per_match |   ga_per_match |
|:--------------|----------:|---------:|-------:|--------:|---------:|------------:|----------------:|------------:|-------------------:|---------------:|---------------:|
| Man United    |         6 |       16 |      5 |       1 |        0 |          12 |               5 |           7 |               2.67 |           2    |           0.83 |
| Arsenal       |         6 |       15 |      5 |       0 |        1 |           9 |               3 |           6 |               2.5  |           1.5  |           0.5  |
| Bournemouth   |         6 |       12 |      3 |       3 |        0 |          10 |               5 |           5 |               2    |           1.67 |           0.83 |
| Nott'm Forest |         6 |       11 |      3 |       2 |        1 |          16 |               7 |           9 |               1.83 |           2.67 |           1.17 |
| Man City      |         6 |       11 |      3 |       2 |        1 |          12 |               6 |           6 |               1.83 |           2    |           1    |
| Leeds         |         6 |       11 |      3 |       2 |        1 |          10 |               7 |           3 |               1.83 |           1.67 |           1.17 |
| Tottenham     |         6 |       11 |      3 |       2 |        1 |           8 |               6 |           2 |               1.83 |           1.33 |           1    |
| Aston Villa   |         6 |       10 |      3 |       1 |        2 |          13 |              11 |           2 |               1.67 |           2.17 |           1.83 |

### Weak recent form

| team           |   matches |   points |   wins |   draws |   losses |   goals_for |   goals_against |   goal_diff |   points_per_match |   gf_per_match |   ga_per_match |
|:---------------|----------:|---------:|-------:|--------:|---------:|------------:|----------------:|------------:|-------------------:|---------------:|---------------:|
| Crystal Palace |         6 |        2 |      0 |       2 |        4 |           6 |              15 |          -9 |               0.33 |           1    |           2.5  |
| Burnley        |         6 |        2 |      0 |       2 |        4 |           5 |              12 |          -7 |               0.33 |           0.83 |           2    |
| Everton        |         6 |        2 |      0 |       2 |        4 |           8 |              13 |          -5 |               0.33 |           1.33 |           2.17 |
| Wolves         |         6 |        3 |      0 |       3 |        3 |           3 |              10 |          -7 |               0.5  |           0.5  |           1.67 |
| Chelsea        |         6 |        4 |      1 |       1 |        4 |           5 |              11 |          -6 |               0.67 |           0.83 |           1.83 |
| Brentford      |         6 |        6 |      1 |       3 |        2 |           7 |               8 |          -1 |               1    |           1.17 |           1.33 |
| West Ham       |         6 |        7 |      2 |       1 |        3 |           6 |               8 |          -2 |               1.17 |           1    |           1.33 |
| Newcastle      |         6 |        7 |      2 |       1 |        3 |           8 |               8 |           0 |               1.17 |           1.33 |           1.33 |

### High-event teams

| team        |   matches |   avg_total_goals |   over_2_5_rate |   btts_rate |
|:------------|----------:|------------------:|----------------:|------------:|
| Chelsea     |        38 |              2.89 |           0.658 |       0.632 |
| Man United  |        38 |              3.13 |           0.632 |       0.711 |
| Man City    |        38 |              2.95 |           0.632 |       0.5   |
| Newcastle   |        38 |              2.84 |           0.632 |       0.658 |
| Tottenham   |        38 |              2.76 |           0.632 |       0.605 |
| Liverpool   |        38 |              3.05 |           0.605 |       0.684 |
| West Ham    |        38 |              2.92 |           0.605 |       0.526 |
| Bournemouth |        38 |              2.95 |           0.553 |       0.658 |

### Low-event teams

| team          |   matches |   avg_total_goals |   over_2_5_rate |   btts_rate |
|:--------------|----------:|------------------:|----------------:|------------:|
| Sunderland    |        38 |              2.37 |           0.447 |       0.474 |
| Wolves        |        38 |              2.5  |           0.447 |       0.447 |
| Everton       |        38 |              2.55 |           0.447 |       0.5   |
| Brighton      |        38 |              2.58 |           0.5   |       0.553 |
| Fulham        |        38 |              2.58 |           0.5   |       0.526 |
| Burnley       |        38 |              2.97 |           0.5   |       0.579 |
| Arsenal       |        38 |              2.58 |           0.526 |       0.474 |
| Nott'm Forest |        38 |              2.61 |           0.526 |       0.474 |

## Codex next-step checklist

- Check whether the backtest is over-firing on any market.
- Compare current-season goal environment to the historical baseline.
- Review promoted teams separately before adding automatic fades.
- Do not change thresholds because of one result or one matchweek.
- If current odds are missing, request manual odds before generating a real weekly card.