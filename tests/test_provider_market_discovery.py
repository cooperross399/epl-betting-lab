"""Market discovery: why totals are incomplete and whether BTTS really is absent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from epl_betting_lab.providers.odds_api_staging_provider import OddsApiStagingProvider
from epl_betting_lab.reports.provider_market_discovery import (
    BULK_CAPABLE_MARKETS,
    EVENT_ONLY_MARKETS,
    DiscoveryError,
    classify_btts,
    classify_totals,
    discover_event_markets,
    estimate_quota_cost,
    save_provider_market_discovery,
    summarize_bulk_response,
)


SECRET = "discovery-secret-must-not-be-written"


def _event(
    event_id: str,
    date: str,
    home: str,
    away: str,
    *,
    totals_points=(2.5,),
    include_btts: bool = False,
    books=("BookA",),
) -> dict:
    bookmakers = []
    for book in books:
        markets = [
            {
                "key": "h2h",
                "outcomes": [
                    {"name": home, "price": -120},
                    {"name": "Draw", "price": 250},
                    {"name": away, "price": 350},
                ],
            }
        ]
        if totals_points:
            markets.append(
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": side, "price": -110, "point": point}
                        for point in totals_points
                        for side in ("Over", "Under")
                    ],
                }
            )
        if include_btts:
            markets.append(
                {
                    "key": "btts",
                    "outcomes": [
                        {"name": "Yes", "price": 110},
                        {"name": "No", "price": -130},
                    ],
                }
            )
        bookmakers.append({"key": book.lower(), "title": book, "markets": markets})
    return {
        "id": event_id,
        "commence_time": f"{date}T14:00:00Z",
        "home_team": home,
        "away_team": away,
        "bookmakers": bookmakers,
    }


WINDOW_EVENTS = [
    _event("e1", "2026-08-21", "Arsenal", "Coventry City"),
    _event("e2", "2026-08-22", "Hull City", "Manchester United"),
    _event("e3", "2026-08-23", "Manchester City", "Bournemouth", totals_points=(3.5,)),
]


# --- bulk analysis (free) --------------------------------------------------


def test_bulk_summary_records_every_totals_line_offered() -> None:
    summary = summarize_bulk_response(WINDOW_EVENTS)

    assert summary["event_count"] == 3
    high_total = next(
        e for e in summary["events"] if e["home_team"] == "Man City"
    )
    assert high_total["totals_points_offered"] == [3.5]
    assert high_total["has_required_totals_line"] is False


def test_bulk_summary_normalises_team_names() -> None:
    summary = summarize_bulk_response(WINDOW_EVENTS)
    names = {e["home_team"] for e in summary["events"]}

    assert "Man City" in names
    assert "Manchester City" not in names


def test_bulk_summary_reports_btts_absence_without_concluding_unavailable() -> None:
    summary = summarize_bulk_response(WINDOW_EVENTS)

    assert summary["btts_returned_by_bulk"] is False
    assert "btts" not in summary["markets_ever_returned"]


def test_totals_classified_incomplete_with_the_real_reason() -> None:
    result = classify_totals(summarize_bulk_response(WINDOW_EVENTS))

    assert result["status"] == "incomplete"
    assert result["events_with_required_line"] == 2
    assert result["events_total"] == 3
    # The cause is line availability, not a broken parser or wrong endpoint.
    assert result["parser_defect"] is False
    assert result["endpoint_limited"] is False
    assert result["region_limited"] is False
    assert "3.5" in result["root_cause"] or "high-expected-goals" in result["root_cause"]


def test_totals_available_when_every_event_offers_the_line() -> None:
    events = [
        _event("e1", "2026-08-21", "Arsenal", "Coventry City"),
        _event("e2", "2026-08-22", "Hull City", "Manchester United"),
    ]
    result = classify_totals(summarize_bulk_response(events))

    assert result["status"] == "available"
    assert result["missing_fixtures"] == []


def test_totals_never_fabricated_for_missing_lines() -> None:
    result = classify_totals(summarize_bulk_response(WINDOW_EVENTS))

    assert "Do not fabricate" in result["recommended_action"]


# --- BTTS classification ---------------------------------------------------


def test_btts_unchecked_is_not_the_same_as_unavailable() -> None:
    """The bug in the earlier conclusion: bulk absence was read as unavailable."""
    result = classify_btts(summarize_bulk_response(WINDOW_EVENTS), None)

    assert result["status"] == "not_checked"
    assert result["status"] != "unavailable"
    assert result["endpoint_limited"] is True
    assert "NOT evidence" in result["root_cause"]


def test_btts_available_when_every_event_returns_it() -> None:
    event_summary = {"event_count": 3, "events_with_btts": 3}
    result = classify_btts(summarize_bulk_response(WINDOW_EVENTS), event_summary)

    assert result["status"] == "available"
    assert result["checked_event_endpoint"] is True


def test_btts_incomplete_when_only_some_events_return_it() -> None:
    event_summary = {"event_count": 3, "events_with_btts": 2}
    result = classify_btts(summarize_bulk_response(WINDOW_EVENTS), event_summary)

    assert result["status"] == "incomplete"
    assert "Do not fabricate" in result["recommended_action"]


def test_btts_unavailable_only_after_the_event_endpoint_returns_nothing() -> None:
    event_summary = {"event_count": 3, "events_with_btts": 0}
    result = classify_btts(summarize_bulk_response(WINDOW_EVENTS), event_summary)

    assert result["status"] == "unavailable"
    assert result["checked_event_endpoint"] is True


def test_endpoint_capability_constants_are_explicit() -> None:
    assert "btts" not in BULK_CAPABLE_MARKETS
    assert "btts" in EVENT_ONLY_MARKETS
    assert "totals" in BULK_CAPABLE_MARKETS


# --- quota -----------------------------------------------------------------


def test_quota_estimate_is_markets_times_regions_per_event() -> None:
    estimate = estimate_quota_cost(
        event_count=10, markets=["btts"], regions=["us"]
    )

    assert estimate["events_listing_cost"] == 0
    assert estimate["cost_per_event_request"] == 1
    assert estimate["total_estimated_cost"] == 10


def test_quota_estimate_scales_with_markets_and_regions() -> None:
    estimate = estimate_quota_cost(
        event_count=10, markets=["btts", "h2h"], regions=["us", "uk"]
    )

    assert estimate["cost_per_event_request"] == 4
    assert estimate["total_estimated_cost"] == 40


# --- event discovery -------------------------------------------------------


def test_event_discovery_requires_a_credential() -> None:
    with pytest.raises(DiscoveryError):
        discover_event_markets([{"provider_event_id": "e1"}], api_key="")


def test_event_discovery_records_btts_per_event() -> None:
    class Response:
        status_code = 200

        def json(self) -> dict:
            return {
                "bookmakers": [
                    {
                        "key": "booka",
                        "title": "BookA",
                        "markets": [
                            {
                                "key": "btts",
                                "outcomes": [
                                    {"name": "Yes", "price": 110},
                                    {"name": "No", "price": -130},
                                ],
                            }
                        ],
                    }
                ]
            }

    result = discover_event_markets(
        [{"provider_event_id": "e1", "date": "2026-08-21"}],
        api_key=SECRET,
        requester=lambda url, **kwargs: Response(),
    )

    assert result["events_with_btts"] == 1
    assert result["bookmakers_offering_btts"] == ["BookA"]


def test_event_discovery_survives_a_failing_event_without_fabricating() -> None:
    class Missing:
        status_code = 404

        def json(self) -> dict:
            return {}

    result = discover_event_markets(
        [{"provider_event_id": "e1"}, {"provider_event_id": "e2"}],
        api_key=SECRET,
        requester=lambda url, **kwargs: Missing(),
    )

    assert result["events_with_btts"] == 0
    assert all(item["has_btts"] is False for item in result["events"])


def test_event_discovery_never_leaks_the_key_into_errors() -> None:
    def boom(url: str, **kwargs: object):
        raise OSError("network down")

    result = discover_event_markets(
        [{"provider_event_id": "e1"}], api_key=SECRET, requester=boom
    )

    assert result["errors"]
    assert all(SECRET not in message for message in result["errors"])


def test_event_discovery_rejects_an_unapproved_host() -> None:
    with pytest.raises(DiscoveryError):
        discover_event_markets(
            [{"provider_event_id": "e1"}],
            api_key=SECRET,
            base_url="https://evil.example.com",
        )


# --- report ----------------------------------------------------------------


def test_report_writes_both_outputs_without_secrets(tmp_path: Path) -> None:
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps(WINDOW_EVENTS), encoding="utf-8")

    result = save_provider_market_discovery(
        raw_response_path=raw,
        output_dir=tmp_path,
        event_summary={"event_count": 3, "events_with_btts": 3},
    )

    for key in ("json", "markdown"):
        text = Path(result[key]).read_text(encoding="utf-8")
        assert SECRET not in text
        assert "apiKey" not in text
    assert result["summary"]["safety"]["odds_fabricated"] is False
    assert result["summary"]["safety"]["secrets_written_or_printed"] is False


def test_report_requires_a_raw_response_path() -> None:
    with pytest.raises(DiscoveryError):
        save_provider_market_discovery()


# --- provider ingestion of event markets -----------------------------------


def test_provider_merges_event_btts_into_the_bulk_payload() -> None:
    """Proves BTTS can be automated end-to-end, with no live call."""
    bulk = [_event("e1", "2026-08-21", "Arsenal", "Coventry City")]

    class BulkResponse:
        status_code = 200
        content = json.dumps(bulk).encode("utf-8")
        headers: dict[str, str] = {}

        def json(self):
            return bulk

    class EventResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "bookmakers": [
                    {
                        "key": "booka",
                        "title": "BookA",
                        "markets": [
                            {
                                "key": "btts",
                                "outcomes": [
                                    {"name": "Yes", "price": 110},
                                    {"name": "No", "price": -130},
                                ],
                            }
                        ],
                    }
                ]
            }

    def requester(url: str, **kwargs: object):
        return EventResponse() if "/events/" in url else BulkResponse()

    provider = OddsApiStagingProvider(
        environment={"EPL_ODDS_API_KEY": SECRET},
        requester=requester,
        include_event_markets=True,
    )
    events, raw_content, _ = provider._fetch_events()

    markets = {
        market["key"]
        for event in events
        for book in event["bookmakers"]
        for market in book["markets"]
    }
    assert "btts" in markets
    assert "h2h" in markets
    # Raw evidence must match what was normalised, or the checksum pair breaks.
    assert json.loads(raw_content.decode("utf-8")) == events
    assert SECRET not in raw_content.decode("utf-8")


def test_provider_skips_event_markets_when_not_requested() -> None:
    bulk = [_event("e1", "2026-08-21", "Arsenal", "Coventry City")]
    calls: list[str] = []

    class BulkResponse:
        status_code = 200
        content = json.dumps(bulk).encode("utf-8")
        headers: dict[str, str] = {}

        def json(self):
            return bulk

    def requester(url: str, **kwargs: object):
        calls.append(url)
        return BulkResponse()

    provider = OddsApiStagingProvider(
        environment={"EPL_ODDS_API_KEY": SECRET}, requester=requester
    )
    provider._fetch_events()

    # No per-event request means no extra quota spent by default.
    assert all("/events/" not in url for url in calls)


def test_provider_records_a_warning_when_an_event_market_call_fails() -> None:
    bulk = [_event("e1", "2026-08-21", "Arsenal", "Coventry City")]

    class BulkResponse:
        status_code = 200
        content = json.dumps(bulk).encode("utf-8")
        headers: dict[str, str] = {}

        def json(self):
            return bulk

    class Failing:
        status_code = 500

        def json(self) -> dict:
            return {}

    def requester(url: str, **kwargs: object):
        return Failing() if "/events/" in url else BulkResponse()

    provider = OddsApiStagingProvider(
        environment={"EPL_ODDS_API_KEY": SECRET},
        requester=requester,
        include_event_markets=True,
    )
    events, _, _ = provider._fetch_events()

    assert provider.event_market_warnings
    assert all(SECRET not in w for w in provider.event_market_warnings)
    # A failed fetch leaves the market missing rather than inventing it.
    markets = {
        market["key"]
        for event in events
        for book in event["bookmakers"]
        for market in book["markets"]
    }
    assert "btts" not in markets


# --- totals region probe ---------------------------------------------------


class _Response:
    """Minimal bulk-odds response for the region probe."""

    def __init__(self, payload, status: int = 200) -> None:
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_totals_probe_requires_a_credential() -> None:
    from epl_betting_lab.reports.provider_market_discovery import probe_totals_regions

    with pytest.raises(DiscoveryError):
        probe_totals_regions(api_key="", regions=["us"])


def test_totals_probe_reports_a_region_that_completes_the_line() -> None:
    from epl_betting_lab.reports.provider_market_discovery import probe_totals_regions

    def requester(url: str, **kwargs):
        region = kwargs["params"]["regions"]
        points = (2.5,) if region == "uk" else (3.5,)
        return _Response(
            [
                _event("e1", "2026-08-23", "Manchester City", "Bournemouth",
                       totals_points=points)
            ]
        )

    result = probe_totals_regions(
        api_key=SECRET, regions=["us", "uk"], requester=requester
    )

    assert result["fixtures_with_line_in_any_region"] == 1
    assert result["missing_in_every_region"] == []
    assert result["complete_in_any_region"] is True


def test_totals_probe_reports_a_fixture_missing_everywhere() -> None:
    from epl_betting_lab.reports.provider_market_discovery import probe_totals_regions

    def requester(url: str, **kwargs):
        return _Response(
            [
                _event("e1", "2026-08-23", "Manchester City", "Bournemouth",
                       totals_points=(3.5,))
            ]
        )

    result = probe_totals_regions(
        api_key=SECRET, regions=["us", "uk", "eu"], requester=requester
    )

    assert result["complete_in_any_region"] is False
    assert len(result["missing_in_every_region"]) == 1


def test_totals_probe_survives_a_rejected_credential() -> None:
    """A rotated key returns 401. That is reported, not raised, and no
    fixture is silently counted as covered."""
    from epl_betting_lab.reports.provider_market_discovery import probe_totals_regions

    class Rejected:
        status_code = 401

        def json(self):
            return []

    result = probe_totals_regions(
        api_key=SECRET, regions=["us"], requester=lambda url, **kw: Rejected()
    )

    assert result["errors"]
    assert result["complete_in_any_region"] is False
    assert SECRET not in " ".join(result["errors"])


def test_totals_probe_states_that_evidence_is_not_a_scope_change() -> None:
    from epl_betting_lab.reports.provider_market_discovery import probe_totals_regions

    result = probe_totals_regions(
        api_key=SECRET, regions=[], requester=lambda url, **kw: _Response([])
    )

    assert "reviewed scope change" in result["note"]


def test_discovery_workflow_is_dispatch_only_and_uploads_a_report() -> None:
    from pathlib import Path

    from epl_betting_lab.config import PROJECT_ROOT

    text = (
        PROJECT_ROOT / ".github" / "workflows" / "provider-market-discovery.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch" in text
    assert "schedule:" not in text
    assert "upload-artifact" in text


def test_totals_probe_names_the_books_carrying_the_line() -> None:
    """A region name is not actionable; a book name is.

    The operator either holds an account at a book or does not, so the decision
    needs book names rather than "uk".
    """
    from epl_betting_lab.reports.provider_market_discovery import probe_totals_regions

    def requester(url: str, **kwargs):
        return _Response(
            [
                _event("e1", "2026-08-21", "Arsenal", "Coventry City",
                       totals_points=(2.5,), books=("Bet365", "Pinnacle")),
                _event("e2", "2026-08-22", "Hull City", "Manchester United",
                       totals_points=(2.5,), books=("Bet365",)),
            ]
        )

    result = probe_totals_regions(
        api_key=SECRET, regions=["uk"], requester=requester
    )

    region = result["per_region"][0]
    # Bet365 covers both fixtures; Pinnacle only one.
    assert region["books_covering_every_fixture"] == ["Bet365"]
    assert region["books_with_line_by_fixture_count"]["Bet365"] == 2
    assert region["books_with_line_by_fixture_count"]["Pinnacle"] == 1
    assert result["books_covering_every_fixture"] == ["Bet365"]


def test_no_book_covers_every_fixture_is_reported_as_empty() -> None:
    from epl_betting_lab.reports.provider_market_discovery import probe_totals_regions

    def requester(url: str, **kwargs):
        return _Response(
            [
                _event("e1", "2026-08-21", "Arsenal", "Coventry City",
                       totals_points=(2.5,), books=("Bet365",)),
                _event("e2", "2026-08-22", "Hull City", "Manchester United",
                       totals_points=(3.5,), books=("Pinnacle",)),
            ]
        )

    result = probe_totals_regions(
        api_key=SECRET, regions=["uk"], requester=requester
    )

    assert result["books_covering_every_fixture"] == []
    assert result["complete_in_any_region"] is False


def test_probe_note_explains_why_books_are_named() -> None:
    from epl_betting_lab.reports.provider_market_discovery import probe_totals_regions

    result = probe_totals_regions(
        api_key=SECRET, regions=[], requester=lambda url, **kw: _Response([])
    )

    assert "actually bet with" in result["note"]
