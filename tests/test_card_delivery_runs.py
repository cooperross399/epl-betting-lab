"""The delivery path, executed rather than read.

Every other test of this path matches strings in the workflow. On 2026-09-15
that was not enough twice over, in the same hour:

  * `test_the_card_is_looked_up_by_the_title_the_module_owns` asserted the text
    `post_card_to_issue.py --title-only` appeared in the workflow. It did. The
    command could not run — `--out` was `required=True`, so argparse exited 2
    before the flag was ever consulted — and because that call is the FIRST
    command of the "Email the card" step under `bash -e`, the step aborted
    before rendering anything. `continue-on-error: true` reported success.

  * `test_a_degraded_run_never_replaces_a_good_card_from_the_same_day` asserted
    the guard compared the day, the previous card and this run's health. It
    did. It asked whether this run was *degraded*, and the run that overwrote
    the card was not degraded — it was healthy and empty. The card built at
    13:26 was replaced by "No card was rendered this run." at 14:30.

Both tests were true sentences about text. These run the code.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.reports.card_notification import ISSUE_TITLE

#: The publish step is shell. Running it needs the same three tools the
#: workflow needs, and a missing one is a hard failure rather than a skip: a
#: skip here would report "the delivery path is fine" on a machine that never
#: ran a line of it, and conftest ends the session red for a skip anyway.
SHELL_TOOLS = ("git", "bash", "jq")


# --- the command the step opens with ---------------------------------------


def test_the_title_lookup_actually_runs() -> None:
    """The first command of "Email the card", executed.

    Not `in text`: that assertion held while the command exited 2 on every
    run. Under `bash -e` this one failure costs the card, the issue comment
    and the feed entry, and the step still reports success.
    """
    result = subprocess.run(
        [sys.executable, "scripts/post_card_to_issue.py", "--title-only"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )

    assert result.returncode == 0, (
        f"the workflow's first command exits {result.returncode}: {result.stderr}"
    )
    assert result.stdout.strip() == ISSUE_TITLE


def test_out_is_still_required_when_a_card_is_being_written() -> None:
    """Making `--out` optional must not let a real render write nowhere."""
    result = subprocess.run(
        [sys.executable, "scripts/post_card_to_issue.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
    )

    assert result.returncode != 0
    assert "--out" in result.stderr


# --- the step that decides what reaches the branch -------------------------


def _publish_step() -> str:
    """The publish step's own shell, with only GitHub's expressions replaced.

    Extracted rather than restated. A copy of the logic here would pass while
    the workflow did something else, which is how a measured model and a
    carded model came apart once already.
    """
    text = (PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml").read_text(
        encoding="utf-8"
    )
    block = text.split("- name: Publish the card to the card-feed branch", 1)[1]
    block = block.split("      - name: Upload reports", 1)[0]
    body = block.split("        run: |\n", 1)[1]
    script = "\n".join(
        line[10:] if line.startswith(" " * 10) else line for line in body.splitlines()
    )
    script = script.replace(
        'REMOTE="https://x-access-token:${GH_TOKEN}@github.com/'
        '${{ github.repository }}"',
        'REMOTE="$TEST_REMOTE"',
    )
    script = script.replace(
        "${{ steps.health.outputs.degraded || 'unknown' }}", "$TEST_DEGRADED"
    )
    script = script.replace("${{ github.event_name }}", "workflow_dispatch")
    script = script.replace("${{ github.server_url }}", "https://example.test")
    script = script.replace("${{ github.repository }}", "test/repo")
    script = script.replace("${{ github.run_id }}", "1")
    assert "${{" not in script, "an unsubstituted expression would run as literal text"
    _refuse_swallowed_yaml(script, "publish step")
    return script


def _refuse_swallowed_yaml(script: str, step: str) -> None:
    """An extractor that runs past its step turns YAML into shell.

    The end anchors are literal step names. Insert a step between this one and
    the anchor and the extracted script grows a tail of `- name:` / `if:` /
    `run: |` lines. They are not indented by ten spaces, so the dedent leaves
    them verbatim and they run as commands. `assert "${{" not in script` does
    not catch it — an inserted step need not contain an expression.
    """
    for line in script.splitlines():
        assert not re.match(r"^\s*- name:", line), (
            f"the {step} extractor ran past the end of its step and swallowed "
            f"YAML as shell: {line!r}"
        )
        assert not re.match(
            r"^\s{1,9}(if|run|env|id|uses|with|timeout-minutes):", line
        ), f"the {step} extractor swallowed a YAML key as shell: {line!r}"


class Feed:
    """A bare repository standing in for the card-feed branch."""

    def __init__(self, root: Path) -> None:
        self.remote = root / "remote"
        self.work = root / "work"
        missing = [tool for tool in SHELL_TOOLS if not shutil.which(tool)]
        assert not missing, (
            f"the publish step cannot be run without {', '.join(missing)}; "
            "the workflow uses all of these on the runner"
        )
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", str(self.work)], check=True)
        self.script = root / "publish.sh"
        self.script.write_text(_publish_step(), encoding="utf-8")

    def run(self, *, card: str | None, degraded: str = "false") -> str:
        for stale in ("card_comment.md", "card_status.json"):
            (self.work / stale).unlink(missing_ok=True)
        if card is not None:
            (self.work / "card_comment.md").write_text(card, encoding="utf-8")
        # `bash -e`, because that is the shell GitHub gives a `run:` block —
        # the workflow sets no `shell:` anywhere. Replaying the step under
        # plain `bash` leaves the harness blind to a command that aborts the
        # step on the runner, which is half of what went wrong on 2026-09-15.
        done = subprocess.run(
            ["bash", "-e", str(self.script)],
            cwd=self.work,
            capture_output=True,
            text=True,
            env={
                "PATH": os.environ["PATH"],
                "HOME": str(self.work),
                "TEST_REMOTE": str(self.remote),
                "TEST_DEGRADED": degraded,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
            },
        )
        assert done.returncode == 0, (
            "the publish step aborted:\n" + done.stdout + done.stderr
        )
        return done.stdout + done.stderr

    def status(self) -> dict:
        shown = subprocess.run(
            ["git", "show", "card-feed:latest_status.json"],
            cwd=self.remote,
            capture_output=True,
            text=True,
        ).stdout
        return json.loads(shown or "{}")

    def published(self) -> str:
        return subprocess.run(
            ["git", "show", "card-feed:latest_card_comment.md"],
            cwd=self.remote,
            capture_output=True,
            text=True,
        ).stdout.strip()


def test_a_healthy_run_that_rendered_nothing_does_not_replace_a_good_card(
    tmp_path: Path,
) -> None:
    """The 2026-09-15 incident, as a test.

    The renderer had crashed, so there was no card; the health step had nothing
    to report, so the run was not degraded. A guard that asks only about
    degradation waves this through, and the day's card is gone.
    """
    feed = Feed(tmp_path)
    feed.run(card="the real card")
    assert feed.published() == "the real card"

    feed.run(card=None, degraded="false")

    assert feed.published() == "the real card", (
        "a run with no card replaced one that had a card"
    )


def test_an_empty_card_file_is_not_a_card(tmp_path: Path) -> None:
    """The file existing is not the same as a card being in it.

    The test is `[ ! -s card_comment.md ]`, not `[ ! -f ... ]`, and nothing
    else in this file tells the two apart: every other case either writes a
    real card or no file at all, and on a missing file the two tests agree.
    A render killed between opening the file and writing it — a job timeout, a
    cancelled runner — leaves nought bytes behind, and under `-f` that is
    published as the day's card and stamped `card: rendered`, which the guard
    below then protects for the rest of the day.
    """
    feed = Feed(tmp_path)
    feed.run(card="the real card")

    feed.run(card="", degraded="false")

    assert feed.published() == "the real card", (
        "an empty card file was published over a real card"
    )
    assert feed.status().get("card") == "rendered", (
        "the branch entry was restamped from a run that had no card"
    )


def test_a_later_real_card_still_replaces_an_earlier_one(tmp_path: Path) -> None:
    """The guard must stay narrow. Refusing every second write of the day
    would freeze the feed on the morning card and hide every later price."""
    feed = Feed(tmp_path)
    feed.run(card="the morning card")

    feed.run(card="the afternoon card")

    assert feed.published() == "the afternoon card"


def test_a_placeholder_does_not_pin_the_feed_for_the_rest_of_the_day(
    tmp_path: Path,
) -> None:
    """A placeholder reports `degraded: false`, exactly like a good card.

    That matters only for a later run which is itself degraded or empty, since
    a healthy run with a card never consults the previous entry at all. Here
    the morning crashed and the afternoon is blocked but knows why: without
    checking that the thing being protected is a real card, the guard mistakes
    the placeholder for one, declines to publish, and the named blocker never
    reaches the feed — the routine is left with "No card was rendered this
    run." for the rest of the day and nothing saying what went wrong.

    Written the obvious way — placeholder, then a healthy card — this test
    passed with the check deleted.
    """
    feed = Feed(tmp_path)
    feed.run(card=None, degraded="false")
    assert "No card was rendered" in feed.published()

    feed.run(card="Needs odds: the provider returned nothing", degraded="true")

    assert feed.published() == "Needs odds: the provider returned nothing"


def test_a_first_failure_of_the_day_still_reaches_the_branch(tmp_path: Path) -> None:
    """Silence has to keep meaning "the run did not finish". With no card
    already on the branch there is nothing to protect, and the routine needs
    to see that the run got this far and had nothing."""
    feed = Feed(tmp_path)

    feed.run(card=None, degraded="true")

    assert "No card was rendered" in feed.published()


def test_a_degraded_run_still_cannot_replace_a_good_card(tmp_path: Path) -> None:
    """The original rule, kept. Widening the guard must not drop what it
    already covered."""
    feed = Feed(tmp_path)
    feed.run(card="the good card")

    feed.run(card="a blocked card", degraded="true")
    assert feed.published() == "the good card"

    feed.run(card="a card from a run that cannot vouch for itself", degraded="unknown")
    assert feed.published() == "the good card"


# --- the step that decides whether anything is rendered at all -------------


def _email_step() -> str:
    """The "Email the card" step's own shell, GitHub expressions substituted."""
    text = (PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml").read_text(
        encoding="utf-8"
    )
    block = text.split("- name: Email the card", 1)[1]
    block = block.split("      - name: Record this run's prices in the price feed", 1)[0]
    body = block.split("        run: |\n", 1)[1]
    script = "\n".join(
        line[10:] if line.startswith(" " * 10) else line for line in body.splitlines()
    )
    script = script.replace("${{ github.event_name }}", "workflow_dispatch")
    script = script.replace("${{ github.server_url }}", "https://example.test")
    script = script.replace("${{ github.repository }}", "test/repo")
    script = script.replace("${{ github.run_id }}", "1")
    script = script.replace("${{ inputs.force_email }}", "false")
    assert "${{" not in script, "an unsubstituted expression would run as literal text"
    _refuse_swallowed_yaml(script, "email step")
    return script


