"""The Beyond section's picks were recorded and never scored.

Both halves of the pair were on disk and nothing joined them: the picks in
`archive/extra_cards/<date>/<time>/extra_competitions_card.json`, the
near-kickoff prices in `price_feed_extra.csv`. `save_live_clv_reports` is
wired to the Premier League archive and the Premier League feed.

The join is the part that can silently produce nothing, so it is what these
tests mostly check — a CLV report of zero rows looks exactly like a section
with no picks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.beyond_clv import (
    as_cards,
    build_beyond_clv,
    load_beyond_records,
    save_beyond_clv_reports,
)

EVENT = "evt-1"
KICKOFF = "2026-09-20T18:00:00+00:00"
NOW = pd.Timestamp("2026-09-21T00:00:00Z")
#: When the card was written — before the closing observation, as a real
#: run is.
WRITTEN = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)


def _record(*, event: str = EVENT, units: float = 0.1, home: str = "Roma") -> dict:
    return {
        "generated_at": "2026-09-20T09:00:00+00:00",
        "selections": [
            {
                "competition": "UCL",
                "home_team": home,
                "away_team": "Inter",
                "market": "btts",
                "selection": "yes",
                "american_odds": 100,
                "book": "DraftKings",
                "provider_event_id": event,
                "kickoff_time": KICKOFF,
                "suggested_units": units,
            }
        ],
    }


def _feed(*, event: str = EVENT, home: str = "AS Roma", odds: int = -120) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competition": ["UCL"],
            "observed_at": ["2026-09-20T17:40:00Z"],
            "provider_event_id": [event],
            "date": ["2026-09-20"],
            # The PROVIDER's spelling, which is not the one the record holds.
            "home_team": [home],
            "away_team": ["Inter Milan"],
            "market": ["btts"],
            "selection": ["yes"],
            "book": ["DraftKings"],
            "american_odds": [odds],
        }
    )


class TestTheRecordBecomesSomethingScoreable:
    def test_a_staked_selection_produces_a_row(self) -> None:
        frame = build_beyond_clv([_record()], _feed(), now=NOW)

        assert len(frame) == 1
        assert frame.iloc[0]["market"] == "btts"

    def test_an_unstaked_row_is_not_a_recommendation(self) -> None:
        """The control. Otherwise this counts rows, not recommendations."""
        assert build_beyond_clv([_record(units=0.0)], _feed(), now=NOW).empty

    def test_the_cards_carry_the_records_generation_time(self) -> None:
        """`first_recommendations` scores at the first price a card offered."""
        cards = as_cards([_record()])

        assert cards[0]["card_generated"] is True
        assert cards[0]["generated_at"] == "2026-09-20T09:00:00+00:00"


class TestTheJoinSurvivesTheNameMap:
    """The trap this section has already fallen into once.

    The card maps the provider's club names onto Football-Data's before
    pricing, so the record says "Roma" where the feed says "AS Roma". A join
    on names finds nothing and reports a clean empty CLV table, which is
    indistinguishable from a section that made no picks. The freshness audit
    came back `unchecked: 3` on exactly this.
    """

    def test_a_renamed_club_still_finds_its_closing_price(self) -> None:
        frame = build_beyond_clv([_record(home="Roma")], _feed(home="AS Roma"), now=NOW)

        assert len(frame) == 1
        row = frame.iloc[0]
        assert row["closing_american_odds"] == -120
        assert row["clv_points_best"] is not None

    def test_the_control_a_different_event_does_not_join(self) -> None:
        """Without this, a join that matched everything would pass above."""
        frame = build_beyond_clv(
            [_record(event="evt-1")], _feed(event="evt-2", home="AS Roma"), now=NOW
        )

        assert len(frame) == 1
        assert pd.isna(frame.iloc[0]["closing_american_odds"]) or (
            frame.iloc[0]["closing_american_odds"] is None
        )


class TestItIsReadFromTheArchiveAndWritten:
    def _archive(self, tmp_path: Path) -> Path:
        root = tmp_path / "archive" / "extra_cards"
        (root / "2026-09-20" / "0900").mkdir(parents=True)
        (root / "2026-09-20" / "0900" / "extra_competitions_card.json").write_text(
            json.dumps(_record()), encoding="utf-8"
        )
        return root

    def test_the_archive_is_read(self, tmp_path: Path) -> None:
        records = load_beyond_records(self._archive(tmp_path))

        assert len(records) == 1
        assert records[0]["selections"][0]["provider_event_id"] == EVENT

    def test_a_missing_archive_is_empty_not_an_error(self, tmp_path: Path) -> None:
        assert load_beyond_records(tmp_path / "nothing") == []

    def test_the_report_says_what_it_is_for(self, tmp_path: Path) -> None:
        """The international pool's only possible evidence, stated as such."""
        paths = save_beyond_clv_reports([_record()], _feed(), tmp_path, now=NOW)
        body = paths["markdown"].read_text(encoding="utf-8")

        assert "Beyond the Premier League" in body
        assert "cannot be backtested" in body
        assert paths["detail"].exists() and paths["summary"].exists()


