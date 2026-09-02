# The BTTS bias was a ratings problem

`CLAUDE.md` carried this for weeks, and it was true when written:

> BTTS has a known, measured, **unfixed** calibration bias of roughly nine
> points, and cannot be profit-backtested because no historical BTTS prices
> exist. It produces most of the picks on a card. Say so rather than patching it.

It is now measured out, by a change made for an entirely different reason.

## What the bias was

Walk-forward over 1,540 matches, the model under-stated how often both teams
score, worst in exactly the bands where it bets:

| Band | Matches | Predicted | Observed | Gap |
|:--|--:|--:|--:|--:|
| 30–45% | 278 | 40.5% | 50.7% | **+10.2** |
| 45–55% | 618 | 50.3% | 56.5% | **+6.2** |
| 55–70% | 609 | 60.2% | 59.1% | −1.1 |
| **All** | 1,540 | 52.4% | 56.6% | **+4.2** |

## Why the obvious fix was the wrong one

`docs/why_better_calibration_lost_money.md` records the attempt: shrink toward
a league-average prior. It improved the gap to 3.9 points and cost about 140
units, because shrinking toward a prior that disagrees with sharp prices
manufactures edges — 546 bets became 851, and the new ones were artefacts of
the shrinkage.

That is why calibration cannot authorise a change in this market. It is also
why the bias sat unfixed rather than patched, which was the right call.

## What actually fixed it

Nothing aimed at BTTS. The opponent-adjusted, time-decayed, xG-blended ratings
built for the 2.5 line — `docs/no_edge_out_of_sample.md` — carry the whole
score matrix, and BTTS falls out of it:

| Ratings | Overall gap | 30–45% | 45–55% | 55–70% | Brier | Log loss |
|:--|--:|--:|--:|--:|--:|--:|
| Legacy (goals ratio, last 38) | +4.2 | +10.2 | +6.2 | −1.1 | 0.2492 | 0.6921 |
| Adjusted, 365d, xG blend | **−0.7** | band emptied | **+0.2** | −1.3 | **0.2444** | **0.6818** |

Reproduce with `scripts/run_btts_calibration.py`.

## The part that distinguishes it from the failed fix

**Brier and log loss improve alongside the calibration.** A shrinkage improves
calibration by making the model less committal, and would leave the
threshold-free scores flat or worse; better ratings improve it by being more
right, and carry them along. Any future change here should be held to the same
test, which is why the report prints both.

**And it bets less, not more.** The failed fix's signature was 546 bets
becoming 851. The bias had a direction — under-stating BTTS-yes manufactures
false edges on the `no` side — and the live card was indeed staking `no`. On
the 2026-09-02 slate the legacy ratings flagged 2 `no` and 1 `yes`; these flag
2 `yes` and no `no`. One slate is not evidence of much, but it points the
opposite way to the failure mode, and the direction was predicted by the
measured bias rather than discovered after the fact.

## What is still true

**No bet rule on BTTS can ever be profit-backtested.** Football-Data ships no
BTTS prices and the bought provider history covers props and corner totals
only. Removing a measured bias is not the same as demonstrating an edge, and
nothing here demonstrates one.

**BTTS is not most of the card.** That claim was also carried in `CLAUDE.md`
and it is false: reconstructed from the `card-feed` branch, BTTS is 4 of the
first 42 best bets. Corners are 23. The correction matters because it changes
where the attention belongs.

Only BTTS moves. `double_chance` and `draw_no_bet` stay on the legacy ratings:
they are derived from the 1X2 probabilities that produced the compression
artefact, and nothing market-specific has been measured for them.
