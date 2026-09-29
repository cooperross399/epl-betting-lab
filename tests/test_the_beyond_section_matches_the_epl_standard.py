"""The Beyond section was held to a looser standard than the card above it.

Two ways, both invisible from inside the section:

  * it priced at whatever book was longest, while the Premier League path
    filters to bettable books twice over. Pinnacle is always the longest
    price and can never be taken;
  * its staked rows sit three screen-lengths above a settled record built
    from the Premier League archive alone, under a sentence saying the only
    rows excluded are unstaked leans.

Every test here carries a control, because a filter test that only shows the
bad row disappearing passes just as well when everything disappears.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.books import is_bettable
from epl_betting_lab.reports.card_scoreboard import (
    ScoredSelection,
    Scoreboard,
    UncountedSection,
    render_scoreboard,
)
from epl_betting_lab.reports.extra_competitions_card import (
    BEYOND_SECTION_NAME,
    latest_prices,
    render_extra_card,
    uncounted_beyond,
    unbettable_books,
)

BETTABLE = "DraftKings"
#: On `books.REFERENCE_BOOKS`, never on the bettable list, and always the
#: longest price on the board — which is exactly why it wins an unfiltered
#: sort. `--regions eu` is one flag away at scripts/collect_extra_competitions.py.
UNBETTABLE = "Pinnacle"


def _feed(books: list[str], odds: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competition": ["UCL"] * len(books),
            "observed_at": ["2026-09-15T10:00:00Z"] * len(books),
            "provider_event_id": ["e1"] * len(books),
            "date": ["2026-09-16"] * len(books),
            "home_team": ["Paris Saint Germain"] * len(books),
            "away_team": ["Inter Milan"] * len(books),
            "market": ["btts"] * len(books),
            "selection": ["yes"] * len(books),
            "book": books,
            "american_odds": odds,
        }
    )


class TestItPricesOnlyAtBooksThatCanBeBet:
    def test_the_longest_price_is_skipped_when_it_cannot_be_taken(self) -> None:
        """The whole defect: longest wins, bettable was never asked."""
        assert not is_bettable(UNBETTABLE)

        priced = latest_prices(_feed([BETTABLE, UNBETTABLE], [100, 150]), "UCL")

        assert list(priced["book"]) == [BETTABLE]
        assert list(priced["american_odds"]) == [100]

    def test_the_control_the_same_row_at_a_bettable_book_is_kept(self) -> None:
        """Without this, dropping every row would pass the test above."""
        priced = latest_prices(_feed([BETTABLE, "FanDuel"], [100, 150]), "UCL")

        assert list(priced["american_odds"]) == [150]
        assert list(priced["book"]) == ["FanDuel"]

    def test_a_selection_only_an_unbettable_book_quotes_is_not_priced(self) -> None:
        """Declined, not fallen back onto. There is no price to fall back to."""
        assert latest_prices(_feed([UNBETTABLE], [150]), "UCL").empty

    def test_the_books_it_will_not_price_at_are_named(self) -> None:
        """A new US book quietly ignored is the reason `unknown_books` exists."""
        feed = _feed([BETTABLE, UNBETTABLE], [100, 150])

        assert unbettable_books(feed, "UCL") == [UNBETTABLE]
        assert unbettable_books(_feed([BETTABLE], [100]), "UCL") == []


class TestTheRecordSaysWhatItDoesNotCover:
    def _record(self, tmp_path: Path, units: list[float]) -> None:
        (tmp_path / "extra_competitions_card.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-09-29T00:00:00+00:00",
                    "selections": [{"suggested_units": u} for u in units],
                }
            ),
            encoding="utf-8",
        )

    def test_staked_beyond_selections_are_counted(self, tmp_path: Path) -> None:
        self._record(tmp_path, [0.1, 0.1, 0.1])
        section = uncounted_beyond(tmp_path)

        assert section is not None
        assert section.staked == 3
        assert section.name == BEYOND_SECTION_NAME

    def test_a_lean_is_not_counted_as_staked(self, tmp_path: Path) -> None:
        """The control. Otherwise this counts rows, not stakes."""
        self._record(tmp_path, [0.1, 0.0, 0.0])
        section = uncounted_beyond(tmp_path)

        assert section is not None and section.staked == 1

    def test_nothing_staked_says_nothing(self, tmp_path: Path) -> None:
        self._record(tmp_path, [0.0])

        assert uncounted_beyond(tmp_path) is None

    def test_no_record_says_nothing(self, tmp_path: Path) -> None:
        """A run before the section existed must not print a sentence."""
        assert uncounted_beyond(tmp_path) is None

    def test_the_section_is_named_once(self) -> None:
        """The scoreboard has to name the section the card heads with.

        Two spellings would drift, and the sentence would name a section the
        reader cannot find.
        """
        heading = render_extra_card({})

        assert f"## {BEYOND_SECTION_NAME}" in heading[0]


class TestTheScoreboardDisclosesTheGap:
    def _board(self) -> Scoreboard:
        """A board with something settled in it.

        An empty board renders to nothing at all, so asserting against one
        would pass whatever the code did — the first version of this test
        wrapped its assertions in `if rendered:` and checked nothing.
        """
        return Scoreboard(
            scored=[
                ScoredSelection(
                    fixture_date="2026-09-20",
                    home_team="Arsenal",
                    away_team="Chelsea",
                    market="1x2",
                    selection="home",
                    american_odds=-110,
                    stake_units=1.0,
                    first_seen="2026-09-19",
                    won=True,
                    profit_units=0.91,
                )
            ]
        )

    def test_the_board_renders_at_all(self) -> None:
        """Guards every assertion below. See `_board`."""
        assert render_scoreboard(self._board())

    def test_the_uncounted_section_is_named_with_its_count(self) -> None:
        rendered = "\n".join(
            render_scoreboard(
                self._board(), uncounted=[UncountedSection(BEYOND_SECTION_NAME, 5)]
            )
        )

        assert BEYOND_SECTION_NAME in rendered
        assert "5 staked selection(s)" in rendered

    def test_the_control_nothing_is_said_when_nothing_is_uncounted(self) -> None:
        """Otherwise the sentence is unconditional and means nothing."""
        rendered = "\n".join(render_scoreboard(self._board(), uncounted=[]))

        assert BEYOND_SECTION_NAME not in rendered

    def test_a_zero_count_says_nothing(self) -> None:
        rendered = "\n".join(
            render_scoreboard(
                self._board(), uncounted=[UncountedSection(BEYOND_SECTION_NAME, 0)]
            )
        )

        assert BEYOND_SECTION_NAME not in rendered


class TestTheDisclosureActuallyReachesTheCard:
    """The helper being right is not the same as the card using it.

    A mutant that changed the email's call to `uncounted=[]` — deleting the
    disclosure from every card that ships — passed every test above. The
    producer was tested; the line handing its result to the consumer was not.
    That is the third time in this repository, so it gets a test of its own
    rather than a note.
    """

    def _outputs(self, tmp_path: Path) -> Path:
        archive = tmp_path / "archive" / "automated_cards" / "2026-09-20" / "0900"
        archive.mkdir(parents=True)
        (archive / "automated_card.json").write_text(
            json.dumps(
                {
                    "card_generated": True,
                    "generated_at": "2026-09-20T09:00:00+00:00",
                    "best_bets": [],
                    "leans": [],
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "extra_competitions_card.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-09-29T00:00:00+00:00",
                    "selections": [{"suggested_units": 0.1} for _ in range(4)],
                }
            ),
            encoding="utf-8",
        )
        return tmp_path

    def _spy(self, monkeypatch) -> list:
        import epl_betting_lab.data.loaders as loaders
        import epl_betting_lab.reports.card_scoreboard as scoreboard

        # Both consumers wrap the scoreboard in a try/except, so a real
        # `load_matches` reading the project's own data file would make these
        # tests pass or fail on what happens to be on disk.
        monkeypatch.setattr(loaders, "load_matches", lambda *a, **k: pd.DataFrame())

        seen: list = []
        real = scoreboard.render_scoreboard

        def spy(board, *, uncounted=()):
            seen.append(list(uncounted))
            return real(board, uncounted=uncounted)

        monkeypatch.setattr(scoreboard, "render_scoreboard", spy)
        return seen

    def test_the_email_passes_the_uncounted_section(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # By basename, not `tests.…`: there is no `tests` package, so the
        # dotted form imports locally (rootdir on the path) and fails in
        # CI with ModuleNotFoundError. pytest's prepend import mode puts
        # the test directory on sys.path, which is what makes this work.
        from test_card_notification import NOW, _comparison, _write
        from epl_betting_lab.reports.card_notification import build_notification

        outputs = self._outputs(tmp_path)
        seen = self._spy(monkeypatch)
        _write(outputs, ready=True, comparison=_comparison(added=[{"label": "x"}]))

        build_notification(output_dir=outputs, now=NOW)

        assert seen, "the email never rendered a scoreboard, so this proves nothing"
        assert [s.staked for s in seen[0]] == [4]
        assert [s.name for s in seen[0]] == [BEYOND_SECTION_NAME]

    def test_the_run_summary_passes_it_too(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Both consumers. The summary carried the same number."""
        from epl_betting_lab.reports.run_summary import build_run_summary

        outputs = self._outputs(tmp_path)
        seen = self._spy(monkeypatch)

        build_run_summary(output_dir=outputs)

        assert seen, "the summary never rendered a scoreboard"
        assert [s.staked for s in seen[0]] == [4]


