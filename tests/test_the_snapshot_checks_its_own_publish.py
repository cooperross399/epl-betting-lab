"""The Closing Snapshot's only persisting step was never checked.

"Report the outcome" read `steps.prices.outcome` and printed "Snapshot
finished." The step that actually commits and pushes to `refs/heads/price-feed`
is `continue-on-error: true` and carried no `id:`, so its outcome was not
merely unchecked — it was unreferenceable. A snapshot that fetched several
hundred book-level prices and then failed to publish one of them finished
green with a log line saying it was done.

It matters more here than in most workflows. This feed is the only forward
evidence the corner markets will ever have, `live_clv` ignores any
observation taken after kick-off, and a snapshot that never publishes and one
that publishes late produce the same empty column downstream.

Same shape as the Matchday Refresh gate, in the workflow next to it — found
only by re-auditing after that one was fixed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from epl_betting_lab.config import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "closing-snapshot.yml"


def _steps() -> list[dict]:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return list(spec["jobs"].values())[0]["steps"]


def _named(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r}")


def _gate(**values):
    script = _named("Report the outcome")["run"]
    for expression, value in (
        (r"\$\{\{ steps\.append\.outputs\.state \}\}", values.get("state", "appended")),
        (r"\$\{\{ steps\.append\.outcome \}\}", values.get("append", "success")),
        (r"\$\{\{ steps\.prices\.outcome \}\}", values.get("prices", "success")),
        (r"\$\{\{ steps\.efl_prices\.outcome \}\}", values.get("efl", "success")),
    ):
        script = re.sub(expression, value, script)
    assert "${{" not in script
    return script


def _run(tmp_path: Path, **values):
    path = tmp_path / "gate.sh"
    path.write_text(_gate(**values), encoding="utf-8")
    return subprocess.run(
        ["bash", "-e", str(path)], cwd=tmp_path, capture_output=True, text=True
    )


def test_the_publishing_step_can_be_referred_to() -> None:
    assert _named("Append the observation to the price feed").get("id") == "append"


class TestAFailedPublishIsAFault:
    def test_a_dead_publish_step_fails_the_snapshot(self, tmp_path: Path) -> None:
        done = _run(tmp_path, state="", append="failure")

        assert done.returncode == 1
        assert "did not reach the price-feed branch" in done.stdout
        # The annotation type as well as the exit code. Swapping `::error::`
        # for `::warning::` leaves the exit status alone, so a test that
        # checks only the return code cannot see it — and the two surface
        # very differently on the run page and in the failure notice.
        assert "::error::" in done.stdout
        assert "::warning::The observation" not in done.stdout

    def test_a_step_that_died_before_reporting_fails_too(self, tmp_path: Path) -> None:
        """Success with no state is the `set -u` abort, or a failed push."""
        done = _run(tmp_path, state="", append="success")

        assert done.returncode == 1


class TestARealPublishPasses:
    @pytest.mark.parametrize("state", ["appended", "unchanged"])
    def test_both_delivered_outcomes_are_clean(self, tmp_path: Path, state) -> None:
        """`unchanged` is delivery too: the observation was already there."""
        done = _run(tmp_path, state=state)

        assert done.returncode == 0, done.stdout + done.stderr
        assert f"price-feed: {state}" in done.stdout
        assert "Snapshot finished." in done.stdout

    def test_a_failed_fetch_warns_and_does_not_fail(self, tmp_path: Path) -> None:
        """One missing observation is not a broken record — the behaviour
        that predates this check, kept."""
        done = _run(tmp_path, prices="failure")

        assert done.returncode == 0, done.stdout + done.stderr
        assert "::warning::" in done.stdout

    def test_nothing_to_publish_warns_rather_than_passing_silently(
        self, tmp_path: Path
    ) -> None:
        """An empty feed is not an append, and it is not a crash either."""
        done = _run(tmp_path, state="nothing-to-publish")

        assert done.returncode == 0, done.stdout + done.stderr
        assert "no feed to publish" in done.stdout

    def test_a_failed_efl_fetch_is_said_out_loud(self, tmp_path: Path) -> None:
        """It had an `id` and was read by nothing."""
        done = _run(tmp_path, efl="failure")

        assert done.returncode == 0, done.stdout + done.stderr
        assert "beyond-the-Premier-League prices" in done.stdout


def test_every_exit_from_the_publish_step_reports_a_state() -> None:
    """The gate reads an empty state as a death, so it has to be one."""
    lines = [
        line
        for line in _named("Append the observation to the price feed")["run"].splitlines()
        if not line.strip().startswith("#")
    ]

    for i, line in enumerate(lines):
        if line.strip() == "exit 0":
            preceding = " ".join(lines[max(0, i - 3):i])
            assert "state=" in preceding and "GITHUB_OUTPUT" in preceding, (
                f"the `exit 0` on line {i} leaves without reporting a state"
            )
    code = "\n".join(lines)
    assert {"state=appended", "state=unchanged", "state=nothing-to-publish"} <= {
        f"state={word}"
        for word in ("appended", "unchanged", "nothing-to-publish")
        if f"state={word}" in code
    }
