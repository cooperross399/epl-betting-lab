"""Every market key a book carries for an event, from the provider's own list.

Cooper, 2026-10-19: "bovada has tackles under player props" and "find goalie
saves figure it out". Probing one guessed key at a time cannot tell a key the
provider spells differently from a market it does not relay: a guessed
`player_goalkeeper_saves` 422s either way. The event-markets endpoint lists
the keys each book actually has for an event, so the question is answered
by the provider rather than by guessing spellings.
"""

from __future__ import annotations

from epl_betting_lab.reports.provider_market_discovery import list_event_market_keys


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_keys_are_listed_per_book_across_events() -> None:
    calls = []

    def requester(url, params=None, timeout=None):
        calls.append((url, dict(params or {})))
        event = url.rstrip("/").split("/")[-2]
        books = {
            "e1": [{"key": "bovada", "title": "Bovada", "markets": [
                {"key": "player_tackles"}, {"key": "player_to_receive_card"}]}],
            "e2": [{"key": "bovada", "title": "Bovada", "markets": [{"key": "player_saves_x"}]},
                   {"key": "fanduel", "title": "FanDuel", "markets": [{"key": "h2h"}]}],
        }[event]
        return _Response({"id": event, "bookmakers": books})

    events = [{"provider_event_id": "e1"}, {"provider_event_id": "e2"}, {"provider_event_id": ""}]
    result = list_event_market_keys(events, api_key="k", requester=requester, regions="us,us2")

    assert result["by_book"] == {
        "Bovada": ["player_saves_x", "player_tackles", "player_to_receive_card"],
        "FanDuel": ["h2h"],
    }
    assert result["events_listed"] == 2
    assert all(url.endswith("/markets") for url, _ in calls)
    assert all(params["regions"] == "us,us2" for _, params in calls)
    assert result["errors"] == []


def test_a_refused_event_is_named_not_dropped() -> None:
    def requester(url, params=None, timeout=None):
        return _Response({"message": "nope"}, status_code=422)

    result = list_event_market_keys([{"provider_event_id": "e1"}], api_key="k", requester=requester)
    assert result["by_book"] == {}
    assert result["events_listed"] == 0
    assert result["errors"] and "e1" in result["errors"][0] and "422" in result["errors"][0]
