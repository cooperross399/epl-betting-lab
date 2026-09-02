"""The probe answers questions about the provider instead of asserting them.

Two claims from outside this project contradicted CLAUDE.md: that Pinnacle can
be fetched by name regardless of region, and that historical BTTS and corner
prices are purchasable. Believing a market unbuyable is what kept corners
unvalidated for weeks, so the cost of being wrong runs both ways.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github/workflows/provider-capability-probe.yml"
SCRIPT = PROJECT_ROOT / "scripts/probe_provider_capabilities.py"


def test_the_probe_never_runs_on_a_schedule():
    """It spends quota and answers a question asked once. CLAUDE.md forbids
    enabling cron that nobody asked for."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text


def test_the_probe_cannot_write_anything():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "issues: write" not in text


def test_the_probe_writes_no_staging_and_creates_no_shadow_run():
    """A probe that disturbed the acceptance evidence window would make the
    answer cost more than the question."""
    script = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("overwrite-staging", "run_provider_shadow_verification", "to_csv", "write_text"):
        assert forbidden not in script, forbidden


def test_the_key_is_read_from_the_environment_and_never_printed():
    """The working key is a repository secret; GitHub never returns its value,
    which is why this runs in Actions rather than on a laptop."""
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'os.environ.get(KEY_ENV' in script
    assert "never printed" in script
    # No print of the key, and no interpolation of it into a logged URL.
    assert "print(key" not in script and "{key}" not in script


def test_it_probes_the_markets_this_project_could_not_validate():
    script = SCRIPT.read_text(encoding="utf-8")
    for market in ("btts", "draw_no_bet", "double_chance", "alternate_totals_corners"):
        assert market in script, market
