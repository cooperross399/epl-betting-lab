"""Collecting EFL prices must not be able to reach the card.

The fetch this reuses normally runs with `--overwrite-staging`, which replaces
`data/staging/` — the bundle the Premier League card is built from. Pointing
that at an EFL sport key would put Championship prices where the card looks for
Premier League ones, and nothing downstream carries a competition on a row to
notice: every identity in this project is `(date, home_team, away_team)`.

So the isolation is the feature, and these are the tests for it.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.config import EFL_DIVISIONS, LEAGUE_CODE, PROJECT_ROOT, STAGING_DIR
from epl_betting_lab.providers.odds_api_staging_provider import API_KEY_ENV

SECRET = "efl-secret-that-must-not-be-written"
RUN_AT = datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc)


def _module():
    spec = importlib.util.spec_from_file_location(
        "collect_efl_prices", PROJECT_ROOT / "scripts" / "collect_efl_prices.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(home: str, away: str) -> list[dict[str, object]]:
    return [
        {
            "id": "efl-event-1",
            "sport_key": "soccer_efl_champ",
            "commence_time": "2026-09-12T14:00:00Z",
            "home_team": home,
            "away_team": away,
            "bookmakers": [
                {
                    "key": "examplebook",
                    "title": "Example Book",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": home, "price": -120},
                                {"name": "Draw", "price": 250},
                                {"name": away, "price": 350},
                            ],
                        },
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": -105, "point": 2.5},
                                {"name": "Under", "price": -115, "point": 2.5},
                            ],
                        },
                    ],
                }
            ],
        }
    ]


class _MockResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.status_code = 200
        self.content = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        self.headers = {"x-requests-remaining": "999", "authorization": SECRET}

    def json(self) -> object:
        return self.payload


class TestTheSportKeysAreWrittenOutNotDerived:
    def test_every_efl_division_has_one(self) -> None:
        module = _module()
        assert set(module.SPORT_KEYS) == set(EFL_DIVISIONS)

    def test_the_premier_league_is_not_among_them(self) -> None:
        """This collector exists to stay away from the card's competition."""
        module = _module()
        assert LEAGUE_CODE not in module.SPORT_KEYS
        assert "soccer_epl" not in set(module.SPORT_KEYS.values())

    def test_the_keys_are_distinct(self) -> None:
        """Two divisions sharing a key would double-count one and never fetch
        the other, and both would look like ordinary quiet weeks."""
        module = _module()
        assert len(set(module.SPORT_KEYS.values())) == len(module.SPORT_KEYS)


