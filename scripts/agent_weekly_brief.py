#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.agent_brief import save_agent_brief
from epl_betting_lab.config import current_season_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an in-season markdown brief for the Codex agent.")
    # Derived, not written down: a hardcoded season does not fail when it goes
    # stale, it just quietly describes the wrong one.
    parser.add_argument(
        "--current-season",
        default=current_season_code(),
        help="Football-Data season code. Defaults to the season being played.",
    )
    parser.add_argument("--recent-matches", type=int, default=6, help="Recent matches per team for form tables")
    args = parser.parse_args()

    matches = load_matches()
    brief_path = save_agent_brief(
        matches,
        OUTPUTS_DIR,
        current_season=args.current_season,
        recent_matches=args.recent_matches,
    )
    print(f"Saved agent weekly brief to {brief_path}")
    print(f"Saved supporting CSVs to {OUTPUTS_DIR}")


if __name__ == "__main__":
    main()
