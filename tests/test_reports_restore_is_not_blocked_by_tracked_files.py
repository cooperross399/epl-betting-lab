"""The matchday-reports artifact must actually land where the board reads it.

`gh run download` refuses to write over a file that already exists ("file
exists") and then fails the whole download. The checkout holds tracked copies
of several reports the artifact carries (provider_shadow_verification.md,
automated_card_input.md, count_calibration.md, a stale
player_props_card.json from 2026-10-19), so downloading the artifact straight
into `data/outputs` failed on every run. Publish Board logged "carried state
but no reports" and published the board with no live props card and no Due
List; the Lineup Check never found a card to check.

The fix downloads into a scratch directory and copies over the checkout. This
test pins it: no workflow may download matchday-reports into a directory where
a tracked file collides with what the artifact carries, and each one that
downloads to scratch copies the result into data/outputs.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _artifact_paths() -> list[str]:
    text = (WORKFLOWS / "matchday-refresh.yml").read_text(encoding="utf-8")
    block = text.split("name: matchday-reports", 1)[1].split("if-no-files-found", 1)[0]
    return re.findall(r"^\s+(data/outputs/\S+)\s*$", block, flags=re.M)


def _tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files", "data/outputs"], cwd=ROOT, capture_output=True, text=True, check=True)
    return set(out.stdout.split())


def _downloads() -> list[tuple[str, str, str]]:
    found = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        for m in re.finditer(r"gh run download \S+ --name matchday-reports --dir (\S+)", text):
            found.append((wf.name, m.group(1).strip('"'), text))
    return found


def test_the_artifact_carries_files_the_checkout_also_tracks():
    # The precondition that made the direct download fail. If this ever goes
    # false the guard below is still right, just no longer load-bearing.
    assert _artifact_paths(), "could not read the matchday-reports upload list"
    assert set(_artifact_paths()) & _tracked()


def test_no_workflow_downloads_reports_over_tracked_files():
    downloads = _downloads()
    assert {name for name, _, _ in downloads} >= {"publish-board.yml", "lineup-check.yml"}
    collide = set(_artifact_paths()) & _tracked()
    for name, target, _ in downloads:
        if target.rstrip("/") == "data/outputs":
            assert not collide, (
                f"{name} downloads matchday-reports into data/outputs, where tracked "
                f"{sorted(collide)} make gh run download fail with 'file exists'"
            )


def test_a_scratch_download_is_copied_over_the_checkout():
    for name, target, text in _downloads():
        if target.rstrip("/") != "data/outputs":
            assert re.search(r'cp -R "?' + re.escape(target.rstrip("/")) + r'/\.?"? data/outputs/?', text), (
                f"{name} downloads matchday-reports to {target} and never copies it into data/outputs"
            )
