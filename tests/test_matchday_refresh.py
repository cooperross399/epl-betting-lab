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


#: The relay that carries the card to Cooper runs at 07:30 New York (11:30
#: UTC in summer) so he can read it at 08:00.
RELAY_UTC = 11.5

#: What GitHub's scheduler actually adds to a trigger on this repository.
#:
#: Measured, not assumed. On 2026-08-29 and 30 the 09:00 cron fired at 14:08
#: and 14:18, and the 10:30 cron at 15:08 and 14:56 — four for four, between
#: 4h26 and 5h18 late. The same crons ran 15 to 55 minutes late the week
#: before, so this is a change in GitHub's behaviour rather than a constant of
#: the schedule, and 5h30 is the observed worst case with a little room.
#:
#: Every deadline in this file is checked against nominal + this, because the
#: fix that preceded it was checked against nominal and shipped a schedule
#: that had already stopped working. If GitHub's delays shrink again, this may
#: come down — but only on evidence, and the early triggers cost little enough
#: that there is no hurry.
OBSERVED_LATENESS_H = 5.5

#: A 12:30 UK kick-off is 11:30 UTC in summer: the earliest of the week.
EARLIEST_KICK_OFF_UTC = 11.5
#: A 20:00 UK evening kick-off is 19:00 UTC; 20:00 UTC is the safe ceiling.
LATEST_KICK_OFF_UTC = 20.0
#: A run older than this is refused as stale, so a card has to be built within
#: this many hours of the kick-off it is meant to cover.
STALE_AFTER_H = 12.0

#: Thursday carries the planning card and has no matches of its own.
MATCH_DAYS = ("5", "6", "0", "1")


def _trigger_hours(day: str) -> list[float]:
    """Nominal UTC hours of every trigger on one cron weekday."""
    return sorted(
        int(line.split('"')[1].split()[1]) + int(line.split('"')[1].split()[0]) / 60
        for line in _workflow().splitlines()
        if "- cron:" in line and line.rstrip().endswith(f'* * {day}"')
    )


def test_every_matchday_beats_the_relay_even_when_github_runs_late() -> None:
    """A card built after the relay is a card he sees the following day.

    This is the failure the 5h30 constant exists for. Every trigger was legal
    at its nominal time all weekend and every one of them landed after the
    relay had already read the feed, so the 08:00 New York read got Saturday's
    card on Sunday and Sunday's on Monday. Nothing failed; the schedule was
    simply being graded on a clock GitHub had stopped keeping.

    Two per day, because one is not a schedule.
    """
    for day in ("4",) + MATCH_DAYS:
        readers = [
            at
            for at in _trigger_hours(day)
            if at + OBSERVED_LATENESS_H <= RELAY_UTC
        ]
        assert len(readers) >= 2, (
            f"day {day} has {len(readers)} trigger(s) that still beat the relay "
            f"at +{OBSERVED_LATENESS_H}h"
        )


def test_the_weekend_runs_land_before_the_earliest_kick_off() -> None:
    """A refresh that arrives after kick-off prices nobody can take."""
    for day in ("6", "0"):
        in_time = [
            at
            for at in _trigger_hours(day)
            if at + OBSERVED_LATENESS_H <= EARLIEST_KICK_OFF_UTC
        ]
        assert in_time, f"day {day} has no trigger landing before a 12:30 UK kick-off"


def test_every_matchday_stays_fresh_through_an_evening_kick_off() -> None:
    """The other end of the same rope, and the reason one trigger cannot do it.

    Beating the relay through a 5h30 delay needs a trigger at 06:00 UTC or
    earlier; surviving twelve hours to a 20:00 UTC kick-off needs one at 08:00
    UTC or later. Drop the late pair to satisfy the relay and every evening
    match reads a card that expired in the early afternoon — which is why the
    fix here was to add triggers rather than to move them.

    Freshness is measured at nominal, where a run is oldest at kick-off; a
    late start only makes the card fresher.
    """
    for day in MATCH_DAYS:
        covering = [
            at
            for at in _trigger_hours(day)
            if at + STALE_AFTER_H >= LATEST_KICK_OFF_UTC
            and at + OBSERVED_LATENESS_H <= LATEST_KICK_OFF_UTC
        ]
        assert covering, f"day {day} has no trigger still fresh at a 20:00 UTC kick-off"


