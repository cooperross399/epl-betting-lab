"""The captured odds live in a private repository, never on this public one.

The Odds API's terms forbid redistributing its data as downloadable files that
serve as raw data, and a branch of a public repository is exactly that. The
NHL lab moved its closing lines private on 2026-10-01; this lab's
`price-feed` branch was still public on 2026-10-31 with 79 day files of
book-by-book prices. Every workflow step now goes through
`scripts/price_feed_remote.sh`, which writes only to the private repository.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
HELPER = ROOT / "scripts" / "price_feed_remote.sh"


def _steps():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(path.read_text())
        for job in (doc.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                yield path.name, step


def _code(run: str) -> str:
    return "\n".join(line for line in run.splitlines() if not line.strip().startswith("#"))


def test_no_step_fetches_or_pushes_the_price_feed_directly():
    offenders = []
    for name, step in _steps():
        run = _code(step.get("run") or "")
        for line in run.splitlines():
            if re.search(r"git (fetch|push)\b.*price-feed", line):
                offenders.append(f"{name}: {step.get('name')}: {line.strip()}")
    assert offenders == [], offenders


def test_every_step_touching_the_feed_uses_the_helper_and_the_secret():
    touching = []
    for name, step in _steps():
        run = _code(step.get("run") or "")
        if "feed_fetch" in run or "feed_push" in run:
            touching.append((name, step))
            assert ". scripts/price_feed_remote.sh" in run, (name, step.get("name"))
            env = step.get("env") or {}
            assert env.get("EPL_PRICE_FEED_TOKEN") == "${{ secrets.EPL_PRICE_FEED_TOKEN }}", (name, step.get("name"))
    names = {(n, s.get("name")) for n, s in touching}
    # The five steps that read or write the feed.
    assert len(names) >= 5, names
    assert {n for n, _ in names} >= {"matchday-refresh.yml", "closing-snapshot.yml", "publish-board.yml"}


def _bash(script: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f". {HELPER}\n{script}"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **env},
    )


def test_without_the_token_nothing_is_pushed_anywhere():
    out = _bash("feed_push deadbeef", {"GH_TOKEN": "t", "GITHUB_REPOSITORY": "cooperross399/epl-betting-lab"})
    assert out.returncode != 0
    assert "never published to the public repository" in out.stdout


def test_the_push_remote_is_the_private_repository():
    out = _bash("feed_remote", {"EPL_PRICE_FEED_TOKEN": "x"})
    assert out.stdout.endswith("github.com/cooperross399/epl-price-feed")
    assert "epl-betting-lab" not in out.stdout