def _run_email_step(tmp_path: Path, *, renderer: str) -> subprocess.CompletedProcess:
    """Run the step with `python` and `gh` stubbed, under GitHub's own shell.

    `bash -e` is not incidental — it is the shell GitHub gives a `run:` block,
    and half of what went wrong on 2026-09-15 was a step aborting under it and
    still reporting success.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "python").write_text(renderer, encoding="utf-8")
    (stubs / "gh").write_text("#!/usr/bin/env bash\necho '[]'\n", encoding="utf-8")
    for stub in stubs.iterdir():
        stub.chmod(0o755)

    step = tmp_path / "email.sh"
    step.write_text(_email_step(), encoding="utf-8")
    return subprocess.run(
        ["bash", "-e", str(step)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"},
    )


#: Renders nothing and exits 2 — what argparse did to every run after the
#: delivery issue was renamed.
CRASHES = """#!/usr/bin/env bash
case "$*" in
  *--title-only*) echo "Soccer Card — this week's picks"; exit 0 ;;
esac
echo "post_card_to_issue.py: error: something broke" >&2
exit 2
"""

#: Renders a card and reports that the selections did not move.
QUIET = """#!/usr/bin/env bash
case "$*" in
  *--title-only*) echo "Soccer Card — this week's picks"; exit 0 ;;
esac
echo "a real card" > card_comment.md
echo "Soccer Card — this week's picks" > card_title.txt
echo "nothing moved"
echo "skip"
"""


def test_a_crashed_renderer_fails_the_step_instead_of_reading_as_no_change(
    tmp_path: Path,
) -> None:
    """The decision used to arrive through `| tail -1`, which reports the exit
    status of `tail`. `tail` succeeds on empty input, so a renderer that died
    produced an empty decision, and the branch below reads anything that is not
    `post` as "the selections did not change" — the one outcome that is
    supposed to mean everything is fine."""
    done = _run_email_step(tmp_path, renderer=CRASHES)

    assert done.returncode != 0, (
        "a renderer that exited 2 left the step reporting success"
    )
    assert "Not emailing" not in done.stdout, (
        "a crash was reported as a quiet matchday"
    )


def test_a_quiet_matchday_still_ends_the_step_cleanly(tmp_path: Path) -> None:
    """The check must separate a crash from the ordinary case it resembles:
    a run that rendered a card and found nothing worth sending."""
    done = _run_email_step(tmp_path, renderer=QUIET)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "Not emailing" in done.stdout
    assert (tmp_path / "card_comment.md").read_text().strip() == "a real card"
