"""Error messages must say what to do, and must not cascade."""

from __future__ import annotations

import json
from pathlib import Path

from epl_betting_lab.reports.automated_card import build_automated_card
from epl_betting_lab.reports.scheduled_task_bridge import (
    BLOCKER_NEEDS_ODDS,
    BLOCKER_PROVIDER_NOT_TRUSTED,
    BLOCKER_REMEDIES,
    build_epl_card_task,
    build_epl_model_task,
)


def _write(outputs: Path, name: str, payload: dict) -> None:
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / name).write_text(json.dumps(payload), encoding="utf-8")


# --- cascading blockers ----------------------------------------------------


def test_no_evidence_reports_one_root_blocker_not_four(tmp_path: Path) -> None:
    """Four failing checks with one cause sends the reader chasing four
    problems. Downstream checks are skipped once a prerequisite failed."""
    summary = build_automated_card(output_dir=tmp_path)

    assert len(summary["blockers"]) == 1
    assert "No automated card input report found" in summary["blockers"][0]
    assert summary["skipped_checks"]


def test_the_root_blocker_names_the_command_to_run(tmp_path: Path) -> None:
    summary = build_automated_card(output_dir=tmp_path)

    assert "run_api_first_card_workflow.py" in summary["blockers"][0]


def test_skipped_checks_explain_why_they_were_not_run(tmp_path: Path) -> None:
    summary = build_automated_card(output_dir=tmp_path)

    assert any("not checked" in item for item in summary["skipped_checks"])


def test_next_action_leads_with_the_root_blocker(tmp_path: Path) -> None:
    """"Resolve the listed blockers" is not an instruction."""
    summary = build_automated_card(output_dir=tmp_path)

    assert summary["next_action"].startswith("Start here:")
    assert "Resolve the listed blockers" not in summary["next_action"]


def test_downstream_checks_still_run_when_the_prerequisite_is_present(
    tmp_path: Path,
) -> None:
    """Skipping must be conditional, not a way of hiding real failures."""
    _write(
        tmp_path,
        "automated_card_input.json",
        {"eligibility": {"eligible_markets": ["1x2"]}},
    )

    summary = build_automated_card(output_dir=tmp_path)

    assert summary["skipped_checks"] == []
    assert any("allowlisted" in item for item in summary["blockers"])


# --- remedies --------------------------------------------------------------


def test_every_named_blocker_has_a_remedy() -> None:
    """A terse label reads well in a status line and says nothing about the
    fix, so each one carries a remedy."""
    from epl_betting_lab.reports import scheduled_task_bridge as bridge

    named = {
        value
        for key, value in vars(bridge).items()
        if key.startswith("BLOCKER_") and isinstance(value, str)
    }

    assert named
    assert named <= set(BLOCKER_REMEDIES)


def test_card_next_action_includes_the_remedy(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "week1_launch_readiness.json",
        {"fixture_status": "Fresh (10)", "odds_completeness_percentage": 0.0,
         "missing_odds_count": 140, "slate_warnings": []},
    )

    summary = build_epl_card_task(output_dir=tmp_path)

    assert summary["blockers"]
    first = summary["blockers"][0]
    assert BLOCKER_REMEDIES[first].split(":")[0][:20] in summary["next_action"]


def test_model_next_action_includes_the_remedy(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "week1_launch_readiness.json",
        {"fixture_status": "Fresh (10)", "odds_completeness_percentage": 0.0,
         "missing_odds_count": 140, "slate_warnings": []},
    )

    summary = build_epl_model_task(output_dir=tmp_path)

    assert summary["blockers"]
    assert "Start with" in summary["next_action"]


def test_remedies_never_instruct_placing_a_bet_or_settling() -> None:
    joined = " ".join(BLOCKER_REMEDIES.values()).lower()

    assert "place a bet" not in joined
    assert "apply settlement" not in joined
