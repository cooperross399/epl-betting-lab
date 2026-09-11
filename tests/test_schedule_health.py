"""Noticing when a scheduled run did not happen.

The delivery design asks the reader to treat silence as "it ran and nothing
moved". A schedule that never fires produces no run, no summary, no email and
no red tick — indistinguishable from a quiet week, and the one failure that
design cannot otherwise see.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.reports.schedule_health import (
    LATENESS_ALLOWANCE,
    MAX_EXPECTED_GAP,
    degraded_streak_report,
    gap_report,
    most_recent,
    parse_run_time,
)


NOW = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)


def _ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


class TestGapReport:
    def test_a_normal_gap_is_not_flagged(self) -> None:
        stale, _ = gap_report(_ago(24), now=NOW)
        assert stale is False

    def test_the_widest_planned_gap_is_not_flagged(self) -> None:
        """Monday to Thursday is three days and is entirely normal."""
        stale, _ = gap_report(_ago(72), now=NOW)
        assert stale is False

    def test_ordinary_lateness_is_not_flagged(self) -> None:
        """GitHub starts scheduled runs late; twenty minutes is unremarkable
        and an hour is documented. Crying wolf would train the reader to ignore
        the one message that matters."""
        stale, _ = gap_report(_ago(72 + 5), now=NOW)
        assert stale is False

    def test_a_missed_run_is_flagged(self) -> None:
        stale, message = gap_report(_ago(24 * 7), now=NOW)

        assert stale is True
        assert "did not happen" in message

    def test_the_message_says_how_long_it_has_been(self) -> None:
        _, message = gap_report(_ago(168), now=NOW)
        assert "168 hours" in message

    def test_it_says_what_to_check(self) -> None:
        """A warning with no next step is only an interruption."""
        _, message = gap_report(_ago(240), now=NOW)
        assert "still enabled" in message

    def test_a_first_run_is_not_a_missed_run(self) -> None:
        stale, message = gap_report(None, now=NOW)

        assert stale is False
        assert "baseline" in message

    def test_an_on_time_run_still_reports_the_gap(self) -> None:
        """How the reader learns the check exists at all."""
        _, message = gap_report(_ago(24), now=NOW)
        assert "expected" in message

    def test_a_naive_timestamp_is_treated_as_utc(self) -> None:
        naive = (NOW - timedelta(hours=24)).replace(tzinfo=None)
        stale, _ = gap_report(naive, now=NOW)
        assert stale is False

    def test_the_threshold_allows_for_lateness(self) -> None:
        assert LATENESS_ALLOWANCE > timedelta(hours=1)
        assert MAX_EXPECTED_GAP >= timedelta(days=3)


class TestParsing:
    def test_it_reads_a_github_timestamp(self) -> None:
        parsed = parse_run_time("2026-08-20T13:12:57Z")
        assert parsed is not None and parsed.year == 2026

    def test_an_unreadable_timestamp_is_ignored(self) -> None:
        assert parse_run_time("not a time") is None

    def test_an_empty_string_is_ignored(self) -> None:
        assert parse_run_time("") is None

    def test_the_latest_of_several_is_used(self) -> None:
        latest = most_recent(
            ["2026-08-18T13:00:00Z", "2026-08-20T13:00:00Z", "2026-08-19T13:00:00Z"]
        )
        assert latest is not None and latest.day == 20

    def test_unreadable_entries_do_not_hide_a_good_one(self) -> None:
        latest = most_recent(["rubbish", "2026-08-20T13:00:00Z"])
        assert latest is not None and latest.day == 20

    def test_nothing_readable_means_no_previous_run(self) -> None:
        assert most_recent(["rubbish", ""]) is None


class TestTheTwoWatchesAreIndependent:
    """One check cannot catch its own total absence."""

    def _workflow(self, name: str) -> str:
        return (PROJECT_ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )

    def test_the_matchday_run_measures_its_own_gap(self) -> None:
        text = self._workflow("matchday-refresh.yml")

        assert "Check the schedule has not gone quiet" in text
        assert "check_schedule_health.py" in text

    def test_a_missed_run_degrades_the_matchday_run(self) -> None:
        """A degraded run always emails, so the news travels."""
        text = self._workflow("matchday-refresh.yml")

        assert "--append-to run_degraded.txt" in text

    def test_the_health_check_does_not_clear_the_degradation_record(self) -> None:
        """It writes the file the recorder then appends to."""
        text = self._workflow("matchday-refresh.yml")
        recorder = text.split("Record what went wrong", 1)[1].split("- name:", 1)[0]

        assert "touch run_degraded.txt" in recorder
        assert ": > run_degraded.txt" not in recorder

    def test_an_unrelated_schedule_watches_the_matchday_one(self) -> None:
        text = self._workflow("weekly-lab-check.yml")

        assert "Watch that the matchday schedule is still running" in text
        assert "--fail-when-stale" in text

    def test_the_watchdog_runs_on_its_own_cron(self) -> None:
        """Sharing a schedule would share the failure."""
        text = self._workflow("weekly-lab-check.yml")

        assert "schedule:" in text
        assert "cron:" in text

    def test_the_watchdog_may_only_read(self) -> None:
        text = self._workflow("weekly-lab-check.yml")
        header = text.split("jobs:", 1)[0]

        assert "actions: read" in header
        assert "contents: write" not in header


class TestDidItRunIsNotDidItSucceed:
    """The two questions were conflated, and it latched.

    Both watchdogs measured the gap to the last *successful* matchday run. Every
    matchday run is red by design while Football-Data is down, so from
    2026-09-09 the check saw no run at all and printed "at least one run did not
    happen. Check that the workflow is still enabled" at the top of every card,
    while 19 of 19 crons had fired.

    It could not recover on its own either: that sentence alone made the run
    degraded, a degraded run exits non-zero, and a non-zero run is not a
    success. The gap could never close, even after the upstream feed came back.
    """

    def _workflow(self, name: str) -> str:
        return (PROJECT_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "workflow", ["matchday-refresh.yml", "weekly-lab-check.yml"]
    )
    def test_no_schedule_check_filters_the_run_list_to_successes(self, workflow: str) -> None:
        text = self._workflow(workflow)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # the note explaining why, which must survive
            assert "--status success" not in stripped, (
                f"{workflow}: asking 'did the cron fire' with the answer to "
                "'did the run succeed' makes a data outage look like a "
                "scheduler outage, and latches"
            )

    def test_the_state_restore_does_not_require_a_green_run(self) -> None:
        """The card archive is not in git, so the restore chain IS the
        out-of-sample ledger. Pinned to green runs it froze on 2026-09-05 for
        nine runs, and the card of 2026-09-07 — 8 staked selections — sat in an
        artifact the restore could not reach."""
        text = self._workflow("matchday-refresh.yml")
        block = text.split("- name: Restore the previous state", 1)[1].split("- name:", 1)[0]
        assert "--status success" not in block
        assert "gh run download" in block


class TestADegradedStreakIsItsOwnAlarm:
    """The condition the success filter was watching by accident, asked on
    purpose. On 2026-09-06 the refresh began failing and produced eight blocked
    cards over two days; nothing escalated, because each run reported its own
    fault and no one thing counted them."""

    def test_a_long_run_of_failures_is_reported(self) -> None:
        streaking, sentence = degraded_streak_report(["failure"] * 9)
        assert streaking
        assert "9 consecutive runs" in sentence

    def test_a_single_bad_day_is_not(self) -> None:
        streaking, _ = degraded_streak_report(["failure", "failure", "success"])
        assert not streaking

    def test_a_success_breaks_the_streak(self) -> None:
        streaking, _ = degraded_streak_report(["success"] + ["failure"] * 20)
        assert not streaking

    def test_an_in_flight_run_is_skipped_not_counted(self) -> None:
        """A run with no conclusion has not finished failing. Counting it as a
        failure would fire the alarm one run early; counting it as a success
        would silence a real streak."""
        streaking, _ = degraded_streak_report([None] + ["failure"] * 4)
        assert streaking
        streaking, _ = degraded_streak_report([None, "success"] + ["failure"] * 9)
        assert not streaking

    def test_a_cancelled_run_did_not_succeed(self) -> None:
        streaking, _ = degraded_streak_report(["cancelled"] * 5)
        assert streaking

    def test_no_runs_at_all_is_not_a_streak(self) -> None:
        """That is the gap check's question, and answering it here too would
        put the same sentence in the card twice."""
        streaking, _ = degraded_streak_report([])
        assert not streaking
