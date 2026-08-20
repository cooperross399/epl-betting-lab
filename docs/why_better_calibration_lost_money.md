# Better calibration, worse money

A record of a change that was not made, and why. It is here because the
reasoning behind it was good, the evidence for it was strong, and it would have
cost real money — which makes it the kind of mistake worth being able to
recognise a second time.

## What prompted it

BTTS produces most of the picks on a live card and cannot be profit-backtested:
Football-Data ships historical prices for 1X2 and the 2.5 goals line, and none
at all for BTTS. So the only check available is calibration — does a stated
probability match how often the thing happens.

Measured walk-forward across five seasons, the raw model under-stated both
teams scoring in exactly the bands where it bets:

| Predicted band | Matches | Predicted | Observed | Gap |
|:---------------|--------:|----------:|---------:|----:|
| 30-45%         |     307 |     40.2% |    49.5% | +9.3% |
| 45-55%         |     619 |     50.3% |    59.0% | +8.6% |
| 55-70%         |     735 |     60.1% |    55.2% | -4.9% |

Predictions too extreme in both directions. The same shape the corners model
had before shrinkage, and the same fix applied: pull each team's attack and
defence toward the league average by how much evidence stands behind it.

## It worked, by the measure it was aimed at

| Shrinkage | BTTS gap | Over 2.5 gap | 1X2 home gap |
|----------:|---------:|-------------:|-------------:|
| none      |     9.2% |        14.5% |         8.4% |
| 20        |     6.7% |        10.4% |         4.4% |
| 40        |     3.9% |         9.1% |         7.4% |
| 80        |     3.2% |         2.4% |        13.6% |

Twenty improved all three markets at once. On calibration alone it is a clear,
unambiguous improvement, and it would have been easy to ship on that evidence.

## Then the profit backtest ran

| | Bets | Profit (units) | ROI |
|:--|--:|--:|--:|
| Before | 546 | +7.17 | **+1.3%** |
| After  | 851 | -134.18 | **-15.8%** |

Strictly better calibration. Roughly a hundred and forty units worse.

## Why

Edge does not come from being right on average. It comes from being right where
the price is wrong.

Shrinking toward the league average makes a model more often approximately
correct, and less able to say anything the market has not already said. Worse,
it moves probabilities toward a prior that disagrees with sharp prices in a
systematic direction, so the model finds *more* apparent edges — 546 bets became
851 — and the new ones are artefacts of the shrinkage rather than mispricings.

A well-calibrated model that agrees with the closing line everywhere has no
edge anywhere. Calibration is a property of being sensible. Profit is a
property of disagreeing with a specific price, correctly.

## What to take from it

**Calibration is a precondition, not a goal.** It rules a model out. It cannot
rule one in.

**Never ship a model change on calibration evidence alone where a price-based
backtest is available.** For 1X2 and the 2.5 line it always is — Football-Data
ships the odds. For BTTS and corners it never is, which means model changes
there carry a risk that cannot be measured before the fact, and should be
correspondingly rare.

**The BTTS bias is real and is still there.** It was not fixed, because the
available fix cost more than the problem. It is a known, measured, unresolved
weakness in the market that produces most of the card, and the honest position
is to say so rather than to have patched it into something that looked better
and performed worse.
