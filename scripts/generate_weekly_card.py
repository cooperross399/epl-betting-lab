#!/usr/bin/env python
from __future__ import annotations

import pandas as pd

from epl_betting_lab.config import MAX_DEFAULT_JUICE, MIN_EDGE, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures, load_current_odds
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.reports.weekly_card import build_weekly_card, card_to_markdown
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.totals import evaluate_total_25


def main() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    matches = load_matches()
    fixtures = load_upcoming_fixtures()
    odds = load_current_odds()

    model = PoissonGoalsModel().fit(matches, last_n_matches_per_team=38)
    projections = model.project_fixtures(fixtures)
    candidates = pd.concat([
        evaluate_1x2_value(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
        evaluate_total_25(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE, matches=matches),
        evaluate_btts(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
    ], ignore_index=True)

    card = build_weekly_card(candidates)
    card_path = OUTPUTS_DIR / "weekly_card.csv"
    markdown_path = OUTPUTS_DIR / "weekly_card.md"
    card.to_csv(card_path, index=False)
    markdown_path.write_text(card_to_markdown(card), encoding="utf-8")

    print(card_to_markdown(card))
    print(f"\nSaved CSV to {card_path}")
    print(f"Saved Markdown to {markdown_path}")


if __name__ == "__main__":
    main()
