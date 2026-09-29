"""The board's history exists only in an artifact chain, so the chain is the record.

`web/site_history.py` rebuilds `history/index.json` from whatever frozen boards
are on disk. That is fine while the restore works and catastrophic when it does
not: an empty restore produces a one-entry history, uploads it as the newest
`board-history` artifact, and deploys it to the public Archive page. Every
earlier frozen board and every line series goes, and the run finishes green.

Nothing here is hypothetical about the mechanism — matchday-refresh.yml carries
a comment describing the same pinned-restore bug freezing its card archive for
nine runs, and the loop that fixed it. This file kept the pinned version.
"""

from __future__ import annotations

import re

import yaml

from epl_betting_lab.config import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-board.yml"


def _steps() -> list[dict]:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return list(spec["jobs"].values())[0]["steps"]


def _named(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r}")


def _conditions(script: str) -> str:
    """Only the `if`/`elif` test expressions of a shell script.

    Asserting an identifier appears anywhere in a step is not a guard on the
    step's logic, because the identifier also appears in the `::error::`
    message the step prints. Three mutants proved it: replacing a condition
    with `[ "no" = "yes" ]` while leaving the message intact passed every one
    of these tests. A check on a condition has to read the condition.
    """
    out, joining = [], False
    for line in script.splitlines():
        stripped = line.strip()
        if joining or re.match(r"^(if|elif)\b", stripped):
            out.append(stripped)
            joining = not stripped.endswith("then")
    return "\n".join(out)


def _code(script: str) -> str:
    """The script with its comments removed.

    The comment explaining why `--limit 1` was wrong contains the string
    `--limit 1`, so a guard reading the raw step matched its own explanation.
    A guard that reads a file has to read the part of it that executes.
    """
    return "\n".join(
        line for line in script.splitlines() if not line.strip().startswith("#")
    )


def _order(name: str) -> int:
    for i, step in enumerate(_steps()):
        if step.get("name") == name:
            return i
    raise AssertionError(f"no step named {name!r}")


def test_the_restores_walk_back_instead_of_pinning_to_the_newest_run() -> None:
    """`--limit 1 --status completed` is the bug, not a detail of it.

    "Completed" includes failed, cancelled and timed out. A run that died
    before its upload carries no artifact, so pinning to it restores nothing,
    and the `|| echo` beside it turns that into a line of log.
    """
    script = _code(_named("Restore the lab's latest run and the board's history")["run"])

    # `"--limit 1" not in script` is the obvious spelling and it can never
    # pass: `--limit 10` contains `--limit 1`. The boundary is the assertion.
    assert not re.search(r"--limit 1(?![0-9])", script), (
        "pinned to the newest completed run again; it may be a failed one"
    )
    assert script.count("--limit 10") == 2, (
        "both restores — the lab's state and the board's history — need the "
        "walk-back, not just one of them"
    )
    assert script.count("break") == 2


def test_the_restore_says_how_much_history_it_found() -> None:
    """The guard below cannot compare against a number nobody wrote down."""
    step = _named("Restore the lab's latest run and the board's history")

    assert step.get("id") == "restore"
    assert 'echo "boards=' in step["run"]
    assert 'echo "candidates=' in step["run"]


def test_the_history_guard_precedes_the_upload_and_the_deploy() -> None:
    """Order is the whole protection.

    The upload makes the wiped history the newest artifact for the next run;
    the deploy puts it on the public Archive page. A check that runs after
    either of them reports a loss that has already happened.
    """
    guard = _order("The history must not shrink")

    assert guard < _order("Keep the history")
    assert guard < _order("Upload the site")
    assert guard < _order("Deploy to GitHub Pages")


def test_the_history_guard_refuses_rather_than_warns() -> None:
    """A warning in a log nobody reads is how the record would go anyway."""
    script = _code(_named("The history must not shrink")["run"])

    assert script.count("exit 1") == 3, (
        "three ways to be blind: the restore failed, the restore said nothing, "
        "or the history shrank"
    )
    conditions = _conditions(script)

    assert "-lt" in conditions
    assert "steps.restore.outcome" in conditions, (
        "the restore is continue-on-error, so a death inside it is invisible "
        "unless someone checks its outcome — in the condition, not only in "
        "the message the condition guards"
    )
    assert '-z "$before"' in conditions, (
        "an empty count means the restore died before saying what it found"
    )


def test_keeping_the_history_is_not_run_on_a_failed_job() -> None:
    """The obvious fix is the wrong one, so it is pinned shut.

    `if: always()` on the upload would publish a PARTIAL history from a run
    that failed midway, making the truncated copy the newest artifact — the
    chain poisoned rather than left intact. A failed run must carry no
    board-history artifact at all.
    """
    step = _named("Keep the history")

    assert "if" not in step, (
        "an `if:` here — always() in particular — would upload a partial "
        "history from a failed run and poison the chain"
    )
