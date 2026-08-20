"""The operating model is load-bearing, so it is tested like code.

These docs replace chat history as project memory. If they drift from reality —
wrong repo path, wrong market scope, a resurrected manual-odds instruction — a
future session inherits a false picture and acts on it. That is a correctness
problem, not a documentation nicety.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from epl_betting_lab.config import PROJECT_ROOT


REQUIRED_DOCS = (
    "CLAUDE.md",
    "docs/claude_autonomy_operating_model.md",
    "docs/epl_scheduled_tasks_bridge.md",
    "docs/no_terminal_operations.md",
    "README.md",
)

ACTIVE_PATH = "/Users/cooperross/Projects/epl-betting-lab"


def _read(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


def _flat(relative: str) -> str:
    """Lowercased with newlines collapsed, so assertions test meaning rather
    than where a sentence happens to wrap."""
    return " ".join(_read(relative).split()).lower()


@pytest.mark.parametrize("relative", REQUIRED_DOCS)
def test_every_document_a_session_reads_first_exists(relative: str) -> None:
    assert (PROJECT_ROOT / relative).is_file(), relative


def test_claude_md_names_the_active_repo_path() -> None:
    text = _read("CLAUDE.md")

    assert ACTIVE_PATH in text
    assert "Downloads" in text  # named specifically so it is not reused


def test_claude_md_points_at_the_operating_model() -> None:
    text = _read("CLAUDE.md")

    assert "docs/claude_autonomy_operating_model.md" in text
    assert "docs/no_terminal_operations.md" in text


def test_the_reading_order_is_recorded_somewhere_a_session_will_see_it() -> None:
    text = _read("CLAUDE.md")

    assert "Read these first" in text


# --- the facts that must not drift ----------------------------------------


@pytest.mark.parametrize(
    "relative",
    ["CLAUDE.md", "docs/claude_autonomy_operating_model.md"],
)
def test_market_scope_is_recorded_as_1x2_and_btts_only(relative: str) -> None:
    text = _read(relative)

    assert "1x2" in text
    assert "btts" in text
    assert "total_2_5" in text


def test_totals_are_documented_as_excluded_for_availability() -> None:
    """Never as unprofitable: that would misrepresent why it is out."""
    text = _flat("docs/claude_autonomy_operating_model.md")

    assert "excluded" in text
    assert "availability, not profitability" in text
    assert "never describe an excluded market as unprofitable" in text


def test_settle_is_documented_as_preview_only() -> None:
    for relative in ("CLAUDE.md", "docs/claude_autonomy_operating_model.md"):
        assert "preview-only" in _read(relative).lower()


def test_manual_odds_entry_is_documented_as_not_required() -> None:
    text = _read("docs/claude_autonomy_operating_model.md")

    assert "manual odds entry" in text.lower()
    assert "not required" in text.lower()


def test_legacy_current_odds_is_marked_as_not_the_active_source() -> None:
    text = _read("docs/claude_autonomy_operating_model.md")

    assert "current_odds.csv" in text
    assert "legacy" in text.lower()


# --- the no-ChatGPT and no-Terminal rules ---------------------------------


def test_the_no_chatgpt_rule_is_written_down() -> None:
    text = _read("docs/claude_autonomy_operating_model.md")

    assert "No ChatGPT" in text
    assert "no-ChatGPT rule" in text or "No ChatGPT" in text


def test_a_hard_stop_is_documented_as_not_giving_up() -> None:
    """The rule that matters most: stopping early is a failure, not safety."""
    text = _read("docs/claude_autonomy_operating_model.md")

    assert "not permission to give up" in text.lower()
    assert "smallest possible Cooper action" in text


def test_hard_stops_are_enumerated() -> None:
    text = _read("docs/claude_autonomy_operating_model.md")

    for stop in (
        "placing a bet",
        "applying settlement",
        "bet_ledger.csv",
        "force merge",
        "weakening the secrets guard",
    ):
        assert stop in text, stop


def test_the_approval_flow_is_browser_based() -> None:
    text = _read("docs/no_terminal_operations.md")

    assert "APPROVED_FOR_ALLOWLIST_PR" in text
    assert "GitHub" in text


def test_credential_guidance_never_instructs_printing_the_key() -> None:
    text = _read("docs/no_terminal_operations.md")

    assert "never prints" in text.lower() or "never print" in text.lower()
    assert "quota" in text.lower()


# --- routine prompts -------------------------------------------------------


@pytest.mark.parametrize("routine", ["EPL Model", "EPL CARD", "EPL SETTLE"])
def test_each_routine_has_a_copy_paste_prompt(routine: str) -> None:
    text = _read("docs/epl_scheduled_tasks_bridge.md")

    assert routine in text


def test_routine_prompts_forbid_chatgpt_and_terminal() -> None:
    text = _read("docs/epl_scheduled_tasks_bridge.md")

    assert text.count("ChatGPT") >= 3  # one per routine prompt


def test_routine_prompts_do_not_depend_on_a_local_checkout() -> None:
    """They read email instead.

    The prompts used to run commands against a local path, which meant they
    silently could not run whenever the machine was off — the exact situation
    a scheduled routine exists for. The card is delivered by email now, so a
    routine works from anywhere with the laptop shut.
    """
    text = _read("docs/epl_scheduled_tasks_bridge.md")
    prompts = text.split("## Exact routine prompts", 1)[1]
    prompts = prompts.split("## Safe vs unsafe actions", 1)[0]

    assert ACTIVE_PATH not in prompts
    assert "PYTHONPATH=src" not in prompts
    assert "Search Gmail" in prompts


def test_card_routine_forbids_publishing_picks_when_blocked() -> None:
    """A blocked card means nothing was generated, never "no value found"."""
    text = _read("docs/epl_scheduled_tasks_bridge.md")

    assert 'It never means "no value found"' in text
    assert "is not a reason to suggest a bet" in text


def test_card_routine_forbids_inventing_anything() -> None:
    text = _read("docs/epl_scheduled_tasks_bridge.md")

    assert "Do not compute, adjust, or invent" in text


def test_card_routine_keeps_the_zero_unit_rule() -> None:
    """The rule survived the move from filesystem to email."""
    text = _read("docs/epl_scheduled_tasks_bridge.md")

    assert "zero-unit row is not a small bet" in text


def test_routines_explain_that_no_email_is_not_a_fault() -> None:
    """Silence is information here, and only safe if that is stated."""
    text = _read("docs/epl_scheduled_tasks_bridge.md")

    assert "selections have not changed" in text
    assert "failure email" in text or "failure notification" in text


# --- CI ---------------------------------------------------------------------


def _workflow(name: str) -> str:
    return (PROJECT_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_a_workflow_runs_the_full_suite_on_pull_requests() -> None:
    """Otherwise "CI is green" means only that the policy gate passed."""
    text = _workflow("tests.yml")

    assert "pull_request" in text
    assert "pytest" in text


def test_the_test_workflow_uses_no_secret() -> None:
    text = _workflow("tests.yml")

    assert "secrets." not in text


def test_the_test_workflow_is_not_scheduled() -> None:
    text = _workflow("tests.yml")

    assert "schedule:" not in text


def test_the_credential_workflow_stays_dispatch_only() -> None:
    text = _workflow("provider-credential-check.yml")

    assert "workflow_dispatch" in text
    assert "schedule:" not in text


# --- newly built tooling must be discoverable ------------------------------


def test_the_status_page_is_documented() -> None:
    """Tooling a future session cannot find may as well not exist."""
    assert "status.html" in _read("docs/no_terminal_operations.md")
    assert "status.html" in _read("docs/claude_autonomy_operating_model.md")


def test_the_one_command_refresh_is_documented() -> None:
    text = _read("docs/claude_autonomy_operating_model.md")

    assert "refresh_all_reports.py" in text
    assert "dependency-ordered" in text.lower() or "dependency order" in text.lower()


def test_refreshing_and_refetching_are_documented_as_separate() -> None:
    """Conflating them is how someone spends quota expecting a redraw."""
    text = _flat("docs/claude_autonomy_operating_model.md")

    assert "separate, deliberate action" in text
    assert "spends no quota" in text


def test_the_card_comparison_report_is_documented() -> None:
    assert "automated_card_comparison" in _read(
        "docs/claude_autonomy_operating_model.md"
    )


def test_the_per_book_clv_report_is_documented() -> None:
    assert "clv_by_book" in _read("docs/claude_autonomy_operating_model.md")


def test_the_readme_separates_the_current_workflow_from_the_legacy_one() -> None:
    """Most of the README documents the manual-odds era.

    A session reading top-to-bottom would otherwise take a superseded flow for
    the current one and reintroduce manual odds entry.
    """
    text = _read("README.md")

    assert "## Current workflow" in text
    assert "## Legacy sections below" in text
    assert "refresh_all_reports.py" in text
    # Flattened: the phrase wraps across lines in the rendered document.
    assert "no longer the active source" in _flat("README.md")


def test_the_readme_never_tells_anyone_to_cd_into_the_dead_path() -> None:
    """The banner says Downloads is dead; a `cd` into it nine lines later is a
    trap, and the newer instruction is the one people scroll past."""
    text = _read("README.md")

    assert "cd ~/Downloads/epl-betting-lab" not in text
    assert "cd ~/Projects/epl-betting-lab" in text


def test_the_pr_workflow_compiles_every_module() -> None:
    """A module can be invalid on the CI Python and still pass the suite if no
    test imports it, which is how weekly_card.py stayed broken for a month."""
    text = (
        PROJECT_ROOT / ".github" / "workflows" / "tests.yml"
    ).read_text(encoding="utf-8")

    assert "compileall" in text


def test_the_totals_decision_is_recorded_as_settled() -> None:
    """Coverage numbers alone would invite a future session to re-investigate
    and reach a different answer. The reason it is settled has to be written
    down, not inferred from "8 of 10"."""
    text = _flat("docs/claude_autonomy_operating_model.md")

    assert "settled" in text
    assert "no account at any of them" in text
    assert "availability, not profitability" in text


def test_the_standing_note_travels_with_the_data() -> None:
    """A report should explain itself without anyone finding the docs.

    The note now records a reversal rather than the original exclusion, so it
    has to carry both halves: what was concluded, and why that conclusion did
    not survive. A note saying only the new answer would leave the next reader
    wondering whether the old reasoning had been considered.
    """
    from epl_betting_lab.market_eligibility import MARKET_EXCLUSION_NOTES

    note = MARKET_EXCLUSION_NOTES["total_2_5"]

    assert "William Hill" in note
    assert "bulk `totals`" in note
    assert "alternate_totals" in note
    assert "BetRivers" in note or "FanDuel" in note


def test_an_excluded_market_reason_carries_the_standing_note() -> None:
    import pandas as pd

    from epl_betting_lab.market_eligibility import evaluate_market_eligibility

    fixtures = pd.DataFrame(
        [{"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"}]
    )
    report = evaluate_market_eligibility(
        pd.DataFrame(columns=["date", "home_team", "away_team", "market", "selection"]),
        fixtures,
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )

    totals = next(m for m in report.markets if m.market == "total_2_5")
    assert "William Hill" in totals.reason


def test_an_eligible_market_does_not_carry_an_exclusion_note() -> None:
    """The note explains an exclusion; attaching it to an included market would
    contradict the report."""
    import pandas as pd

    from epl_betting_lab.market_eligibility import evaluate_market_eligibility

    fixtures = pd.DataFrame(
        [{"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"}]
    )
    odds = pd.DataFrame(
        [
            {
                "date": "2026-08-21",
                "home_team": "Arsenal",
                "away_team": "Coventry",
                "market": "total_2_5",
                "selection": side,
                "american_odds": "-110",
                "book": "BookA",
            }
            for side in ("over", "under")
        ]
    )
    report = evaluate_market_eligibility(
        odds,
        fixtures,
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )

    totals = next(m for m in report.markets if m.market == "total_2_5")
    assert totals.status == "eligible"
    assert "William Hill" not in totals.reason
