# Fading the public: tested, and not there

Cooper asked whether expert or website predictions, and the side the public is
on, could feed the model — the reasoning being that public money distorts
prices and the value sits on the unpopular side. The reasoning is sound and the
mechanism is real. This records what happened when it was measured, so it is
not re-derived from scratch.

## Tipster and website predictions: not pursued

Not measured, and deliberately. A published prediction carries no price, no
stake, no record, and no accountability, and the ones that are free are mostly
the favourite restated. There is nothing to backtest and no way to tell a good
one from a lucky one at the sample sizes available. The *mechanism* Cooper was
pointing at — crowd money moving prices — is real and is what was tested.

## What was tested

Football-Data ships **Pinnacle** (`PSH/PSD/PSA`) on 1,730 of 1,920 matches,
with closing prices, alongside recreational books and a bookmaker average.
Pinnacle takes sharp action and moves on it; recreational books shade toward
the public. So the disagreement between them is the public lean, and no model
is needed to test it — this is a question about prices alone.

Held out by date: train to 2025-07-01 (1,520 matches), test after (210).

| | Train | Held out |
|:--|--:|--:|
| Fade the public (soft market coldest on a side) | +19.6% / 56 bets | **−34.6% / 29** |
| Follow the public (the same signal inverted, as a control) | −10.4% / 48 | **−41.4% / 36** |
| Sharp fair beats the best available price | +0.4% / 1,698 | **−7.6% / 100** |

Both directions lose out of sample. When a signal and its exact inverse both
lose, the sample is telling you it has nothing to say.

## Why, and it is not that the idea is wrong

**The disagreement barely exists.** Once each side's margin is removed
properly, Pinnacle's mean margin is 3.1% and the bookmaker average's 4.4%, and
a fair-probability disagreement larger than two points fires on **0.0%** of
selections. Larger than one point: about 2% of them. There is no public lean
sitting in the static price spread to exploit, because the average of eleven
books already sits nearly on top of the sharpest one.

## Two dead ends worth recording, because both looked like findings

**Normalising the margin away manufactures edges.** Scaling three prices to sum
to one overstates favourites and understates longshots, so a "sharp fair versus
price" edge computed that way is a longshot generator: it flagged 38% of all
selections and lost 27% on held-out bets. Using the power method — solve k so
the de-vigged probabilities sum to one — removes it. This is not an argument
against betting longshots; it is that the estimator was inventing edges that
were not there.

**"The best price beats a sharp book's price" is arithmetic, not a signal.** It
is true of 93.2% of selections, because the maximum across ten books exceeds
any single book's price nearly always. A closing-line number computed from that
comparison measures the same tautology and looks encouragingly positive while
meaning nothing.

## Where the idea could still live

The signal that fade-the-public strategies actually use is not a static price
spread. It is **ticket and money percentages**, which no source this project
reaches provides, and **reverse line movement** — the price drifting against
the popular side, which is the observable footprint of sharp money and needs a
time series rather than a snapshot.

That time series did not exist when this was tested. It does now:
`refs/heads/price-feed` records all eleven books at every run from 2026-09-02.
When it holds a few weeks of matchdays, reverse line movement becomes testable
for the first time — and unlike everything above, it would be testable on the
markets that actually carry this card.

One concrete gap first: **Pinnacle is not among the books fetched live.** The
provider is queried with `--regions us` and Pinnacle sits under `eu`. Without a
sharp reference in the feed there is nothing to measure soft-book drift
against, so adding that region is the prerequisite for any of this.
