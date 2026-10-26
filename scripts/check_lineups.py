#!/usr/bin/env python
"""Check the card's picks against the confirmed lineups (ESPN, keyless).

Reads the latest props card and the latest archived card, checks every pick
kicking off in the next few hours, and writes data/outputs/lineup_check.md and
lineup_check.json. Spends no credits and places nothing.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.config import AUTOMATED_CARD_JSON, OUTPUTS_DIR, PROPS_CARD_JSON
from epl_betting_lab.reports.lineup_check import build_lineup_check, render, save_lineup_check


def _json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def latest_card(archive: Path) -> dict:
    cards = sorted(archive.glob(f"*/*/{AUTOMATED_CARD_JSON}"))
    return _json(cards[-1]) if cards else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default=str(OUTPUTS_DIR))
    parser.add_argument("--hours", type=float, default=3.0)
    args = parser.parse_args()
    outputs = Path(args.outputs)
    props = [p for p in _json(outputs / PROPS_CARD_JSON).get("picks") or [] if isinstance(p, dict)]
    card = latest_card(outputs / "archive" / "automated_cards")
    team_picks = [
        r for r in card.get("best_bets") or []
        if isinstance(r, dict) and float(r.get("suggested_units") or 0) > 0
    ]
    check = build_lineup_check(props, team_picks, now=datetime.now(timezone.utc), hours=args.hours)
    save_lineup_check(check, outputs)
    print(render(check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
