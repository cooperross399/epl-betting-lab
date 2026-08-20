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
