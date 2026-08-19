"""Deciding when a card is worth an email.

Five emails a week would train the reader to ignore them, and an alert nobody
opens is worse than no alert because it still looks like coverage. So the rule
is narrow: the selections changed. It has to be exactly right, because the
reader is being asked to treat silence as information.
"""

from __future__ import annotations

from datetime import datetime, timezone
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

    def test_a_price_move_alone_stays_quiet(self) -> None:
        post, reason = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(price_changed=[{"label": "x"}, {"label": "y"}]),
        )
        assert post is False
        assert "2 price move(s) only" in reason

    def test_an_identical_card_stays_quiet(self) -> None:
        post, _ = decide(
            card={"card_ready": True},
            generated={"card_generated": True},
            comparison=_comparison(),
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
        )
        assert post is False
        assert "nothing new" in reason

    def test_a_card_ready_flag_without_generation_is_not_a_card(self) -> None:
        post, _ = decide(
            card={"card_ready": True},
            generated={"card_generated": False},
            comparison=_comparison(),
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

        assert "no message means" in body.lower()

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
        assert "Email the card when the picks change" in self._workflow()

    def test_it_may_write_issues_and_nothing_else(self) -> None:
        header = self._workflow().split("jobs:", 1)[0]

        assert "issues: write" in header
        assert "contents: write" not in header

    def test_delivery_failure_does_not_fail_the_run(self) -> None:
        """A card that was built must not be lost because email broke."""
        text = self._workflow()
        step = text.split("Email the card when the picks change", 1)[1]
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
