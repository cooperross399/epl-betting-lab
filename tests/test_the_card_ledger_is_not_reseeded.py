"""A green run whose restore found nothing would reseed the card archive.

`archive/automated_cards` is the only record of what the card recommended,
and `card_scoreboard.load_archived_cards` reads the settled record from it.
It survives between runs in the `matchday-state` artifact and nowhere else.

The restore walked ten candidates and, finding none, printed "This run
establishes the baseline" and exited 0 — a green step. The upload is
`if: always()`, so it then published a `matchday-state` artifact holding
this run's single card. That artifact is the newest, so every later
walk-back stops at it and fifty-odd cards are orphaned in artifacts that
expire in ninety days. The board-history wipe, in the workflow beside it.

The guard sits on the UPLOAD, not the restore: the restore is
`continue-on-error`, so an `exit 1` there marks the step red and the job
carries on — and `always()` would publish anyway.
"""

from __future__ import annotations

import re

import yaml

from epl_betting_lab.config import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"


def _steps() -> list[dict]:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return list(spec["jobs"].values())[0]["steps"]


def _named(name: str) -> dict:
    for step in _steps():
        if (step.get("name") or "").startswith(name):
            return step
    raise AssertionError(f"no step starting {name!r}")


def test_the_upload_is_skipped_when_the_restore_could_not_reach_the_chain() -> None:
    upload = _named("Upload the state for the next run")

    assert upload["if"] == "always() && steps.restore.outputs.safe != 'false'", (
        f"the state upload's condition is {upload.get('if')!r}; a bare "
        "always() reseeds the card archive from one card"
    )


def test_the_guard_is_on_the_upload_because_the_restore_cannot_fail() -> None:
    """Stated as a test so the two facts stay connected.

    If the restore ever stops being continue-on-error, an `exit 1` there
    becomes viable and this arrangement can be revisited — but only then.
    """
    restore = _named("Restore the previous state")

    assert restore.get("continue-on-error") is True
    assert restore.get("id") == "restore"


def test_the_restore_reports_whether_publishing_is_safe() -> None:
    code = "\n".join(
        line for line in _named("Restore the previous state")["run"].splitlines()
        if not line.strip().startswith("#")
    )

    assert code.count("safe=true") == 2, (
        "both safe paths — a real restore and a genuine first run — have to "
        "say so, or the upload is skipped on a healthy baseline run"
    )
    assert code.count("safe=false") == 2, (
        "both unsafe paths — an exhausted window and a failed listing — have "
        "to say so"
    )


def test_a_genuine_first_run_still_uploads() -> None:
    """The control. A guard that blocks the first run ever is a deadlock."""
    code = _named("Restore the previous state")["run"]

    assert 'if [ "$seen" -gt 0 ]; then' in code, (
        "the refusal must depend on prior runs existing, not merely on "
        "having restored nothing"
    )


def test_the_listing_is_captured_and_checked() -> None:
    """A failed `gh run list` must not read as "no prior runs"."""
    code = _named("Restore the previous state")["run"]

    assert "if ! prior=$(gh run list --workflow matchday-refresh.yml" in code
    assert "for candidate in $prior; do" in code


def test_the_window_excludes_the_running_job() -> None:
    code = _named("Restore the previous state")["run"]

    assert 'if [ "$candidate" = "${{ github.run_id }}" ]; then' in code
