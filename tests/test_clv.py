from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.clv import enrich_clv_bets, save_clv_reports, summarize_clv


def _sample_bets() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": "2026-08-21",
            "home_team": "Arsenal",
            "away_team": "Everton",
            "market": "1x2",
            "selection": "home",
            "american_odds": -110,
            "opening_american_odds": -110,
            "closing_american_odds": -130,
            "calibrated_edge": 0.05,
            "goal_environment_adjusted_edge": 0.05,
            "goal_environment_adjusted_would_bet": True,
            "won": True,
            "goal_environment_adjusted_profit_units": 0.91,
            "profit_units": 0.91,
        },
        {
            "date": "2026-08-22",
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "total_2_5",
            "selection": "over",
            "american_odds": 120,
            "opening_american_odds": 120,
            "closing_american_odds": pd.NA,
            "calibrated_edge": 0.07,
            "goal_environment_adjusted_edge": 0.07,
            "goal_environment_adjusted_would_bet": True,
            "won": False,
            "goal_environment_adjusted_profit_units": -1.0,
            "profit_units": -1.0,
        },
        {
            "date": "2026-08-23",
            "home_team": "Spurs",
            "away_team": "Wolves",
            "market": "btts",
            "selection": "yes",
            "american_odds": -105,
            "closing_american_odds": -115,
            "goal_environment_adjusted_would_bet": True,
            "won": True,
            "profit_units": 0.95,
        },
    ])


def test_enrich_clv_calculates_positive_probability_points() -> None:
    clv = enrich_clv_bets(_sample_bets())
    row = clv[clv["market"] == "1x2"].iloc[0]

    # BTTS is measured now that it is an allowlisted card market. It was
    # previously filtered out, so every BTTS bet was invisible to CLV.
    assert set(clv["market"]) == {"1x2", "total_2_5", "btts"}
    assert bool(row["has_closing_odds"]) is True
    assert row["clv_probability_points"] > 0
    assert row["clv_american_odds_movement"] == 20


def test_missing_closing_odds_stays_missing() -> None:
    clv = enrich_clv_bets(_sample_bets())
    row = clv[clv["market"] == "total_2_5"].iloc[0]

    assert bool(row["has_closing_odds"]) is False
    assert pd.isna(row["closing_implied_probability"])
    assert pd.isna(row["clv_probability_points"])


def test_summarize_clv_counts_missing_prices() -> None:
    summary = summarize_clv(enrich_clv_bets(_sample_bets()), ["market"])
    totals = summary[summary["market"] == "total_2_5"].iloc[0]

    assert totals["bets"] == 1
    assert totals["with_closing_odds"] == 0
    assert totals["missing_closing_odds"] == 1


def test_save_clv_reports(tmp_path) -> None:
    paths = save_clv_reports(_sample_bets(), tmp_path)

    assert paths["market"].name == "clv_by_market.csv"
    assert paths["selection"].name == "clv_by_selection.csv"
    assert paths["team"].name == "clv_by_team.csv"
    assert paths["markdown"].name == "clv_report.md"
    assert paths["market"].exists()
    assert paths["selection"].exists()
    assert paths["team"].exists()
    assert "Closing-Line Value Report" in paths["markdown"].read_text(encoding="utf-8")


# --- markets measured ------------------------------------------------------


def test_btts_is_measured_by_clv() -> None:
    """The card recommends BTTS, so CLV has to measure it.

    While CLV filtered to 1x2 and total_2_5, a BTTS bet could be recommended,
    placed, and settled without ever appearing in closing-line analysis.
    """
    from epl_betting_lab.reports.clv import CLV_MEASURED_MARKETS

    assert "btts" in CLV_MEASURED_MARKETS


def test_measured_markets_follow_the_supported_set() -> None:
    """A newly allowlisted market must not be silently excluded from CLV."""
    from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
    from epl_betting_lab.reports.clv import CLV_MEASURED_MARKETS

    assert set(CLV_MEASURED_MARKETS) == set(MARKET_SELECTIONS)


# --- per-book breakdown ----------------------------------------------------


def test_book_breakdown_groups_by_sportsbook() -> None:
    from epl_betting_lab.reports.clv import build_clv_book_breakdown, enrich_clv_bets

    clv = enrich_clv_bets(_sample_bets())
    breakdown = build_clv_book_breakdown(clv)

    assert "book" in breakdown.columns
    assert len(breakdown) >= 1


def test_a_missing_book_is_named_not_dropped() -> None:
    """A bet with no book still counts; it is attributed to 'unknown book'."""
    from epl_betting_lab.reports.clv import build_clv_book_breakdown, enrich_clv_bets

    bets = _sample_bets()
    bets["book"] = ""
    breakdown = build_clv_book_breakdown(enrich_clv_bets(bets))

    assert list(breakdown["book"]) == ["unknown book"]
    assert int(breakdown["bets"].sum()) > 0


def test_book_and_market_breakdown_separates_the_two() -> None:
    """A book strong at one market must not be credited for another."""
    from epl_betting_lab.reports.clv import (
        build_clv_book_market_breakdown,
        enrich_clv_bets,
    )

    breakdown = build_clv_book_market_breakdown(enrich_clv_bets(_sample_bets()))

    assert {"book", "market"}.issubset(breakdown.columns)


def test_book_breakdowns_are_empty_not_broken_without_bets() -> None:
    import pandas as pd

    from epl_betting_lab.reports.clv import (
        build_clv_book_breakdown,
        build_clv_book_market_breakdown,
    )

    empty = pd.DataFrame()

    assert build_clv_book_breakdown(empty).empty
    assert build_clv_book_market_breakdown(empty).empty


def test_rendered_report_includes_the_book_breakdown() -> None:
    """The CSVs existed but the human-readable report omitted them, which is
    where a person would actually look."""
    from epl_betting_lab.reports.clv import (
        build_clv_book_breakdown,
        build_clv_book_market_breakdown,
        enrich_clv_bets,
        render_clv_report,
        summarize_clv,
    )

    clv = enrich_clv_bets(_sample_bets())
    text = render_clv_report(
        summarize_clv(clv, ["market"]),
        summarize_clv(clv, ["market", "selection"]),
        summarize_clv(clv, ["market"]),
        summarize_clv(clv, ["market"]),
        summarize_clv(clv, ["market"]),
        build_clv_book_breakdown(clv),
        build_clv_book_market_breakdown(clv),
    )

    assert "## By book" in text
    assert "## By book and market" in text
    assert "where to take a price" in text


def test_rendered_report_still_works_without_book_data() -> None:
    from epl_betting_lab.reports.clv import (
        enrich_clv_bets,
        render_clv_report,
        summarize_clv,
    )

    clv = enrich_clv_bets(_sample_bets())
    summary = summarize_clv(clv, ["market"])

    text = render_clv_report(summary, summary, summary, summary, summary)

    assert "## By book" in text
    assert "No CLV rows available." in text
