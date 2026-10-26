#!/usr/bin/env python
"""Check the card's picks against the confirmed lineups (ESPN, keyless).

Reads the latest props card and the latest archived card, checks every pick
kicking off in the next few hours, and writes data/outputs/lineup_check.md and
lineup_check.json. Spends no credits and places nothing.

`--wait-for-next-kickoff` is for the scheduled runs that cover what no Closing
Snapshot reaches (midweek rounds, odd kick-off times): the run finds the next
pick kicking off within what one job may wait, sleeps until shortly before
it, when the teams are out, and checks then. GitHub starts scheduled runs
hours late, so the schedule fires several times a day and each run waits for
whatever is next; two runs checking the same kick-off is harmless.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from epl_betting_lab.config import AUTOMATED_CARD_JSON, OUTPUTS_DIR, PROPS_CARD_JSON
from epl_betting_lab.reports.lineup_check import (
    _kickoff,
    build_lineup_check,
    render,
    save_lineup_check,
)

#: Clubs name their teams about an hour before kick-off; this is after that.
CHECK_BEFORE = timedelta(minutes=35)
#: A kick-off closer than this cannot be waited for; the check would land late.
MIN_AHEAD = timedelta(minutes=40)
#: A job may run six hours; the wait stays well inside that.
MAX_AHEAD = timedelta(hours=5, minutes=30)


def _json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def latest_card(archive: Path) -> dict:
    cards = sorted(archive.glob(f"*/*/{AUTOMATED_CARD_JSON}"))
    return _json(cards[-1]) if cards else {}


def next_kickoff(picks: list[dict], *, now: datetime) -> datetime | None:
    """The earliest pick kick-off far enough ahead to wait for, within one job."""
    ahead = sorted(
        k for p in picks
        if (k := _kickoff(p.get("kickoff_time") or p.get("commence_time")))
        and now + MIN_AHEAD <= k <= now + MAX_AHEAD
    )
    return ahead[0] if ahead else None


def check_at(kickoff: datetime) -> datetime:
    return kickoff - CHECK_BEFORE


def _say(name: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default=str(OUTPUTS_DIR))
    parser.add_argument("--hours", type=float, default=3.0)
    parser.add_argument("--wait-for-next-kickoff", action="store_true")
    args = parser.parse_args()
    outputs = Path(args.outputs)
    props = [p for p in _json(outputs / PROPS_CARD_JSON).get("picks") or [] if isinstance(p, dict)]
    card = latest_card(outputs / "archive" / "automated_cards")
    team_picks = [
        r for r in card.get("best_bets") or []
        if isinstance(r, dict) and float(r.get("suggested_units") or 0) > 0
    ]
    if args.wait_for_next_kickoff:
        kickoff = next_kickoff([*props, *team_picks], now=datetime.now(timezone.utc))
        if kickoff is None:
            print("No pick kicks off within this run's reach; nothing to check.")
            _say("checked", "false")
            return 0
        pause = (check_at(kickoff) - datetime.now(timezone.utc)).total_seconds()
        print(f"Next pick kicks off {kickoff:%a %H:%M} UTC; checking at {check_at(kickoff):%H:%M}.")
        if pause > 0:
            time.sleep(pause)
    check = build_lineup_check(props, team_picks, now=datetime.now(timezone.utc), hours=args.hours)
    save_lineup_check(check, outputs)
    _say("checked", "true" if (check.props or check.team_picks) else "false")
    print(render(check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
