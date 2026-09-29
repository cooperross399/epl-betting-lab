"""A Closing Snapshot fires eight hours early and waits for its slot.

Between 2026-09-08 and 2026-09-29 GitHub started this workflow 2.4 h late at
the median and 4.8 h at worst, against a twenty-minute lead on kick-off. Every
Friday and Monday snapshot landed after its match had started, so the
single-slot days got no closing observation at all. Each cron now fires
`ROUND_LEAD` before its slot and `scripts/wait_for_round.py` holds the run.

What this pins, because each is a way the fix can quietly undo itself:

* every cron lands on the slot it is meant for once the lead is added —
  including the weekday, which moves back a day for any cron that crosses
  midnight;
* the snapshot job waits for both wait jobs, and still runs when a wait
  fails (a bare `if:` would carry an implicit success() and skip it);
* the concurrency group sits on the snapshot job, not the workflow, where
  one waiting run would cancel the next.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from epl_betting_lab.config import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "closing-snapshot.yml"
SCRIPT = PROJECT_ROOT / "scripts" / "wait_for_round.py"

#: The slots, twenty minutes before each kick-off (UTC, UK summer time), as
#: (cron weekday, hour, minute). Saturday 12:30 and 15:00 UK, Sunday 14:00 UK,
#: Friday and Monday 20:00 UK.
SLOTS = {(6, 11, 10), (6, 13, 40), (0, 12, 40), (5, 18, 40), (1, 18, 40)}


def _script():
    spec = importlib.util.spec_from_file_location("wait_for_round", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _document() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _crons() -> list[str]:
    document = _document()
    # PyYAML reads the bare key `on` as True.
    triggers = document.get("on", document.get(True))
    return [entry["cron"] for entry in triggers["schedule"]]


def _slot_of(cron: str, lead: timedelta) -> tuple[int, int, int]:
    """(weekday, hour, minute) the cron's run is held until, by arithmetic.

    Deliberately not the script: this is the independent statement of what
    the script has to agree with.
    """
    minute, hour, day_of_month, month, weekday = cron.split()
    assert minute.isdigit() and hour.isdigit(), cron
    assert weekday.isdigit(), f"{cron}: one numeric weekday per cron"
    total = int(weekday) * 24 * 60 + int(hour) * 60 + int(minute)
    total += int(lead.total_seconds() // 60)
    total %= 7 * 24 * 60
    return total // (24 * 60), (total // 60) % 24, total % 60


def _cron_weekday(moment: datetime) -> int:
    """Cron numbering: Sunday is 0."""
    return (moment.weekday() + 1) % 7


def test_every_cron_lands_on_its_slot() -> None:
    lead = _script().ROUND_LEAD
    assert lead == timedelta(hours=8)
    crons = _crons()
    slots = [_slot_of(cron, lead) for cron in crons]
    assert len(slots) == len(set(slots)), "two crons share a slot"
    assert set(slots) == SLOTS


def test_the_lead_arithmetic_moves_the_weekday_back_across_midnight() -> None:
    """A Saturday 03:00 slot is a Friday 19:00 cron, not a Saturday one."""
    lead = timedelta(hours=8)
    assert _slot_of("0 19 * * 5", lead) == (6, 3, 0)
    assert _slot_of("0 19 * * 6", lead) == (0, 3, 0)
    assert _slot_of("40 10 * * 5", lead) == (5, 18, 40)


@pytest.mark.parametrize("lateness_h", [0.0, 2.4, 4.8, 7.9])
def test_the_script_holds_every_real_cron_until_its_slot(lateness_h: float) -> None:
    """End to end on the real crons: a run started `lateness_h` after its
    cron waits until a moment on the slot's own weekday and time."""
    module = _script()
    week = datetime(2026, 10, 4, tzinfo=timezone.utc)  # a Sunday: cron day 0
    for cron in _crons():
        minute, hour, _, _, weekday = cron.split()
        fired = week + timedelta(days=int(weekday), hours=int(hour), minutes=int(minute))
        assert _cron_weekday(fired) == int(weekday)
        now = fired + timedelta(hours=lateness_h)
        target = module.target_for(cron, "", now)
        assert (_cron_weekday(target), target.hour, target.minute) in SLOTS
        assert (_cron_weekday(target), target.hour, target.minute) == _slot_of(
            cron, module.ROUND_LEAD
        )
        assert target == fired + module.ROUND_LEAD


