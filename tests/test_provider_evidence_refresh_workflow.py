"""The evidence refresh fetches and reports, and does nothing beyond that."""

from __future__ import annotations

from epl_betting_lab.config import PROJECT_ROOT


def _workflow() -> str:
    return (
        PROJECT_ROOT / ".github" / "workflows" / "provider-evidence-refresh.yml"
    ).read_text(encoding="utf-8")


def test_it_runs_only_when_a_human_dispatches_it() -> None:
    text = _workflow()

    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "cron:" not in text


def test_it_produces_evidence_and_nothing_downstream_of_it() -> None:
    """No card, no email, no issue comment, no settlement, no state upload.

    The matchday refresh owns all of those. This workflow exists only so an
    allowlist PR can carry evidence fetched with the repository credential,
    and evidence must never arrive with side effects attached.
    """
    text = _workflow()

    assert "run_provider_shadow_verification.py" in text
    assert "run_api_first_card_workflow.py" in text
    assert "run_automated_card" not in text
    assert "post_card_to_issue" not in text
    assert "gh issue" not in text
    assert "matchday-state" not in text
    assert "settle" not in text.lower()


def test_it_cannot_write_back_to_the_repository() -> None:
    text = _workflow()

    assert "contents: read" in text
    assert "persist-credentials: false" in text
    assert "git push" not in text