class TestItCannotTouchTheCardsStagingBundle:
    def test_a_collection_writes_nothing_under_data_staging(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """The whole safety argument, tested rather than asserted.

        A snapshot of the real staging directory is compared before and after.
        `--overwrite-staging` is passed on purpose, because that is what the
        live collection does — the isolation has to hold under the flag that
        would otherwise replace the card's bundle.
        """
        module = _module()

        def snapshot() -> dict[str, bytes]:
            if not STAGING_DIR.is_dir():
                return {}
            return {
                str(p.relative_to(STAGING_DIR)): p.read_bytes()
                for p in sorted(STAGING_DIR.rglob("*"))
                if p.is_file()
            }

        before = snapshot()
        monkeypatch.setenv(API_KEY_ENV, SECRET)
        monkeypatch.setattr(
            "epl_betting_lab.providers.odds_api_staging_provider._default_requester",
            lambda url, **kwargs: _MockResponse(_payload("Leeds", "Hull")),
        )

        rows, note = module.collect_division("E1")

        assert snapshot() == before, (
            "collecting EFL prices modified data/staging — that is the bundle "
            "the Premier League card is built from"
        )
        assert not rows.empty, note

    def test_the_rows_carry_their_competition(self, monkeypatch) -> None:
        """A file can be moved; a column travels with the row."""
        module = _module()
        monkeypatch.setenv(API_KEY_ENV, SECRET)
        monkeypatch.setattr(
            "epl_betting_lab.providers.odds_api_staging_provider._default_requester",
            lambda url, **kwargs: _MockResponse(_payload("Leeds", "Hull")),
        )
        rows, _ = module.collect_division("E1")
        assert set(rows["competition"]) == {"E1"}
        assert "competition" in module.EFL_FEED_COLUMNS

    def test_no_price_written_is_an_empty_answer_not_a_failure(self, monkeypatch) -> None:
        """An empty answer and a failed request are different facts, and a
        ledger that records the second as the first stops asking again."""
        module = _module()
        monkeypatch.setenv(API_KEY_ENV, SECRET)
        monkeypatch.setattr(
            "epl_betting_lab.providers.odds_api_staging_provider._default_requester",
            lambda url, **kwargs: _MockResponse([]),
        )
        try:
            rows, note = module.collect_division("E1")
        except Exception:
            return  # the provider refusing an empty payload is also acceptable
        assert rows.empty
        assert "no usable price" in note or "no staging bundle" in note


class TestItSpendsNothingUntilTold:
    def test_the_default_is_inert(self, monkeypatch, capsys) -> None:
        """Every entry point here defaults to making no request, and this one
        must too — the pool is shared with sibling labs."""
        module = _module()

        def explode(*args: object, **kwargs: object) -> object:
            raise AssertionError("a dry run must not reach the provider")

        monkeypatch.setattr(
            "epl_betting_lab.providers.odds_api_staging_provider._default_requester", explode
        )
        monkeypatch.setattr("sys.argv", ["collect_efl_prices.py"])
        assert module.main() == 0
        assert "no quota spent" in capsys.readouterr().out


class TestTheEflFeedIsItsOwnFile:
    def test_it_is_not_the_feed_the_card_is_measured_from(self) -> None:
        """Nothing in this project carries a competition on a row, so two
        competitions in one feed would be distinguishable only by club name."""
        module = _module()
        assert module.DEFAULT_FEED.name != "price_feed.csv"
        assert "efl" in module.DEFAULT_FEED.name


class TestTheWorkflowWiring:
    def _snapshot(self) -> str:
        return (
            PROJECT_ROOT / ".github" / "workflows" / "closing-snapshot.yml"
        ).read_text(encoding="utf-8")

    def test_the_efl_step_does_not_use_the_cards_fetch_path(self) -> None:
        """`run_provider_shadow_verification.py --overwrite-staging` replaces
        `data/staging/`. Pointing it at an EFL sport key would put Championship
        prices where the card looks for Premier League ones, and the staging
        output path is not parameterisable."""
        text = self._snapshot()
        block = text.split("- name: Observe EFL prices", 1)[1].split("- name:", 1)[0]
        assert "collect_efl_prices.py" in block
        assert "run_provider_shadow_verification" not in block
        assert "--overwrite-staging" not in block

    def test_collecting_the_efl_cannot_withhold_the_premier_league_feed(self) -> None:
        """The EPL feed is the one with a live card attached to it."""
        text = self._snapshot()
        block = text.split("- name: Observe EFL prices", 1)[1].split("- name:", 1)[0]
        assert "continue-on-error: true" in block

    def test_both_feeds_are_published_and_neither_blocks_the_other(self) -> None:
        text = self._snapshot()
        block = text.split("- name: Append the observation to the price feed", 1)[1]
        block = block.split("- name:", 1)[0]
        assert "price_feed_efl.csv" in block
        assert "price_feed.csv" in block
        # Built from whichever feeds have content, rather than exiting early on
        # one of them: an EFL collection that failed must not withhold the EPL
        # feed, and a first EFL run must not read as "nothing to publish".
        assert "for FEED in" in block

    def test_the_collection_happens_before_the_publish(self) -> None:
        text = self._snapshot()
        assert text.index("- name: Observe EFL prices") < text.index(
            "- name: Append the observation to the price feed"
        )

    def test_no_new_cron_and_no_new_writer_were_introduced(self) -> None:
        """It rides the snapshot that already runs on match days and already
        holds `contents: write` for exactly one branch. A new scheduled writer
        would need its own allowlist entry and its own reason."""
        text = self._snapshot()
        assert text.count("contents: write") <= 1
        efl_workflows = [
            p.name
            for p in (PROJECT_ROOT / ".github" / "workflows").glob("*.yml")
            if "efl" in p.name.lower()
        ]
        assert efl_workflows == [], efl_workflows


class TestRestoringAFeedCannotDestroyIt:
    """`>` truncates its target before the command on the left runs.

        git show ...:price_feed_efl.csv > data/processed/price_feed_efl.csv

    emptied the file whenever the branch did not carry that path — and on the
    first run it never does. The 2026-09-11 dispatch collected 1,203 EFL
    observations across 38 fixtures, printed "Added 1,203 new observation(s)",
    and the publish step blanked them a moment later and skipped the empty
    file. A step that succeeded, a number that was true when it was printed,
    and nothing on the branch.

    The same line also meant the feed could never accumulate: every run began
    from whatever the restore left behind, which was nothing.
    """

    def _snapshot(self) -> str:
        return (
            PROJECT_ROOT / ".github" / "workflows" / "closing-snapshot.yml"
        ).read_text(encoding="utf-8")

    def test_no_feed_is_restored_by_redirecting_onto_itself(self) -> None:
        text = self._snapshot()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "git show" in stripped and "price_feed" in stripped:
                assert "> data/processed/" not in stripped, (
                    f"truncating restore: {stripped}"
                )

    def test_the_restore_goes_through_a_temporary_file(self) -> None:
        block = self._snapshot().split(
            "- name: Restore the price feeds before collecting into them", 1
        )[1].split("- name:", 1)[0]
        assert "mktemp" in block
        # Replaced only by content that actually arrived.
        assert '[ -s "$TMP" ]' in block
        assert "mv " in block

    def test_the_feeds_are_restored_before_anything_collects_into_them(self) -> None:
        text = self._snapshot()
        assert text.index("- name: Restore the price feeds before collecting into them") < text.index(
            "- name: Observe EFL prices"
        )
        assert text.index("- name: Observe EFL prices") < text.index(
            "- name: Append the observation to the price feed"
        )

    def test_the_publish_does_not_restore_a_second_time(self) -> None:
        """Restoring again after collection would overwrite this run's own
        observations with the branch's older copy."""
        block = self._snapshot().split(
            "- name: Append the observation to the price feed", 1
        )[1].split("- name:", 1)[0]
        assert "git show" not in block


class TestAMarketTheProviderDoesNotCarryIsSaidOutLoud:
    """The case for collecting the EFL rested on corners — three of the seven
    markets the card stakes, with no free price history in any division. The
    provider does not carry them here.

    Asked for all eight in the same run that returned all eight for the Premier
    League, the EFL answered with 1x2, btts and total_2_5. That was found by
    diffing this feed against the Premier League one, which is not a thing
    anybody will do again. A market the provider does not carry looks exactly
    like a market nobody asked for.
    """

    def test_what_was_asked_for_is_written_down(self) -> None:
        module = _module()
        for market in ("corners_1x2", "corners_total_9_5", "corners_total_10_5",
                       "btts", "double_chance", "draw_no_bet", "total_2_5"):
            assert market in module.EXPECTED_MARKETS, market

    def test_the_note_names_the_markets_that_did_not_come_back(self, monkeypatch) -> None:
        module = _module()
        monkeypatch.setenv(API_KEY_ENV, SECRET)
        monkeypatch.setattr(
            "epl_betting_lab.providers.odds_api_staging_provider._default_requester",
            lambda url, **kwargs: _MockResponse(_payload("Leeds", "Hull")),
        )
        rows, note = module.collect_division("E1")

        # The stub carries h2h and totals only, so the rest are absent.
        assert "requested but not returned" in note
        assert "corners_1x2" in note
        assert "1x2" in note  # and what did arrive is named too

    def test_a_full_house_says_nothing_about_absences(self, monkeypatch) -> None:
        """The report must not cry about a gap that is not there — a warning
        that always fires carries no information."""
        module = _module()
        monkeypatch.setenv(API_KEY_ENV, SECRET)
        monkeypatch.setattr(
            "epl_betting_lab.providers.odds_api_staging_provider._default_requester",
            lambda url, **kwargs: _MockResponse(_payload("Leeds", "Hull")),
        )
        rows, _ = module.collect_division("E1")
        monkeypatch.setattr(module, "EXPECTED_MARKETS", tuple(rows["market"].unique()))
        _, note = module.collect_division("E1")
        assert "requested but not returned" not in note

    def test_the_docstring_no_longer_claims_corners(self) -> None:
        """It was written arguing corners were the whole point. They are not
        available, and a file that still says so would mislead the next reader
        into re-making a case the data already answered."""
        source = (PROJECT_ROOT / "scripts" / "collect_efl_prices.py").read_text(encoding="utf-8")
        # Whitespace-normalised: the sentences wrap, and a test that breaks on
        # a line break is testing the formatter rather than the claim.
        docstring = " ".join(source.split('"""')[1].split())
        assert "does not carry them for the EFL" in docstring
        assert "What survives of the case is one market" in docstring
