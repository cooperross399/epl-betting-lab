"""When credits run low, the extras stop before the main card does.

On 2026-10-10 the quota hit zero and every run after it was degraded: no
prices for anything, the Premier League card included. The NHL lab caps its
spend in code. Here, below `SHED_EXTRAS_BELOW` the props refresh and the
cup/European/Championship price collection are skipped, and below
`CARD_RESERVE` the Closing Snapshot's purchase is skipped too, so what is left
goes to the matchday card. An unknown quota sheds nothing: a missing reading
is not a low one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from epl_betting_lab.providers.quota_gate import (
    CARD_RESERVE,
    SHED_EXTRAS_BELOW,
    allowed,
    remaining_credits,
)

ROOT = Path(__file__).resolve().parents[1]


def _shadow(tmp_path: Path, remaining) -> Path:
    path = tmp_path / "provider_shadow_verification.json"
    path.write_text(json.dumps({"api_quota": {"requests_remaining": remaining}}))
    return path


def test_the_tiers_are_ordered():
    assert CARD_RESERVE < SHED_EXTRAS_BELOW


def test_plenty_of_credits_spends_on_everything(tmp_path: Path):
    path = _shadow(tmp_path, "50000")
    assert allowed("extras", path) and allowed("snapshot", path)


def test_low_credits_shed_the_extras_and_keep_the_snapshot(tmp_path: Path):
    path = _shadow(tmp_path, str(SHED_EXTRAS_BELOW - 1))
    assert not allowed("extras", path)
    assert allowed("snapshot", path)


def test_very_low_credits_keep_only_the_card(tmp_path: Path):
    path = _shadow(tmp_path, str(CARD_RESERVE - 1))
    assert not allowed("extras", path)
    assert not allowed("snapshot", path)


def test_an_unknown_quota_sheds_nothing(tmp_path: Path):
    assert remaining_credits(tmp_path / "absent.json") is None
    assert allowed("extras", tmp_path / "absent.json")
    assert allowed("extras", _shadow(tmp_path, ""))


def test_the_script_exits_one_when_shed(tmp_path: Path):
    path = _shadow(tmp_path, "10")
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts/quota_gate.py"), "extras", "--shadow", str(path)],
        capture_output=True, text=True, env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert out.returncode == 1
    assert "skipped" in out.stdout


def _step(workflow: str, name: str) -> dict:
    doc = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())
    for job in doc["jobs"].values():
        for step in job.get("steps") or []:
            if step.get("name") == name:
                return step
    raise AssertionError(name)


def test_every_extra_purchase_asks_the_gate_first():
    for workflow, name, tier in [
        ("matchday-refresh.yml", "Refresh the props card", "extras"),
        ("closing-snapshot.yml", "Observe EFL prices", "extras"),
        ("closing-snapshot.yml", "Fetch prices", "snapshot"),
    ]:
        run = _step(workflow, name)["run"]
        assert f"scripts/quota_gate.py {tier}" in run, (workflow, name)
