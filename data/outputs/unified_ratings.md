# One rating scale across the English divisions

A cup tie is two clubs from different competitions, and the card's ratings are fitted inside one. Since the model refuses a club it has never seen, a Carabao Cup fixture cannot be priced at all. Promotion and relegation are the only bridge between the pools, and this asks what they are worth.

Pool: **10,444 matches**, 100 clubs, 100 division changes.

## The scale is sane, but only opponent-adjusted

Mean fitted rating for the clubs of each division. The card's own `CARD_RATINGS` is the unadjusted ratio, which has no way to know the leagues differ — it is shown beside the joint fit for contrast.

| Division | Clubs | Attack (adjusted) | Defence (adjusted) | Attack (legacy) | Defence (legacy) |
|:--|--:|--:|--:|--:|--:|
| E0 | 20 | 1.274 | 0.811 | 1.189 | 0.974 |
| E1 | 24 | 1.021 | 0.946 | 0.977 | 0.981 |
| E2 | 24 | 0.965 | 1.034 | 1.018 | 0.986 |
| E3 | 32 | 0.840 | 1.134 | 0.912 | 1.057 |

The adjusted columns are monotone in both directions. The legacy ones are not: they rate the bottom division level with the top, because a ratio against the league average cannot see that the league changed.

## What a rating is worth across a division change

Out of sample and walk-forward: for every club that changed division, the ratings are fitted only on matches played before its new season began, then used to predict the goals it actually scored. The comparison keeps the division gap and throws away the club — it replaces the club's own rating with the average of its new division.

**3,643 matches, 100 clubs.**

| Share of the club's own rating kept | RMSE |
|:--|--:|
| 0.00 (average for the new division) | 1.1402 |
| 0.15 | 1.1400  ← best |
| 0.30 | 1.1409 |
| 0.45 | 1.1428 |
| 0.60 | 1.1457 |
| 0.75 | 1.1497 |
| 0.90 | 1.1546 |
| 1.00 (carried across intact) | 1.1585 |

Carrying the rating intact costs **+0.0183 RMSE** against throwing it away, 95% interval **+0.0046 to +0.0338**, resampling clubs rather than matches because a club's matches share its rating.

The best share is **0.15**, and it beats keeping none of it by 0.0002 RMSE — inside the noise. `CARRIED_RATING_SHARE = 0.15` records it.

## What this answers

A cup tie **can** be priced on this scale, and the price carries almost no private information. The division gap is real and well estimated — it is what the winning baseline uses. But a market that knows which divisions two clubs are in knows that too, and prices it with the vig on its side. A model beats a market by disagreeing with it usefully, and after a division change this one has almost nothing left to disagree with.

So: yes, validly. No, not profitably. Nothing here is wired to the card.