def test_every_matchday_has_a_backup_trigger() -> None:
    """GitHub drops scheduled events under load, and dropped one the day this
    was written: 13:00 Thursday produced no run at all. A trigger that usually
    works is not a trigger a card can depend on."""
    text = _workflow()
    days = [
        line.split("* *", 1)[1].strip().strip('"')
        for line in text.splitlines()
        if "- cron:" in line
    ]

    for day in ("4", "5", "6", "0", "1"):
        assert days.count(day) >= 2, f"day {day} has no backup trigger"


def test_a_duplicate_run_cannot_collide_with_the_first() -> None:
    """Two triggers ninety minutes apart must serialise, not race."""
    text = _workflow()

    assert "group: matchday-refresh" in text
    assert "cancel-in-progress: false" in text


#: Measured, not estimated: two live runs moved the counter from 340 to 311.
MEASURED_REQUESTS_PER_RUN = 62  # measured from consecutive live runs

#: Each extra per-event market costs one request per fixture.
REQUESTS_PER_EXTRA_MARKET_PER_RUN = 10

#: The plan in use. Raised from 500 once the schedule needed to cover every
#: matchday and price every market; at 500 those two were mutually exclusive.
MONTHLY_REQUEST_ALLOWANCE = 20_000
#: 10:00 America/New_York in summer, the Thursday automation cutoff.
THURSDAY_CUTOFF_UTC = 14.0
#: Midnight America/New_York in summer: earlier is still Wednesday there.
NEW_YORK_MIDNIGHT_UTC = 4.0
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

    The work moved to the schedule and the card is published to a branch, so
    the routines read rather than execute. The property being protected is the
    same one: a routine must never hand a task back to Cooper.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    prompts = text.split("## Exact routine prompts", 1)[1]
    prompts = prompts.split("## Safe vs unsafe actions", 1)[0]

    assert prompts.count("card-feed") >= 2  # one per live routine
    for handoff in ("open a Terminal", "ask ChatGPT"):
        assert handoff in prompts
    # Nothing in a prompt may tell him to run a command.
    assert "PYTHONPATH=src" not in prompts
    assert "scripts/" not in prompts


