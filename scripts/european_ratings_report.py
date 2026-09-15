#!/usr/bin/env python
"""Rate every European club on one scale, and test the bridge that makes it one.

Free: Football-Data's domestic leagues and openfootball's Champions League
results. No provider is touched and no quota is spent.
"""
from __future__ import annotations

import argparse
import collections
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import COUNTRY_TO_LEAGUE, EUROPEAN_LEAGUE_NAMES, OUTPUTS_DIR
from epl_betting_lab.models.european_ratings import (
    EUROPEAN_RATINGS,
    build_european_pool,
    measure_bridge,
)
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUTS_DIR / "european_ratings.md")
    args = parser.parse_args()

    pool = build_european_pool()
    model = PoissonGoalsModel().fit(pool.matches, config=EUROPEAN_RATINGS)
    bridge = measure_bridge(pool)
    low, high = bridge.interval()

    strengths = pd.DataFrame(
        [
            {
                "club": club,
                "country": pool.country_of.get(club),
                "attack": s.attack,
                "defense": s.defense,
            }
            for club, s in model.team_strengths.items()
        ]
    ).dropna(subset=["country"])

    lines = [
        "# One rating scale across European football",
        "",
        "Clubs never move between countries, so nothing links one country's ratings "
        "to another's the way promotion links the English divisions. Fitted "
        "separately, every league is normalised to its own average and a Spanish "
        "rating means nothing against an English one.",
        "",
        "European ties are the bridge: matches with results, played between clubs "
        "from two different domestic pools.",
        "",
        f"**{pool.domestic:,} domestic matches** across {len(set(COUNTRY_TO_LEAGUE.values()))} "
        f"leagues, **{pool.ties:,} European ties** linking them, "
        f"{len(strengths)} clubs rated.",
        "",
        "## Does the bridged scale carry club-level information?",
        "",
        "Walk-forward: fit on everything before a season, predict that season's "
        "European ties. The comparison keeps the country gap and throws away the "
        "club — it replaces the club's own rating with the mean rating of its own "
        "league. Beating that is what shows the scale carries more than a "
        "league-level difference a market already knows.",
        "",
        "| | RMSE |",
        "|:--|--:|",
        f"| Club's own rating, bridged scale | **{bridge.joint_rmse:.4f}** |",
        f"| Naive — club = average of its own league | {bridge.naive_rmse:.4f} |",
        "",
        f"**{bridge.improvement:+.2f}%**, difference "
        f"{bridge.joint_rmse - bridge.naive_rmse:+.4f}, 95% interval "
        f"**{low:+.4f} to {high:+.4f}** over {bridge.ties} held-out ties, "
        "resampling ties rather than innings because a tie's two innings share "
        "one match and one pair of ratings.",
        "",
        "This is the opposite of the English division result, where carrying a "
        "club's rating through a promotion was *worse* than discarding it. The "
        "difference makes sense: a promoted club becomes a different thing at a "
        "higher level, while a Champions League club in Europe is the same side "
        "against comparable opposition.",
        "",
        "## What this is not",
        "",
        "It predicts goals better than a naive prior. **It is not evidence of "
        "beating a price.** The Premier League model also predicts goals "
        "respectably and carries beta = -0.023 against the closing line — the "
        "share of its disagreement with the market that holds information is "
        "indistinguishable from zero. Whether these ratings beat a Champions "
        "League price needs the closing-line record the price collection is "
        "accumulating, not this table.",
        "",
        "## Mean rating by country",
        "",
        "| Country | League | Clubs | Attack | Defence |",
        "|:--|:--|--:|--:|--:|",
    ]
    grouped = strengths.groupby("country").agg(
        clubs=("club", "size"), attack=("attack", "mean"), defense=("defense", "mean")
    ).sort_values("attack", ascending=False)
    for country, row in grouped.iterrows():
        league = EUROPEAN_LEAGUE_NAMES.get(COUNTRY_TO_LEAGUE.get(country, ""), "")
        lines.append(
            f"| {country} | {league} | {int(row['clubs'])} | "
            f"{row['attack']:.3f} | {row['defense']:.3f} |"
        )

    lines += [
        "",
        "## The strongest clubs on the unified scale",
        "",
        "| Club | Country | Attack | Defence |",
        "|:--|:--|--:|--:|",
    ]
    for _, row in strengths.nlargest(12, "attack").iterrows():
        lines.append(
            f"| {row['club']} | {row['country']} | {row['attack']:.3f} | {row['defense']:.3f} |"
        )

    lines += [
        "",
        "Read that ordering with care. PSV Eindhoven, Sporting, Benfica, "
        "Fenerbahce, Galatasaray and Celtic all sit above Real Madrid and "
        "Manchester City, which is not a credible European power ranking. A club "
        "that dominates a weak domestic league scores heavily against weak "
        "opposition, and the 701 European ties correct that only partly: most of "
        "a club's matches are domestic, so most of its rating is. The bridge is "
        "strong enough to carry club-level information out of sample — that is "
        "what the test above measures — and not strong enough to make the "
        "attack column a ranking. A Champions League price built on it should "
        "expect the weak-league sides to be overrated.",
        "",
    ]

    missing = collections.Counter(country for _, country in pool.unresolved)
    lines += [
        "",
        "## Who cannot be rated",
        "",
        f"{sum(missing.values())} club appearances belong to countries "
        "Football-Data does not publish. Those clubs stay unrated, and the model "
        "refuses to price a club it has no rating for, so their ties are declined "
        "rather than guessed at.",
        "",
        "| Country | Appearances |",
        "|:--|--:|",
    ]
    for country, count in missing.most_common(12):
        lines.append(f"| {country} | {count} |")
    lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
