# What the evidence actually supports

Every market has now been measured as far as the available data allows. This is
what came back, stated plainly, because the numbers are more encouraging than
the conclusion and it would be easy to read only the numbers.

## The two markets with real prices

| Market | Bets | Profit | ROI | 95% interval on ROI |
|:-------|-----:|-------:|----:|:--------------------|
| 1X2 (after the longshot cap) | 500 | +26.7u | +5.3% | −3.4% .. +14.1% |
| BTTS (bought, bettable books) | 31 | +0.2u | +0.66% | −34.2% .. +34.7% |
| Every bought market together | 273 | −0.96u | −0.35% | −14.7% .. +15.6% |

The BTTS row read 51 bets at +15.0% until 2026-09-29. That was the first
harvest, priced at the best price across books — a maximum over books Cooper
cannot bet, optimistic by construction, and ruled unusable when the bettable
filter went in. The generated report dropped those rows and this table did
not follow, so the most flattering number in the project was also its most
quoted one.

One point estimate is positive and small, one is negative. **No interval
excludes zero.**

Nothing here demonstrates an edge. The results are equally consistent with a
small real edge and with a model that is breaking even.

## How much data would settle it

| If the true edge were | Bets needed to separate it from zero |
|----------------------:|-------------------------------------:|
| +5%                   | ~1,537 |
| +10%                  | ~384 |
| +15%                  | ~171 |

The 1X2 backtest places about 125 bets a season. Demonstrating a +5% edge would
take roughly twelve seasons of them. That is not a gap that more careful
analysis closes — it is more seasons than the sport has played since the data
starts.

So the honest position is that this system's edge is **unproven and likely to
stay unproven for years**, whatever it turns out to be.

## What that means in practice

**The stake sizing is already right.** A unit is $25 and a C-tier bet is 0.1
units — $2.50. That is the correct size for a position whose expected value is
genuinely uncertain, and it is worth noticing that the sizing was more honest
than any claim made about the model.

**Beware anything that improves the estimate a lot.** With intervals this wide,
a change can move measured ROI several points purely by chance. That is how the
shrinkage change came to look like an improvement across every market while
costing 140 units — see `why_better_calibration_lost_money.md`.

**Prefer changes with a mechanism.** The longshot cap was worth making not
because it improved ROI from +1.3% to +5.3%, but because a model with
independent-Poisson tails is known to overstate long prices, the excluded band
went 0 for 12, and the result held across every threshold from +300 to +600. The
ROI improvement is the weakest part of that argument.

## Slicing the same data does not produce new evidence

Investigating this project produced roughly twenty-five segment analyses of the
same four seasons: by selection, by price band, by edge band, by season, by
market, by conviction. Exactly one of them cleared 95% significance — bets with
a calibrated edge between 3.5% and 4.5% returned +21.6% over 166 bets, naive
interval +6.4% to +36.8%.

That is what chance looks like. With twenty-five looks at one dataset, the
probability of at least one 95% result is 72%. Correcting for the number of
looks widens that interval to −0.2% to +43.4%, which includes zero like every
other.

The pattern around it says the same thing. Leans, at the smallest edges, lose.
Bets above 4.5% edge lose slightly. Only the narrow band between them wins — a
sweet spot with losses on both sides, found after the fact, in data that has
been searched hard. Nothing about the model explains why that band and not its
neighbours.

So it is recorded and not acted on. A threshold moved to sit on it would be
fitted to this sample and to nothing else. The rule that survives is the one
already written down: prefer a change with a mechanism, and treat a result that
improves the estimate a lot as a reason for suspicion rather than enthusiasm.

## What cannot be measured at all

`corners_1x2`. The provider does not retain a historical corner match-result
price and no free archive carries one, so it can be checked for calibration
only — which rules a model out and cannot rule one in.

That is the whole list now. This section used to name corners, double chance
and draw-no-bet as well, saying they "have no historical prices anywhere" and
"have been checked for calibration only". All of them were subsequently
bought fixture by fixture, exactly as it said BTTS had been, and they are in
the table above with bets and intervals — measured, and in two cases measured
negative. A section describing what cannot be known is the last place that
should lag the thing it describes.

## The one thing that is certain

Every claim above rests on results already observed. The first genuinely
out-of-sample evidence this project will ever have is the season now being
played, one matchweek at a time. That is worth more than any further slicing of
the seasons already in the file.
