#!/usr/bin/env python
from __future__ import annotations

import pandas as pd
import sys

from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, MIN_EDGE, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures, load_current_odds
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.reports.thursday_best_bets import (
    build_thursday_best_bets,
    missing_current_odds_message,
    render_thursday_best_bets,
    save_thursday_best_bets,
)
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.totals import evaluate_total_25


def main() -> None:
    current_odds_path = MANUAL_DIR / "current_odds.csv"
    if not current_odds_path.exists():
        raise FileNotFoundError(missing_current_odds_message(current_odds_path))

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    matches = load_matches()
    fixtures = load_upcoming_fixtures()
    odds = load_current_odds(current_odds_path)

    model = PoissonGoalsModel().fit(matches, last_n_matches_per_team=38)
    projections = model.project_fixtures(fixtures)
    candidates = pd.concat([
        evaluate_1x2_value(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
        evaluate_total_25(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE, matches=matches),
        evaluate_btts(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
    ], ignore_index=True)

    report = build_thursday_best_bets(candidates)
    paths = save_thursday_best_bets(report, OUTPUTS_DIR)

    print(render_thursday_best_bets(report))
    print(f"\nSaved CSV to {paths['csv']}")
    print(f"Saved Markdown to {paths['markdown']}")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
