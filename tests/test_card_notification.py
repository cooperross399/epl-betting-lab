"""Deciding when a card is worth an email.

Five emails a week would train the reader to ignore them, and an alert nobody
opens is worse than no alert because it still looks like coverage. So the rule
is narrow: the selections changed. It has to be exactly right, because the
reader is being asked to treat silence as information.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from epl_betting_lab.reports.card_notification import (
    ISSUE_TITLE,
    build_notification,
    decide,
)


NOW = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)


def _pick(**over: object) -> dict[str, object]:
    row = {
        "home_team": "Arsenal",
        "away_team": "Coventry",
        "market": "1x2",
        "selection": "home",
        "confidence_tier": "B",
        "calibrated_edge": 0.05,
        "american_odds": 146.0,
        "book": "FanDuel",
        "suggested_units": 0.25,
    }
    row.update(over)
    return row


def _comparison(**over: object) -> dict[str, object]:
    payload = {
        "comparable": True,
        "added": [],
        "removed": [],
        "moved_section": [],
        "price_changed": [],
        "unchanged_count": 8,
    }
    payload.update(over)
    return payload


class TestWhenToSend:
    def test_a_new_selection_sends(self) -> None:
        post, reason = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(added=[{"label": "x"}]),
        )
        assert post is True
        assert "1 added" in reason

    def test_a_dropped_selection_sends(self) -> None:
        post, reason = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(removed=[{"label": "x"}]),
        )
        assert post is True
        assert "1 dropped" in reason

    def test_a_selection_moving_section_sends(self) -> None:
        """Best bet to lean is a change of advice, not a change of price."""
        post, _ = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(moved_section=[{"label": "x"}]),
        )
        assert post is True

    def test_a_price_move_alone_stays_quiet_once_today_is_covered(self) -> None:
        post, reason = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(price_changed=[{"label": "x"}, {"label": "y"}]),
            last_sent=NOW - timedelta(hours=2),
            now=NOW,
        )
        assert post is False
        assert "2 price move(s)" in reason

    def test_an_identical_card_stays_quiet_once_today_is_covered(self) -> None:
        post, _ = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(),
            last_sent=NOW - timedelta(hours=2),
            now=NOW,
        )
        assert post is False

    def test_the_first_ever_card_sends(self) -> None:
        post, reason = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison={"comparable": False},
        )
        assert post is True
        assert "nothing to compare" in reason

    def test_losing_a_card_sends(self) -> None:
        """A card that existed and now does not is worth knowing about."""
        post, reason = decide(
            card={"card_ready": False},
            generated={"card_generated": False},
            comparison=_comparison(removed=[{"label": "x"}]),
        )
        assert post is True
        assert "blocked" in reason

    def test_staying_blocked_stays_quiet(self) -> None:
        """Otherwise a broken week emails five times saying the same thing."""
        post, reason = decide(
            card={"card_ready": False},
            generated={"card_generated": False},
            comparison=_comparison(),
            last_sent=NOW - timedelta(hours=2),
            now=NOW,
        )
        assert post is False
        assert "nothing new" in reason

    def test_a_card_ready_flag_without_generation_is_not_a_card(self) -> None:
        post, _ = decide(
            card={"card_ready": True},
            generated={"card_generated": False},
            comparison=_comparison(),
            last_sent=NOW - timedelta(hours=2),
            now=NOW,
        )
        assert post is False


def _write(tmp_path: Path, *, ready: bool, comparison: dict) -> None:
    (tmp_path / "epl_card_task.json").write_text(
        json.dumps(
            {
                "card_ready": ready,
                "included_markets": ["1x2", "btts"],
                "excluded_markets": ["total_2_5"],
                "best_bets": [_pick()] if ready else [],
                "leans": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "automated_card.json").write_text(
        json.dumps({"card_generated": ready, "root_blocker": "" if ready else "No odds."}),
        encoding="utf-8",
    )
    (tmp_path / "automated_card_comparison.json").write_text(
        json.dumps(comparison), encoding="utf-8"
    )


class TestTheMessage:
    def test_it_carries_the_picks(self, tmp_path: Path) -> None:
        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "Arsenal v Coventry" in body
        assert "+146" in body

    def test_prices_are_signed(self, tmp_path: Path) -> None:
        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "146.0" not in body

    def test_markets_read_as_prose(self, tmp_path: Path) -> None:
        _write(tmp_path, ready=True, comparison=_comparison())
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "1x2, btts" in body
        assert "['1x2'" not in body

    def test_it_says_what_changed(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            ready=True,
            comparison=_comparison(added=[{"label": "Newcastle v Liverpool 1x2 home"}]),
        )
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "**Added:** Newcastle v Liverpool 1x2 home" in body

    def test_it_explains_that_silence_is_meaningful(self, tmp_path: Path) -> None:
        """The reader is being asked to treat no-email as information."""
        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        # The promise changed: it used to be "no message means nothing moved".
        # Now a card arrives daily, so a silent day means a run did not happen.
        assert "a run did not happen" in body.lower()

    def test_a_blocked_card_is_not_reported_as_no_value(self, tmp_path: Path) -> None:
        _write(tmp_path, ready=False, comparison=_comparison(removed=[{"label": "x"}]))
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "blocked" in body
        assert "Start here:" in body

    def test_it_never_claims_a_bet_was_placed(self, tmp_path: Path) -> None:
        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "No bet was placed" in body

    def test_a_zero_unit_row_is_not_emailed_as_a_pick(self, tmp_path: Path) -> None:
        (tmp_path / "epl_card_task.json").write_text(
            json.dumps(
                {
                    "card_ready": True,
                    "included_markets": ["1x2"],
                    "excluded_markets": [],
                    "best_bets": [_pick(selection="draw", suggested_units=0.0)],
                    "leans": [],
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "automated_card.json").write_text(
            json.dumps({"card_generated": True}), encoding="utf-8"
        )
        (tmp_path / "automated_card_comparison.json").write_text(
            json.dumps(_comparison(added=[{"label": "x"}])), encoding="utf-8"
        )
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "| draw |" not in body

    def test_the_run_link_is_included_when_given(self, tmp_path: Path) -> None:
        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        body = build_notification(
            output_dir=tmp_path, now=NOW, run_url="https://example.invalid/run"
        )["body"]

        assert "https://example.invalid/run" in body


class TestTheWorkflowAgrees:
    def _workflow(self) -> str:
        from epl_betting_lab.config import PROJECT_ROOT

        return (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

    def test_the_delivery_step_exists(self) -> None:
        assert "Email the card" in self._workflow()

    def test_it_may_write_issues_and_nothing_else(self) -> None:
        header = self._workflow().split("jobs:", 1)[0]

        assert "issues: write" in header
        assert "contents: write" not in header

    def test_delivery_failure_does_not_fail_the_run(self) -> None:
        """A card that was built must not be lost because email broke."""
        text = self._workflow()
        step = text.split("- name: Email the card", 1)[1]
        step = step.split("- name:", 1)[0]

        assert "continue-on-error: true" in step

    def test_the_title_is_not_duplicated_in_shell(self) -> None:
        """Two copies would drift and post to two different issues."""
        text = self._workflow()

        assert "--title-out" in text
        assert ISSUE_TITLE not in text


class TestSendingOnDemand:
    """A delivery path that only fires on change cannot be checked on demand.

    Without this the first proof that email works would be the first week the
    picks moved — which is the worst possible time to discover it does not.
    """

    def _workflow(self) -> str:
        from epl_betting_lab.config import PROJECT_ROOT

        return (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

    def test_the_card_can_be_sent_on_demand(self) -> None:
        text = self._workflow()

        assert "force_email" in text
        assert "Send the card even if the selections did not change" in text

    def test_forcing_is_off_by_default(self) -> None:
        """The schedule must stay quiet unless the picks move."""
        text = self._workflow()
        block = text.split("force_email:", 1)[1].split("permissions:", 1)[0]

        assert "default: false" in block

    def test_forcing_is_a_manual_input_not_a_schedule_setting(self) -> None:
        text = self._workflow()
        dispatch = text.split("workflow_dispatch:", 1)[1].split("permissions:", 1)[0]

        assert "force_email" in dispatch


class TestTheCommentReachesAPerson:
    """Posting is not delivering.

    On a repository you own, GitHub's default notification setting is
    "participating and @mentions". A comment written by Actions on an issue
    nobody has touched can notify nobody — the delivery step would report
    success on every run and quietly reach no one, which is the failure mode
    this whole design is meant to avoid.
    """

    def _body(self, tmp_path: Path) -> str:
        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        return build_notification(output_dir=tmp_path, now=NOW)["body"]

    def test_the_comment_mentions_someone(self, tmp_path: Path) -> None:
        from epl_betting_lab.reports.card_notification import NOTIFY_HANDLE

        assert NOTIFY_HANDLE.startswith("@")
        assert NOTIFY_HANDLE in self._body(tmp_path)

    def test_the_mention_is_near_the_top_where_it_notifies(
        self, tmp_path: Path
    ) -> None:
        from epl_betting_lab.reports.card_notification import NOTIFY_HANDLE

        body = self._body(tmp_path)
        assert body.index(NOTIFY_HANDLE) < 120

    def test_a_blocked_card_still_reaches_someone(self, tmp_path: Path) -> None:
        """Losing the card is exactly when the message must not go unseen."""
        from epl_betting_lab.reports.card_notification import NOTIFY_HANDLE

        _write(tmp_path, ready=False, comparison=_comparison(removed=[{"label": "x"}]))
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert NOTIFY_HANDLE in body


class TestADegradedRunAlwaysSends:
    """Silence means "nothing moved" only if failure breaks the silence."""

    def test_a_degraded_run_sends_even_with_no_changes(self) -> None:
        post, reason = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(),
            degraded=["Prices could not be refreshed."],
        )
        assert post is True
        assert "went wrong" in reason

    def test_a_degraded_blocked_run_still_sends(self) -> None:
        """Staying blocked is normally quiet; a failure must override that."""
        post, _ = decide(
            card={"card_ready": False},
            generated={"card_generated": False},
            comparison=_comparison(),
            degraded=["No match dataset."],
        )
        assert post is True

    def test_a_clean_unchanged_run_still_stays_quiet(self) -> None:
        post, _ = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(),
            degraded=[],
            last_sent=NOW - timedelta(hours=2),
            now=NOW,
        )
        assert post is False

    def test_the_message_says_what_went_wrong(self, tmp_path: Path) -> None:
        _write(tmp_path, ready=True, comparison=_comparison())
        body = build_notification(
            output_dir=tmp_path,
            now=NOW,
            degraded=["Provider prices could not be refreshed."],
        )["body"]

        assert "### What went wrong" in body
        assert "Provider prices could not be refreshed." in body

    def test_the_message_warns_the_card_may_be_built_on_less(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, ready=True, comparison=_comparison())
        body = build_notification(
            output_dir=tmp_path, now=NOW, degraded=["Something broke."]
        )["body"]

        assert "whatever evidence was available" in body

    def test_the_footer_promises_failures_break_the_silence(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "whenever a run goes wrong" in body


class TestReadingTheDegradedRecord:
    def test_missing_file_is_not_degraded(self, tmp_path: Path) -> None:
        from epl_betting_lab.reports.card_notification import read_degraded

        assert read_degraded(tmp_path / "nope.txt") == []

    def test_empty_file_is_not_degraded(self, tmp_path: Path) -> None:
        from epl_betting_lab.reports.card_notification import read_degraded

        path = tmp_path / "d.txt"
        path.write_text("\n  \n", encoding="utf-8")
        assert read_degraded(path) == []

    def test_each_line_is_a_reason(self, tmp_path: Path) -> None:
        from epl_betting_lab.reports.card_notification import read_degraded

        path = tmp_path / "d.txt"
        path.write_text("one\ntwo\n", encoding="utf-8")
        assert read_degraded(path) == ["one", "two"]

    def test_no_path_is_not_degraded(self) -> None:
        from epl_betting_lab.reports.card_notification import read_degraded

        assert read_degraded(None) == []


class TestTheProductionPathIsExercised:
    """Every test passed `output_dir`. Production does not.

    A local import shadowed the module-level OUTPUTS_DIR for the whole
    function, so the default path raised UnboundLocalError while every test
    passed — because a conditional expression never evaluates the branch it
    does not take. The delivery step is continue-on-error, so the only symptom
    would have been email quietly stopping.
    """

    def test_it_builds_with_no_output_directory(self) -> None:
        from epl_betting_lab.reports.card_notification import build_notification

        result = build_notification()

        assert isinstance(result["body"], str)
        assert result["body"].strip()

    def test_it_builds_with_no_arguments_at_all(self) -> None:
        from epl_betting_lab.reports.card_notification import build_notification

        assert build_notification()["should_post"] in {True, False}


class TestTheEmailSaysHowItWasStarted:
    """A manual run and a scheduled one read identically in an inbox.

    Testing this system produced a run of failure mails indistinguishable from
    real ones, and a routine reading them reported a stale manual test as the
    current state.
    """

    def _body(self, tmp_path: Path, trigger: str) -> str:
        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        from epl_betting_lab.reports.card_notification import build_notification

        return build_notification(
            output_dir=tmp_path, now=NOW, trigger=trigger,
            degraded=["something broke"],
        )["body"]

    def test_a_manual_run_says_so_in_the_heading(self, tmp_path: Path) -> None:
        assert "manual run" in self._body(tmp_path, "workflow_dispatch")

    def test_a_manual_run_explains_what_that_means(self, tmp_path: Path) -> None:
        body = self._body(tmp_path, "workflow_dispatch")

        assert "started by hand, not by the schedule" in body

    def test_a_scheduled_run_is_not_labelled(self, tmp_path: Path) -> None:
        """The normal case should not carry a caveat."""
        body = self._body(tmp_path, "schedule")

        assert "manual run" not in body

    def test_an_unknown_trigger_is_treated_as_scheduled(self, tmp_path: Path) -> None:
        assert "manual run" not in self._body(tmp_path, "")

    def test_the_workflow_passes_the_trigger_through(self) -> None:
        from epl_betting_lab.config import PROJECT_ROOT

        text = (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

        assert "--trigger" in text
        assert "github.event_name" in text


class TestOneCardADay:
    """Sending only on change is wrong for something that reads daily.

    A price drifting is not news to a person. But a routine running every day
    then reads a message from days ago and reports it as the state of play,
    which is exactly what the first routine run did.
    """

    def _decide(self, last_sent, comparison=None):
        from epl_betting_lab.reports.card_notification import decide

        return decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=comparison or _comparison(price_changed=[{"label": "x"}]),
            last_sent=last_sent,
            now=NOW,
        )

    def test_the_first_card_of_the_day_sends(self) -> None:
        post, reason = self._decide(NOW - timedelta(days=1))

        assert post is True
        assert "First card of the day" in reason
        assert "unchanged" in reason

    def test_a_second_run_the_same_day_stays_quiet(self) -> None:
        """Ten runs a week must not become ten messages."""
        post, _ = self._decide(NOW - timedelta(hours=2))

        assert post is False

    def test_a_second_run_still_sends_when_selections_change(self) -> None:
        post, reason = self._decide(
            NOW - timedelta(hours=2), _comparison(added=[{"label": "x"}])
        )

        assert post is True
        assert "added" in reason

    def test_nothing_sent_before_means_send(self) -> None:
        post, _ = self._decide(None)

        assert post is True

    def test_a_degraded_run_sends_whatever_the_day(self) -> None:
        from epl_betting_lab.reports.card_notification import decide

        post, _ = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(),
            degraded=["broke"],
            last_sent=NOW - timedelta(hours=1),
            now=NOW,
        )

        assert post is True

    def test_the_footer_says_a_silent_day_means_a_missed_run(self, tmp_path: Path) -> None:
        """The promise changed, so the wording had to."""
        from epl_betting_lab.reports.card_notification import build_notification

        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        body = build_notification(output_dir=tmp_path, now=NOW)["body"]

        assert "one card a day" in body
        assert "a run did not happen" in body


class TestTheEmailCarriesQuota:
    """The routine prompts ask for quota and a routine reads email.

    The first EPL Watch run reported "provider quota: missing" every week,
    correctly: the figure was only ever in the run summary, which a routine
    never sees.
    """

    def _body(self, tmp_path: Path, remaining: str) -> str:
        from epl_betting_lab.reports.card_notification import build_notification
        import json as _json

        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        (tmp_path / "provider_shadow_verification.json").write_text(
            _json.dumps({"api_quota": {"requests_remaining": remaining}}),
            encoding="utf-8",
        )
        return build_notification(output_dir=tmp_path, now=NOW)["body"]

    def test_the_card_states_the_quota(self, tmp_path: Path) -> None:
        assert "Provider quota:" in self._body(tmp_path, "5000")

    def test_it_says_how_many_runs_that_buys(self, tmp_path: Path) -> None:
        assert "about 80 more runs" in self._body(tmp_path, "5000")

    def test_a_low_quota_warns_in_the_email_too(self, tmp_path: Path) -> None:
        assert "Top this up" in self._body(tmp_path, "500")

    def test_an_unknown_quota_is_left_out_rather_than_guessed(
        self, tmp_path: Path
    ) -> None:
        assert "Provider quota:" not in self._body(tmp_path, "")

    def test_the_email_and_the_summary_use_the_same_arithmetic(self) -> None:
        """Two implementations would eventually disagree."""
        from epl_betting_lab.config import PROJECT_ROOT

        source = (
            PROJECT_ROOT / "src/epl_betting_lab/reports/card_notification.py"
        ).read_text(encoding="utf-8")

        assert "from epl_betting_lab.reports.run_summary import _quota_line" in source


class TestEveryRunSaysHowItStarted:
    """Labelling only manual runs left the other kind ambiguous.

    A health check reading an older message could not tell whether "no label"
    meant scheduled or meant the message predated labelling, and correctly said
    so rather than guessing. Labelling both makes an unlabelled message mean
    exactly one thing: it is old.
    """

    def _heading(self, tmp_path: Path, trigger: str) -> str:
        from epl_betting_lab.reports.card_notification import build_notification

        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        return build_notification(
            output_dir=tmp_path, now=NOW, trigger=trigger
        )["body"].splitlines()[0]

    def test_a_scheduled_run_says_so(self, tmp_path: Path) -> None:
        assert "scheduled run" in self._heading(tmp_path, "schedule")

    def test_a_manual_run_says_so(self, tmp_path: Path) -> None:
        assert "manual run" in self._heading(tmp_path, "workflow_dispatch")

    def test_the_two_labels_are_distinguishable(self, tmp_path: Path) -> None:
        """"scheduled run" contains neither word of "manual run"."""
        scheduled = self._heading(tmp_path, "schedule")

        assert "manual" not in scheduled

    def test_an_unknown_trigger_carries_no_label(self, tmp_path: Path) -> None:
        """So an unlabelled message means one thing: it predates labelling."""
        heading = self._heading(tmp_path, "")

        assert "run" not in heading.split("UTC")[-1]

    def test_only_the_manual_caveat_appears_for_manual_runs(
        self, tmp_path: Path
    ) -> None:
        from epl_betting_lab.reports.card_notification import build_notification

        _write(tmp_path, ready=True, comparison=_comparison(added=[{"label": "x"}]))
        scheduled = build_notification(
            output_dir=tmp_path, now=NOW, trigger="schedule"
        )["body"]

        assert "started by hand" not in scheduled
