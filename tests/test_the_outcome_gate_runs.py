"""The outcome gate, executed rather than read.

It was checked by extracting its `if`/`elif` expressions and asserting the
right identifiers appeared in them. That is a real improvement on grepping
the whole step — it killed three mutants that a whole-step grep did not —
and it still cannot see what the gate DOES with a value it reads correctly.

The gate read `steps.publish.outputs.state`, compared it against empty, and
treated `published` and `placeholder` alike, because the publish step wrote
`published` for both. Every condition-level check passed.

So: substitute the six step expressions, run the body, assert the exit code.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from epl_betting_lab.config import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"


def _gate_script() -> str:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in list(spec["jobs"].values())[0]["steps"]:
        if step.get("name") == "Report the outcome":
            return step["run"]
    raise AssertionError("the outcome gate is gone; re-pin this file")


def _run(
    tmp_path: Path,
    *,
    state: str = "published",
    publish: str = "success",
    email: str = "success",
    feed: str = "appended",
    feed_outcome: str = "success",
    degraded: str = "false",
    refusal: str = "false",
    rebuild: str = "success",
):
    script = _gate_script()
    for expression, value in (
        (r"\$\{\{ steps\.publish\.outputs\.state \}\}", state),
        (r"\$\{\{ steps\.publish\.outcome \}\}", publish),
        (r"\$\{\{ steps\.email\.outcome \}\}", email),
        (r"\$\{\{ steps\.prices_feed\.outputs\.state \}\}", feed),
        (r"\$\{\{ steps\.prices_feed\.outcome \}\}", feed_outcome),
        (r"\$\{\{ steps\.health\.outputs\.degraded \}\}", degraded),
        (r"\$\{\{ steps\.health\.outputs\.expected_refusal \}\}", refusal),
        (r"\$\{\{ steps\.rebuild\.outcome \}\}", rebuild),
    ):
        script = re.sub(expression, value, script)
    assert "${{" not in script, "an unsubstituted expression would run as shell"

    path = tmp_path / "gate.sh"
    path.write_text(script, encoding="utf-8")
    return subprocess.run(
        ["bash", "-e", str(path)], cwd=tmp_path, capture_output=True, text=True
    )


class TestItFailsWhenNoCardWasDelivered:
    def test_a_placeholder_is_not_a_delivery(self, tmp_path: Path) -> None:
        """The hole the condition-level checks could not see."""
        done = _run(tmp_path, state="placeholder")

        assert done.returncode == 1
        assert "Only the no-card placeholder" in done.stdout
        assert "Clean run." not in done.stdout

    def test_a_placeholder_fails_even_when_the_provider_refusal_was_expected(
        self, tmp_path: Path
    ) -> None:
        """The refusal path exits 0. Delivery has to be judged before it."""
        done = _run(tmp_path, state="placeholder", refusal="true")

        assert done.returncode == 1

    def test_an_empty_state_is_a_death(self, tmp_path: Path) -> None:
        done = _run(tmp_path, state="")

        assert done.returncode == 1
        assert "did not reach the card-feed branch" in done.stdout

    def test_a_failed_publish_step_fails_the_run(self, tmp_path: Path) -> None:
        done = _run(tmp_path, publish="failure", state="")

        assert done.returncode == 1


class TestItPassesWhatShouldPass:
    @pytest.mark.parametrize("state", ["published", "left-alone"])
    def test_a_real_delivery_is_a_clean_run(self, tmp_path: Path, state) -> None:
        """Both are deliveries: one pushed a card, one declined to replace one."""
        done = _run(tmp_path, state=state)

        assert done.returncode == 0, done.stdout + done.stderr
        assert "Clean run." in done.stdout
        assert f"card-feed: {state}" in done.stdout

    def test_a_failed_email_warns_and_does_not_fail(self, tmp_path: Path) -> None:
        done = _run(tmp_path, email="failure")

        assert done.returncode == 0, done.stdout + done.stderr
        assert "::warning::" in done.stdout

    def test_an_expected_refusal_is_not_a_fault(self, tmp_path: Path) -> None:
        done = _run(tmp_path, refusal="true")

        assert done.returncode == 0, done.stdout + done.stderr
        assert "Not a fault" in done.stdout

    def test_a_degraded_run_still_fails(self, tmp_path: Path) -> None:
        """The behaviour that predates the delivery check, kept."""
        done = _run(tmp_path, degraded="true")

        assert done.returncode == 1
        assert "This run was degraded" in done.stdout


class TestTheFourthPublishingStep:
    """The price-feed push in this workflow had no `id` either.

    Three publishing steps were given one today — the card, the board
    history, the snapshot's append — and this fourth one was missed, in the
    workflow that was fixed first. Its outcome was unreferenceable, so a run
    that fetched prices and failed to append any of them said nothing.

    It WARNS rather than failing. The card is the day's deliverable and a
    missing feed row is one supplementary observation; the Closing
    Snapshot's near-kickoff capture, which does fail hard, is the one
    `live_clv` reads. Failing a delivered card over a lost feed row would
    invert "a run never ends with nothing to show".
    """

    def test_a_lost_feed_row_warns(self, tmp_path: Path) -> None:
        done = _run(tmp_path, feed="", feed_outcome="failure")

        assert done.returncode == 0, done.stdout + done.stderr
        assert "did not reach the price-feed branch" in done.stdout
        assert "::warning::" in done.stdout

    def test_a_step_that_died_before_reporting_warns_too(self, tmp_path: Path) -> None:
        done = _run(tmp_path, feed="")

        assert done.returncode == 0, done.stdout + done.stderr
        assert "::warning::" in done.stdout

    @pytest.mark.parametrize("state", ["appended", "unchanged", "nothing-to-publish"])
    def test_the_control_a_delivered_row_says_so_quietly(
        self, tmp_path: Path, state
    ) -> None:
        done = _run(tmp_path, feed=state)

        assert done.returncode == 0, done.stdout + done.stderr
        assert f"price-feed: {state}" in done.stdout
        assert "did not reach the price-feed" not in done.stdout

    def test_it_does_not_fail_a_run_whose_card_landed(self, tmp_path: Path) -> None:
        """The judgement, pinned: a lost feed row is not a lost card."""
        done = _run(tmp_path, feed="", feed_outcome="failure", state="published")

        assert done.returncode == 0
        assert "Clean run." in done.stdout


def test_every_publishing_step_in_this_workflow_can_be_referred_to() -> None:
    """Three publishing steps got an `id` today and a fourth was missed.

    A step that pushes to a branch and carries no `id` has an outcome the
    gate cannot name, which is how each of the others hid. Enumerated from
    the workflow rather than listed by hand, so a fifth one added later
    fails this instead of joining them.
    """
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = list(spec["jobs"].values())[0]["steps"]
    pushers = [
        s for s in steps
        if "git push" in (s.get("run") or "") and "refs/heads/" in (s.get("run") or "")
    ]

    assert pushers, "no publishing step found; the detector is broken"
    for step in pushers:
        assert step.get("id"), (
            f"{step.get('name')!r} pushes to a branch with no id, so the "
            "outcome gate cannot see whether it worked"
        )
