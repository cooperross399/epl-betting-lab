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


def test_every_matchday_has_a_run() -> None:
    """A run older than 12 hours is refused as stale.

    Friday's run expires at 01:00 UTC Saturday, and a typical matchweek puts
    six matches on Saturday, three on Sunday and one on Monday — all after
    that. Covering only Thursday would mean nine of eleven matches read from an
    already-stale card.
    """
    text = _workflow()
    days = {
        line.split("* *", 1)[1].strip().strip('"')
        for line in text.splitlines()
        if "- cron:" in line
    }

    assert days == {"4", "5", "6", "0", "1"}


def test_the_weekend_runs_land_before_the_earliest_kick_off() -> None:
    """A 12:30 UK kick-off is 11:30 UTC in summer; 13:00 would be too late."""
    text = _workflow()
    weekend = [
        line
        for line in text.splitlines()
        if "- cron:" in line and line.rstrip().endswith(('* * 6"', '* * 0"'))
    ]

    assert len(weekend) == 2
    for line in weekend:
        hour = int(line.split('"')[1].split()[1])
        assert hour <= 9, f"{hour}:00 UTC is too late for a 12:30 UK kick-off"


#: Measured, not estimated: two live runs moved the counter from 340 to 311.
MEASURED_REQUESTS_PER_RUN = 15

#: Each extra per-event market costs one request per fixture.
REQUESTS_PER_EXTRA_MARKET_PER_RUN = 10

#: The plan in use. Raised from 500 once the schedule needed to cover every
#: matchday and price every market; at 500 those two were mutually exclusive.
MONTHLY_REQUEST_ALLOWANCE = 20_000
WEEKS_PER_MONTH = 4.35


def test_the_cadence_stays_inside_the_request_allowance() -> None:
    """One run a week is ~65 requests a month against a 500 allowance."""
    text = _workflow()
    runs_per_week = text.count("- cron:")

    monthly = runs_per_week * WEEKS_PER_MONTH * MEASURED_REQUESTS_PER_RUN
    assert monthly < MONTHLY_REQUEST_ALLOWANCE


def test_the_cadence_leaves_room_for_manual_dispatches() -> None:
    """A schedule that exactly fills the allowance cannot be run by hand."""
    text = _workflow()
    runs_per_week = text.count("- cron:")

    monthly = runs_per_week * WEEKS_PER_MONTH * MEASURED_REQUESTS_PER_RUN
    spare_runs = (MONTHLY_REQUEST_ALLOWANCE - monthly) / MEASURED_REQUESTS_PER_RUN
    assert spare_runs >= 5


def test_the_allowance_covers_every_market_the_project_knows() -> None:
    """The point of running weekly: modelling, not credits, is the limit.

    If this ever fails, a market was added that the schedule cannot afford to
    price — which would show up as a market quietly missing from the card
    rather than as an error.
    """
    from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

    text = _workflow()
    runs_per_month = text.count("- cron:") * WEEKS_PER_MONTH
    # 1x2 and totals arrive together in one bulk call; the rest are per-event.
    extra_markets = len(MARKET_SELECTIONS) - 2
    monthly = runs_per_month * (
        MEASURED_REQUESTS_PER_RUN
        + extra_markets * REQUESTS_PER_EXTRA_MARKET_PER_RUN
    )

    assert monthly < MONTHLY_REQUEST_ALLOWANCE, (
        f"{len(MARKET_SELECTIONS)} markets would cost ~{monthly:.0f} credits a "
        f"month against {MONTHLY_REQUEST_ALLOWANCE}"
    )


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
    """They no longer ask him to run anything because they no longer run anything.

    The work moved to the schedule and the card arrives by email, so the
    routines read rather than execute. The property being protected is the same
    one: a routine must never hand a task back to Cooper.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    prompts = text.split("## Exact routine prompts", 1)[1]
    prompts = prompts.split("## Safe vs unsafe actions", 1)[0]

    assert prompts.count("Search Gmail") >= 3  # one per routine
    for handoff in ("open a Terminal", "ask ChatGPT"):
        assert handoff in prompts
    # Nothing in a prompt may tell him to run a command.
    assert "PYTHONPATH=src" not in prompts
    assert "scripts/" not in prompts


def test_routine_prompts_know_the_totals_question_is_settled() -> None:
    """Otherwise a routine re-investigates it every week."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )

    assert "Do not re-investigate" in text


# --- memory across runs ----------------------------------------------------
#
# A runner starts empty every time and the card archive is not tracked in git,
# so without an explicit restore the "since the previous refresh" diff is
# permanently blank and the Friday card can never say what moved since
# Thursday. The first CI run proved exactly that.


def test_the_previous_state_is_restored() -> None:
    text = _workflow()

    assert "Restore the previous state" in text
    assert "matchday-state" in text


def test_the_restore_reads_the_previous_successful_run() -> None:
    text = _workflow()

    assert "--status success" in text
    assert "gh run download" in text


def test_a_missing_state_does_not_fail_the_run() -> None:
    """First run, pruned artifact, or API hiccup must not lose the card."""
    text = _workflow()
    restore = text.split("Restore the previous state", 1)[1]
    restore = restore.split("- name:", 1)[0]

    assert "continue-on-error: true" in restore


def test_the_restore_never_touches_prices_or_protected_files() -> None:
    """It runs before the fetch, so it must not be able to clobber it."""
    text = _workflow()
    restore = text.split("Restore the previous state", 1)[1]
    restore = restore.split("- name:", 1)[0]

    assert "--dir data" in restore
    assert "data/staging" not in restore
    assert "data/manual" not in restore


def test_the_state_is_carried_forward_for_the_next_run() -> None:
    """Both halves: the card archive for the diff, the dataset as a fallback."""
    text = _workflow()

    assert "Upload the state for the next run" in text
    assert "data/outputs/archive/automated_cards" in text
    assert "data/processed/epl_historical_matches.csv" in text


