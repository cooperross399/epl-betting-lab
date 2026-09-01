#!/usr/bin/env python
"""Score bet rules on seasons they were not tuned on, for each ratings config.

Regenerates data/outputs/out_of_sample_{legacy,xg_blend}*.{csv,md}. Read the
test columns; the train columns are only what a rule may be chosen on.
"""
from __future__ import annotations

import argparse

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches_with_xg
from epl_betting_lab.models.poisson_goals import RatingConfig
from epl_betting_lab.reports.out_of_sample import (
    save_out_of_sample_reports,
    walk_forward_probabilities,
)

RATINGS = {
    "legacy": ("Old ratings: goals ratio, last 38 matches", RatingConfig.legacy()),
    "xg_blend": (
        "Opponent-adjusted, 365-day half-life, 70% xG / 30% goals",
        RatingConfig(opponent_adjusted=True, half_life_days=365, goal_source="blend", xg_weight=0.7),
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", nargs="+", choices=sorted(RATINGS), default=sorted(RATINGS))
    args = parser.parse_args()
    matches = load_matches_with_xg()
    for slug in args.ratings:
        name, config = RATINGS[slug]
        probs = walk_forward_probabilities(matches, config)
        paths = save_out_of_sample_reports(probs, OUTPUTS_DIR, model_name=name, slug=slug)
        print(f"{slug}: {len(probs)} matches scored")
        for key, path in paths.items():
            print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
