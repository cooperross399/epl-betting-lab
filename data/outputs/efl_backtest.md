# EFL backtest

## What this is

A walk-forward test of the ratings model on the three EFL divisions, priced against Football-Data's own bookmaker odds. No provider credit was spent: the prices ship in the same files as the results.

**This is a goals model, not the model the EPL card bets.** Understat publishes xG for six top-tier leagues and none of the EFL, and the card fits a 70/30 xG blend. Asking for the blend here would not fail — it would silently produce this same goals model, because every EFL row has empty xG. So goals were requested explicitly. No number below is comparable with an EPL number.

## Headline

At the closing average price, taking every selection the model rated at 3% edge or better:

- **19,114 bets** across 6,339 matches
- **-7.20% ROI**, 95% interval **-9.92% to -4.53%**
- probability the true ROI is above zero: **0.0%**

## The card does not fit one model, so both are measured

`total_2_5` and `btts` are priced on TOTALS_RATINGS — opponent adjusted, 365-day half life. `1x2` and `draw_no_bet` are priced on `CARD_RATINGS = RatingConfig.legacy()`, the unadjusted ratio with no time decay. Measuring one and reporting it against a card that runs two is the fault this module exists to avoid, so the row marked **card** below is the one that answers the question for that market; the other is a robustness check.

| Market | Ratings | Bets | ROI | 95% interval | P(>0) | |
|:--|:--|--:|--:|:--|--:|:--|
| `1x2` | adjusted_goals | 5,405 | -8.24% | -12.18% to -4.43% | 0.0% |  |
| `1x2` | legacy_goals | 5,738 | -5.69% | -9.53% to -1.65% | 0.1% | **card** |
| `draw_no_bet` | adjusted_goals | 685 | -3.25% | -9.44% to +3.09% | 14.6% |  |
| `draw_no_bet` | legacy_goals | 762 | -3.24% | -9.17% to +2.77% | 14.3% | **card** |
| `total_2_5` | adjusted_goals | 3,005 | -9.31% | -12.61% to -5.89% | 0.0% | **card** |
| `total_2_5` | legacy_goals | 3,519 | -7.89% | -11.23% to -4.61% | 0.0% |  |

## By division and market

Closing average, edge >= 3%. An interval that excludes zero is a result, not a hint.

| Division | Market | Bets | ROI | 95% interval | P(>0) |
|:--|:--|--:|--:|:--|--:|
| E1 | `1x2` | 1,931 | -7.41% | -14.53% to -0.43% | 1.9% |
| E1 | `draw_no_bet` | 231 | -5.11% | -15.81% to +5.43% | 17.2% |
| E1 | `total_2_5` | 1,106 | -6.59% | -12.30% to -0.96% | 1.1% |
| E2 | `1x2` | 1,710 | -8.67% | -15.85% to -1.39% | 1.1% |
| E2 | `draw_no_bet` | 211 | +1.71% | -9.42% to +12.66% | 62.2% |
| E2 | `total_2_5` | 869 | -16.48% | -22.78% to -10.21% | 0.0% |
| E3 | `1x2` | 1,764 | -8.73% | -15.92% to -1.50% | 0.9% |
| E3 | `draw_no_bet` | 243 | -5.79% | -16.42% to +4.19% | 12.7% |
| E3 | `total_2_5` | 1,030 | -6.17% | -12.13% to -0.58% | 1.8% |
| E1 | `1x2` | 1,916 | -0.56% | -7.57% to +6.74% | 43.0% |
| E1 | `draw_no_bet` | 231 | -9.23% | -20.10% to +1.23% | 4.0% |
| E1 | `total_2_5` | 1,231 | -6.69% | -12.19% to -1.44% | 0.5% |
| E2 | `1x2` | 1,864 | -7.31% | -14.27% to -0.80% | 1.6% |
| E2 | `draw_no_bet` | 254 | -1.24% | -11.53% to +9.01% | 43.0% |
| E2 | `total_2_5` | 1,046 | -14.44% | -20.17% to -8.63% | 0.0% |
| E3 | `1x2` | 1,958 | -9.15% | -15.73% to -2.62% | 0.2% |
| E3 | `draw_no_bet` | 277 | -0.08% | -9.42% to +9.44% | 50.1% |
| E3 | `total_2_5` | 1,242 | -3.56% | -8.79% to +1.64% | 8.7% |

## Does the model's own edge predict anything?

ROI within each edge band, not above each threshold — a cumulative sweep hides the shape because every band is contaminated by the ones above it. If the edge estimate carried information, ROI would climb across these rows.

| Edge band | Bets | ROI |
|:--|--:|--:|
| < -5% | 39,356 | -5.60% |
| -5..0% | 8,860 | -6.60% |
| 0..3% | 4,370 | -9.41% |
| 3..6% | 3,490 | -6.75% |
| 6..10% | 3,876 | -6.62% |
| 10..20% | 5,696 | -4.56% |
| > 20% | 6,052 | -10.32% |

## Calibration

What the model said would happen, beside what did, and beside what the market said. Every candidate selection, not just the ones bet.

| Model probability | Selections | Model | Market | Actual | Model error |
|:--|--:|--:|--:|--:|--:|
| (0.0, 0.1] | 226 | 7.1% | 24.2% | 20.4% | +13.3 pp |
| (0.1, 0.2] | 2,622 | 16.7% | 22.7% | 20.2% | +3.5 pp |
| (0.2, 0.3] | 18,893 | 25.7% | 28.9% | 26.8% | +1.1 pp |
| (0.3, 0.4] | 12,476 | 35.3% | 39.7% | 37.8% | +2.5 pp |
| (0.4, 0.5] | 17,015 | 45.1% | 49.1% | 46.7% | +1.6 pp |
| (0.5, 0.6] | 13,749 | 54.5% | 55.1% | 51.2% | -3.4 pp |
| (0.6, 0.7] | 4,696 | 63.6% | 59.7% | 56.5% | -7.1 pp |
| (0.7, 0.8] | 689 | 73.5% | 62.3% | 62.6% | -10.9 pp |
| (0.8, 0.9] | 133 | 84.4% | 58.4% | 57.1% | -27.3 pp |
| (0.9, 1.0] | 29 | 94.3% | 57.6% | 44.8% | -49.4 pp |

## Coverage

The card bets seven markets. This test could price three. A market absent from the tables above was not measured and found fine — it was not measured.

| Card market | Measured here | Why not |
|:--|:--|:--|
| `total_2_5` | yes | |
| `btts` | **no** | Football-Data quotes no both-teams-to-score price. |
| `double_chance` | **no** | Football-Data quotes no double-chance price. It could be derived from the 1X2 prices, but a derived price is not one anybody could have taken — books charge more for the combination — and betting it would manufacture an edge out of the arithmetic. |
| `draw_no_bet` | yes | |
| `corners_1x2` | **no** | Football-Data carries corner counts (HC/AC) but no corner prices. |
| `corners_total_9_5` | **no** | Football-Data carries corner counts (HC/AC) but no corner prices. |
| `corners_total_10_5` | **no** | Football-Data carries corner counts (HC/AC) but no corner prices. |

`1x2` is measured here and is *not* on the card — it is kept as a reference because it is the market Football-Data prices most completely, and because the card excluded it for losing out of sample.
