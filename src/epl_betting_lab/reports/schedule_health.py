"""Notice when a scheduled run did not happen.

The delivery design asks the reader to treat silence as "it ran and nothing
moved". That is only safe if every way of going wrong breaks the silence, and
one way does not: a schedule that never fires produces no run, no summary, no
email and no red tick. It is indistinguishable from a quiet week.

Two independent checks close it, because a single one would share the failure
it is meant to catch.

**Each run measures the gap behind it.** If more time has passed since the
previous run than the schedule allows for, this run says so — and a degraded
run always emails, so the news travels.

**A second, unrelated schedule watches the first.** The weekly check already
runs on its own cron; if the matchday refresh has gone quiet it says so there.
Two schedules failing in the same week is far less likely than one, and nothing
here can detect its own total absence.

**"Did it run" and "did it succeed" are different questions.** Both callers used
to ask the first with the answer to the second — `gh run list --status success`
— and a data outage therefore masqueraded as a scheduler outage. Every matchday
run is red by design while Football-Data is down, so from 2026-09-09 the check
saw no run at all, reported "at least one run did not happen. Check that the
workflow is still enabled", and put that sentence at the top of every card while
19 of 19 crons had fired. Worse, it latched: the false sentence alone made the
run degraded, a degraded run exits non-zero, and a non-zero run is not a success
— so the gap could never close again, even after the upstream feed recovered.

The gap check now counts every run whatever its conclusion. The condition the
success filter was accidentally watching — runs happening but not succeeding —
is a real thing worth escalating, and `degraded_streak_report` below asks it
directly instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone


#: Longest gap the matchday schedule should ever leave. Runs are Thursday,
#: Friday, Saturday, Sunday and Monday, so the widest planned gap is Monday to
#: Thursday: three days. Four days allows a full missed day plus GitHub's
#: habitual lateness without crying wolf.
MAX_EXPECTED_GAP = timedelta(days=4)

#: GitHub routinely starts a scheduled run late — twenty minutes is ordinary,
#: and an hour is documented. A gap is only reported once it exceeds the
#: planned spacing by more than this, so ordinary lateness stays quiet.
LATENESS_ALLOWANCE = timedelta(hours=6)


def gap_report(
    previous_run: datetime | None,
    *,
    now: datetime | None = None,
    max_expected: timedelta = MAX_EXPECTED_GAP,
) -> tuple[bool, str]:
    """Is the gap behind this run longer than the schedule allows?

    Returns (is_stale, sentence). The sentence is worth reporting either way:
    a run that is on time saying so is how the reader learns the check exists.
    """
    moment = now or datetime.now(timezone.utc)
    if previous_run is None:
        return False, "No previous run to compare against; this one is the baseline."

    if previous_run.tzinfo is None:
        previous_run = previous_run.replace(tzinfo=timezone.utc)
    gap = moment - previous_run
    hours = gap.total_seconds() / 3600.0

    if gap > max_expected + LATENESS_ALLOWANCE:
        days = max_expected.days
        return True, (
            f"The previous run was {hours:.0f} hours ago. The schedule should "
            f"never leave more than {days} days, so at least one run did not "
            "happen. Check that the workflow is still enabled."
        )
    return False, f"The previous run was {hours:.0f} hours ago, which is expected."


def parse_run_time(value: str) -> datetime | None:
    """An ISO timestamp from the GitHub API, or None if it cannot be read."""
    text = (value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def most_recent(timestamps: Sequence[str]) -> datetime | None:
    """The latest readable timestamp, ignoring any that will not parse."""
    parsed = [t for t in (parse_run_time(value) for value in timestamps) if t]
    return max(parsed) if parsed else None


#: How many consecutive non-succeeding runs before the streak is worth saying
#: out loud. Two is one bad matchday; four is a pattern that has survived a
#: whole weekend and nobody has looked.
MAX_QUIET_DEGRADED_RUNS = 4


def degraded_streak_report(
    conclusions: Sequence[str], *, limit: int = MAX_QUIET_DEGRADED_RUNS
) -> tuple[bool, str]:
    """How many runs in a row have finished without succeeding?

    This is the question the `--status success` filter was asking by accident,
    and it is worth asking on purpose. On 2026-09-06 the matchday refresh began
    failing on a Football-Data outage and produced eight blocked cards over two
    days; nothing escalated, because every individual run reported its own
    degradation and no one thing counted them.

    `conclusions` is most-recent-first, as `gh run list` returns them. An
    in-flight run has no conclusion yet and is skipped rather than counted
    either way — it has not finished failing.
    """
    streak = 0
    for conclusion in conclusions:
        state = str(conclusion or "").strip().lower()
        if state in {"", "in_progress", "queued", "waiting", "pending", "requested"}:
            continue
        if state == "success":
            break
        streak += 1

    if streak < limit:
        return False, f"The last {streak} run(s) did not succeed, which is within the usual range."
    return True, (
        f"{streak} consecutive runs have finished without succeeding. Individually "
        "each one reported its own fault; together they are a pattern that has "
        "outlasted a weekend. Check whether the cause is upstream and still "
        "unresolved, rather than reading another degraded card."
    )
