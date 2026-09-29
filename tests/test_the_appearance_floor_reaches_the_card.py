"""MIN_MATCHES was measured, documented, and applied to nothing.

`_pool_for` fitted the whole `InternationalModel` in order to read one
baseline out of it, and returned three values that did not include
`fitted.rateable`. `InternationalModel.expected_goals` is the only place the
floor is enforced, and it is called from nowhere in src/ or scripts/ — so a
national team with three matches on file was rated off three matches and
priced like any other, because `PoissonGoalsModel.fit` puts every team in the
frame into `team_strengths` whatever its appearance count.

The floor's own docstring carries the measurement: under six appearances the
model loses 0.10 log-loss of skill against knowing nothing about the teams,
95% CI [+0.069, +0.154].

It binds on nothing today — all 55 UEFA Nations League sides clear twelve and
so do all 41 CONCACAF ones — which is exactly why it needs a test rather than
a production run to show it works.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.models.international_ratings import MIN_MATCHES
from epl_betting_lab.reports import extra_competitions_card as card_module
from epl_betting_lab.reports.extra_competitions_card import build_extra_card

HOME, AWAY = "France", "Spain"


def _matches(home_appearances: int) -> pd.DataFrame:
    """A pool where one side is thin and the other is not."""
    rows = []
    for i in range(40):
        rows.append(
            {
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                "home_team": AWAY if i >= home_appearances else HOME,
                "away_team": "Italy",
                "home_goals": 1,
                "away_goals": 1,
            }
        )
    return pd.DataFrame(rows)


def _feed() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competition": ["UNL"] * 2,
            "observed_at": ["2026-09-15T10:00:00Z"] * 2,
            "provider_event_id": ["e1"] * 2,
            "date": ["2026-09-16"] * 2,
            "home_team": [HOME] * 2,
            "away_team": [AWAY] * 2,
            "market": ["btts"] * 2,
            "selection": ["yes", "no"],
            "book": ["DraftKings"] * 2,
            "american_odds": [100, -120],
        }
    )


def _card(monkeypatch, *, home_appearances: int, rateable: set[str] | None):
    matches = _matches(home_appearances)
    monkeypatch.setattr(
        card_module,
        "_pool_for",
        lambda spec: (matches, card_module.INTERNATIONAL_RATINGS, None, rateable),
    )
    return build_extra_card(_feed(), "UNL", now=pd.Timestamp("2026-09-15T12:00:00Z"))


class TestAThinSideIsNotPriced:
    def test_a_side_under_the_floor_is_declined(self, monkeypatch) -> None:
        thin = MIN_MATCHES - 1
        card = _card(
            monkeypatch,
            home_appearances=thin,
            rateable={AWAY, "Italy"},
        )

        assert card.selections.empty
        assert f"{HOME} v {AWAY}" in card.unrated
        assert any(str(MIN_MATCHES) in note for note in card.notes)

    def test_a_thin_AWAY_side_is_declined_too(self, monkeypatch) -> None:
        """Checking only the home side passed every other test here.

        The fixture makes the home team the thin one, so `home not in
        rateable` alone satisfied all of them. Either side being unrateable
        makes the price wrong; the away side is not the safe half.
        """
        card = _card(
            monkeypatch,
            home_appearances=20,
            rateable={HOME, "Italy"},
        )

        assert card.selections.empty
        assert f"{HOME} v {AWAY}" in card.unrated

    def test_the_control_the_same_fixture_prices_when_both_sides_clear_it(
        self, monkeypatch
    ) -> None:
        """Without this, declining everything would pass the test above."""
        card = _card(
            monkeypatch,
            home_appearances=20,
            rateable={HOME, AWAY, "Italy"},
        )

        assert f"{HOME} v {AWAY}" not in card.unrated
        assert card.priced == 1

    def test_a_pool_with_no_floor_prices_as_before(self, monkeypatch) -> None:
        """Club pools have no appearance floor and must be unaffected."""
        card = _card(monkeypatch, home_appearances=20, rateable=None)

        assert card.priced == 1
        assert not any(str(MIN_MATCHES) in note for note in card.notes)


class TestTheFloorTravelsFromTheFit:
    def test_pool_for_returns_the_rateable_set_for_the_international_pool(self) -> None:
        """It was computed on the line above and dropped on the return.

        Stubbed pools cannot show this: the value has to come out of the real
        `_pool_for` or the wiring is untested.
        """
        import ast
        import inspect
        import textwrap

        source = textwrap.dedent(inspect.getsource(card_module._pool_for))
        tree = ast.parse(source)
        returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]

        assert "fitted.rateable" in source
        assert returns, "no return statements found; the parse is wrong"
        # Counted through the parser, not with `source.count("return")` —
        # that counted the word "returned" in the comment explaining the fix
        # and read 4 where there are 3 statements.
        for node in returns:
            assert isinstance(node.value, ast.Tuple), ast.dump(node)
            assert len(node.value.elts) == 4, (
                "every branch has to return four values or the unpack raises"
            )