class TestTheStepIsInThePipeline:
    """A scorer nothing calls is the defect this fixes, one layer up."""

    def test_refresh_all_runs_it(self) -> None:
        from epl_betting_lab.reports.refresh_all import _steps

        names = [name for name, _label, _fn in _steps()]

        assert "beyond_clv" in names

    def test_it_reads_the_extra_feed_not_the_premier_league_one(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Run the step and see which feed it asks for.

        Reading the source and splitting on `"),"` cut the text at
        `_beyond_records(),` and asserted against half a lambda. Running it
        cannot be fooled that way, and it also proves the step is callable —
        a step that raises on every run is the repo's favourite defect.
        """
        import epl_betting_lab.reports.price_feed as price_feed
        import epl_betting_lab.reports.refresh_all as refresh_all

        asked: list[str] = []

        def spy(path, *args, **kwargs):
            asked.append(str(path))
            return pd.DataFrame()

        # Patched before `_steps()`, which binds `load_feed` when it runs.
        monkeypatch.setattr(price_feed, "load_feed", spy)
        monkeypatch.setattr(refresh_all, "_beyond_records", lambda: [_record()])

        step = next(fn for name, _l, fn in refresh_all._steps() if name == "beyond_clv")
        step(tmp_path)

        assert asked == [str(refresh_all.PROCESSED_DIR / "price_feed_extra.csv")]
        assert (tmp_path / "beyond_clv_report.md").exists()


class TestTheEventIdComesFromProductionNotTheFixture:
    """Two mutants survived because every fixture above supplies it by hand.

    Deleting `provider_event_id` from `latest_prices`' columns, and deleting
    it from the record rows, both passed — the join tests built their record
    dicts literally, so nothing exercised the path that puts the id there.
    A fixture that supplies what production drops tests the fixture.

    These chain the real producer to the real consumer: a feed goes through
    `latest_prices`, the result becomes an `ExtraCard`, and the record is
    built from it.
    """

    def _priced(self) -> pd.DataFrame:
        from epl_betting_lab.reports.extra_competitions_card import latest_prices

        return latest_prices(_feed(home="AS Roma"), "UCL")

    def test_price_selection_carries_the_event_id(self) -> None:
        priced = self._priced()

        assert "provider_event_id" in priced.columns
        assert list(priced["provider_event_id"]) == [EVENT]

    def test_the_record_written_from_a_real_card_carries_it(self) -> None:
        from epl_betting_lab.reports.extra_competitions_card import (
            ExtraCard,
            extra_card_record,
        )

        priced = self._priced().assign(suggested_units=0.1, kickoff_time=KICKOFF)
        record = extra_card_record(
            {"UCL": ExtraCard(selections=priced, priced=1)}, now=WRITTEN
        )

        assert [r["provider_event_id"] for r in record["selections"]] == [EVENT]

    def test_and_that_record_joins_to_the_feed(self) -> None:
        """The whole point of carrying it: end to end, under a renamed club."""
        from epl_betting_lab.reports.extra_competitions_card import (
            ExtraCard,
            extra_card_record,
        )

        # The card's generation time has to precede the observation, or the
        # price is not "later" and there is no closing line to compare to.
        # Defaulting it to the present made this read as a pick made after
        # the market closed.
        priced = self._priced().assign(suggested_units=0.1, kickoff_time=KICKOFF)
        record = extra_card_record(
            {"UCL": ExtraCard(selections=priced, priced=1)}, now=WRITTEN
        )
        frame = build_beyond_clv([record], _feed(home="AS Roma"), now=NOW)

        assert len(frame) == 1
        assert frame.iloc[0]["closing_american_odds"] == -120


class TestTheEventIdSurvivesTheWholeBuilder:
    """The join was proven on a card production never builds.

    `TestTheEventIdComesFromProductionNotTheFixture` chains
    `latest_prices` -> `ExtraCard(...)` -> `extra_card_record`, and
    `build_extra_card` does not do that. It hands `prices` to
    `evaluate_btts` and friends, each of which writes its rows out from a
    FIXED key set — home_team, away_team, market, selection, odds, book and
    the grades — so a column added to `prices` does not survive evaluation.
    The record recorded "", and every Beyond CLV join fell back to names:
    the record says "Roma", the feed says "AS Roma", nothing matches, and an
    empty CLV table is indistinguishable from a section that made no picks.

    So this one runs the real builder.
    """

    def _card(self, monkeypatch):
        import sys

        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
        from test_extra_competitions_card import _stub_international_pool

        from epl_betting_lab.reports.extra_competitions_card import build_extra_card

        _stub_international_pool(monkeypatch)
        feed = pd.DataFrame(
            {
                "competition": ["UNL"] * 2,
                "observed_at": ["2026-09-15T10:00:00Z"] * 2,
                "provider_event_id": ["evt-77"] * 2,
                "date": ["2026-09-16"] * 2,
                "home_team": ["France"] * 2,
                "away_team": ["Spain"] * 2,
                "market": ["double_chance"] * 2,
                "selection": ["home_or_draw", "draw_or_away"],
                "book": ["DraftKings"] * 2,
                "american_odds": [120, -110],
            }
        )
        return build_extra_card(
            feed, "UNL", now=pd.Timestamp("2026-09-15T12:00:00Z")
        )

    def test_the_built_card_carries_the_event_id(self, monkeypatch) -> None:
        card = self._card(monkeypatch)

        assert not card.selections.empty, (
            "nothing was selected, so this proves nothing about the column"
        )
        assert "provider_event_id" in card.selections.columns
        assert set(card.selections["provider_event_id"]) == {"evt-77"}

    def test_and_the_record_written_from_it_does_too(self, monkeypatch) -> None:
        from epl_betting_lab.reports.extra_competitions_card import extra_card_record

        card = self._card(monkeypatch)
        record = extra_card_record({"UNL": card}, now=WRITTEN)

        assert record["selections"]
        for row in record["selections"]:
            assert row["provider_event_id"] == "evt-77", (
                "the record recorded an empty id, so the CLV join falls back "
                "to names the card has already renamed"
            )
