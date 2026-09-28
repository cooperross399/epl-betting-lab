"""The card priced fixtures that had already been played.

On 2026-09-28 at 18:17 UTC the card carried 22 selections and 8 of them were on
finished fixtures: three EFL Cup third-round ties from 15-16 September, a Europa
League matchday-1 tie from the 16th, and three Nations League fixtures from
25-27 September.

The cause was not the provider, a cache, a timezone or a window that stopped
advancing. It was that there was no freshness check at all. `latest_prices`
returns the newest OBSERVATION per fixture, and the feed is append-only — so for
a fixture that stopped being quoted, its last observation is still the newest
one, and it stayed eligible to be priced for as long as the feed existed.

A second fault rode along: the pool spanned rounds. The EFL Cup feed held the
third round and the fourth at the same time, which is why Peterborough United
appeared in two different fixtures (v Barnsley in round three, and as Bradford's
opponent in round four).

`tests/data/price_feed_extra_2026-09-28.csv` is real feed rows for the fixtures
named in that report, so these tests fail against the code as it was.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.reports.extra_competitions_card import (
    ROUND_GAP_DAYS,
    gate_slate,
)

#: The card whose output started this.
GENERATED_AT = pd.Timestamp("2026-09-28 18:17", tz="UTC")

FIXTURE = Path(__file__).parent / "data" / "price_feed_extra_2026-09-28.csv"

#: Fixture, competition, and the date it was actually played on. Results were
#: checked against footballwebpages.co.uk, and England v Spain against
#: englandfootball.com.
ALREADY_PLAYED = [
    ("EFLC", "Fleetwood Town", "Sheffield United", "2026-09-16"),
    ("EFLC", "Everton", "Wolves", "2026-09-16"),
    ("EFLC", "Ipswich", "Arsenal", "2026-09-15"),
    ("UEL", "Anderlecht", "Lyon", "2026-09-16"),
    ("UNL", "England", "Spain", "2026-09-26"),
    ("UNL", "Italy", "Belgium", "2026-09-25"),
    ("UNL", "Gibraltar", "Andorra", "2026-09-27"),
]


def _feed() -> pd.DataFrame:
    return pd.read_csv(FIXTURE)


def _rows(competition: str) -> pd.DataFrame:
    feed = _feed()
    return feed[feed["competition"] == competition]


def _labels(entries) -> set[str]:
    return {label.casefold() for label in entries}


class TestAPlayedFixtureNeverReachesPricing:
    @pytest.mark.parametrize(
        "competition, home, away, played_on",
        ALREADY_PLAYED,
        ids=[f"{c}-{h}-{a}" for c, h, a, _ in ALREADY_PLAYED],
    )
    def test_it_is_dropped_before_anything_is_priced(
        self, competition, home, away, played_on
    ) -> None:
        rows = _rows(competition)
        assert not rows.empty, f"the fixture file has no {competition} rows"

        gate = gate_slate(rows, now=GENERATED_AT)

        surviving = {
            (str(r.home_team).strip().casefold(), str(r.away_team).strip().casefold())
            for r in gate.kept.itertuples()
        }
        assert (home.casefold(), away.casefold()) not in surviving, (
            f"{home} v {away} was played on {played_on} and survived a gate run "
            f"at {GENERATED_AT}"
        )

    def test_the_fixture_file_really_contains_the_fault(self) -> None:
        """A regression test on a file that no longer holds the bad data is a
        test of nothing. Ungated, every one of these is still priceable."""
        for competition, home, away, _ in ALREADY_PLAYED:
            rows = _rows(competition)
            pairs = {
                (str(r.home_team).strip().casefold(), str(r.away_team).strip().casefold())
                for r in rows.itertuples()
            }
            assert (home.casefold(), away.casefold()) in pairs, (
                f"{home} v {away} is missing from the fixture file"
            )

    def test_the_fixtures_still_to_come_survive(self) -> None:
        """The gate has to be a filter, not a wall."""
        gate = gate_slate(_rows("UNL"), now=GENERATED_AT)

        surviving = {
            (str(r.home_team).strip().casefold(), str(r.away_team).strip().casefold())
            for r in gate.kept.itertuples()
        }
        assert ("wales", "norway") in surviving, (
            "Wales v Norway is on 1 October and was dropped"
        )

    def test_every_drop_is_counted_and_named(self) -> None:
        """A section that quietly dropped half its fixtures and one that was
        quoted half as many look identical on the card."""
        gate = gate_slate(_rows("EFLC"), now=GENERATED_AT)

        assert gate.played, "nothing was reported as dropped"
        assert "everton v wolves" in _labels(gate.played)
        assert gate.dropped == len(gate.played) + len(gate.unconfirmed) + len(
            gate.held_back
        )


class TestADateAloneCannotClearAFixture:
    """`date` is a day with no clock. The first version of this gate stamped a
    dated-only fixture at the END of its day, which made a 16:00 kickoff look
    like 23:59 and survive an 18:17 gate — admitting a finished game, the exact
    fault being fixed. It stamps the start of the day instead.
    """

    @staticmethod
    def _dated(date: str, commence: str | None = None) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "competition": "UNL",
                    "commence_time": commence if commence else pd.NA,
                    "date": date,
                    "home_team": "Spain",
                    "away_team": "France",
                    "market": "btts",
                    "selection": "yes",
                    "american_odds": 100,
                    "book": "Book",
                    "observed_at": "2026-09-28T06:00:00Z",
                }
            ]
        )

    def test_a_same_day_fixture_with_no_timestamp_is_withheld(self) -> None:
        gate = gate_slate(self._dated("2026-09-28"), now=GENERATED_AT)

        assert gate.kept.empty, (
            "a fixture dated today with no kickoff time was priced; a date "
            "cannot show it had not started"
        )

    def test_a_later_day_survives(self) -> None:
        gate = gate_slate(self._dated("2026-09-29"), now=GENERATED_AT)

        assert len(gate.kept) == 1

    def test_the_provider_timestamp_is_preferred_over_the_date(self) -> None:
        """With a real kickoff a same-day fixture still to come is priceable,
        which is the point of carrying it."""
        gate = gate_slate(
            self._dated("2026-09-28", commence="2026-09-28T19:45:00Z"),
            now=GENERATED_AT,
        )

        assert len(gate.kept) == 1

    def test_a_provider_timestamp_before_the_run_is_dropped(self) -> None:
        gate = gate_slate(
            self._dated("2026-09-28", commence="2026-09-28T16:00:00Z"),
            now=GENERATED_AT,
        )

        assert gate.kept.empty
        assert _labels(gate.played) == {"spain v france"}

    def test_a_pair_quoted_with_two_kickoffs_is_unconfirmed(self) -> None:
        """Same convention as the Premier League card: an ambiguous kickoff
        cannot show a game has not started."""
        rows = pd.concat(
            [
                self._dated("2026-10-01", commence="2026-10-01T18:45:00Z"),
                self._dated("2026-10-01", commence="2026-10-02T18:45:00Z"),
            ],
            ignore_index=True,
        )

        gate = gate_slate(rows, now=GENERATED_AT)

        assert gate.kept.empty
        assert _labels(gate.unconfirmed) == {"spain v france"}


class TestASlateIsOneRound:
    """The EFL Cup pool held round three and round four at once, which is why
    Peterborough United appeared in two fixtures.

    In the 2026-09-28 data the freshness gate resolves that on its own, because
    the earlier round was entirely played — so the flag itself needs constructed
    data, where two FUTURE rounds coexist. That happens whenever a competition
    quotes the next matchday before the current one is done.
    """

    @staticmethod
    def _two_rounds(second: str) -> pd.DataFrame:
        rows = []
        for home, away, commence in (
            ("Spain", "France", "2026-10-01T18:45:00Z"),
            ("Italy", "Belgium", "2026-10-02T18:45:00Z"),
            ("Wales", "Norway", second),
        ):
            rows.append(
                {
                    "competition": "UNL",
                    "commence_time": commence,
                    "date": commence[:10],
                    "home_team": home,
                    "away_team": away,
                    "market": "btts",
                    "selection": "yes",
                    "american_odds": 100,
                    "book": "Book",
                    "observed_at": "2026-09-28T06:00:00Z",
                }
            )
        return pd.DataFrame(rows)

    def test_a_later_round_is_held_back_and_flagged(self) -> None:
        gate = gate_slate(self._two_rounds("2026-11-15T18:45:00Z"), now=GENERATED_AT)

        assert gate.rounds == 2
        assert _labels(gate.held_back) == {"wales v norway"}
        surviving = {
            (str(r.home_team).casefold(), str(r.away_team).casefold())
            for r in gate.kept.itertuples()
        }
        assert surviving == {("spain", "france"), ("italy", "belgium")}

    def test_one_round_spread_over_a_few_days_is_not_two_rounds(self) -> None:
        """A Nations League window spans five days and a cup round three. The
        threshold has to sit above that and below the 28-day gap between Europa
        League matchdays."""
        gate = gate_slate(self._two_rounds("2026-10-05T18:45:00Z"), now=GENERATED_AT)

        assert gate.rounds == 1
        assert not gate.held_back
        assert len(gate.kept) == 3

    def test_the_threshold_sits_between_the_measured_spans(self) -> None:
        assert 5 < ROUND_GAP_DAYS < 28


class TestThePremierLeagueCardKeepsItsOwnGate:
    """It was not lucky. Across 111 archived Premier League cards and 1,506
    rows, none had a kickoff at or before the card that priced them, because
    `automated_card` already quarantines those. This guards that rather than
    adding a second mechanism beside it.
    """

    def test_the_quarantine_rule_is_still_there(self) -> None:
        source = (
            PROJECT_ROOT
            / "src"
            / "epl_betting_lab"
            / "reports"
            / "automated_card.py"
        ).read_text(encoding="utf-8")

        assert "KICKOFF_UNCONFIRMED_STATUS" in source
        assert "kickoff <= now" in source or "fact.kickoff <= now" in source

    def test_both_cards_treat_an_unconfirmed_kickoff_the_same_way(self) -> None:
        """Two sections withholding on different rules would be the harder bug
        to find later."""
        from epl_betting_lab.reports.automated_card import (
            KICKOFF_UNCONFIRMED_STATUS,
        )
        from epl_betting_lab.reports.extra_competitions_card import (
            KICKOFF_UNCONFIRMED,
        )

        assert KICKOFF_UNCONFIRMED == KICKOFF_UNCONFIRMED_STATUS


class TestTheCardItselfUsesTheGate:
    """`gate_slate` working and `build_extra_card` using it are two different
    facts, and only the first was tested — so replacing the gated rows with the
    ungated ones left the whole suite green. The same producer/consumer gap that
    let a competition baseline be computed and then ignored.
    """

    @staticmethod
    def _stub_pool(monkeypatch) -> None:
        """A tiny offline international pool, so no test reaches the network."""
        from epl_betting_lab.data.international_results import parse_archive
        from epl_betting_lab.models import international_ratings

        header = (
            "date,home_team,away_team,home_score,away_score,tournament,city,"
            "country,neutral"
        )
        rows = [
            f"20{15 + i // 12:02d}-{1 + i % 12:02d}-05,{home},{away},{hg},{ag},"
            f"{tournament},Town,Country,{neutral}"
            for home, away, hg, ag, neutral, tournament in (
                ("England", "Spain", 2, 1, "FALSE", "UEFA Nations League"),
                ("Spain", "England", 1, 1, "FALSE", "UEFA Nations League"),
                ("Wales", "Norway", 1, 1, "FALSE", "UEFA Nations League"),
                ("Norway", "Wales", 1, 2, "FALSE", "UEFA Nations League"),
                ("England", "Wales", 1, 1, "TRUE", "UEFA Nations League"),
                ("England", "Spain", 4, 0, "FALSE", "Friendly"),
                ("Wales", "Norway", 3, 1, "FALSE", "Friendly"),
                ("Spain", "Wales", 3, 0, "FALSE", "Friendly"),
                ("Norway", "England", 4, 1, "FALSE", "Friendly"),
            )
            for i in range(60)
        ]
        results = parse_archive("\n".join([header, *rows]) + "\n")
        monkeypatch.setattr(
            international_ratings,
            "load_international_results",
            lambda **kwargs: results,
        )
        monkeypatch.setattr(
            "epl_betting_lab.reports.extra_competitions_card.build_international_pool",
            lambda **kwargs: international_ratings.build_international_pool(
                results=results
            ),
        )

    def test_no_played_fixture_reaches_the_pricing_stage(self, monkeypatch) -> None:
        """Captured at the evaluator, which is the first thing downstream of the
        gate.

        An earlier version of this test patched the evaluator to RETURN England
        v Spain unconditionally and then asserted it was absent from the card —
        which the stub itself made impossible, so the test failed on its own
        fixture rather than on the code. What the gate can actually promise is
        that a played fixture is never offered to be priced.
        """
        from epl_betting_lab.reports.extra_competitions_card import build_extra_card

        self._stub_pool(monkeypatch)
        seen: dict[str, pd.DataFrame] = {}

        def capture(projections, odds, *args, **kwargs):
            seen["projections"] = projections.copy()
            return pd.DataFrame()

        monkeypatch.setattr(
            "epl_betting_lab.reports.extra_competitions_card.evaluate_draw_no_bet",
            capture,
        )

        build_extra_card(_rows("UNL"), "UNL", now=GENERATED_AT)

        assert "projections" in seen, "nothing was priced at all, so this proves nothing"
        priced = {
            (str(r.home_team).casefold(), str(r.away_team).casefold())
            for r in seen["projections"].itertuples()
        }
        assert ("england", "spain") not in priced, (
            "England v Spain was played on 26 September and was offered for "
            "pricing by a card generated on the 28th"
        )
        assert ("wales", "norway") in priced, (
            "the 1 October fixture was dropped too, so the gate is a wall"
        )

    def test_the_card_reports_what_the_gate_dropped(self, monkeypatch) -> None:
        from epl_betting_lab.reports.extra_competitions_card import build_extra_card

        self._stub_pool(monkeypatch)

        card = build_extra_card(_rows("UNL"), "UNL", now=GENERATED_AT)

        assert card.gate is not None, "the card does not carry the gate"
        assert card.gate.played, "the gate dropped nothing on a feed full of played ties"
        assert any("already kicked off" in note for note in card.notes), (
            "the card does not say how many fixtures it dropped"
        )


class TestTheBuildScriptRuns:
    """`build_extra_card.py` is the production entry point and nothing executed
    it. A one-line crash in it — `pd.Timestamp.utcnow().tz_localize("UTC")`,
    which raises because pandas already returns tz-aware — left the whole suite
    green while the script could not start. The same shape as the workflow step
    that died on its first command and reported success.
    """

    def test_main_completes_on_the_2026_09_28_feed(self, tmp_path, capsys) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "build_extra_card", PROJECT_ROOT / "scripts" / "build_extra_card.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        out = tmp_path / "extra_competitions_card.md"
        # main() reads argv, so drive it the way the workflow does
        import sys

        argv = sys.argv
        sys.argv = [
            "build_extra_card.py",
            "--feed",
            str(FIXTURE),
            "--out",
            str(out),
        ]
        try:
            exit_code = module.main()
        finally:
            sys.argv = argv

        assert exit_code == 0
        printed = capsys.readouterr().out
        assert "dropped" in printed, (
            "the run output does not report what the gate dropped per competition"
        )


def test_the_fixture_file_carries_no_key_shaped_value() -> None:
    """The provider's event ids are 32 hex characters, which the repository's
    secrets guard cannot tell from a credential — and it is right not to try.
    They are replaced with short synthetic ids; the gate never reads that column.

    This is here because the guard scans TRACKED files, so the suite passed
    locally while the file was still untracked and only went red in CI once it
    was committed. A test beside the file itself fails in either place.
    """
    import re

    body = FIXTURE.read_text(encoding="utf-8")

    assert not re.search(r"[0-9a-f]{32}", body), (
        "the fixture file contains a key-shaped value"
    )
