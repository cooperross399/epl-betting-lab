# EFL backtest

## What this is

A walk-forward test of the ratings model on the three EFL divisions, priced against Football-Data's own bookmaker odds. No provider credit was spent: the prices ship in the same files as the results.

**This is a goals model, not the model the EPL card bets.** Understat publishes xG for six top-tier leagues and none of the EFL, and the card fits a 70/30 xG blend. Asking for the blend here would not fail — it would silently produce this same goals model, because every EFL row has empty xG. So goals were requested explicitly. No number below is comparable with an EPL number.

## Headline

At the closing average price, taking every selection the model rated at 3% edge or better:

- **9,095 bets** across 5,686 matches
- **-8.22% ROI**, 95% interval **-11.18% to -5.23%**
- probability the true ROI is above zero: **0.0%**

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

## Does the model's own edge predict anything?

ROI within each edge band, not above each threshold — a cumulative sweep hides the shape because every band is contaminated by the ones above it. If the edge estimate carried information, ROI would climb across these rows.

| Edge band | Bets | ROI |
|:--|--:|--:|
| < -5% | 19,679 | -5.28% |
| -5..0% | 4,809 | -6.61% |
| 0..3% | 2,267 | -8.10% |
| 3..6% | 1,824 | -7.28% |
| 6..10% | 2,062 | -8.61% |
| 10..20% | 2,768 | -4.57% |
| > 20% | 2,441 | -12.73% |

## Calibration

What the model said would happen, beside what did, and beside what the market said. Every candidate selection, not just the ones bet.

| Model probability | Selections | Model | Market | Actual | Model error |
|:--|--:|--:|--:|--:|--:|
| (0.0, 0.1] | 22 | 8.9% | 10.4% | 9.1% | +0.2 pp |
| (0.1, 0.2] | 906 | 17.1% | 18.8% | 16.1% | -1.0 pp |
| (0.2, 0.3] | 9,646 | 25.8% | 28.3% | 26.3% | +0.5 pp |
| (0.3, 0.4] | 6,364 | 35.3% | 39.2% | 37.4% | +2.1 pp |
| (0.4, 0.5] | 8,952 | 45.2% | 49.4% | 46.9% | +1.8 pp |
| (0.5, 0.6] | 7,106 | 54.5% | 55.6% | 51.8% | -2.6 pp |
| (0.6, 0.7] | 2,086 | 63.3% | 60.9% | 57.3% | -6.0 pp |
| (0.7, 0.8] | 182 | 72.7% | 66.7% | 67.0% | -5.6 pp |

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
