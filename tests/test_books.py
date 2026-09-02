"""A bet may only be priced at a book Cooper can use.

The card recommends the best price across bookmakers, which is safe only while
every bookmaker is one he can bet at. Fetching the `eu` region for Pinnacle —
the sharp reference that makes reverse line movement measurable — puts prices
in the same feed that must never be staked.
"""

from __future__ import annotations

from epl_betting_lab.books import (
    BETTABLE_BOOKS,
    REFERENCE_BOOKS,
    is_bettable,
    is_reference,
    unknown_books,
)


def test_the_sharp_reference_is_never_bettable():
    """The whole hazard in one assertion: Pinnacle is US-unavailable, and a
    recommendation at a price he cannot take is worse than none, because it
    looks exactly like the ones he can."""
    assert not (BETTABLE_BOOKS & REFERENCE_BOOKS)
    assert is_reference("Pinnacle") and not is_bettable("Pinnacle")


def test_the_books_seen_in_a_live_us_fetch_are_all_bettable():
    live = {"BetMGM", "BetOnline.ag", "BetRivers", "BetUS", "Bovada", "Caesars",
            "DraftKings", "FanDuel", "Fanatics", "LowVig.ag", "MyBookie.ag"}
    assert live <= BETTABLE_BOOKS
    assert BETTABLE_BOOKS == live, "adding a book is a decision about where money is held"


def test_surrounding_whitespace_does_not_change_a_book_s_role():
    assert is_bettable(" FanDuel ") and is_reference("Pinnacle ")


def test_nothing_is_bettable_by_accident():
    for value in (None, "", "   ", "SomeNewEuropeanBook", 42):
        assert not is_bettable(value), value


def test_an_unrecognised_book_is_reported_rather_than_silently_dropped():
    """A new US book quietly ignored is real value lost with no trace — the
    failure mode this project keeps rediscovering."""
    found = unknown_books(["FanDuel", "Pinnacle", "NewUSBook", "NewUSBook", "", None])
    assert found == ["NewUSBook"]


def test_a_feed_of_only_known_books_reports_nothing():
    assert unknown_books(["FanDuel", "Pinnacle"]) == []


# --- the card may never quote a price that cannot be taken -------------------


def _quotes(pairs):
    import pandas as pd
    return pd.DataFrame([{"book": b, "american_odds": o} for b, o in pairs])


def test_a_better_price_at_an_unbettable_book_is_not_recommended():
    """The hazard in one test. If a sharp or European book is ever fetched, its
    price is usually the best one on the board — and it is the one price that
    must never reach the card, because it looks like the others and cannot be
    taken."""
    from epl_betting_lab.reports.automated_card_input import _best_quote

    best = _best_quote(_quotes([("Pinnacle", "+140"), ("FanDuel", "+120")]))
    assert best is not None and best["book"] == "FanDuel"


def test_a_selection_only_an_unbettable_book_priced_produces_no_row():
    """Better a missing pick than an unplayable one."""
    from epl_betting_lab.reports.automated_card_input import _best_quote

    assert _best_quote(_quotes([("Pinnacle", "+140")])) is None


def test_an_unrecognised_book_never_prices_a_bet_by_default():
    """A book has to be listed to be bettable. Silence is not consent: a name
    the provider starts returning tomorrow is unknown until someone decides."""
    from epl_betting_lab.reports.automated_card_input import _best_quote

    assert _best_quote(_quotes([("SomeNewBook", "+300")])) is None
