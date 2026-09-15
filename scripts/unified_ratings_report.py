#!/usr/bin/env python
"""Can a cup tie be priced? Fit one scale across the English divisions and test it.

Costs nothing: every input is already on disk, and no provider is touched.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, CARD_RATINGS
from epl_betting_lab.models.unified_ratings import (
    CARRIED_RATING_SHARE,
    UNIFIED_RATINGS,
    build_pool,
    division_changes,
    measure_carry,
    scale_by_division,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUTS_DIR / "unified_ratings.md")
    args = parser.parse_args()

    pool = build_pool()
    unified = PoissonGoalsModel().fit(pool, config=UNIFIED_RATINGS)
    legacy = PoissonGoalsModel().fit(pool, config=CARD_RATINGS)
    carry = measure_carry(pool)

    lines = [
        "# One rating scale across the English divisions",
        "",
        "A cup tie is two clubs from different competitions, and the card's ratings "
        "are fitted inside one. Since the model refuses a club it has never seen, a "
        "Carabao Cup fixture cannot be priced at all. Promotion and relegation are "
        "the only bridge between the pools, and this asks what they are worth.",
        "",
        f"Pool: **{len(pool):,} matches**, "
        f"{len(set(pool['home_team']) | set(pool['away_team']))} clubs, "
        f"{len(division_changes(pool))} division changes.",
        "",
        "## The scale is sane, but only opponent-adjusted",
        "",
        "Mean fitted rating for the clubs of each division. The card's own "
        "`CARD_RATINGS` is the unadjusted ratio, which has no way to know the "
        "leagues differ — it is shown beside the joint fit for contrast.",
        "",
        "| Division | Clubs | Attack (adjusted) | Defence (adjusted) | Attack (legacy) | Defence (legacy) |",
        "|:--|--:|--:|--:|--:|--:|",
    ]
    adjusted = scale_by_division(unified, pool)
    plain = scale_by_division(legacy, pool)
    for division in adjusted.index:
        a, p = adjusted.loc[division], plain.loc[division]
        lines.append(
            f"| {division} | {int(a['clubs'])} | {a['attack']:.3f} | {a['defense']:.3f} "
            f"| {p['attack']:.3f} | {p['defense']:.3f} |"
        )
    lines += [
        "",
        "The adjusted columns are monotone in both directions. The legacy ones are "
        "not: they rate the bottom division level with the top, because a ratio "
        "against the league average cannot see that the league changed.",
        "",
        "## What a rating is worth across a division change",
        "",
        "Out of sample and walk-forward: for every club that changed division, the "
        "ratings are fitted only on matches played before its new season began, then "
        "used to predict the goals it actually scored. The comparison keeps the "
        "division gap and throws away the club — it replaces the club's own rating "
        "with the average of its new division.",
        "",
        f"**{carry.matches:,} matches, {carry.clubs} clubs.**",
        "",
        "| Share of the club's own rating kept | RMSE |",
        "|:--|--:|",
    ]
    best = carry.best_share
    for share in carry.shares:
        if share not in carry.rmse:
            continue
        mark = "  ← best" if share == best else ""
        label = {0.0: " (average for the new division)", 1.0: " (carried across intact)"}.get(share, "")
        lines.append(f"| {share:.2f}{label} | {carry.rmse[share]:.4f}{mark} |")

    low, high = carry.interval()
    gap = carry.rmse.get(1.0, float("nan")) - carry.rmse.get(0.0, float("nan"))
    lines += [
        "",
        f"Carrying the rating intact costs **{gap:+.4f} RMSE** against throwing it "
        f"away, 95% interval **{low:+.4f} to {high:+.4f}**, resampling clubs rather "
        "than matches because a club's matches share its rating.",
        "",
        f"The best share is **{best:.2f}**, and it beats keeping none of it by "
        f"{carry.rmse[0.0] - carry.rmse[best]:.4f} RMSE — inside the noise. "
        f"`CARRIED_RATING_SHARE = {CARRIED_RATING_SHARE}` records it.",
        "",
        "## What this answers",
        "",
        "A cup tie **can** be priced on this scale, and the price carries almost no "
        "private information. The division gap is real and well estimated — it is "
        "what the winning baseline uses. But a market that knows which divisions two "
        "clubs are in knows that too, and prices it with the vig on its side. A model "
        "beats a market by disagreeing with it usefully, and after a division change "
        "this one has almost nothing left to disagree with.",
        "",
        "So: yes, validly. No, not profitably. Nothing here is wired to the card.",
        "",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
