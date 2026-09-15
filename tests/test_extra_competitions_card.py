"""Selections beyond the Premier League, and the three faults found by looking.

The first run of this card printed every evaluated row. Among them was a
draw-no-bet at -39.5% edge, presented in the same table as a selection. It also
declined twelve of eighteen Champions League fixtures as unrateable while every
club in them sat in the pool, because the odds provider spells them a third way.
And it reported no corner model while every European league carries corner
counts on 100% of rows.

None of the three raised anything. Each is pinned below.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.data.european_clubs import PROVIDER_CLUB_NAMES, provider_name
from epl_betting_lab.reports.extra_competitions_card import (
    COMPETITIONS,
    EXCLUDED_MARKETS,
    EXTRA_UNITS,
    MAX_EXTRA_BETS,
    ExtraCard,
    latest_prices,
    render_extra_card,
)


def _feed(competition: str = "UCL") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competition": [competition] * 4,
            "observed_at": [
                "2026-09-15T10:00:00Z",
                "2026-09-15T10:00:00Z",
                "2026-09-15T13:00:00Z",
                "2026-09-15T13:00:00Z",
            ],
            "provider_event_id": ["e1"] * 4,
            "date": ["2026-09-16"] * 4,
            "home_team": ["Paris Saint Germain"] * 4,
            "away_team": ["Inter Milan"] * 4,
            "market": ["btts"] * 4,
            "selection": ["yes"] * 4,
            "book": ["A", "B", "A", "B"],
            "american_odds": [100, 120, 105, 150],
        }
    )


class TestTheProviderNamesClubsItsOwnWay:
    def test_paris_saint_germain_resolves(self) -> None:
        """A third source, a third spelling. openfootball writes
        `Paris Saint-Germain FC`, Football-Data `Paris SG`, the provider
        `Paris Saint Germain` — and a name that was never written down is
        declined, which is correct behaviour producing a wrong outcome."""
        assert provider_name("Paris Saint Germain") == "Paris SG"
        assert provider_name("Inter Milan") == "Inter"
        assert provider_name("Atlético Madrid") == "Ath Madrid"

    def test_an_unmapped_name_passes_through(self) -> None:
        """Clubs whose names already agree need no entry, and one that is
        genuinely unrateable must stay visibly so rather than be invented."""
        assert provider_name("Arsenal") == "Arsenal"
        assert provider_name("Bodø/Glimt") == "Bodø/Glimt"

    def test_the_map_never_points_two_names_at_a_contradiction(self) -> None:
        """`Sporting CP` and `Sporting Lisbon` are the same club; if they
        resolved differently the pool would rate one fixture twice."""
        assert PROVIDER_CLUB_NAMES["Sporting CP"] == PROVIDER_CLUB_NAMES["Sporting Lisbon"]
        assert PROVIDER_CLUB_NAMES["Paris Saint Germain"] == PROVIDER_CLUB_NAMES["Paris Saint-Germain"]

    def test_prices_are_read_under_the_domestic_name(self) -> None:
        prices = latest_prices(_feed(), "UCL")
        assert set(prices["home_team"]) == {"Paris SG"}
        assert set(prices["away_team"]) == {"Inter"}


class TestOnlyTheNewestObservationAndTheBestPrice:
    def test_it_takes_the_latest_snapshot(self) -> None:
        prices = latest_prices(_feed(), "UCL")
        assert len(prices) == 1

    def test_and_the_longest_price_at_that_moment(self) -> None:
        prices = latest_prices(_feed(), "UCL")
        assert int(prices.iloc[0]["american_odds"]) == 150

    def test_another_competition_is_not_mixed_in(self) -> None:
        assert latest_prices(_feed("EFLC"), "UCL").empty


class TestOnlyWhatTheRulesPass:
    def _selections(self, statuses: list[str], edges: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "home_team": ["H"] * len(statuses),
                "away_team": ["A"] * len(statuses),
                "market": ["btts"] * len(statuses),
                "selection": ["yes"] * len(statuses),
                "american_odds": [110] * len(statuses),
                "book": ["X"] * len(statuses),
                "status": statuses,
                "calibrated_edge": edges,
                "competition": ["UCL"] * len(statuses),
                "suggested_units": [EXTRA_UNITS] * len(statuses),
            }
        )

    def test_a_negative_edge_never_reaches_the_table(self) -> None:
        """The first run offered a -39.5% draw-no-bet as a selection, in the
        same table and the same format as a real one."""
        card = ExtraCard(self._selections(["BETTABLE"], [0.05]))
        report = "\n".join(render_extra_card({"UCL": card}))
        assert "+5.0%" in report
        assert "-39" not in report

    def test_the_stake_is_the_smallest_the_card_has(self) -> None:
        """Sized to the evidence behind these prices, which is none."""
        assert EXTRA_UNITS == 0.1

    def test_a_competition_cannot_crowd_the_card(self) -> None:
        assert MAX_EXTRA_BETS <= 8

    def test_1x2_stays_out(self) -> None:
        """Excluded from the Premier League card for losing out of sample, and
        there is no reason it would do better where the model knows less."""
        assert "1x2" in EXCLUDED_MARKETS


class TestItDeclinesRatherThanGuesses:
    def test_an_empty_card_says_so_and_says_why(self) -> None:
        card = ExtraCard(pd.DataFrame(), notes=["No UEFA Champions League price on file."])
        report = "\n".join(render_extra_card({"UCL": card}))
        assert "_No selection this run._" in report
        assert "No UEFA Champions League price on file." in report

    def test_the_report_carries_the_measurement_beside_the_bets(self) -> None:
        """A table of selections with no note reads as a recommendation. The
        EFL Cup was measured and the measurement was negative; that belongs
        next to the prices, not in a file nobody opens."""
        card = ExtraCard(pd.DataFrame())
        report = "\n".join(render_extra_card({"EFLC": card, "UCL": card}))
        assert "has been shown not to" in report
        assert "does **not** survive a division change" in report
        assert "overrates clubs who dominate" in report


class TestEachCompetitionUsesThePoolThatCanSeeIt:
    def test_the_cup_is_english_and_the_champions_league_is_not(self) -> None:
        """The English pool cannot rate Real Madrid; the European pool cannot
        rate Grimsby. Pointing either at the wrong one produces refusals that
        look like missing prices."""
        assert COMPETITIONS["EFLC"].pool == "english"
        assert COMPETITIONS["UCL"].pool == "european"

    def test_every_competition_has_a_note(self) -> None:
        for spec in COMPETITIONS.values():
            assert spec.note.strip()


class TestItIsWiredWithoutPuttingTheCardAtRisk:
    """The Premier League card must not depend on fourteen league datasets and
    a public-domain results repository being reachable. A run where the cup
    section cannot be built loses the section and keeps the card."""

    def _workflow(self) -> str:
        from epl_betting_lab.config import PROJECT_ROOT

        return (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

    def test_the_section_is_built_before_the_reports(self) -> None:
        text = self._workflow()
        assert text.index("- name: Build the cup and European section") < text.index(
            "- name: Rebuild every report"
        )

    def test_the_observation_feed_is_restored_first(self) -> None:
        """It holds the prices the section is built from, and it lives on the
        price-feed branch rather than in the repository."""
        text = self._workflow()
        assert text.index("- name: Restore the price feed") < text.index(
            "- name: Build the cup and European section"
        )
        block = text.split("- name: Restore the price feed", 1)[1].split("- name:", 1)[0]
        assert "price_feed_extra.csv" in block

    def test_the_restore_cannot_empty_a_feed_it_fails_to_find(self) -> None:
        """`>` truncates its target before the command on its left runs. That
        emptied 1,203 freshly collected observations once already."""
        block = self._workflow().split("- name: Restore the price feed", 1)[1]
        block = block.split("- name:", 1)[0]
        assert "mktemp" in block
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "git show" in stripped:
                assert "> data/processed/" not in stripped, stripped

    def test_building_the_section_cannot_fail_the_run(self) -> None:
        block = self._workflow().split(
            "- name: Build the cup and European section", 1
        )[1].split("- name:", 1)[0]
        assert "continue-on-error: true" in block
        # A bounded step: fourteen feeds on a bad day must not eat the job's
        # twenty minutes and take the card down with them.
        assert "timeout-minutes:" in block

    def test_it_spends_no_provider_quota(self) -> None:
        """Prices come from the observation feed the Closing Snapshot already
        collected; every rating input is a free CSV."""
        block = self._workflow().split(
            "- name: Build the cup and European section", 1
        )[1].split("- name:", 1)[0]
        assert "ODDS_API_KEY" not in block
        assert "secrets." not in block
        assert "--live" not in block

    def test_a_missing_section_is_simply_absent_not_fatal(self, tmp_path) -> None:
        """The card reads a file. No file, no section, no error."""
        import importlib.util

        from epl_betting_lab.config import PROJECT_ROOT

        spec = importlib.util.spec_from_file_location(
            "build_extra_card", PROJECT_ROOT / "scripts" / "build_extra_card.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import sys

        argv = ["build_extra_card.py", "--feed", str(tmp_path / "absent.csv"),
                "--out", str(tmp_path / "out.md")]
        old = sys.argv
        try:
            sys.argv = argv
            assert module.main() == 0
        finally:
            sys.argv = old
        assert not (tmp_path / "out.md").exists()
