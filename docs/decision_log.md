# Decision log

Judgment calls and owner decisions, newest first. CLAUDE.md carries the
operating state; this file carries why it changed.

## 2026-11-21: every EPL stake and record on the 1u Due List ladder

Cooper: *"use the due list ladder style pricing but with 1u as the main
instead of .25u"* and *"records/profits on the website for EPL"*. The same
rule the CBB lab adopted the same day (its decision 115).

| Price | Stake |
|:--|--:|
| up to +199 | 1u on a plus price, or enough to win 1u on a minus price (at -150, risk 1.5u to win 1u) |
| +200 to +500 | 0.6u |
| +501 to +1500 | 0.4u |
| longer than +1500 | 0.2u |

- A push or void returns 0 and is not a win or a loss. A pick with no usable
  price is graded and counted unpriced; it is staked nothing.
- The favoured-side ("straight up") record risks 1u flat under +200 and the
  ladder from +200, graded on the favoured outcome's own frozen 1X2 price; a
  draw it did not name is a loss.
- The card keeps its tiers' proportions from the new base: C (every bet the
  card has ever staked; 0.1u before) is the ladder's size, B 2.5x, A 5x. The
  trust weight and the line move still only demote a best bet to an
  unstaked lean, as before.
- Every past night is restated: `GRADING = 2` and the new `STAKE_RULE`
  re-settle each kept night once from its frozen boards.
- Found while doing it: 1X2 and double-chance picks were never graded on the
  site (`grade_pick` returned None), so the 1X2 picks on the card since
  2026-10-19 never reached the record. Both are graded now.
- Shared pages are pinned from `betting-lab-shared`, which this session's
  GitHub access does not reach. The change is made at publish
  (`web/smooth_pages.EPL_PATCHES`), on the published copies only; the shared
  repository still owes the same change and a re-pin for every lab.
- Nothing about what is bet changed: no market, bar, model or policy moved,
  and no market has a demonstrated edge.
