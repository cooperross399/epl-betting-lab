"""The history guard, executed rather than read.

The first version of it was checked by asserting `exit 1` appeared three
times and that `-lt` and `steps.restore.outcome` were in the text. All of
that was true of a step that could not refuse a TOTAL wipe: with
`before` = 0, `-z "0"` is false and nothing is `-lt 0`, so every branch was
unreachable in exactly the state the restore loop produces when none of the
ten candidates carries an artifact. The run would publish a one-entry
history over the whole chain and deploy it.

`candidates` — the value that tells "first run ever" from "window
exhausted" — was computed, written to the step output, described in a
comment as read by this step, and read by nothing.

So: substitute the step expressions, run the body, assert the exit code.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from epl_betting_lab.config import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-board.yml"


def _guard_script() -> str:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in list(spec["jobs"].values())[0]["steps"]:
        if step.get("name") == "The history must not shrink":
            return step["run"]
    raise AssertionError("the guard step is gone; re-pin this file")


def _run(tmp_path: Path, *, boards: str, candidates: str, outcome: str, after: int):
    script = _guard_script()
    for expression, value in (
        (r"\$\{\{ steps\.restore\.outputs\.boards \}\}", boards),
        (r"\$\{\{ steps\.restore\.outputs\.candidates \}\}", candidates),
        (r"\$\{\{ steps\.restore\.outcome \}\}", outcome),
    ):
        script = re.sub(expression, value, script)
    assert "${{" not in script, "an unsubstituted expression would run as shell"

    history = tmp_path / "dist" / "data" / "history"
    history.mkdir(parents=True)
    for i in range(after):
        (history / f"2026-09-{20 + i:02d}.json").write_text("{}", encoding="utf-8")
    (history / "index.json").write_text("{}", encoding="utf-8")

    path = tmp_path / "guard.sh"
    path.write_text(script, encoding="utf-8")
    return subprocess.run(
        ["bash", "-e", str(path)], cwd=tmp_path, capture_output=True, text=True
    )


class TestItRefusesTheWipeItWasWrittenFor:
    def test_a_total_wipe_with_prior_runs_is_refused(self, tmp_path: Path) -> None:
        """The case every branch of the first version missed."""
        done = _run(tmp_path, boards="0", candidates="3", outcome="success", after=1)

        assert done.returncode == 1
        assert "none carried a board-history artifact" in done.stdout

    def test_the_control_a_genuine_first_run_is_allowed(self, tmp_path: Path) -> None:
        """Otherwise the fix is "refuse whenever nothing was restored", which
        deadlocks the workflow the first time it ever runs."""
        done = _run(tmp_path, boards="0", candidates="0", outcome="success", after=1)

        assert done.returncode == 0, done.stdout + done.stderr
        assert "history starts with this one" in done.stdout

    def test_a_partial_shrink_is_refused(self, tmp_path: Path) -> None:
        done = _run(tmp_path, boards="8", candidates="3", outcome="success", after=1)

        assert done.returncode == 1
        assert "The history shrank" in done.stdout

    def test_the_control_an_intact_history_passes(self, tmp_path: Path) -> None:
        done = _run(tmp_path, boards="8", candidates="3", outcome="success", after=8)

        assert done.returncode == 0, done.stdout + done.stderr
        assert "History intact: 8 restored, 8 to publish" in done.stdout

    def test_a_growing_history_passes(self, tmp_path: Path) -> None:
        done = _run(tmp_path, boards="8", candidates="3", outcome="success", after=9)

        assert done.returncode == 0, done.stdout + done.stderr


class TestItRefusesWhatItCannotSee:
    @pytest.mark.parametrize(
        "boards,candidates,outcome,reason",
        [
            ("8", "3", "failure", "did not succeed"),
            ("", "3", "success", "reported no board count"),
            ("0", "", "success", "reported no candidate count"),
        ],
    )
    def test_an_unreadable_restore_stops_the_publish(
        self, tmp_path: Path, boards, candidates, outcome, reason
    ) -> None:
        done = _run(
            tmp_path, boards=boards, candidates=candidates, outcome=outcome, after=1
        )

        assert done.returncode == 1
        assert reason in done.stdout


def test_the_candidate_count_excludes_the_running_job() -> None:
    """`gh run list` includes the run executing the step.

    Counting every row makes `candidates` at least 1 on the first publish
    this repository ever does, and a count that cannot be zero cannot make
    the one distinction it exists for.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    restore = next(
        s for s in list(spec["jobs"].values())[0]["steps"] if s.get("id") == "restore"
    )

    assert 'if [ "$candidate" = "${{ github.run_id }}" ]; then' in restore["run"]
