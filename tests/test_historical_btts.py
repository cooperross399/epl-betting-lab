"""Harvesting historical BTTS prices.

BTTS produces most of the picks on a card and has never been profit-backtested,
because Football-Data carries no BTTS odds. The provider sells them, one event
at a time, at ten credits each — so the harvest has to be careful with money
and honest about what it sampled.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from epl_betting_lab.providers import historical_btts
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
    def test_it_returns_a_row_per_selection(self) -> None:
        """Long rows, not wide.

        A wide table would need a column per line of every ladder and would
        change shape whenever a book added one.
        """
        result = harvest_btts_history(
            DAY,
            api_key="k",
            budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
        )

        assert len(result.rows) == 2
        assert {r["selection"] for r in result.rows} == {"Yes", "No"}
        assert all(r["home_team"] == "Arsenal" for r in result.rows)

    def test_each_row_names_its_market(self) -> None:
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
        )

        assert {r["market"] for r in result.rows} == {"btts"}

    def test_a_line_is_kept_in_the_selection(self) -> None:
        """Otherwise a totals ladder collapses into a single column."""
        payload = {"data": {"bookmakers": [{"title": "FanDuel", "markets": [
            {"key": "alternate_totals_corners", "outcomes": [
                {"name": "Over", "point": 9.5, "price": -110},
                {"name": "Over", "point": 10.5, "price": 120},
            ]}]}]}}
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["alternate_totals_corners"],
            requester=_requester([_event()], payload),
        )

        assert {r["selection"] for r in result.rows} == {"Over@9.5", "Over@10.5"}

    def test_it_keeps_both_selections(self) -> None:
        result = harvest_btts_history(
            DAY,
            api_key="k",
            budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload(yes=150, no=-180)),
        )
        prices = {r["selection"]: r["american"] for r in result.rows}

        assert prices == {"Yes": 150, "No": -180}

    def test_several_markets_travel_in_one_request(self) -> None:
        """They must be priced at the same instant to be comparable."""
        payload = {"data": {"bookmakers": [{"title": "FanDuel", "markets": [
            {"key": "btts", "outcomes": [{"name": "Yes", "price": 150}]},
            {"key": "draw_no_bet", "outcomes": [{"name": "Arsenal", "price": -140}]},
        ]}]}}
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts", "draw_no_bet"],
            requester=_requester([_event()], payload),
        )

        assert {r["market"] for r in result.rows} == {"btts", "draw_no_bet"}
        assert len({r["sampled_at"] for r in result.rows}) == 1

    def test_asking_for_more_markets_costs_more(self) -> None:
        budget = HarvestBudget(limit=1000)
        harvest_btts_history(
            DAY, api_key="k", budget=budget,
            markets=["btts", "draw_no_bet", "corners_1x2"],
            requester=_requester([_event()], _btts_payload()),
        )

        # One slate snapshot, plus ten credits per market on one event.
        assert budget.spent == 10 + 30

    def test_it_keeps_every_book_named_rather_than_one_maximum(self) -> None:
        """Which book quoted a price is the only thing that says whether it
        could have been taken.

        Collapsing books into a single maximum is optimistic by construction -
        the max runs over books Cooper may not bet, and `bettable_only` fails
        closed without a `book` column. The book is already in the response,
        so keeping it costs nothing and buys the Pinnacle reference free.
        """
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

        assert {(r["book"], r["american"]) for r in result.rows} == {
            ("A", 140),
            ("B", 165),
        }

    def test_it_samples_before_that_fixture_own_kick_off(self) -> None:
        """Not at a fixed hour of the day.

        Sampling every matchday at one time bought some fixtures twice, missed
        the lead on others, and once returned a price stamped after kick-off —
        an in-play number that would have read as a very good bet.
        """
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()), hours_before=3,
        )

        # Kick-off 14:00, so three hours before is 11:00.
        assert result.rows[0]["sampled_at"] == "2025-08-16T11:00:00Z"

    def test_the_sample_is_always_before_kick_off(self) -> None:
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()), hours_before=3,
        )
        row = result.rows[0]

        assert row["sampled_at"] < row["commence_time"]

    def test_a_fixture_seen_on_two_days_is_bought_once(self) -> None:
        """Slate snapshots return everything upcoming, so they overlap."""
        two_days = [
            datetime(2025, 8, 16, 15, 0, tzinfo=timezone.utc),
            datetime(2025, 8, 17, 15, 0, tzinfo=timezone.utc),
        ]
        result = harvest_btts_history(
            two_days, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
        )

        # Two selections from one fixture, not four from two.
        assert len(result.rows) == 2

    def test_a_fixture_already_bought_is_not_bought_again(self) -> None:
        """Credits already spent must not be spent twice."""
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
            already_harvested=["2025-08-16|arsenal|chelsea|btts"],
        )

        assert result.rows == []
        assert result.already_had == 1

    def test_a_fixture_bought_for_one_market_is_still_bought_for_another(self) -> None:
        """What is held is a fixture AND a market.

        Keying on the fixture alone meant the 150 dates already bought for
        corners counted as bought for everything: a BTTS harvest over that
        window would skip all of them, spend nothing, and report a green
        "already hold 150 fixtures" while recording no BTTS price. The
        harvester is named after BTTS and had never bought any.
        """
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts"],
            requester=_requester([_event()], _btts_payload()),
            already_harvested=["2025-08-16|arsenal|chelsea|alternate_totals_corners"],
        )

        assert result.already_had == 0
        assert [row["market"] for row in result.rows] == ["btts", "btts"]

    def test_only_the_missing_markets_are_paid_for(self) -> None:
        """Re-requesting a held market would charge full price for a duplicate."""
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts", "alternate_totals_corners"],
            requester=_requester([_event()], _btts_payload()),
            already_harvested=["2025-08-16|arsenal|chelsea|alternate_totals_corners"],
        )

        # One slate snapshot plus the ONE missing market, at ten credits
        # each. Requesting both markets would have cost thirty.
        assert result.credits_spent == 10 + 10

    def test_a_market_with_no_price_anywhere_is_recorded_as_a_miss(self) -> None:
        """A miss leaves no row, so without this it is re-bought forever."""
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts", "draw_no_bet"],
            requester=_requester([_event()], _btts_payload()),
        )

        assert [miss["market"] for miss in result.misses] == ["draw_no_bet"]
        assert result.misses[0]["home_team"] == "Arsenal"

    def test_a_dropped_connection_does_not_throw_away_the_whole_harvest(
        self, monkeypatch
    ) -> None:
        """A blip two-thirds through a season used to lose the season.

        Rows are written only at the end, so an exception escaping mid-run
        discarded every credit that run had already spent - which is exactly
        what a `Connection reset by peer` did on 2026-09-02, after roughly
        four minutes of paid requests.
        """
        monkeypatch.setattr(historical_btts, "_sleep", lambda _seconds: None)
        underlying = _requester([_event()], _btts_payload())
        calls = {"n": 0}

        def flaky(url, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ConnectionError("Connection reset by peer")
            return underlying(url, **kwargs)

        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000), requester=flaky,
        )

        # The retry carried it: the fixture is still priced.
        assert result.rows

    def test_a_request_that_never_recovers_is_skipped_not_raised(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(historical_btts, "_sleep", lambda _seconds: None)

        def dead(url, **kwargs):
            raise ConnectionError("Connection reset by peer")

        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000), requester=dead,
        )

        assert result.rows == []

    def test_a_rate_limited_request_is_not_recorded_as_no_price(
        self, monkeypatch
    ) -> None:
        """The worst bug this harvester has had.

        `_event_prices` returned `{}` for "the provider answered and had no
        price" AND for "the request failed". The caller wrote the second into
        the misses ledger, which is fed back into `already` on every later
        --append run - so one rate-limit burst across a 150-fixture window
        would spend 1,500 credits, record 150 permanent false negatives, and
        exit 0. No later run would ever buy them.

        A non-200 raises nothing: the requester is a bare `requests.get`.
        """
        monkeypatch.setattr(historical_btts, "_sleep", lambda _seconds: None)

        def rate_limited(url, **kwargs):
            if "/events/" in url:
                return _Response({}, status_code=429)
            return _Response({"data": [_event()]})

        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts"], requester=rate_limited,
        )

        assert result.misses == [], "a failed request is not an absent price"
        assert result.rows == []
        assert result.errors, "and it has to be said out loud"

    def test_a_retryable_status_is_actually_retried(self, monkeypatch) -> None:
        """The retry loop only caught raised exceptions, so a 429 - which
        `requests.get` returns rather than raises - was never retried once."""
        monkeypatch.setattr(historical_btts, "_sleep", lambda _seconds: None)
        calls = {"n": 0}

        def flaky(url, **kwargs):
            if "/events/" not in url:
                return _Response({"data": [_event()]})
            calls["n"] += 1
            if calls["n"] == 1:
                return _Response({}, status_code=429)
            return _Response(_btts_payload())

        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts"], requester=flaky,
        )

        assert calls["n"] == 2
        assert result.rows

    def test_a_genuine_empty_answer_is_still_recorded_as_a_miss(
        self, monkeypatch
    ) -> None:
        """The fix must not stop real misses being remembered, or every run
        re-buys the same nothing."""
        monkeypatch.setattr(historical_btts, "_sleep", lambda _seconds: None)
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts", "draw_no_bet"],
            requester=_requester([_event()], _btts_payload()),
        )

        assert [miss["market"] for miss in result.misses] == ["draw_no_bet"]

    def test_a_cached_day_costs_nothing(self) -> None:
        """Slates were re-bought on every run: a season is 283 days at ten
        credits, so 2,830 credits went on snapshots before a single price,
        and resuming from the same --start paid all of it again."""
        event = _event()
        cache = {
            "2025-08-16": [
                {
                    "id": event["id"],
                    "commence_time": event["commence_time"],
                    "home_team": event["home_team"],
                    "away_team": event["away_team"],
                }
            ]
        }
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts"],
            requester=_requester([_event()], _btts_payload()),
            cached_events=cache,
        )

        assert result.snapshots == 0
        assert result.snapshots_from_cache == 1
        # Ten for the one market, and nothing for the slate.
        assert result.credits_spent == 10
        assert result.rows

    def test_what_a_paid_snapshot_learned_is_handed_back_for_caching(self) -> None:
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["btts"],
            requester=_requester([_event()], _btts_payload()),
        )

        assert [row["day"] for row in result.discovered] == ["2025-08-16"]
        assert result.discovered[0]["home_team"] == "Arsenal"

    def test_a_failed_slate_is_not_an_empty_matchday(self, monkeypatch) -> None:
        """Returning [] would silently mean 'no fixtures that day'."""
        monkeypatch.setattr(historical_btts, "_sleep", lambda _seconds: None)
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=lambda url, **kwargs: _Response({}, status_code=503),
        )

        assert result.events_seen == 0
        assert result.errors

    def test_an_unreadable_kick_off_is_reported_not_guessed(self) -> None:
        broken = dict(_event())
        broken["commence_time"] = "not a time"
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([broken], _btts_payload()),
        )

        assert result.rows == []
        assert any("kick-off" in e for e in result.errors)

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

    def test_a_player_prop_row_names_its_player(self) -> None:
        """The player is the outcome's identity. Without it every player's
        Over@0.5 is one key and the ladder collapses into a single meaningless
        best price — which is what the first props harvest bought."""
        payload = {"data": {"bookmakers": [{"title": "FanDuel", "markets": [
            {"key": "player_shots_on_target", "outcomes": [
                {"name": "Over", "description": "Bukayo Saka", "point": 1.5, "price": -120},
                {"name": "Over", "description": "Kai Havertz", "point": 1.5, "price": 210},
            ]},
        ]}]}}
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["player_shots_on_target"],
            requester=_requester([_event()], payload),
        )

        assert len(result.rows) == 2
        by_player = {r["player"]: r for r in result.rows}
        assert by_player["Bukayo Saka"]["american"] == -120
        assert by_player["Kai Havertz"]["american"] == 210
        assert all(r["selection"] == "Over@1.5" for r in result.rows)

    def test_a_price_is_per_book_per_player_never_pooled(self) -> None:
        """Two players on the same line must never collapse into one price,
        and neither must two books."""
        payload = {"data": {"bookmakers": [
            {"title": "FanDuel", "markets": [
                {"key": "player_shots_on_target", "outcomes": [
                    {"name": "Over", "description": "Bukayo Saka", "point": 0.5, "price": -200},
                ]},
            ]},
            {"title": "DraftKings", "markets": [
                {"key": "player_shots_on_target", "outcomes": [
                    {"name": "Over", "description": "Bukayo Saka", "point": 0.5, "price": -185},
                    {"name": "Over", "description": "Kai Havertz", "point": 0.5, "price": 105},
                ]},
            ]},
        ]}}
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            markets=["player_shots_on_target"],
            requester=_requester([_event()], payload),
        )

        assert {(r["book"], r["player"], r["american"]) for r in result.rows} == {
            ("FanDuel", "Bukayo Saka", -200),
            ("DraftKings", "Bukayo Saka", -185),
            ("DraftKings", "Kai Havertz", 105),
        }

    def test_a_row_that_names_its_book_does_count_as_held(self) -> None:
        """The migration rule must not make every run re-buy everything."""
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
        )
        assert result.rows and all(row["book"] for row in result.rows)

        again = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
            already_harvested=["2025-08-16|arsenal|chelsea|btts"],
        )
        assert again.rows == []

    def test_a_match_level_row_has_an_empty_player(self) -> None:
        result = harvest_btts_history(
            DAY, api_key="k", budget=HarvestBudget(limit=1000),
            requester=_requester([_event()], _btts_payload()),
        )

        assert all(r["player"] == "" for r in result.rows)


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


class TestTheHarvestFile:
    """The script's file handling: migration, and what counts as bought."""

    def _module(self):
        import importlib.util

        from epl_betting_lab.config import PROJECT_ROOT

        spec = importlib.util.spec_from_file_location(
            "_harvest", PROJECT_ROOT / "scripts" / "harvest_historical_btts.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _legacy_file(self, tmp_path):
        path = tmp_path / "historical_market_odds.csv"
        path.write_text(
            "sampled_at,commence_time,home_team,away_team,market,selection,american\n"
            "2026-05-09T11:00:00Z,2026-05-09T14:00:00Z,Fulham,Bournemouth,btts,Yes,150.0\n"
            "2026-05-09T11:00:00Z,2026-05-09T14:00:00Z,Fulham,Everton,player_shots_on_target,Over@0.5,410.0\n",
            encoding="utf-8",
        )
        return path

    def test_a_playerless_prop_row_does_not_count_as_bought(self, tmp_path) -> None:
        """It collapsed every player into one price; the fixture must be
        re-bought correctly. The BTTS fixture stays bought."""
        module = self._module()
        already, legacy, needs_migration = module._read_existing(
            self._legacy_file(tmp_path), append=True
        )

        assert needs_migration is True
        assert len(legacy) == 2
        assert already == []  # no `book` column, so nothing counts as held

    def test_migration_keeps_every_old_row_under_the_new_header(
        self, tmp_path
    ) -> None:
        import csv as _csv

        module = self._module()
        path = self._legacy_file(tmp_path)
        already, legacy, needs_migration = module._read_existing(path, append=True)

        migrated = module._write_rows(
            path,
            [
                {
                    "sampled_at": "2026-05-09T11:00:00Z",
                    "commence_time": "2026-05-09T14:00:00Z",
                    "home_team": "Fulham",
                    "away_team": "Everton",
                    "market": "player_shots_on_target",
                    "player": "Raul Jimenez",
                    "selection": "Over@0.5",
                    "american": 390.0,
                }
            ],
            append=True,
            needs_migration=needs_migration,
            legacy_rows=legacy,
        )

        assert migrated == 2
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(_csv.DictReader(handle))
        assert len(rows) == 3
        assert rows[0]["player"] == ""
        assert rows[2]["player"] == "Raul Jimenez"
        # A second read no longer needs migration, and the attributed fixture
        # now counts as bought.
        already2, _, needs2 = module._read_existing(path, append=True)
        assert needs2 is False
        assert already2 == []  # migrated rows still carry no book
