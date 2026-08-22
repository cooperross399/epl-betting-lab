"""Live prop prices stage in their own file, invisible to the card."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from epl_betting_lab.providers.player_props_staging import (
    LIVE_CREDITS_PER_EVENT,
    PROP_EVENT_MARKETS,
    PROPS_STAGING_FILENAME,
    PlayerPropsFetchError,
    extract_prop_rows,
    fetch_player_props,
    write_props_staging,
)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _event_payload(event_id="e1"):
    return {
        "id": event_id,
        "commence_time": "2026-08-23T13:00:00Z",
        "home_team": "Newcastle United",
        "away_team": "Liverpool",
        "bookmakers": [
            {
                "title": "FanDuel",
                "markets": [
                    {
                        "key": "player_shots_on_target",
                        "outcomes": [
                            {
                                "name": "Over",
                                "description": "Alexander Isak",
                                "point": 1.5,
                                "price": 120,
                            },
                            {
                                "name": "Over",
                                "description": "Mohamed Salah",
                                "point": 1.5,
                                "price": -105,
                            },
                        ],
                    },
                    {
                        "key": "player_goal_scorer_anytime",
                        "outcomes": [
                            {
                                "name": "Yes",
                                "description": "Alexander Isak",
                                "price": 210,
                            }
                        ],
                    },
                    {
                        "key": "player_to_receive_card",
                        "outcomes": [
                            {
                                "name": "Yes",
                                "description": "Someone Reckless",
                                "price": 300,
                            }
                        ],
                    },
                    {
                        "key": "h2h",
                        "outcomes": [{"name": "Liverpool", "price": -130}],
                    },
                ],
            }
        ],
    }


class TestExtraction:
    def test_rows_carry_player_line_and_book(self) -> None:
        rows = extract_prop_rows(
            _event_payload(), fetched_at="2026-08-23T10:00:00Z"
        )
        by_player = {
            (r["market"], r["player"]): r for r in rows
        }

        sot = by_player[("player_shots_on_target", "Alexander Isak")]
        assert sot["selection"] == "Over@1.5"
        assert sot["american_odds"] == 120
        assert sot["book"] == "FanDuel"
        scorer = by_player[("player_goal_scorer_anytime", "Alexander Isak")]
        assert scorer["selection"] == "Yes"

    def test_unpriceable_markets_are_not_staged(self) -> None:
        """Cards and match markets are not the model's to price; a price
        nothing can price is quota spent on nothing, and staging it would
        imply otherwise."""
        rows = extract_prop_rows(
            _event_payload(), fetched_at="2026-08-23T10:00:00Z"
        )

        assert {r["market"] for r in rows} <= set(PROP_EVENT_MARKETS)
        assert all(r["market"] != "player_to_receive_card" for r in rows)

    def test_team_names_are_canonical(self) -> None:
        rows = extract_prop_rows(
            _event_payload(), fetched_at="2026-08-23T10:00:00Z"
        )

        assert all(r["home_team"] == "Newcastle" for r in rows)


class TestFetch:
    def _requester(self, calls: list[dict]):
        def request(url, params=None, timeout=None):
            calls.append({"url": url, "params": params})
            if url.endswith("/events"):
                return _Response(
                    [{"id": "e1"}, {"id": "e2"}]
                )
            return _Response(_event_payload(url.rsplit("/", 2)[-2]))

        return request

    def test_the_cost_is_markets_times_events(self) -> None:
        calls: list[dict] = []
        result = fetch_player_props(
            api_key="k",
            requester=self._requester(calls),
            fetched_at="2026-08-23T10:00:00Z",
        )

        assert result.events_seen == 2
        assert result.events_priced == 2
        assert result.credits_spent == 2 * LIVE_CREDITS_PER_EVENT

    def test_max_events_caps_the_spend(self) -> None:
        calls: list[dict] = []
        result = fetch_player_props(
            api_key="k",
            requester=self._requester(calls),
            max_events=1,
            fetched_at="2026-08-23T10:00:00Z",
        )

        assert result.credits_spent == LIVE_CREDITS_PER_EVENT

    def test_a_missing_credential_is_refused(self) -> None:
        with pytest.raises(PlayerPropsFetchError, match="credential"):
            fetch_player_props(api_key="", fetched_at="x")

    def test_a_failed_event_is_reported_and_skipped(self) -> None:
        def request(url, params=None, timeout=None):
            if url.endswith("/events"):
                return _Response([{"id": "bad"}])
            return _Response({}, status_code=503)

        result = fetch_player_props(
            api_key="k", requester=request, fetched_at="x"
        )

        assert result.events_priced == 0
        assert len(result.errors) == 1


class TestStagingFile:
    def test_the_file_lands_beside_but_never_inside_match_staging(
        self, tmp_path: Path
    ) -> None:
        rows = extract_prop_rows(
            _event_payload(), fetched_at="2026-08-23T10:00:00Z"
        )
        target = write_props_staging(rows, staging_dir=tmp_path)

        assert target.name == PROPS_STAGING_FILENAME
        with target.open(encoding="utf-8", newline="") as handle:
            read = list(csv.DictReader(handle))
        assert len(read) == len(rows)
        assert read[0]["player"] == "Alexander Isak"

    def test_existing_evidence_is_not_replaced_by_accident(
        self, tmp_path: Path
    ) -> None:
        write_props_staging([], staging_dir=tmp_path)

        with pytest.raises(PlayerPropsFetchError, match="already exists"):
            write_props_staging([], staging_dir=tmp_path)

        write_props_staging([], staging_dir=tmp_path, overwrite=True)