def test_the_archive_outlives_the_reports() -> None:
    """It is the only link between one matchweek and the next."""
    text = _workflow()

    assert "retention-days: 90" in text


def test_reading_actions_is_the_only_permission_added() -> None:
    text = _workflow()
    header = text.split("jobs:", 1)[0]

    assert "actions: read" in header
    assert "contents: read" in header
    # Nothing in this workflow may write to the repository.
    assert "contents: write" not in header
    assert "actions: write" not in header
    assert "pull-requests: write" not in header


# --- a blocked run must say what to do -------------------------------------


def test_a_blocked_summary_leads_with_the_root_cause(tmp_path: Path) -> None:
    """The routine feeds carry terse labels that name no fix."""
    _write(
        tmp_path,
        "epl_card_task.json",
        {"card_ready": False, "blockers": ["Needs odds", "Provider not trusted"]},
    )
    _write(
        tmp_path,
        "automated_card.json",
        {
            "card_generated": False,
            "root_blocker": "No market is eligible. See data/outputs/x.md.",
            "blockers": [
                "No market is eligible. See data/outputs/x.md.",
                "Provider is not allowlisted.",
            ],
            "next_action": "Start here: No market is eligible. See data/outputs/x.md.",
        },
    )

    summary = build_run_summary(output_dir=tmp_path, now=NOW)

    assert "**Start here:** No market is eligible. See data/outputs/x.md." in summary
    # The terse label must not be what the reader is left with.
    assert "- Needs odds" not in summary


def test_a_blocked_summary_counts_the_blockers_that_may_clear(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "epl_card_task.json", {"card_ready": False})
    _write(
        tmp_path,
        "automated_card.json",
        {
            "card_generated": False,
            "root_blocker": "Root cause.",
            "blockers": ["Root cause.", "Consequence one.", "Consequence two."],
        },
    )

    summary = build_run_summary(output_dir=tmp_path, now=NOW)

    assert "2 further blocker(s) may clear once that is resolved" in summary
    assert "- Consequence one." in summary
    # The root cause must not be repeated in the consequence list.
    assert summary.count("Root cause.") == 1


def test_terse_blockers_are_still_shown_when_there_is_no_better_source(
    tmp_path: Path,
) -> None:
    """Falling back is better than showing nothing."""
    _write(
        tmp_path,
        "epl_card_task.json",
        {"card_ready": False, "blockers": ["Needs odds"]},
    )

    summary = build_run_summary(output_dir=tmp_path, now=NOW)

    assert "- Needs odds" in summary


# --- the model needs data the runner does not have -------------------------


def test_historical_results_are_fetched_before_the_card_is_built() -> None:
    """The first live CI run failed here: no dataset, so no card, ever."""
    text = _workflow()

    assert "scripts/fetch_data.py" in text
    assert text.index("fetch_data.py") < text.index("refresh_all_reports.py")


def test_results_are_fetched_before_any_quota_is_spent() -> None:
    """If the free source is down, stop before paying the odds provider."""
    text = _workflow()

    assert text.index("fetch_data.py") < text.index(
        "run_provider_shadow_verification.py"
    )


def test_fetching_results_needs_no_secret() -> None:
    text = _workflow()
    step = text.split("Fetch historical results", 1)[1].split("- name:", 1)[0]

    assert "secrets." not in step


# --- a bad run must never be a quiet run -----------------------------------
#
# The reader is asked to treat no-email as "nothing moved". That is only safe
# if everything that can go wrong breaks the silence. These pin the chain that
# makes it true.


def test_the_external_fetches_cannot_abort_the_run() -> None:
    """Both sources are outside this repo and will have bad days."""
    text = _workflow()
    for step in ("Fetch historical results", "Refetch provider prices"):
        block = text.split(f"- name: {step}", 1)[1].split("- name:", 1)[0]
        assert "continue-on-error: true" in block, step


def test_the_credential_check_stays_hard() -> None:
    """Without a key there is no refresh to degrade to."""
    text = _workflow()
    block = text.split("- name: Check the provider credential", 1)[1]
    block = block.split("- name:", 1)[0]

    assert "continue-on-error" not in block


def test_a_degraded_run_is_recorded_in_one_place() -> None:
    """The summary, the email, and the exit status must not disagree."""
    text = _workflow()

    assert "Record what went wrong" in text
    assert "run_degraded.txt" in text


def test_the_summary_and_the_email_both_read_that_record() -> None:
    text = _workflow()

    assert text.count("--degraded-file run_degraded.txt") >= 2


def test_a_missing_dataset_is_named_as_the_reason_no_card_exists() -> None:
    text = _workflow()

    assert "No match dataset" in text


def test_the_run_still_finishes_red_when_degraded() -> None:
    """Degrading must not quietly turn a failure into a green tick."""
    text = _workflow()
    block = text.split("- name: Report the outcome", 1)[1]

    assert "exit 1" in block
    assert "::error::" in block


def test_only_the_final_step_can_fail_the_job() -> None:
    """Anything failing earlier would skip the card, summary, and email."""
    text = _workflow()
    before_final = text.split("- name: Report the outcome", 1)[0]
    rebuild = before_final.split("- name: Rebuild every report", 1)[1]
    rebuild = rebuild.split("- name:", 1)[0]

    assert "continue-on-error: true" in rebuild


def test_the_card_is_built_and_sent_even_after_a_failure() -> None:
    text = _workflow()
    for step in ("Rebuild every report", "Write the card to the run summary",
                 "Email the card", "Upload reports"):
        block = text.split(f"- name: {step}", 1)[1].split("- name:", 1)[0]
        assert "if: always()" in block, step
