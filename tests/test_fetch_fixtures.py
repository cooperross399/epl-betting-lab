"""The upcoming slate is fetched, not typed, and never silently erased."""

from __future__ import annotations

from datetime import date

import pytest

from epl_betting_lab.data.fetch_fixtures import (
    FixturesUnavailable,
    parse_fixtures,
)


HEADER = b"Div,Date,Time,HomeTeam,AwayTeam,Referee\n"
FEED = HEADER + (
    b"B1,28/08/2026,19:45,Genk,Beveren,\n"
    b"E0,28/08/2026,20:00,Crystal Palace,Man City,A Madley\n"
    b"E0,29/08/2026,12:30,Liverpool,Nott'm Forest,S Barrott\n"
    b"E0,31/08/2026,20:00,Aston Villa,Arsenal,J Gillett\n"
    b"E0,24/08/2026,20:00,Fulham,Chelsea,M Oliver\n"
)


def test_only_the_english_top_flight_is_kept() -> None:
    fixtures = parse_fixtures(FEED, today=date(2026, 8, 28))

    assert set(fixtures["home_team"]) == {"Crystal Palace", "Liverpool", "Aston Villa"}
    assert "Genk" not in set(fixtures["home_team"])


def test_finished_fixtures_are_dropped() -> None:
    fixtures = parse_fixtures(FEED, today=date(2026, 8, 28))

    assert "Fulham" not in set(fixtures["home_team"])
    assert fixtures["date"].tolist() == ["2026-08-28", "2026-08-29", "2026-08-31"]


def test_dates_are_read_day_first() -> None:
    """Football-Data writes DD/MM/YYYY.

    Left to infer, pandas reads 03/08/2026 as March and moves the fixture five
    months — into a window nothing will ever select.
    """
    feed = HEADER + b"E0,03/08/2026,15:00,Arsenal,Chelsea,\n"

    fixtures = parse_fixtures(feed, today=date(2026, 8, 1))

    assert fixtures["date"].tolist() == ["2026-08-03"]


def test_the_shape_matches_what_the_card_reads() -> None:
    fixtures = parse_fixtures(FEED, today=date(2026, 8, 28))

    assert list(fixtures.columns) == ["date", "home_team", "away_team", "notes"]


def test_an_html_redirect_page_is_not_parsed_as_fixtures() -> None:
    """Football-Data answers some requests with a page, not a 404."""
    with pytest.raises(FixturesUnavailable):
        parse_fixtures(b"<html><body>Not here</body></html>", today=date(2026, 8, 28))


def test_a_feed_with_nothing_upcoming_refuses_rather_than_emptying_the_slate() -> None:
    """An empty result written over the file would erase the slate.

    That is the failure this module exists to end, so it is raised rather than
    returned and the caller keeps the previous slate.
    """
    with pytest.raises(FixturesUnavailable):
        parse_fixtures(FEED, today=date(2027, 1, 1))
