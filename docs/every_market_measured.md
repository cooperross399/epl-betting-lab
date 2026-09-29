# Every market, measured against real prices

Football-Data carries historical odds for 1X2 and the 2.5 goals line and
nothing else, so for a long time everything else could only be checked for
calibration — which rules a model out and cannot rule one in. The provider
sells historical prices per event, so the rest were bought: 291 fixtures of
BTTS, and 150 fixtures of double chance, draw-no-bet and corner totals.

**The first harvest priced them at the best price across books, and those
numbers are gone.** A maximum taken over books Cooper cannot bet is optimistic
by construction; the run that produced it was ruled unusable and the generated
report drops those rows. The table below is the bettable-books measurement out
of `data/outputs/derived_market_backtest.md`, which is what the card's own
rules would have taken at prices that were really available.

The superseded figures sat in this table for weeks and were quoted from
CLAUDE.md as the answer to "does it work?". Four of the five were more
flattering than the truth, and `corners_total_10_5` went from +1.7% to
−18.8%. They are listed at the bottom so the size of that gap is on the
record rather than merely corrected.

| Market | Bets | Profit | ROI | 95% interval | Source |
|:-------|-----:|-------:|----:|:-------------|:-------|
| `1x2` | 500 | +26.7u | +5.3% | −3.4% .. +14.1% | Football-Data, 4 seasons |
| `btts` | 31 | +0.2u | +0.66% | −34.2% .. +34.7% | bought, bettable books |
| `draw_no_bet` | 68 | +5.6u | +8.24% | −22.4% .. +43.9% | bought, bettable books |
| `corners_total_9_5` | 74 | +5.6u | +7.6% | −12.5% .. +28.6% | bought, bettable books |
| `corners_total_10_5` | 48 | −9.0u | −18.82% | −47.0% .. +11.7% | bought, bettable books |
| `double_chance` | 52 | −3.4u | −6.47% | −34.8% .. +23.4% | bought, bettable books |
| `total_2_5` | 6 | −0.7u | −10.8% | −90.8% .. +69.2% | Football-Data, 4 seasons |
| `corners_1x2` | — | — | — | — | **no history exists** |

Across every bought market together: **273 bets, −0.96u, −0.35% ROI, −14.7%
to +15.6%.** The pooled result is a loss, and its interval contains zero.

### What the best-price-across-books harvest said

| Market | Bets | ROI | now |
|:-------|-----:|----:|----:|
| `btts` | 51 | +15.0% | +0.66% |
| `draw_no_bet` | 49 | +13.0% | +8.24% |
| `corners_total_9_5` | 33 | +14.0% | +7.6% |
| `corners_total_10_5` | 37 | +1.7% | −18.82% |
| `double_chance` | 32 | −10.5% | −6.47% |

**Every interval includes zero.** Not one market has a demonstrated edge.

## What the headline numbers hide

**Draw-no-bet is +8.24% on 68 bets, eighteen of them pushes.** This paragraph
read "+13.0% is thirteen bets" until 2026-09-29, with a home/away split of
+66.5% on n=13 against −6.3% on n=36. Those are the best-price-across-books
figures; the table above replaced them and the paragraph reading it did not
move. The split has not been recomputed on the bettable-books sample, so it
is retracted rather than restated — the honest summary of the current
measurement is the interval, −22.4% to +43.9%, which contains zero and most
of the plausible range on either side of it.

**Three point estimates are negative, and the worst is corners.**
`corners_total_10_5` is −18.82% on 48 bets, `total_2_5` is −10.8% on 6, and
`double_chance` is −6.47% on 52. This paragraph said double chance was "the
only negative point estimate", which was true of the harvest and not of the
measurement table; it then said two, which missed `total_2_5` because the
guard counting them looked only at the markets whose prices were bought.

Double chance's number is still structural, and that part holds.
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
