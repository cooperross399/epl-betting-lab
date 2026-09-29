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
    # By name, not position: the first jobs are the waits that hold a
    # scheduled run until its slot, and they publish nothing.
    return spec["jobs"]["snapshot"]["steps"]


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
        (r"\$\{\{ steps\.restore_feeds\.outputs\.state \}\}",
         values.get("restore", "restored")),
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


class TestAFeedMayNotShrink:
    """The restore and the publish fetch the branch independently.

    Nothing connects them. If the restore's fetch fails and the append
    step's succeeds, the append starts from an empty frame — `load_feed`
    returns empty for a missing path — and publishes only this run's rows
    over a valid parent, because every feed name is in REPLACING
    unconditionally. Reproduced against a bare remote: feeds of 64,001 and
    5,001 rows came back as 501 and 301, pushed as a fast-forward and
    accepted, with the run green and the gate printing "price-feed:
    appended".

    The rows survive in `price-feed~1` because the push is not a force, so
    the loss is recoverable by hand. Nothing noticed, which is the defect.
    """

    def _append_script(self) -> str:
        return _named("Append the observation to the price feed")["run"]

    def test_the_publish_step_compares_against_the_parent(self) -> None:
        script = self._append_script()

        assert 'git show "$PARENT:$FEED"' in script, (
            "nothing reads the branch's own row count, so a truncated feed "
            "publishes as a fast-forward and is accepted"
        )
        assert '"$NOW_ROWS" -lt "$WAS_ROWS"' in script

    def test_a_shrinking_feed_is_refused_not_warned(self) -> None:
        # Extracted by LINES to the block's own `fi`. Splitting the text on
        # "fi" cuts at the first two letters it finds, which is inside the
        # message, not at the end of the block — the same cut that made an
        # earlier version of this suite assert against half a statement.
        lines = self._append_script().splitlines()
        start = next(
            i for i, l in enumerate(lines) if 'if [ -n "$SHRANK" ]; then' in l
        )
        block_lines = []
        for line in lines[start:]:
            block_lines.append(line)
            if line.strip() == "fi":
                break
        block = "\n".join(block_lines)

        assert "::error::" in block
        assert "exit 1" in block
        assert "state=refused-shrink" in block, (
            "the gate reads an empty state as a death; a deliberate refusal "
            "has to say which it was"
        )

    def test_the_refusal_says_the_branch_is_untouched(self) -> None:
        """A message that stops a publish has to say what was and was not done."""
        script = self._append_script()

        assert "The branch is untouched" in script

    def test_the_restore_reports_a_failed_fetch(self) -> None:
        """It exited 0 printing nothing, with no id for the gate to read."""
        step = _named("Restore the price feeds before collecting into them")

        assert step.get("id") == "restore_feeds"
        assert "state=no-fetch" in step["run"]
        assert "state=restored" in step["run"]

    def test_the_gate_surfaces_a_failed_restore(self, tmp_path: Path) -> None:
        script = _named("Report the outcome")["run"]

        assert "steps.restore_feeds.outputs.state" in script


def test_the_gate_warns_when_the_restore_could_not_read_the_branch(
    tmp_path: Path,
) -> None:
    """Run it. The restore's failure was silent in every sense."""
    done = _run(tmp_path, restore="no-fetch")

    assert done.returncode == 0, done.stdout + done.stderr
    assert "could not read the existing price feed" in done.stdout


def test_the_control_a_restored_run_says_nothing_about_it(tmp_path: Path) -> None:
    done = _run(tmp_path, restore="restored")

    assert done.returncode == 0, done.stdout + done.stderr
    assert "could not read the existing price feed" not in done.stdout