def test_a_cron_across_midnight_waits_into_the_next_day() -> None:
    module = _script()
    fired = datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)  # Friday
    target = module.target_for("0 19 * * 5", "", fired + timedelta(hours=3))
    assert target == datetime(2026, 10, 3, 3, 0, tzinfo=timezone.utc)
    assert _cron_weekday(target) == 6


def test_a_run_later_than_the_lead_fetches_at_once(monkeypatch) -> None:
    module = _script()
    slept: list[float] = []
    monkeypatch.setattr(module.time, "sleep", slept.append)

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401 - a fixed clock
            return datetime(2026, 10, 2, 19, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(module, "datetime", _Clock)
    # Friday 10:40 cron, slot 18:40, started 8h50 late: no wait at all.
    assert module.main(["--schedule", "40 10 * * 5"]) == 0
    assert slept == []
    # Started by hand: no schedule, no wait.
    assert module.main(["--schedule", ""]) == 0
    assert slept == []
    # Started on time: waits, but never past the budget.
    monkeypatch.setattr(
        _Clock, "now", classmethod(lambda cls, tz=None: datetime(2026, 10, 2, 10, 45, tzinfo=timezone.utc))
    )
    assert module.main(["--schedule", "40 10 * * 5", "--budget-minutes", "340"]) == 0
    assert slept == [340 * 60.0]


def test_the_snapshot_waits_for_both_wait_jobs_and_survives_a_failed_one() -> None:
    jobs = _document()["jobs"]
    assert set(jobs) == {"wait", "wait-more", "snapshot"}
    assert "needs" not in jobs["wait"]
    assert jobs["wait-more"]["needs"] == "wait"
    assert jobs["snapshot"]["needs"] == "wait-more"
    for name in ("wait-more", "snapshot"):
        condition = str(jobs[name].get("if", ""))
        assert condition.startswith("${{ !cancelled()"), (name, condition)
        # Nothing may imply success() of an upstream wait.
        assert "success()" not in condition, (name, condition)
    for name in ("wait", "wait-more"):
        (step,) = [
            s for s in jobs[name]["steps"] if "wait_for_round.py" in str(s.get("run", ""))
        ]
        assert step["env"]["SCHEDULE"] == "${{ github.event.schedule }}"
        assert '--schedule "$SCHEDULE"' in step["run"]
        budget = float(step["run"].split("--budget-minutes")[1].split()[0])
        # Two budgets have to cover the lead, and each must end inside its job.
        assert budget < int(jobs[name]["timeout-minutes"]) <= 360
        assert 2 * budget >= _script().ROUND_LEAD.total_seconds() / 60
        # A wait job writes nothing.
        assert jobs[name]["permissions"] == {"contents": "read"}


def test_the_concurrency_group_is_on_the_snapshot_job() -> None:
    document = _document()
    assert "concurrency" not in document
    assert document["jobs"]["snapshot"]["concurrency"] == {
        "group": "closing-snapshot",
        "cancel-in-progress": False,
    }
    for name in ("wait", "wait-more"):
        assert "concurrency" not in document["jobs"][name]


def test_an_at_time_just_reached_is_now_not_tomorrow() -> None:
    """The NHL lab's run 36582803431: a second wait leg starting seconds after
    its `--at` time read it as tomorrow's and failed the run."""
    module = _script()
    utc = timezone.utc
    now = datetime(2026, 9, 29, 19, 45, 6, tzinfo=utc)
    assert module.target_for("", "19:45", now) == datetime(2026, 9, 29, 19, 45, tzinfo=utc)
    assert module.target_for("", "00:45", now) == datetime(2026, 9, 30, 0, 45, tzinfo=utc)
    late = datetime(2026, 9, 30, 0, 10, tzinfo=utc)
    assert module.target_for("", "23:50", late) == datetime(2026, 9, 29, 23, 50, tzinfo=utc)