class TestTheUnbettableNoteReachesTheCard:
    """The helper was tested and the card's use of it was not.

    `unbettable_books` had four assertions on its return value and nothing
    asserted the card ever prints it, so deleting the call site was
    invisible — the producer tested, the line handing its result to the
    consumer not. Third time in one day for that shape.
    """

    def _card(self, monkeypatch, books: list[str]):
        import sys
        from pathlib import Path as _Path

        sys.path.insert(0, str(_Path(__file__).parent))
        from test_extra_competitions_card import _stub_international_pool

        from epl_betting_lab.reports.extra_competitions_card import build_extra_card

        _stub_international_pool(monkeypatch)
        feed = pd.DataFrame(
            {
                "competition": ["UNL"] * len(books),
                "observed_at": ["2026-09-15T10:00:00Z"] * len(books),
                "provider_event_id": ["evt-9"] * len(books),
                "date": ["2026-09-16"] * len(books),
                "home_team": ["France"] * len(books),
                "away_team": ["Spain"] * len(books),
                "market": ["double_chance"] * len(books),
                "selection": (["home_or_draw", "draw_or_away"] * len(books))[: len(books)],
                "book": books,
                "american_odds": ([120, -110] * len(books))[: len(books)],
            }
        )
        return build_extra_card(
            feed, "UNL", now=pd.Timestamp("2026-09-15T12:00:00Z")
        )

    def test_the_card_names_a_book_it_will_not_price_at(self, monkeypatch) -> None:
        card = self._card(monkeypatch, [BETTABLE, UNBETTABLE])

        assert any(UNBETTABLE in note for note in card.notes), card.notes

    def test_the_control_no_note_when_every_book_is_bettable(
        self, monkeypatch
    ) -> None:
        card = self._card(monkeypatch, [BETTABLE, "FanDuel"])

        assert not any("not on the bettable list" in note for note in card.notes)

    def test_an_all_unbettable_feed_says_why_rather_than_no_price(
        self, monkeypatch
    ) -> None:
        """The early return reported "No price on file", which is false.

        The feed was quoted all along; the filter emptied it. The note
        explaining that sat forty lines below a path this case never reaches.
        """
        card = self._card(monkeypatch, [UNBETTABLE, UNBETTABLE])

        joined = " ".join(card.notes)
        assert "No bettable" in joined, card.notes
        assert UNBETTABLE in joined
