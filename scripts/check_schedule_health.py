#!/usr/bin/env python
"""Has the matchday schedule gone quiet?

A schedule that never fires produces no run, no summary, no email and no red
tick. It looks exactly like a week in which nothing changed, which is the one
failure the delivery design cannot otherwise see.
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from epl_betting_lab.reports.schedule_health import gap_report, most_recent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "timestamps",
        nargs="*",
        help="ISO run timestamps, most recent first. Usually from `gh run list`.",
    )
    parser.add_argument(
        "--append-to",
        help="File to append the reason to when a run appears to be missing, "
        "so the caller can treat it as a degradation.",
    )
    parser.add_argument(
        "--max-days",
        type=float,
        help="Longest acceptable gap in days. Defaults to the matchday cadence; "
        "the closing snapshot runs on match days only, so it needs a wider one.",
    )
    parser.add_argument(
        "--fail-when-stale",
        action="store_true",
        help="Exit non-zero when a run is missing, so a watchdog goes red.",
    )
    args = parser.parse_args()

    previous = most_recent(args.timestamps)
    if args.max_days:
        stale, sentence = gap_report(previous, max_expected=timedelta(days=args.max_days))
    else:
        stale, sentence = gap_report(previous)
    print(sentence)

    if stale and args.append_to:
        with open(args.append_to, "a", encoding="utf-8") as handle:
            handle.write(sentence + "\n")
    if stale and args.fail_when_stale:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
