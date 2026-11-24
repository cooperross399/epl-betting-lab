"""A Pages deploy that cannot see its own artifact yet gets one more try.

Four Publish Board runs between 2026-11-21 and 2026-11-24 failed the same
way: `upload-pages-artifact` finalised `github-pages`, and under a second
later `deploy-pages` listed the run's artifacts, found only `board-history`
("Found 1 artifact(s)") and stopped with "No artifacts named github-pages".
The artifact was there; the listing had not caught up. Each failure left the
public board on the previous build until the next publish, hours later.

The fix is one retry of the deploy after a pause, never a swallowed failure:
the first attempt may fail quietly only because a second, unguarded attempt
follows it, and that second attempt failing still fails the job.
"""

from __future__ import annotations

import yaml

from epl_betting_lab.config import PROJECT_ROOT

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "publish-board.yml"


def _job() -> dict:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return list(spec["jobs"].values())[0]


def _deploys() -> list[dict]:
    return [s for s in _job()["steps"] if str(s.get("uses", "")).startswith("actions/deploy-pages")]


def test_the_deploy_is_tried_twice():
    assert len(_deploys()) == 2


def test_only_the_first_attempt_may_fail_quietly():
    first, second = _deploys()
    assert first.get("continue-on-error") is True
    assert not second.get("continue-on-error")
    assert first["id"] in second["if"] and "failure" in second["if"]


def test_the_retry_waits_for_the_listing_to_catch_up():
    steps = _job()["steps"]
    first, second = _deploys()
    between = steps[steps.index(first) + 1 : steps.index(second)]
    assert any("sleep" in str(s.get("run", "")) and first["id"] in str(s.get("if", "")) for s in between)


def test_the_environment_url_comes_from_whichever_attempt_deployed():
    url = _job()["environment"]["url"]
    for step in _deploys():
        assert f"steps.{step['id']}.outputs.page_url" in url
