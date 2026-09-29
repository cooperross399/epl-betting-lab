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


def _run(
    tmp_path: Path,
    *,
    boards: str,
    candidates: str,
    outcome: str,
    after: int,
    restart: str = "false",
):
    script = _guard_script()
    for expression, value in (
        (r"\$\{\{ steps\.restore\.outputs\.boards \}\}", boards),
        (r"\$\{\{ steps\.restore\.outputs\.candidates \}\}", candidates),
        (r"\$\{\{ steps\.restore\.outcome \}\}", outcome),
        (r"\$\{\{ inputs\.restart_history \}\}", restart),
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
        assert "carried a board-history artifact" in done.stdout

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
            ("0", "", "success", "could not say how many prior publish runs"),
            ("0", "unknown", "success", "failed lookup"),
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


class TestTheRefusalHasAWayOut:
    """The refusal was an absorbing state.

    It fails the job before "Keep the history", which carries no `if:` by
    design, so a refusing run adds one more artifact-less run to the window
    the restore reads. Once the window holds nothing else, every later run
    refuses on the same line — the Pages deploy stops and the Archive
    freezes even after the original cause is fixed.

    Re-running an older publish does not help: the loop skips the re-run's
    own id, which is the only run in reach still carrying the artifact. The
    recovery the old message named could not work.
    """

    def test_restart_history_publishes_over_the_refusal(self, tmp_path: Path) -> None:
        done = _run(
            tmp_path, boards="0", candidates="9", outcome="success", after=1,
            restart="true",
        )

        assert done.returncode == 0, done.stdout + done.stderr
        assert "restart_history was set" in done.stdout
        assert "Everything earlier is dropped" in done.stdout

    def test_an_empty_input_is_not_an_escape(self, tmp_path: Path) -> None:
        """The value the schedule and workflow_run triggers actually supply.

        `inputs.restart_history` is only "false" on a dispatch that left the
        default alone. On the two triggers that fire this workflow in
        practice there is no inputs context at all and the expression is the
        empty string, which every test here was passing "false" for.
        """
        done = _run(
            tmp_path, boards="0", candidates="9", outcome="success", after=1,
            restart="",
        )

        assert done.returncode == 1, (
            "an empty input opened the escape, so every scheduled run would "
            "publish over the chain"
        )

    def test_the_control_without_it_the_refusal_still_stands(
        self, tmp_path: Path
    ) -> None:
        """An escape that is always open is not a guard."""
        done = _run(tmp_path, boards="0", candidates="9", outcome="success", after=1)

        assert done.returncode == 1

    def test_the_message_names_mechanisms_that_exist(self, tmp_path: Path) -> None:
        """"Clear this by hand" named no mechanism at all.

        The replacement has to name two that do, and say plainly that the
        obvious one does not work: this check runs BEFORE the upload, so
        repairing the uploader leaves a repaired run refusing here and still
        carrying no artifact.
        """
        done = _run(tmp_path, boards="0", candidates="9", outcome="success", after=1)

        assert "restart_history" in done.stdout
        assert "gh run download" in done.stdout, "no concrete recovery named"
        assert "does NOT clear this" in done.stdout, (
            "the message still implies fixing the uploader is enough"
        )

    def test_restart_history_does_not_excuse_a_broken_restore(
        self, tmp_path: Path
    ) -> None:
        """It answers "the window is exhausted", not "nothing can be read".

        A restore that died still cannot say what was there, and publishing
        over the chain on that basis is the wipe the step exists to stop.
        """
        done = _run(
            tmp_path, boards="", candidates="9", outcome="failure", after=1,
            restart="true",
        )

        assert done.returncode == 1


def test_the_candidate_window_is_wide_enough_to_survive_a_failure_run() -> None:
    """Ten was short enough to be exhausted by about three days of failures.

    Artifact retention here is 400 days, so a wider window costs a few
    skipped downloads and removes the only realistic route into the
    absorbing state.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    restore = next(
        s for s in list(spec["jobs"].values())[0]["steps"] if s.get("id") == "restore"
    )
    # The board-history loop only. The lab-state restore beside it reads a
    # different workflow and is not what the refusal counts.
    board = restore["run"].split("--workflow publish-board.yml")[1]
    window = re.search(r"--limit (\d+)", board)

    assert window, "the board-history restore no longer states a window"
    assert int(window.group(1)) >= 40, window.group(1)


def test_the_run_listing_is_captured_and_its_exit_status_checked() -> None:
    """Inline in a `for` header, a failed listing looks like no prior runs.

    `for candidate in $(gh run list ...)` discards the command's exit
    status: an auth failure or a rate limit yields nothing, `seen` stays 0,
    and the total-wipe refusal reads that as "no prior run has ever
    published" — so a broken lookup takes the first-run path and publishes
    a one-entry history over the chain. The wipe through the front door of
    the guard written to stop it.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    restore = next(
        s for s in list(spec["jobs"].values())[0]["steps"] if s.get("id") == "restore"
    )
    code = "\n".join(
        line for line in restore["run"].splitlines()
        if not line.strip().startswith("#")
    )

    assert "if ! prior=$(gh run list --workflow publish-board.yml" in code, (
        "the publish-run listing is not captured with its exit status checked"
    )
    assert "for candidate in $prior; do" in code
    assert 'echo "candidates=unknown"' in code, (
        "a failed listing has to be reported as unknown, not as zero"
    )
