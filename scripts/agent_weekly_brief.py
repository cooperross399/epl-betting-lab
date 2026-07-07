#!/usr/bin/env python
from __future__ import annotations

import argparse

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.agent_brief import save_agent_brief


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an in-season markdown brief for the Codex agent.")
    parser.add_argument("--current-season", default="2627", help="Football-Data season code, e.g. 2627 for 2026/27")
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
