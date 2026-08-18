"""The hands-off refresh must automate reporting and nothing beyond it."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.reports.run_summary import build_run_summary


NOW = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
KEY_SHAPED = "abcdef01" * 4


def _workflow() -> str:
    return (
        PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
    ).read_text(encoding="utf-8")


def _write(outputs: Path, name: str, payload: dict) -> None:
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / name).write_text(json.dumps(payload), encoding="utf-8")


# --- what the schedule may and may not do ----------------------------------


def test_the_refresh_is_scheduled() -> None:
    text = _workflow()

    assert "schedule:" in text
    assert "cron:" in text


def test_it_runs_twice_a_week_because_a_run_goes_stale_in_12_hours() -> None:
    """A single weekly run would produce a card already blocked when read."""
    text = _workflow()

    assert text.count("- cron:") == 2
    assert "12 hours as stale" in text


def test_the_schedule_never_places_a_bet_or_settles() -> None:
    text = _workflow().lower()

    assert "settle_bet_ledger" not in text
    assert "prefill_bet_ledger" not in text
    assert "--apply" not in text
    assert "--force" not in text


def test_the_schedule_never_touches_protected_manual_files() -> None:
    text = _workflow()

    assert "data/manual/" not in text


def test_the_schedule_cannot_allowlist_a_provider() -> None:
    text = _workflow()

    assert "staging_provider_policy" not in text
    assert "create_receipt_from_github_approval" not in text


def test_the_workflow_declares_its_scope_in_writing() -> None:
    text = _workflow()

    assert "does NOT place a bet" in text
    assert "recommendation" in text


def test_it_checks_the_credential_before_spending_quota() -> None:
    """A rotated key should fail legibly, not as a confusing provider error."""
    text = _workflow()

    assert text.index("check_provider_credential.py") < text.index(
        "run_provider_shadow_verification.py"
    )


def test_concurrent_runs_cannot_both_write_staging() -> None:
    text = _workflow()

    assert "concurrency:" in text
    assert "cancel-in-progress: false" in text


def test_a_dispatch_can_skip_the_refetch() -> None:
    """Rebuilding reports without spending quota has to stay possible."""
    text = _workflow()

    assert "skip_provider_fetch" in text


# --- the summary a person actually reads -----------------------------------


def test_summary_shows_the_card_when_one_was_produced(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "epl_card_task.json",
        {
            "card_ready": True,
            "included_markets": ["1x2", "btts"],
            "excluded_markets": ["total_2_5"],
            "manual_odds_entry_required": False,
            "best_bets": [
                {
                    "home_team": "Man City",
                    "away_team": "Bournemouth",
                    "market": "btts",
                    "selection": "no",
                    "american_odds": 146,
                    "book": "FanDuel",
                    "suggested_units": 0.25,
                }
            ],
            "leans": [],
        },
    )
    _write(tmp_path, "automated_card.json", {"card_generated": True})

    text = build_run_summary(output_dir=tmp_path, now=NOW)

    assert "Man City" in text
    assert "FanDuel" in text
    assert "Best bets" in text


def test_summary_calls_a_blocked_card_blocked(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "epl_card_task.json",
        {"card_ready": False, "blockers": ["Provider not trusted"]},
    )

    text = build_run_summary(output_dir=tmp_path, now=NOW)

    assert "No card was produced" in text
    assert "not a card with no value" in text
    assert "Provider not trusted" in text


def test_summary_states_no_bet_is_placed(tmp_path: Path) -> None:
    text = build_run_summary(output_dir=tmp_path, now=NOW)

    assert "no bet is ever placed" in text.lower()
    assert "preview-only" in text.lower()


def test_summary_carries_no_credential(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "provider_shadow_verification.json",
        {"verdict": "Shadow ready for review", "api_quota": {"requests_remaining": "340"}},
    )

    text = build_run_summary(output_dir=tmp_path, now=NOW)

    assert KEY_SHAPED not in text
    assert "apiKey" not in text


def test_summary_survives_missing_reports(tmp_path: Path) -> None:
    text = build_run_summary(output_dir=tmp_path, now=NOW)

    assert "EPL Betting Lab" in text


# --- routine prompts --------------------------------------------------------


def test_routine_prompts_do_the_work_rather_than_asking_cooper_to() -> None:
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )

    assert text.count("Do the whole sequence yourself") >= 2
    assert "Do not ask Cooper to run anything" in text


def test_routine_prompts_know_the_totals_question_is_settled() -> None:
    """Otherwise a routine re-investigates it every week."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )

    assert "Do not re-investigate" in text
