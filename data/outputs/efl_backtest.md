# EFL backtest

## What this is

A walk-forward test of the ratings model on the three EFL divisions, priced against Football-Data's own bookmaker odds. No provider credit was spent: the prices ship in the same files as the results.

**This is a goals model, not the model the EPL card bets.** Understat publishes xG for six top-tier leagues and none of the EFL, and the card fits a 70/30 xG blend. Asking for the blend here would not fail — it would silently produce this same goals model, because every EFL row has empty xG. So goals were requested explicitly. No number below is comparable with an EPL number.

## Headline

At the closing average price, taking every selection the model rated at 3% edge or better:

- **19,142 bets** across 6,348 matches
- **-7.17% ROI**, 95% interval **-9.70% to -4.62%**
- probability the true ROI is above zero: **0.0%**

## The card does not fit one model, so both are measured

`total_2_5` and `btts` are priced on TOTALS_RATINGS — opponent adjusted, 365-day half life. `1x2` and `draw_no_bet` are priced on `CARD_RATINGS = RatingConfig.legacy()`, the unadjusted ratio with no time decay. Measuring one and reporting it against a card that runs two is the fault this module exists to avoid, so the row marked **card** below is the one that answers the question for that market; the other is a robustness check.

| Market | Ratings | Bets | ROI | 95% interval | P(>0) | |
|:--|:--|--:|--:|:--|--:|:--|
| `1x2` | adjusted_goals | 5,411 | -8.28% | -12.18% to -4.18% | 0.0% |  |
| `1x2` | legacy_goals | 5,747 | -5.62% | -9.50% to -1.83% | 0.3% | **card** |
| `draw_no_bet` | adjusted_goals | 685 | -3.25% | -9.44% to +3.09% | 14.6% |  |
| `draw_no_bet` | legacy_goals | 762 | -3.24% | -9.17% to +2.77% | 14.3% | **card** |
| `total_2_5` | adjusted_goals | 3,011 | -9.30% | -12.60% to -5.78% | 0.0% | **card** |
| `total_2_5` | legacy_goals | 3,526 | -7.81% | -10.78% to -4.66% | 0.0% |  |

## The price you pay, on identical bets

Same model, same selections, same threshold — settled at three different execution prices. The spread between them is larger than any model change measured in this project.

| Price taken | Ratings | Bets | ROI | 95% interval | P(>0) |
|:--|:--|--:|--:|:--|--:|
| closing_average | adjusted_goals | 9,107 | -8.24% | -11.06% to -5.19% | 0.0% |
| closing_average | legacy_goals | 10,035 | -6.21% | -8.88% to -3.51% | 0.0% |
| closing_best * | adjusted_goals | 12,818 | -2.93% | -5.38% to -0.54% | 1.0% |
| closing_best * | legacy_goals | 13,325 | -2.02% | -4.27% to +0.34% | 4.9% |
| opening_average | adjusted_goals | 8,546 | -7.80% | -10.50% to -4.80% | 0.0% |
| opening_average | legacy_goals | 9,724 | -7.20% | -10.00% to -4.62% | 0.0% |

\* `closing_best` is an **upper bound, not a result.** It is the highest price Football-Data saw across its panel at its collection instant. Taking it requires an account at whichever book was the outlier, that book still offering it, and it accepting the stake — and the book offering an outlier price is the one most likely to restrict an account that keeps taking it. It is also unverified whether the panel maximum is simultaneously obtainable at all, or an artefact of prices collected moments apart. Treat the gap between `closing_average` and `closing_best` as the size of the execution problem, not as profit.

## By division and market

Closing average, edge >= 3%. An interval that excludes zero is a result, not a hint.

| Division | Market | Bets | ROI | 95% interval | P(>0) |
|:--|:--|--:|--:|:--|--:|
| E1 | `1x2` | 1,936 | -7.65% | -14.45% to -0.54% | 1.6% |
| E1 | `draw_no_bet` | 231 | -5.11% | -15.81% to +5.43% | 17.2% |
| E1 | `total_2_5` | 1,112 | -6.57% | -12.58% to -0.60% | 1.4% |
| E2 | `1x2` | 1,711 | -8.53% | -15.77% to -1.15% | 0.8% |
| E2 | `draw_no_bet` | 211 | +1.71% | -9.42% to +12.66% | 62.2% |
| E2 | `total_2_5` | 869 | -16.48% | -22.78% to -10.21% | 0.0% |
| E3 | `1x2` | 1,764 | -8.73% | -15.92% to -1.50% | 0.9% |
| E3 | `draw_no_bet` | 243 | -5.79% | -16.42% to +4.19% | 12.7% |
| E3 | `total_2_5` | 1,030 | -6.17% | -12.13% to -0.58% | 1.8% |
| E1 | `1x2` | 1,924 | -0.51% | -7.20% to +6.71% | 43.1% |
| E1 | `draw_no_bet` | 231 | -9.23% | -20.10% to +1.23% | 4.0% |
| E1 | `total_2_5` | 1,237 | -6.41% | -11.99% to -0.78% | 1.3% |
| E2 | `1x2` | 1,865 | -7.18% | -13.91% to -0.42% | 2.0% |
| E2 | `draw_no_bet` | 254 | -1.24% | -11.53% to +9.01% | 43.0% |
| E2 | `total_2_5` | 1,047 | -14.52% | -20.29% to -8.62% | 0.0% |
| E3 | `1x2` | 1,958 | -9.15% | -15.73% to -2.62% | 0.2% |
| E3 | `draw_no_bet` | 277 | -0.08% | -9.42% to +9.44% | 50.1% |
| E3 | `total_2_5` | 1,242 | -3.56% | -8.79% to +1.64% | 8.7% |

## Does the model's own edge predict anything?

ROI within each edge band, not above each threshold — a cumulative sweep hides the shape because every band is contaminated by the ones above it. If the edge estimate carried information, ROI would climb across these rows.

| Edge band | Bets | ROI |
|:--|--:|--:|
| < -5% | 39,412 | -5.63% |
| -5..0% | 8,869 | -6.61% |
| 0..3% | 4,377 | -9.38% |
| 3..6% | 3,496 | -6.70% |
| 6..10% | 3,878 | -6.58% |
| 10..20% | 5,704 | -4.57% |
| > 20% | 6,064 | -10.28% |

## Calibration

What the model said would happen, beside what did, and beside what the market said. Every candidate selection, not just the ones bet.

| Model probability | Selections | Model | Market | Actual | Model error |
|:--|--:|--:|--:|--:|--:|
| (0.0, 0.1] | 226 | 7.1% | 24.2% | 20.4% | +13.3 pp |
| (0.1, 0.2] | 2,626 | 16.7% | 22.7% | 20.1% | +3.5 pp |
| (0.2, 0.3] | 18,919 | 25.7% | 28.9% | 26.8% | +1.1 pp |
| (0.3, 0.4] | 12,499 | 35.3% | 39.7% | 37.8% | +2.5 pp |
| (0.4, 0.5] | 17,037 | 45.1% | 49.1% | 46.7% | +1.6 pp |
| (0.5, 0.6] | 13,766 | 54.5% | 55.1% | 51.2% | -3.4 pp |
| (0.6, 0.7] | 4,702 | 63.6% | 59.7% | 56.6% | -7.0 pp |
| (0.7, 0.8] | 691 | 73.5% | 62.3% | 62.7% | -10.8 pp |
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
