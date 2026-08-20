# Every market, measured against real prices

Football-Data carries historical odds for 1X2 and the 2.5 goals line and
nothing else, so for a long time everything else could only be checked for
calibration — which rules a model out and cannot rule one in. The provider
sells historical prices per event, so the rest were bought: 291 fixtures of
BTTS, and 150 fixtures of double chance, draw-no-bet and corner totals, priced
three hours before each kick-off at the best price across books.

This is what came back.

| Market | Bets | Profit | ROI | 95% interval | Source |
|:-------|-----:|-------:|----:|:-------------|:-------|
| `1x2` | 500 | +26.7u | +5.3% | −3.4% .. +14.1% | Football-Data, 4 seasons |
| `btts` | 51 | +7.7u | +15.0% | −12.4% .. +42.5% | bought, 291 fixtures |
| `draw_no_bet` | 49 | +6.4u | +13.0% | −15.0% .. +41.0% | bought, 150 fixtures |
| `corners_total_9_5` | 33 | +4.6u | +14.0% | −20.2% .. +48.1% | bought, 150 fixtures |
| `corners_total_10_5` | 37 | +0.6u | +1.7% | −30.5% .. +33.9% | bought, 150 fixtures |
| `double_chance` | 32 | −3.4u | −10.5% | −45.2% .. +24.1% | bought, 150 fixtures |
| `total_2_5` | 6 | −0.7u | −10.8% | −90.8% .. +69.2% | Football-Data, 4 seasons |
| `corners_1x2` | — | — | — | — | **no history exists** |

**Every interval includes zero.** Not one market has a demonstrated edge.

## What the headline numbers hide

**Draw-no-bet's +13.0% is thirteen bets.** The home side returned +66.5% on
n=13; the away side returned −6.3% on n=36. A number that large from a sample
that small is what noise looks like, and the larger half of the same sample
points the other way.

**Double chance is the only negative point estimate, and it is structural.**
Three hundred and thirty-eight of its four hundred and fifty candidates —
seventy-five per cent — were refused for juice. Double chance on a favourite
prices around −400 and the project refuses anything worse than −160, so what
survives is the underdog side, and that side returned −13.4%. This market is
being asked to do the opposite of what it is for.

**Corners over 9.5 is the most interesting of them**, at +14.0% on 33 bets, and
it is also the corner market with the best calibration after shrinkage — 1.6%
worst-band gap against 9.0% for the 10.5 line. Two independent measurements
agreeing is worth more than either alone, and it is still 33 bets.

**Corners 1X2 cannot be measured at any price.** The provider offers it live
and does not retain it historically: a probe returned `alternate_totals_corners`
and `double_chance` for the same fixture and no `corners_1x2` at all. It can be
modelled and calibrated and never backtested, so enabling it would be a bet on
the model with no way to check the bet first.

## What this changes

I previously recommended enabling double chance and draw-no-bet on the grounds
that they were arithmetic on the 1X2 distribution and therefore trusted no more
than 1X2 already is. That argument was sound and incomplete: being derived from
a sound distribution does not make a market profitable once its own prices and
its own juice limit are applied. Measured, one is negative and the other rests
on thirteen bets.

The honest recommendation is now to enable nothing new on this evidence.

## What would change it

Every sample here is one partial season. The cheapest way to make these numbers
mean something is more of them: about 10 credits per market per fixture, so a
second season of one market is roughly 4,000 credits. The samples that most
deserve it are corners over 9.5 and draw-no-bet, in that order — the first
because two independent measurements agree, the second because its result hangs
on a subsample small enough to be an accident.

None of that changes the arithmetic in `what_we_can_and_cannot_claim.md`:
separating a true 5% edge from zero takes about 1,537 bets, and no market here
is within an order of magnitude of that.
