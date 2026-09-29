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
    degraded: str = "false",
    refusal: str = "false",
    rebuild: str = "success",
):
    script = _gate_script()
    for expression, value in (
        (r"\$\{\{ steps\.publish\.outputs\.state \}\}", state),
        (r"\$\{\{ steps\.publish\.outcome \}\}", publish),
        (r"\$\{\{ steps\.email\.outcome \}\}", email),
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