def test_routine_prompts_carry_the_totals_history() -> None:
    """A routine must not re-run an investigation, nor repeat a stale answer.

    Totals were excluded on evidence that was correct about the market it
    examined and silent about another. Telling a routine only "settled, do not
    re-investigate" is what let that stand unchallenged; telling it only the
    new answer would invite the old investigation again. It gets both.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )

    assert "reopened" in text.lower()
    assert "alternate_totals" in text
    assert "bulk `totals`" in text


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


def test_the_workflow_takes_no_permission_it_does_not_use() -> None:
    """`contents: write` is here for the card feed and nothing else.

    It was `contents: read` until delivery moved off email: publishing the card
    to a branch needs write. The narrowing that keeps that honest is not in the
    permission — GitHub cannot scope it to one ref — but in
    `test_every_push_targets_the_card_feed_branch`, which pins every push in
    this file to `refs/heads/card-feed`.
    """
    text = _workflow()
    header = text.split("jobs:", 1)[0]

    assert "actions: read" in header
    assert "contents: write" in header
    # Still nothing that could approve, merge, or rewrite history.
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


def test_the_provider_report_is_uploaded_when_a_fetch_fails() -> None:
    """It is the only thing that says why a fetch was blocked.

    A run that could not fetch prices left no way to see the reason without
    editing the workflow and running it again — on a schedule that runs five
    times a week, that is a whole matchday lost to a round trip.
    """
    text = _workflow()

    assert "data/outputs/provider_shadow_verification.md" in text
    assert "data/outputs/staging_input_validation.md" in text


def test_the_stated_credit_cost_matches_the_schedule() -> None:
    """A cost written in a comment drifts away from the schedule beside it.

    The figure here was once four times too low, computed from a per-run cost
    that predated the extra markets — the sort of error that only matters when
    someone relies on it to decide the cadence is affordable.
    """
    text = _workflow()
    runs_per_week = text.count("- cron:")
    monthly = runs_per_week * WEEKS_PER_MONTH * MEASURED_REQUESTS_PER_RUN

    # The comment should state a figure within a reasonable distance of truth.
    assert "5,100 credits a month" in text
    assert 4_700 < monthly < 5_600, f"schedule now costs ~{monthly:.0f}"
    assert monthly < MONTHLY_REQUEST_ALLOWANCE


def _thursday_trigger_hours() -> list[float]:
    return _trigger_hours("4")


def test_thursday_triggers_precede_the_policy_cutoff() -> None:
    """The provider policy refuses a Thursday receipt after 10:00 New York.

    That is 14:00 UTC in summer. A Thursday trigger later than that is blocked
    by policy every week, and reports a provider fault rather than a scheduling
    one.

    Checked at the landing time, not the nominal one. 10:30 UTC was inside the
    window on paper and outside it in practice: at the delay GitHub actually
    runs it lands about 15:30, is refused every Thursday, and — firing last —
    replaces that morning's good card on the feed with a blocked one.
    """
    for at in _thursday_trigger_hours():
        landing = at + OBSERVED_LATENESS_H
        assert landing < THURSDAY_CUTOFF_UTC, (
            f"{at:.2f} UTC lands at {landing:.2f} UTC, past the cutoff"
        )


def test_thursday_triggers_start_on_thursday_in_new_york() -> None:
    """A trigger before 04:00 UTC is Wednesday evening in New York.

    Its receipt would not be a Thursday receipt, so the cutoff would never be
    evaluated at all. Buying slack that way skips the gate rather than beating
    it, which is not the trade this schedule is allowed to make.
    """
    for at in _thursday_trigger_hours():
        assert at >= NEW_YORK_MIDNIGHT_UTC, f"{at:.2f} UTC is Wednesday in New York"


def test_thursday_keeps_slack_for_a_late_cron() -> None:
    """Landing inside the window is not the same as surviving a delay.

    The triggers were legal on 2026-08-27 and still produced no card: GitHub
    started both about nine and a half hours late, so both receipts were
    stamped past the deadline. The earliest trigger therefore has to hold most
    of the window open behind it, and one trigger is not a schedule — a single
    dropped run would take the whole Thursday with it.
    """
    hours = _thursday_trigger_hours()

    assert len(hours) >= 3, "one late or dropped trigger must not cost the day"
    slack = THURSDAY_CUTOFF_UTC - hours[0]
    assert slack >= 9.0, f"earliest Thursday trigger has only {slack:.1f}h of slack"
    # Spread, not clustered: three triggers in one hour share one outage. Four
    # hours rather than six, because Thursday is fenced on both sides — nothing
    # before 04:00 UTC is a Thursday receipt in New York, and nothing landing
    # after 14:00 UTC is accepted — which leaves 04:00 to 08:30 UTC once the
    # observed delay is taken off the back. The whole window is the spread.
    assert hours[-1] - hours[0] >= 4.0, "triggers are bunched too closely together"


def test_the_card_routine_prompt_matches_how_leans_are_staked() -> None:
    """The prompt asked for lean unit sizes after leans stopped carrying one.

    A routine reading a stale prompt would ask the reader to act on a stake
    that is always zero, which is exactly the confusion the change was meant
    to end.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "carry no stake" in flat
    assert "information, not a bet" in flat


def test_the_routine_prompt_carries_the_honest_headline() -> None:
    """Asked whether it works, a routine should not guess."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "No market in this project has a demonstrated edge" in flat


def test_the_prompts_tell_a_card_apart_from_a_failure() -> None:
    """One publish can be either, and they read very differently."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "Selections changed" in flat
    assert "Something went wrong" in flat
    # The status file settles it before any table is read.
    assert "START with latest_status.json" in flat
    assert "degraded" in flat


def test_the_prompts_use_the_same_staleness_window_as_the_watchdog() -> None:
    """Four days, because the card runs ten times a week.

    An eight-day window would have called a missed weekend normal.
    """
    from epl_betting_lab.reports.schedule_health import MAX_EXPECTED_GAP

    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )

    assert MAX_EXPECTED_GAP.days == 4
    assert "four days" in " ".join(text.split())


def test_the_prompts_name_the_delivery_issue() -> None:
    """Searching by number is exact; searching by title is not."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )

    assert "#162" in text


def test_the_prompts_carry_the_longshot_cap() -> None:
    """So a routine can explain a missing big price instead of guessing."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "+600" in flat
    assert "0 for 12" in flat


def test_the_model_prompt_refuses_to_propose_market_scope_changes() -> None:
    """Scope changes are reviewed decisions behind the policy gate.

    Since 2026-08-21 all eight priced markets are enabled (PR #224), so the
    rule cuts both ways: a routine proposes neither enabling nor disabling,
    and it carries both the measurement evidence and the decision made
    against its recommendation.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "Do not propose enabling or disabling a market" in flat
    assert "recommended enabling nothing new" in flat
    assert "enabled all eight" in flat


def test_the_settle_routine_checks_the_schedule_is_alive() -> None:
    """It used to only look for failures, which a dead schedule never produces."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "a run was probably missed" in flat
    assert "may need enabling" in flat


