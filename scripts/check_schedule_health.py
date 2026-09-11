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

from epl_betting_lab.reports.schedule_health import (
    degraded_streak_report,
    gap_report,
    most_recent,
)


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
        "--fail-when-streaking",
        action="store_true",
        help="Exit non-zero when too many runs in a row have failed. Only safe "
        "on a watchdog whose own conclusion is not what it is counting.",
    )
    parser.add_argument(
        "--fail-when-stale",
        action="store_true",
        help="Exit non-zero when a run is missing, so a watchdog goes red.",
    )
    parser.add_argument(
        "--conclusions",
        nargs="*",
        default=None,
        help="Run conclusions, most recent first, to check for a run of runs "
        "that fired but did not succeed. A different question from the gap: "
        "asking it with `--status success` is what made a data outage look "
        "like a scheduler outage.",
    )
    args = parser.parse_args()

    # The streak must never reach the degradation file, and this is a hard
    # refusal rather than a convention because the failure is self-sustaining
    # and invisible.
    #
    # A sentence in run_degraded.txt sets degraded=true, which makes "Report
    # the outcome" exit 1, which makes the run's conclusion `failure` — and
    # that failure is inside the window the NEXT run's streak check reads. So a
    # streak that ever fires keeps itself firing: the runs it counts are the
    # runs it caused. Simulated forward from the real nine-failure history with
    # the upstream fault cleared, it never returns to green.
    #
    # That is precisely the latch this whole change exists to remove, and the
    # first draft of the fix reintroduced it. The streak belongs to a watchdog
    # on a different schedule, whose own conclusion is not what it measures.
    if args.conclusions is not None and args.append_to:
        parser.error(
            "--conclusions cannot be combined with --append-to. A degraded-run "
            "streak written into the degradation file makes the run degraded, "
            "which makes it fail, which feeds the streak. Report the streak "
            "from a watchdog on a separate schedule instead."
        )

    if args.conclusions is not None:
        streaking, streak_sentence = degraded_streak_report(args.conclusions)
        print(streak_sentence)
        if streaking and args.fail_when_streaking:
            return 1

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
