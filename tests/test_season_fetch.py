"""Fetching the seasons the model is fitted on.

The season being played is published incrementally: before its first match
Football-Data answers with a redirect page rather than a 404, and
`raise_for_status` is silent on 3xx. Left unchecked that page is written to
disk as `E0.csv` and parsed as if it were results.

The asymmetry here is the point. The current season may be missing, because it
genuinely is until the season starts. A completed season may not, because its
absence would quietly shrink the training set.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datetime import date

from epl_betting_lab.config import (
    CURRENT_SEASON,
    DEFAULT_SEASONS,
    current_season_code,
    recent_season_codes,
)
from epl_betting_lab.data import fetch_football_data as fetcher


REDIRECT_PAGE = b"<html><head><title>300 Multiple Choices</title></head></html>"
RESULTS_CSV = (
    b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
    b"E0,16/08/2025,Arsenal,Chelsea,2,1,H\n"
)


class TestRecognisingAResultsCsv:
    def test_a_real_csv_is_accepted(self) -> None:
        assert fetcher._looks_like_a_results_csv(RESULTS_CSV) is True

    def test_a_redirect_page_is_rejected(self) -> None:
        assert fetcher._looks_like_a_results_csv(REDIRECT_PAGE) is False

    def test_an_empty_body_is_rejected(self) -> None:
        assert fetcher._looks_like_a_results_csv(b"") is False

    def test_a_csv_without_the_expected_columns_is_rejected(self) -> None:
        assert fetcher._looks_like_a_results_csv(b"a,b,c\n1,2,3\n") is False

    def test_leading_whitespace_does_not_hide_html(self) -> None:
        assert fetcher._looks_like_a_results_csv(b"\n\n  " + REDIRECT_PAGE) is False


class TestSeasonSchedule:
    def test_the_current_season_is_the_last_entry(self) -> None:
        assert DEFAULT_SEASONS[-1] == CURRENT_SEASON

    def test_the_schedule_reaches_the_season_being_played(self) -> None:
        """No longer a fixed value: it is derived, so it cannot go stale."""
        assert CURRENT_SEASON == current_season_code()

    def test_seasons_are_oldest_first(self) -> None:
        assert DEFAULT_SEASONS == sorted(DEFAULT_SEASONS)


def _stub_fetch(monkeypatch, unpublished: set[str]) -> None:
    def _fetch(season: str, league: str = "E0", raw_dir: Path | None = None) -> Path:
        if season in unpublished:
            raise fetcher.SeasonNotPublished(f"{season} is not published")
        path = fetcher.RAW_DIR / f"football_data_E0_{season}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(RESULTS_CSV)
        return path

    monkeypatch.setattr(fetcher, "fetch_season", _fetch)


class TestBuildingTheDataset:
    def test_an_unpublished_current_season_is_skipped(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(fetcher, "PROCESSED_DIR", tmp_path / "processed")
        _stub_fetch(monkeypatch, unpublished={"2627"})

        frame = fetcher.fetch_and_build_dataset(["2526", "2627"], force=True)

        assert set(frame["season"]) == {"2526"}

    def test_a_missing_completed_season_is_refused(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """Its absence would shrink the training set without anyone noticing."""
        monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(fetcher, "PROCESSED_DIR", tmp_path / "processed")
        _stub_fetch(monkeypatch, unpublished={"2425"})

        with pytest.raises(RuntimeError, match="Completed season 2425"):
            fetcher.fetch_and_build_dataset(["2425", "2526", "2627"], force=True)

    def test_a_total_outage_leaves_the_existing_dataset_alone(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(fetcher, "PROCESSED_DIR", tmp_path / "processed")
        _stub_fetch(monkeypatch, unpublished={"2627"})

        with pytest.raises(RuntimeError, match="No season could be fetched"):
            fetcher.fetch_and_build_dataset(["2627"], force=True)

        assert not (tmp_path / "processed" / "epl_historical_matches.csv").exists()

    def test_the_current_season_is_included_once_published(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path / "raw")
        monkeypatch.setattr(fetcher, "PROCESSED_DIR", tmp_path / "processed")
        _stub_fetch(monkeypatch, unpublished=set())

        frame = fetcher.fetch_and_build_dataset(["2526", "2627"], force=True)

        assert set(frame["season"]) == {"2526", "2627"}
        assert isinstance(frame, pd.DataFrame)


class TestTheSeasonRollsOverWithoutHelp:
    """A hardcoded season list does not fail when it goes stale.

    It silently keeps fitting the model on seasons that ended before the
    matches being predicted, and nothing in the output says so. That is the
    worst shape a defect can take in a system meant to run unattended, so the
    season is derived from the date instead of written down.
    """

    def test_today_is_unchanged_by_deriving_it(self) -> None:
        """The derivation must reproduce the list it replaced."""
        assert recent_season_codes(6, date(2026, 8, 19)) == [
            "2122",
            "2223",
            "2324",
            "2425",
            "2526",
            "2627",
        ]

    def test_a_new_season_is_picked_up_in_august(self) -> None:
        assert current_season_code(date(2027, 8, 1)) == "2728"

    def test_midseason_january_still_reports_the_season_that_started(self) -> None:
        assert current_season_code(date(2027, 1, 15)) == "2627"

    def test_june_still_reports_the_season_that_just_ended(self) -> None:
        """Seasons run August to May, so June belongs to the season gone by."""
        assert current_season_code(date(2026, 6, 30)) == "2526"

    def test_july_is_the_rollover_boundary(self) -> None:
        assert current_season_code(date(2026, 7, 1)) == "2627"

    def test_it_keeps_working_years_from_now(self) -> None:
        assert current_season_code(date(2030, 9, 10)) == "3031"

    def test_the_window_stays_the_requested_length(self) -> None:
        for count in (3, 5, 6, 10):
            assert len(recent_season_codes(count, date(2026, 8, 19))) == count

    def test_the_window_ends_with_the_current_season(self) -> None:
        moment = date(2028, 11, 2)
        assert recent_season_codes(6, moment)[-1] == current_season_code(moment)

    def test_the_window_is_oldest_first(self) -> None:
        codes = recent_season_codes(6, date(2026, 8, 19))
        assert codes == sorted(codes)
