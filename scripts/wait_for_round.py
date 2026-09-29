#!/usr/bin/env python3
"""Hold a scheduled Closing Snapshot until the slot it was scheduled for.

Used by Closing Snapshot (slots twenty minutes before kick-off: Saturday 11:10
and 13:40, Sunday 12:40, Friday and Monday 18:40 UTC).

    python scripts/wait_for_round.py --schedule "10 3 * * 6"
    python scripts/wait_for_round.py --at 2026-10-03T11:10Z

WHY. A snapshot is only a closing observation if it lands before kick-off:
`live_clv` reads observations strictly before kick-off and ignores the rest.
GitHub starts this repository's scheduled runs hours late - Closing Snapshot
2.4 h at the median and 4.8 h at worst between 2026-09-08 and 2026-09-29,
and every Friday and Monday firing in that stretch landed after its 20:00 UK
kick-off (the Monday ones after the final whistle). A cron written twenty
minutes before kick-off therefore observes a match already under way.
Lateness is not stable enough to aim a cron at: it moves by hours between
days, and the target is twenty minutes wide.

So every cron fires `ROUND_LEAD` before its slot, and the run waits here,
before any price is fetched, until the slot. Lateness up to `ROUND_LEAD` then
costs nothing; beyond it, the run fetches as soon as it starts, which is what
every run did before. A run is never held past its slot and never fetches
early because it started early.

A job may run for at most six hours, so the wait is split across two jobs,
each waiting at most `--budget-minutes`; the second picks up where the first
stopped, because the slot is recomputed from the same cron each time.

The slot is the most recent time the cron named, at or before now, plus
`ROUND_LEAD`: a scheduled run always starts after its cron time, and never a
day late. Only the cron's minute and hour are read here, so every cron must
name one numeric minute and one numeric hour. When cron + `ROUND_LEAD` crosses
midnight, the cron's day-of-week has to be the day BEFORE the slot's; the
tests pin that for every cron.

A DELIBERATE COPY. The NHL lab carries the original of this script. Labs never
import one another (tests/test_no_sibling_lab_import.py), so this lab holds its
own copy; only the comments differ. Change one, compare the other.

`--at` is for a run started by hand: it waits until that UTC time, which must
be in the future and within `MAX_AT_AHEAD`. No schedule and no `--at` means
no wait. Nothing here fetches, spends a credit or reads a secret.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

#: How far before its slot every Closing Snapshot cron fires. Covers every
#: lateness measured on this repository's snapshots (worst 4.8 h) and the
#: account-wide worst (7.72 h, a Matchday Refresh cron) with room to spare.
ROUND_LEAD = timedelta(hours=8)

#: The furthest ahead a hand-started run may be told to wait: two jobs of at
#: most six hours each, less the time the capture itself needs.
MAX_AT_AHEAD = timedelta(hours=11)


def round_for(schedule: str, now: datetime) -> datetime:
    """The round a run fired by `schedule` is for."""
    fields = schedule.split()
    if len(fields) != 5:
        raise ValueError(f"not a five-field cron: {schedule!r}")
    minute, hour = int(fields[0]), int(fields[1])
    fired = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if fired > now:
        fired -= timedelta(days=1)
    return fired + ROUND_LEAD


def parse_at(value: str, now: datetime) -> datetime:
    """A UTC time to wait for: ISO (`2026-09-29T21:30Z`) or `HH:MM`, taken as
    the next time the clock reads that."""
    text = value.strip()
    if len(text) == 5 and text[2] == ":":
        target = now.replace(
            hour=int(text[:2]), minute=int(text[3:]), second=0, microsecond=0
        )
        return target if target > now else target + timedelta(days=1)
    target = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if target.tzinfo is None:
        raise ValueError(f"--at needs a UTC offset or a trailing Z: {value!r}")
    return target.astimezone(timezone.utc)


def target_for(schedule: str, at: str, now: datetime) -> datetime | None:
    if at.strip():
        target = parse_at(at, now)
        if target - now > MAX_AT_AHEAD:
            raise ValueError(
                f"--at {at!r} is {target - now} away; a run can wait at most "
                f"{MAX_AT_AHEAD}"
            )
        return target
    if schedule.strip():
        return round_for(schedule, now)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--schedule", default="", help="github.event.schedule")
    parser.add_argument("--at", default="", help="UTC time a hand-started run waits for")
    parser.add_argument("--budget-minutes", type=float, default=340.0)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    try:
        target = target_for(args.schedule, args.at, now)
    except ValueError as exc:
        print(f"::error::{exc}")
        return 2
    if target is None:
        print("Started by hand with no --at: capturing now.")
        return 0
    stamp = f"{target:%Y-%m-%d %H:%M} UTC"
    remaining = target - now
    if remaining <= timedelta(0):
        print(
            f"This round was due at {stamp}; the run started {-remaining} "
            "after it, so it captures now."
        )
        return 0
    wait = min(remaining, timedelta(minutes=args.budget_minutes))
    print(f"Round due at {stamp}; waiting {wait} of the {remaining} left.")
    sys.stdout.flush()
    time.sleep(wait.total_seconds())
    if wait < remaining:
        print("This job's budget is spent; the next wait job holds the rest.")
    else:
        print(f"Reached {stamp}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