def test_the_prompts_check_the_feed_is_todays() -> None:
    """The feed holds one card, so the risk is reading an old one as current.

    A routine run once reported yesterday's state as today's. The branch always
    answers, and it answers with whatever the last run left, so the date is the
    only thing that separates a fresh card from a stale one.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "State the `date` you are reading" in flat
    assert "a run did not finish" in flat
    assert "Never present a stale card's prices as current" in flat


def test_the_prompts_require_stating_what_was_read() -> None:
    """A stale answer should be visible as one."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "State the `date` you are reading" in flat
    assert "not today and today is a matchday" in flat


def test_a_degraded_publish_is_not_reported_as_no_card() -> None:
    """A degraded run still publishes whatever card it managed to build.

    Reading `degraded` as "there is nothing here" would throw away a real card
    on exactly the days something already went wrong.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "report whatever card was still built" in flat
    assert "may rest on stale prices" in flat


def test_the_prompts_know_about_manual_runs() -> None:
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "workflow_dispatch" in flat
    assert "started by hand" in flat
    # A manual run's card is real even though its trigger proves nothing.
    assert "the card itself is real" in flat


def test_the_card_routine_delivers_in_its_own_final_message() -> None:
    """The run's own message is the delivery; a push is a bonus on top.

    The first version made PushNotification the delivery. The routine surface
    has no such tool, so the run reported delivery as broken while its own
    message — the thing that actually appears in Claude — carried nothing.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "your final message IS the delivery" in flat
    assert "is not a failure" in flat


