# The profit was the filter

A record of what the model changes of 2026-08-28 found, and why the live card
did not change with them. It belongs beside `why_better_calibration_lost_money.md`
and is the same lesson from the other side: that one was a better model that
lost money; this is a better model that could not find any to make.

## What changed in the model

Three things, each measured without a betting threshold in the way:

| Ratings | 1X2 log loss | 1X2 Brier | Over 2.5 log loss |
|:--|--:|--:|--:|
| Old: goals ratio, last 38 matches | 1.0014 | 0.5948 | 0.6836 |
| Opponent-adjusted, 365-day half-life | 0.9869 | 0.5872 | 0.6758 |
| …fitted on 70% xG / 30% goals | **0.9835** | **0.5844** | **0.6719** |
| The closing market, de-vigged | 0.9654 | 0.5740 | 0.6698 |

Lower is better. The new ratings close about half the gap to the market on
1X2 and nearly all of it on the 2.5 line. They are, by any threshold-free
measure, a better model: schedule strength no longer flatters a team, evidence
fades with age instead of falling off a cliff, and chances count for more than
the deflections they became.

## Then the backtest ran, the way it always had

| 1X2, one pass over all seasons | Bets | Units | ROI |
|:--|--:|--:|--:|
| Old model, calibrated rule | 502 | **+34.4** | +6.9% |
| New model, calibrated rule | 553 | **−73.8** | −13.4% |

A better model, a hundred units worse. That is the shape of the earlier
mistake, so this time the question was asked properly.

## Where the +34 came from

The raw rule — bet whenever the model clears the price by the minimum edge,
no calibration, no shrinkage — loses with the old model too:

| Old model, 1X2 | Bets | Units | ROI |
|:--|--:|--:|--:|
| Raw rule | 774 | **−5.7** | −0.7% |
| Calibrated rule | 502 | **+34.4** | +6.9% |

The entire profit is the 272 bets the filter removes, and the filter's weights
and thresholds were chosen while looking at this same five-season pass. That
is not evidence of an edge. It is a fit to the answers.

The closing line agrees. Closing odds had been dropped when the dataset was
built, so every CLV figure the project had ever shown was blank; with them
restored, the old model's 502 bets have an average CLV of **−0.21 points** and
only **46.8%** beat the close.

## Held-out seasons

Split by season — rules chosen on 2021/22 through 2024/25, read on 2025/26 and
2026/27 — with a market-anchored rule that blends the model with the price in
logit space (weight `a` on the model) and bets where the blend still clears the
opening price by a margin:

**1X2.** Every cell, both models, loses on the held-out seasons: the old model
between −2% and −6%, the new one between −6% and −15%. Training-season CLV is
negative in every cell. The new model's losses are the compression artefact
`why_better_calibration_lost_money.md` describes — it rates every match closer
than the market does, so its "edges" are draws and long-priced away sides,
which went 381 bets and −98 units in the single-pass backtest.

**Over/under 2.5.** The old model loses everywhere. The new model sits on the
market: held-out CLV between −0.3 and +0.1 points, held-out ROI scattered from
−2% to +14% on 78 to 350 bets. Those are the numbers of a rule with no
demonstrated edge and none ruled out. Choosing the best of them would be the
in-sample mistake again; the honest read is that this market is the one place
the model is not demonstrably behind the price.

### Correction, 2026-09-02: the figures above scored a rule nobody runs

The anchored rule flags a bet on lift over the de-vigged consensus. The card
then zeroes any row whose edge against the *posted* price is not positive —
`_confidence_tier` returns Pass/Avoid on `edge <= 0` — so a row can clear the
lift bar, be marked BETTABLE, and be staked at nothing. That is not a corner
case: the largest lift on the 2026-09-02 slate was +0.024 against an edge of
−0.009. The live rule was therefore strictly tighter than the measured one, and
the published numbers described the looser rule.

`score_rule` now applies the price gate by default, so the figures describe
what runs. At the live setting — model weight 0.5, lift 0.03 — on the held-out
seasons:

| | Bets | CLV (points) | ROI | Units |
|:--|--:|--:|--:|--:|
| The rule that runs (price gate) | 95 | **−0.138** | +7.5% | +7.09 |
| The looser rule scored before | 117 | — | +10.2% | +11.92 |

Profit is positive and closing-line value is negative, on 95 bets. Two weak
proxies pointing opposite ways is not an edge; it is the sample being too small
for either to mean anything, and the CLV sign is the one that should worry a
reader, because it says the market moved against these bets on average. The
grid is reported with both columns so the cost of the gate is visible rather
than asserted: `data/outputs/out_of_sample_*_total_2_5.csv`.

The gate stays, for a reason that is not the ROI. A row with `edge <= 0` is a
price the model's own final number calls negative. Staking it because the
backtest happened to include such rows would be letting a measurement authorise
something indefensible on its face.

Full tables: `data/outputs/out_of_sample_*.md`, regenerated by
`scripts/run_out_of_sample.py`.

## What was done with it

- The new ratings are in the code and available to every backtest, behind
  `RatingConfig`. The live card still runs the old ratings, because the only
  bet rule it has was tuned to them, and under that rule the new model bets
  the artefact.
- Closing odds now reach every backtested bet, and CLV is reported. It is the
  only feedback that returns an answer inside a season.
- **1X2 is off the card.** Cooper directed it in chat the same day, after
  being told it was his market-scope call ("yes keep going do everything");
  `CARD_DISABLED_MARKETS` in `reports/automated_card_input.py` is the record.
  The library still judges 1X2 on coverage; the card declines it on top.
- **The 2.5 line is live on the new ratings, under the anchored rule, at the
  smallest stake.** `TOTALS_RATINGS` prices it; `evaluate_total_25_anchored`
  blends the model with the consensus price at weight 0.5 and bets only a
  3-point lift — the conservative end of the grid, fixed before the held-out
  seasons were read and not to be re-tuned on them. Every such row carries
  `selection_rule = market_anchored` and is capped at tier C (0.1u) whatever
  its ranking score. It is tracked forward by CLV; raising the stake is a
  decision for that record to earn.

## What to take from it

Calibration rules a model out. Profit on the seasons the rule was tuned on
rules nothing in. Only held-out seasons and the closing line can do that, and
on this data they say: better model, no edge — which is worth knowing, because
a rule that is not beating the close is paying the margin on every bet.
