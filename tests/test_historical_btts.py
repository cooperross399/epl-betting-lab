"""Harvesting historical BTTS prices.

BTTS produces most of the picks on a card and has never been profit-backtested,
because Football-Data carries no BTTS odds. The provider sells them, one event
at a time, at ten credits each — so the harvest has to be careful with money
and honest about what it sampled.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from epl_betting_lab.providers.historical_btts import (
    HarvestBudget,
    harvest_btts_history,
    matchdays_between,
)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _event(event_id="e1", home="Arsenal", away="Chelsea"):
    return {
        "id": event_id,
        "home_team": home,
        "away_team": away,
        "commence_time": "2025-08-16T14:00:00Z",
    }


def _btts_payload(yes=150, no=-180, book="FanDuel"):
    return {
        "data": {
            "bookmakers": [
                {
                    "title": book,
                    "markets": [
                        {
                            "key": "btts",
                            "outcomes": [
                                {"name": "Yes", "price": yes},
                                {"name": "No", "price": no},
                            ],
                        }
                    ],
                }
            ]
        }
    }


def _requester(slate_events, btts_payload):
    def _request(url, params=None, timeout=None):
        if "/events/" in url:
            return _Response(btts_payload)
        return _Response({"data": slate_events})

    return _request


DAY = [datetime(2025, 8, 16, 15, 0, tzinfo=timezone.utc)]


class TestHarvest:
    def test_it_returns_a_row_per_fixture(self) -> None:
        result = harvest_btts_history(
            DAY,
            api_key="k",
            budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
        )

        assert len(result.rows) == 1
        assert result.rows[0]["home_team"] == "Arsenal"

    def test_it_keeps_both_selections(self) -> None:
        result = harvest_btts_history(
            DAY,
            api_key="k",
            budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload(yes=150, no=-180)),
        )
        row = result.rows[0]

        assert row["btts_yes_american"] == 150
        assert row["btts_no_american"] == -180

    def test_it_keeps_the_best_price_across_books(self) -> None:
        """The card quotes the best book it can reach, so this must too."""
        payload = {
            "data": {
                "bookmakers": [
                    {"title": "A", "markets": [{"key": "btts", "outcomes": [
                        {"name": "Yes", "price": 140}]}]},
                    {"title": "B", "markets": [{"key": "btts", "outcomes": [
                        {"name": "Yes", "price": 165}]}]},
                ]
            }
        }
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], payload),
        )

        assert result.rows[0]["btts_yes_american"] == 165

    def test_it_records_when_it_sampled(self) -> None:
        """A price without a timestamp cannot be compared to anything."""
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()), hours_before=3,
        )

        assert result.rows[0]["sampled_at"] == "2025-08-16T12:00:00Z"

    def test_a_day_with_no_fixtures_costs_one_snapshot(self) -> None:
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([], {"data": {}}),
        )

        assert result.rows == []
        assert result.credits_spent == 10

    def test_an_event_without_btts_is_skipped_not_invented(self) -> None:
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], {"data": {"bookmakers": []}}),
        )

        assert result.rows == []
        assert result.events_seen == 1
        assert result.events_with_btts == 0


class TestBudget:
    def test_it_stops_before_exceeding_the_limit(self) -> None:
        budget = HarvestBudget(limit=15)
        result = harvest_btts_history(
            DAY, api_key="k", budget=budget,
            requester=_requester([_event("a"), _event("b")], _btts_payload()),
        )

        assert budget.spent <= 15
        assert result.stopped_early is True

    def test_it_reports_what_it_spent(self) -> None:
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
        )

        # One slate snapshot plus one event.
        assert result.credits_spent == 20

    def test_a_zero_budget_spends_nothing(self) -> None:
        budget = HarvestBudget(limit=0)
        result = harvest_btts_history(
            DAY, api_key="k", budget=budget,
            requester=_requester([_event()], _btts_payload()),
        )

        assert budget.spent == 0
        assert result.rows == []
        assert result.stopped_early is True


class TestMatchdays:
    def test_it_covers_the_range_inclusively(self) -> None:
        days = matchdays_between(
            datetime(2025, 8, 16), datetime(2025, 8, 18)
        )

        assert len(days) == 3

    def test_every_day_is_at_the_same_hour(self) -> None:
        days = matchdays_between(
            datetime(2025, 8, 16), datetime(2025, 8, 18), hour=15
        )

        assert {d.hour for d in days} == {15}

    def test_days_are_timezone_aware(self) -> None:
        """A naive timestamp would be formatted as if it were UTC."""
        days = matchdays_between(datetime(2025, 8, 16), datetime(2025, 8, 16))

        assert days[0].tzinfo is timezone.utc


class TestTheHarvestWorkflow:
    """It spends real money, so the guardrails are the point."""

    def _workflow(self) -> str:
        from epl_betting_lab.config import PROJECT_ROOT

        return (
            PROJECT_ROOT / ".github" / "workflows" / "harvest-historical-btts.yml"
        ).read_text(encoding="utf-8")

    def test_it_is_manual_only(self) -> None:
        """Nothing that spends credits per event should run on a timer."""
        text = self._workflow()

        assert "workflow_dispatch:" in text
        assert "schedule:" not in text

    def test_the_credit_ceiling_is_required(self) -> None:
        text = self._workflow()
        block = text.split("credit_limit:", 1)[1].split("hours_before:", 1)[0]

        assert "required: true" in block

    def test_two_harvests_cannot_run_at_once(self) -> None:
        """They would double-spend and interleave their rows."""
        text = self._workflow()

        assert "group: harvest-historical-btts" in text
        assert "cancel-in-progress: false" in text

    def test_it_resumes_from_what_was_already_bought(self) -> None:
        """Credits already spent must not be spent again."""
        text = self._workflow()

        assert "Restore what has already been bought" in text
        assert "--append" in text

    def test_it_places_no_bet_and_changes_no_policy(self) -> None:
        text = self._workflow().lower()

        for forbidden in ("settle", "bet_ledger", "staging_provider_policy", "--force"):
            assert forbidden not in text, forbidden