def test_the_card_routine_knows_where_the_files_actually_are() -> None:
    """The feed is an orphan branch, so a checkout of main does not hold it.

    The first live run had the repository attached and still found nothing:
    the prompt named two files that are not on the branch it had, so the run
    fell through to a web fetch and an unauthenticated clone that a private
    repo can only refuse. It read as an access problem and was a branch
    problem.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "`card-feed` IS AN ORPHAN BRANCH" in flat
    assert "git fetch origin card-feed" in flat
    assert "the card could not be READ" in flat


def test_a_refused_bundle_is_not_reported_as_a_failed_fetch() -> None:
    """The provider step exits non-zero for two different reasons.

    A run refused by the Thursday cutoff reported "prices could not be
    refreshed" while 330 rows of prices sat in the bundle. Deciding which
    happened means reading the reports, which is a script's job rather than a
    heredoc's — covered by tests/test_explain_provider_failure.py.
    """
    text = _workflow()

    assert "explain_provider_failure.py" in text
    assert ">> run_degraded.txt" in text


def test_the_prompts_judge_health_from_labelled_messages_only() -> None:
    """GitHub's failure mail carries no trigger label and no error text.

    Every failure this project has recorded was a manual dispatch, and two
    health checks in a row concluded the pipeline was broken by counting them.
    """
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert 'counting only commits whose `trigger` was "schedule"' in flat
    assert "not evidence" in flat


def test_the_prompts_say_what_only_manual_failures_mean() -> None:
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "Only manual failures" in flat
    assert "do not describe the pipeline as broken" in flat


def test_the_prompts_prefer_saying_they_cannot_tell() -> None:
    """Better than assuming a failure was scheduled."""
    text = (PROJECT_ROOT / "docs" / "epl_scheduled_tasks_bridge.md").read_text(
        encoding="utf-8"
    )
    flat = " ".join(text.split())

    assert "say you cannot tell rather than assuming" in flat


def test_the_props_step_cannot_cost_a_match_card() -> None:
    """The props refresh runs with continue-on-error and gates itself on the
    policy, so while props are held it spends nothing and when it breaks the
    match card still ships."""
    text = _workflow()

    assert "run_props_card_refresh.py" in text
    props_block = text.split("Refresh the props card", 1)[1].split("- name:", 1)[0]
    assert "continue-on-error: true" in props_block
    assert "EPL_ODDS_API_KEY" in props_block

# --- card-feed delivery ----------------------------------------------------


def _workflow_dir():
    return PROJECT_ROOT / ".github" / "workflows"


def test_only_the_matchday_refresh_can_write_to_the_repository() -> None:
    """`contents: write` is the one permission that can rewrite this repo.

    It exists so a run can publish the card to `card-feed`, and for nothing
    else. Any other workflow granting it would be able to move main without a
    pull request.
    """
    granted = [
        path.name
        for path in sorted(_workflow_dir().glob("*.yml"))
        if "contents: write" in path.read_text(encoding="utf-8")
    ]

    assert granted == ["matchday-refresh.yml"], granted


def test_every_push_targets_the_card_feed_branch() -> None:
    """The write permission is repository-wide; the discipline is not.

    Nothing here may push to main, to a tag, or to a branch named by a
    variable — the card feed is the only ref this workflow is allowed to move.
    """
    pushes = [
        line.strip()
        for line in _workflow().splitlines()
        if "git push" in line
    ]

    assert pushes, "the publish step should push"
    for line in pushes:
        assert line.endswith(':refs/heads/card-feed"'), line


def test_the_card_feed_publishes_on_every_run() -> None:
    """A missing commit for today has to mean the run did not finish.

    If publishing were conditional on a card existing, a degraded run would
    leave the feed looking exactly like a workflow that never ran, and the
    routine could not tell silence from failure.
    """
    text = _workflow()
    publish = text.index("Publish the card to the card-feed branch")
    following = text[publish : publish + 4000]

    assert "if: always()" in following
    assert "latest_card_comment.md" in following
    assert "latest_status.json" in following


def test_a_degraded_run_never_replaces_a_good_card_from_the_same_day() -> None:
    """The feed is two files and the last writer wins.

    A day's later triggers are the ones most likely to arrive after a deadline
    and be refused, and a refused run still reaches the publish step because it
    is `if: always()`. Without this guard, Thursday's 10:30 trigger landing past
    the 14:00 cutoff would replace that morning's good card with a blocked one,
    and the relay would carry the blocked one to the read.

    The guard is narrow on purpose: same day, previous card good, this run not
    good. A first-of-the-day failure still publishes, because then there is no
    good card to protect and the routine needs to see the blocker.
    """
    text = _workflow()
    publish = text.index("Publish the card to the card-feed branch")
    following = text[publish : publish + 6000]

    assert 'PREV_DAY" = "$DAY"' in following, "the guard must compare the same day"
    assert 'PREV_DEGRADED" = "false"' in following, "it must only protect a good card"
    assert 'DEGRADED" != "false"' in following, "a good run must still publish"
    # "unknown" must not read as healthy: it is the value when the health step
    # never ran, which is a run that cannot vouch for itself.
    assert "|| 'unknown' }}" in following


def test_a_first_failure_of_the_day_still_reaches_the_feed() -> None:
    """Silence has to keep meaning "the run did not finish".

    The guard may only skip when the branch already holds today's commit. If it
    could skip on an empty or older feed, a blocked run would leave the branch
    looking exactly like a workflow that never started, which is the one thing
    the feed exists to rule out.
    """
    text = _workflow()
    publish = text.index("Publish the card to the card-feed branch")
    following = text[publish : publish + 6000]
    guard = following[following.index("A good card outranks") :]
    skip = guard[: guard.index("exit 0")]

    assert '[ -n "$PARENT" ]' in skip, "no parent means nothing to protect"
    assert skip.count("exit 0") == 0


def test_the_card_comment_notifies_nobody() -> None:
    """Delivery is the feed now, so the comment must not reach an inbox.

    An @mention overrides an ignored subscription, so a mention left in the
    body would keep the emails arriving whatever the watch settings said.
    """
    from epl_betting_lab.reports.card_notification import NOTIFY_HANDLE

    assert NOTIFY_HANDLE == ""


def test_the_slate_is_refreshed_before_prices_are_fetched() -> None:
    """A stale slate makes every fetched price fall outside the window.

    Refreshing it afterwards would spend the provider quota first and only then
    discover there was no fixture to spend it on.
    """
    text = _workflow()

    assert text.index("Refresh the upcoming slate") < text.index("Refetch provider prices")


def test_team_xg_is_fetched_softly_before_prices_are_bought() -> None:
    """The 2.5 line is priced on xG ratings; a bad day at Understat must
    degrade the ratings to goals, not the card to nothing, and must not
    spend provider quota first."""
    text = _workflow()

    assert text.index("Fetch team xG") < text.index("Refetch provider prices")
    block = text.split("- name: Fetch team xG", 1)[1].split("- name:", 1)[0]
    assert "continue-on-error: true" in block
    assert "fetch_understat_xg.py" in block
    assert "secrets." not in block
    assert "Team xG could not be fetched" in text

