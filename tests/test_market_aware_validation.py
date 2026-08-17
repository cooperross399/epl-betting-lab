"""Market-aware completeness: an excluded market must not block eligible ones."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.current_odds_completeness import (
    build_current_odds_completeness,
)


FIXTURES = pd.DataFrame(
    [
        {"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Coventry"},
        {"date": "2026-08-22", "home_team": "Hull", "away_team": "Man United"},
    ]
)

SELECTIONS = {
    "1x2": ("home", "draw", "away"),
    "total_2_5": ("over", "under"),
    "btts": ("yes", "no"),
}


def _odds_csv(tmp_path: Path, markets, *, skip_totals_for=()) -> Path:
    rows = []
    for _, fixture in FIXTURES.iterrows():
        for market in markets:
            if market == "total_2_5" and fixture["home_team"] in skip_totals_for:
                continue
            for selection in SELECTIONS[market]:
                rows.append(
                    {
                        "date": fixture["date"],
                        "home_team": fixture["home_team"],
                        "away_team": fixture["away_team"],
                        "market": market,
                        "selection": selection,
                        "american_odds": "-110",
                        "closing_american_odds": "",
                        "book": "BookA",
                        "notes": "",
                    }
                )
    path = tmp_path / "odds.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_all_markets_mode_still_flags_a_missing_market(tmp_path: Path) -> None:
    """Default behaviour is unchanged when no eligible set is supplied."""
    path = _odds_csv(tmp_path, ("1x2", "total_2_5"))

    issues, summary = build_current_odds_completeness(path, fixtures=FIXTURES)

    assert summary["completion_percentage"] < 1.0
    assert "missing_expected_market_row" in set(issues["issue"])


def test_eligible_markets_mode_ignores_an_excluded_market(tmp_path: Path) -> None:
    """The core fix: 1X2 complete passes even though BTTS is absent."""
    path = _odds_csv(tmp_path, ("1x2",))

    issues, summary = build_current_odds_completeness(
        path, fixtures=FIXTURES, eligible_markets=["1x2"]
    )

    assert summary["completion_percentage"] == 1.0
    assert summary["matches_incomplete"] == 0
    assert "missing_expected_market_row" not in set(issues["issue"])


def test_incomplete_totals_do_not_block_a_1x2_and_btts_scope(tmp_path: Path) -> None:
    """The live situation: totals missing for one fixture, 1X2+BTTS complete."""
    path = _odds_csv(
        tmp_path, ("1x2", "total_2_5", "btts"), skip_totals_for=("Arsenal",)
    )

    _, all_markets = build_current_odds_completeness(path, fixtures=FIXTURES)
    _, eligible_only = build_current_odds_completeness(
        path, fixtures=FIXTURES, eligible_markets=["1x2", "btts"]
    )

    # All-markets mode blocks; market-aware mode passes.
    assert all_markets["completion_percentage"] < 1.0
    assert all_markets["matches_incomplete"] > 0
    assert eligible_only["completion_percentage"] == 1.0
    assert eligible_only["matches_incomplete"] == 0


def test_excluded_market_rows_are_not_judged(tmp_path: Path) -> None:
    """Rows for an excluded market must not raise issues of their own."""
    rows = []
    for _, fixture in FIXTURES.iterrows():
        for selection in SELECTIONS["1x2"]:
            rows.append(
                {
                    "date": fixture["date"],
                    "home_team": fixture["home_team"],
                    "away_team": fixture["away_team"],
                    "market": "1x2",
                    "selection": selection,
                    "american_odds": "-110",
                    "book": "BookA",
                }
            )
        # A blank totals price would normally be a serious error.
        rows.append(
            {
                "date": fixture["date"],
                "home_team": fixture["home_team"],
                "away_team": fixture["away_team"],
                "market": "total_2_5",
                "selection": "over",
                "american_odds": "",
                "book": "BookA",
            }
        )
    path = tmp_path / "odds.csv"
    pd.DataFrame(rows).to_csv(path, index=False)

    issues, summary = build_current_odds_completeness(
        path, fixtures=FIXTURES, eligible_markets=["1x2"]
    )

    serious = issues[issues["severity"] == "error"] if not issues.empty else issues
    assert serious.empty
    assert summary["completion_percentage"] == 1.0


def test_eligible_market_gaps_are_still_caught(tmp_path: Path) -> None:
    """Market-aware must not become permissive for the markets it does judge."""
    path = _odds_csv(tmp_path, ("1x2",))
    frame = pd.read_csv(path)
    frame = frame[~((frame["home_team"] == "Arsenal") & (frame["selection"] == "draw"))]
    frame.to_csv(path, index=False)

    issues, summary = build_current_odds_completeness(
        path, fixtures=FIXTURES, eligible_markets=["1x2"]
    )

    assert summary["completion_percentage"] < 1.0
    assert "missing_expected_market_row" in set(issues["issue"])


def test_blank_price_in_an_eligible_market_is_still_serious(tmp_path: Path) -> None:
    path = _odds_csv(tmp_path, ("1x2",))
    frame = pd.read_csv(path, dtype=str).fillna("")
    frame.loc[0, "american_odds"] = ""
    frame.to_csv(path, index=False)

    issues, _ = build_current_odds_completeness(
        path, fixtures=FIXTURES, eligible_markets=["1x2"]
    )

    assert "blank_american_odds" in set(issues["issue"])


def test_empty_eligible_set_demands_nothing(tmp_path: Path) -> None:
    """An explicit empty scope judges no market; callers fall back instead."""
    path = _odds_csv(tmp_path, ("1x2",))

    issues, summary = build_current_odds_completeness(
        path, fixtures=FIXTURES, eligible_markets=[]
    )

    serious = issues[issues["severity"] == "error"] if not issues.empty else issues
    assert serious.empty
    assert summary["matches_incomplete"] == 0
