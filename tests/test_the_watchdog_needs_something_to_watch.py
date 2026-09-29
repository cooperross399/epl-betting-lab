"""An empty lookup and an idle schedule are the same empty list.

`check_schedule_health.py` given nothing printed "this one is the baseline"
and "the last 0 run(s) did not succeed, which is within the usual range",
and exited 0. Both messages are true of a workflow that has never run and
of a `gh run list` that failed on auth, a rate limit or an API hiccup —
and only one of those is fine.

Matchday Refresh has run hundreds of times, so for its watchdog an empty
list is a broken lookup. The caller is the only one who knows that, so it
says so with `--require-runs`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from epl_betting_lab.config import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "scripts" / "check_schedule_health.py"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "weekly-lab-check.yml"


def _run(*args: str):
    """The interpreter running the tests, not whatever `python` resolves to.

    A bare "python" is not on PATH on this machine, and hard-coding a PATH
    made the test depend on the layout of the box rather than the script.
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )


class TestAnEmptyLookupIsNotHealth:
    def test_no_runs_with_require_runs_is_a_fault(self) -> None:
        done = _run("--fail-when-stale", "--require-runs")

        assert done.returncode == 1
        assert "the lookup failed" in done.stdout

    def test_no_conclusions_with_require_runs_is_a_fault(self) -> None:
        done = _run("--conclusions", "--fail-when-streaking", "--require-runs")

        assert done.returncode == 1

    def test_the_control_one_recent_run_is_healthy(self) -> None:
        """Without this, "always fail" would pass the two above."""
        from datetime import datetime, timedelta, timezone

        recent = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        done = _run(recent, "--fail-when-stale", "--require-runs")

        assert done.returncode == 0, done.stdout + done.stderr

    def test_without_the_flag_an_empty_list_is_still_a_baseline(self) -> None:
        """A genuinely new workflow must not be forced to fail."""
        done = _run("--fail-when-stale")

        assert done.returncode == 0, done.stdout + done.stderr
        assert "baseline" in done.stdout


def test_both_matchday_watchdogs_pass_the_flag() -> None:
    """The script being able to refuse is not the watchdog asking it to."""
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = [s for j in spec["jobs"].values() for s in j["steps"]]
    checks = [
        s for s in steps
        if "check_schedule_health.py" in (s.get("run") or "")
        and "matchday-refresh.yml" in (s.get("run") or "")
    ]

    assert len(checks) == 2, "expected the gap check and the streak check"
    for step in checks:
        assert "--require-runs" in step["run"], step.get("name")
