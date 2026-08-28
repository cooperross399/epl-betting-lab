"""Coverage-scope separation, BTTS-unavailable handling, and Week 1 windowing."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.reports.provider_shadow_verification import (
    _btts_availability_metrics,
    _core_market_coverage_metrics,
    _slate_coverage_metrics,
)
from epl_betting_lab.reports.week1_launch_readiness import run_week1_launch_readiness
from epl_betting_lab.selected_slate import (
    filter_to_selected_window,
    outside_selected_window,
    selected_window,
    selected_window_label,
)


ROUND_ONE = [
    ("2026-08-21", "Arsenal", "Coventry"),
    ("2026-08-22", "Hull", "Man United"),
    ("2026-08-24", "Fulham", "Chelsea"),
]
ROUND_TWO = [
    ("2026-08-28", "Crystal Palace", "Man City"),
    ("2026-08-30", "Leeds", "Brentford"),
]


def _fixture_frame(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "home_team", "away_team"])


def _odds_frame(
    rows: list[tuple[str, str, str]],
    *,
    markets: tuple[str, ...] = ("1x2", "total_2_5"),
    book: str = "ExampleBook",
) -> pd.DataFrame:
    records = []
    for match_date, home, away in rows:
        for market in markets:
            selections = {
                "1x2": ("home", "draw", "away"),
                "total_2_5": ("over", "under"),
                "btts": ("yes", "no"),
            }[market]
            for selection in selections:
                records.append(
                    {
                        "date": match_date,
                        "home_team": home,
                        "away_team": away,
                        "market": market,
                        "selection": selection,
                        "american_odds": "-110",
                        "book": book,
                    }
                )
    return pd.DataFrame(records)


# --- selected window -------------------------------------------------------


def test_selected_window_is_the_round_still_to_be_played() -> None:
    frame = _fixture_frame(ROUND_ONE + ROUND_TWO)

    assert selected_window(frame["date"], today=date(2026, 8, 17)) == (
        date(2026, 8, 21),
        date(2026, 8, 24),
    )


def test_selected_window_moves_on_once_the_round_has_been_played() -> None:
    """The bug this replaces: a window written down once stops matching.

    Every provider price falls outside a window that has stopped moving, so
    every market reads `unavailable` and the card comes back Blocked with
    nothing wrong anywhere else.
    """
    frame = _fixture_frame(ROUND_ONE + ROUND_TWO)

    assert selected_window(frame["date"], today=date(2026, 8, 25)) == (
        date(2026, 8, 28),
        date(2026, 8, 30),
    )
    assert len(filter_to_selected_window(frame, today=date(2026, 8, 25))) == 2


def test_selected_window_holds_while_its_own_round_is_in_progress() -> None:
    frame = _fixture_frame(ROUND_ONE + ROUND_TWO)

    # Saturday of a Friday-to-Sunday round still describes the whole round,
    # so a card built mid-round covers the fixtures that are left.
    assert selected_window(frame["date"], today=date(2026, 8, 29)) == (
        date(2026, 8, 28),
        date(2026, 8, 30),
    )


def test_selected_window_falls_back_to_the_last_round_when_nothing_is_upcoming() -> None:
    frame = _fixture_frame(ROUND_ONE)

    assert selected_window(frame["date"], today=date(2027, 1, 1)) == (
        date(2026, 8, 21),
        date(2026, 8, 24),
    )


def test_window_filters_split_the_two_rounds() -> None:
    frame = _fixture_frame(ROUND_ONE + ROUND_TWO)
    today = date(2026, 8, 17)

    assert len(filter_to_selected_window(frame, today=today)) == 3
    assert len(outside_selected_window(frame, today=today)) == 2


def test_window_boundaries_are_inclusive() -> None:
    frame = _fixture_frame(
        [("2026-08-21", "A", "B"), ("2026-08-24", "C", "D"), ("2026-09-01", "E", "F")]
    )

    assert len(filter_to_selected_window(frame, today=date(2026, 8, 17))) == 2


def test_an_undated_frame_selects_nothing_rather_than_everything() -> None:
    frame = _fixture_frame([]).assign(date=[])

    assert selected_window(frame["date"], today=date(2026, 8, 17)) is None
    assert filter_to_selected_window(frame, today=date(2026, 8, 17)).empty


# --- coverage scopes -------------------------------------------------------


def test_coverage_scopes_use_different_denominators(tmp_path: Path) -> None:
    """The bug this fixes: 100% of provider-returned events read as 100% of slate."""
    manual = tmp_path / "data" / "manual"
    manual.mkdir(parents=True)
    _fixture_frame(ROUND_ONE + ROUND_TWO).to_csv(
        manual / "upcoming_fixtures.csv", index=False
    )

    # Provider returned only round one, and covered it completely.
    odds = _odds_frame(ROUND_ONE)
    staging_fixtures = _fixture_frame(ROUND_ONE)

    coverage = _slate_coverage_metrics(
        odds, staging_fixtures, repository_root=tmp_path, today=date(2026, 8, 17)
    )

    assert coverage["provider_returned"]["status"] == "Complete"
    assert coverage["provider_returned"]["coverage_percentage"] == 1.0

    assert coverage["selected_week1_window"]["expected_fixture_count"] == 3
    assert coverage["selected_week1_window"]["status"] == "Complete"

    # ...but the full file is only 3 of 5.
    assert coverage["full_upcoming_fixtures"]["expected_fixture_count"] == 5
    assert coverage["full_upcoming_fixtures"]["covered_fixture_count"] == 3
    assert coverage["full_upcoming_fixtures"]["status"] == "Incomplete"


def test_every_scope_names_its_denominator(tmp_path: Path) -> None:
    manual = tmp_path / "data" / "manual"
    manual.mkdir(parents=True)
    _fixture_frame(ROUND_ONE + ROUND_TWO).to_csv(
        manual / "upcoming_fixtures.csv", index=False
    )

    coverage = _slate_coverage_metrics(
        _odds_frame(ROUND_ONE), _fixture_frame(ROUND_ONE), repository_root=tmp_path
    )

    for key in (
        "provider_returned",
        "selected_week1_window",
        "full_upcoming_fixtures",
    ):
        assert coverage[key]["denominator"].strip()


def test_partial_window_coverage_warns_against_conflating_scopes(
    tmp_path: Path,
) -> None:
    manual = tmp_path / "data" / "manual"
    manual.mkdir(parents=True)
    _fixture_frame(ROUND_ONE + ROUND_TWO).to_csv(
        manual / "upcoming_fixtures.csv", index=False
    )

    # Provider returned one match; complete for itself, incomplete for the window.
    subset = ROUND_ONE[:1]
    coverage = _slate_coverage_metrics(
        _odds_frame(subset), _fixture_frame(subset), repository_root=tmp_path
    )

    assert coverage["provider_returned"]["status"] == "Complete"
    assert coverage["selected_week1_window"]["status"] == "Incomplete"
    assert any("not slate coverage" in w or "slate coverage" in w
               for w in coverage["warnings"])


def test_missing_upcoming_file_is_not_checked_rather_than_complete(
    tmp_path: Path,
) -> None:
    coverage = _slate_coverage_metrics(
        _odds_frame(ROUND_ONE), _fixture_frame(ROUND_ONE), repository_root=tmp_path
    )

    assert coverage["full_upcoming_fixtures"]["status"] == "Not checked"
    assert coverage["selected_week1_window"]["status"] == "Not checked"


# --- BTTS availability -----------------------------------------------------


def test_zero_btts_rows_report_unavailable_and_untrusted() -> None:
    odds = _odds_frame(ROUND_ONE, markets=("1x2", "total_2_5"))
    market_coverage = {"market_counts": {"1x2": 9, "total_2_5": 6, "btts": 0}}

    btts = _btts_availability_metrics(odds, market_coverage)

    assert btts["status"] == "Unavailable"
    assert btts["btts_row_count"] == 0
    assert btts["trusted"] is False
    assert btts["fabricated"] is False
    assert "manually" in btts["recommended_action"]
    assert "Never fabricate" in btts["recommended_action"]


def test_btts_available_when_rows_returned() -> None:
    odds = _odds_frame(ROUND_ONE, markets=("1x2", "btts"))
    market_coverage = {"market_counts": {"1x2": 9, "total_2_5": 0, "btts": 6}}

    btts = _btts_availability_metrics(odds, market_coverage)

    assert btts["status"] == "Available"
    assert btts["btts_row_count"] == 6
    assert btts["bookmakers_with_btts"] == ["ExampleBook"]


def test_btts_is_never_marked_trusted_even_when_available() -> None:
    odds = _odds_frame(ROUND_ONE, markets=("btts",))
    btts = _btts_availability_metrics(
        odds, {"market_counts": {"1x2": 0, "total_2_5": 0, "btts": 6}}
    )

    # Shadow output is untrusted regardless of availability.
    assert btts["trusted"] is False


def test_core_market_coverage_is_reported_separately_from_btts() -> None:
    market_coverage = {
        "market_counts": {"1x2": 9, "total_2_5": 6, "btts": 0},
        "missing_fixture_selections": [
            "2026-08-21: arsenal vs coventry | btts yes",
            "2026-08-21: arsenal vs coventry | btts no",
        ],
    }

    core = _core_market_coverage_metrics(market_coverage)

    # Only BTTS is missing, so the core markets are complete on their own terms.
    assert core["status"] == "Complete"
    assert core["missing_fixture_selections"] == []
    assert core["row_count"] == 15


def test_core_market_coverage_still_flags_missing_totals() -> None:
    market_coverage = {
        "market_counts": {"1x2": 9, "total_2_5": 4, "btts": 0},
        "missing_fixture_selections": [
            "2026-08-21: arsenal vs coventry | total_2_5 over",
            "2026-08-21: arsenal vs coventry | btts yes",
        ],
    }

    core = _core_market_coverage_metrics(market_coverage)

    assert core["status"] == "Incomplete"
    assert core["missing_fixture_selections"] == [
        "2026-08-21: arsenal vs coventry | total_2_5 over"
    ]


# --- Week 1 readiness warnings --------------------------------------------


def _run_readiness(tmp_path: Path, fixtures: list[tuple[str, str, str]]) -> dict:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    _fixture_frame(fixtures).to_csv(fixtures_path, index=False)
    odds_path = tmp_path / "current_odds.csv"
    result = run_week1_launch_readiness(
        fixtures_path=fixtures_path,
        current_odds_path=odds_path,
        output_dir=tmp_path / "outputs",
        today=date(2026, 8, 17),
    )
    return result["summary"]


def test_week1_counts_only_the_selected_window(tmp_path: Path) -> None:
    summary = _run_readiness(tmp_path, ROUND_ONE + ROUND_TWO)

    assert summary["upcoming_fixture_count"] == 5
    assert summary["selected_window_fixture_count"] == 3
    # The old fallback would have reported 5 here.
    assert summary["week1_fixture_count"] == 3


def test_week1_warns_about_fixtures_outside_the_window(tmp_path: Path) -> None:
    summary = _run_readiness(tmp_path, ROUND_ONE + ROUND_TWO)

    assert summary["fixtures_outside_selected_window_count"] == 2
    assert any("outside the selected Week 1 window" in w for w in summary["slate_warnings"])


def test_week1_warns_when_odds_template_spans_more_than_the_window(
    tmp_path: Path,
) -> None:
    summary = _run_readiness(tmp_path, ROUND_ONE + ROUND_TWO)

    # The template is built from all upcoming fixtures, so it spans both rounds.
    assert summary["odds_rows_outside_selected_window_count"] > 0
    assert any(
        "outside the selected Week 1 window" in w and "not modified" in w
        for w in summary["slate_warnings"]
    )


def test_week1_does_not_warn_when_slate_is_exactly_the_window(
    tmp_path: Path,
) -> None:
    summary = _run_readiness(tmp_path, ROUND_ONE)

    assert summary["fixtures_outside_selected_window_count"] == 0
    assert summary["odds_rows_outside_selected_window_count"] == 0
    assert not any("outside the selected Week 1 window" in w for w in summary["slate_warnings"])


def test_week1_never_overwrites_an_existing_odds_file(tmp_path: Path) -> None:
    fixtures_path = tmp_path / "upcoming_fixtures.csv"
    _fixture_frame(ROUND_ONE).to_csv(fixtures_path, index=False)
    odds_path = tmp_path / "current_odds.csv"
    odds_path.write_text("date,home_team,away_team\nkeep,me,please\n", encoding="utf-8")
    before = odds_path.read_bytes()

    run_week1_launch_readiness(
        fixtures_path=fixtures_path,
        current_odds_path=odds_path,
        output_dir=tmp_path / "outputs",
        today=date(2026, 8, 17),
    )

    assert odds_path.read_bytes() == before


def test_window_label_is_shared_between_reports(tmp_path: Path) -> None:
    summary = _run_readiness(tmp_path, ROUND_ONE)
    expected = selected_window_label(
        _fixture_frame(ROUND_ONE)["date"], today=date(2026, 8, 17)
    )
    assert summary["selected_window"] == expected
    assert expected == "2026-08-21 through 2026-08-24"
