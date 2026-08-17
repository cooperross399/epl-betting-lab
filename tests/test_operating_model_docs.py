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
    assert "data availability, not profitability" in text
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


def test_routine_prompts_use_the_active_repo_path() -> None:
    text = _read("docs/epl_scheduled_tasks_bridge.md")

    assert ACTIVE_PATH in text


def test_card_routine_forbids_publishing_picks_when_blocked() -> None:
    text = _read("docs/epl_scheduled_tasks_bridge.md")

    assert "publish NO pick" in text


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
