"""A durable record of observed prices, and the CLV it makes possible.

Every CLV figure this project published came from `run_backtest.py` measuring
backtested bets against Football-Data closes — in-sample, and a different
population from the card. The live card's `closing_american_odds` was written
as the empty string by its only producer, 0 of 448 staged rows ever carried
one, so live CLV did not exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.reports.live_clv import (
    CAPTURED,
    NO_KICKOFF,
    NO_LATER_PRICE,
    NOT_PLAYED,
    build_live_clv,
    render_live_clv,
    summarize_live_clv,
)
from epl_betting_lab.reports.price_feed import (
    append_snapshot,
    event_id_from_notes,
    load_feed,
    observed_at,
    snapshot_rows,
)

NOTES = "the_odds_api event eb2553d10d63dc912b99f8fd0d675721; bookmaker betmgm; fetched 2026-08-17T16:39:44-04:00"


def _staged(rows):
    return pd.DataFrame(
        [{"date": "2026-09-05", "home_team": "H", "away_team": "A", "market": m,
          "selection": s, "american_odds": o, "book": b, "notes": NOTES}
         for m, s, o, b in rows]
    )


def _prov(when="2026-09-05T12:00:00+00:00"):
    return {"generated_at": when, "provider_name": "the_odds_api"}


# --- the feed ---------------------------------------------------------------


def test_the_event_id_is_recovered_from_the_notes_every_staged_row_carries():
    assert event_id_from_notes(NOTES) == "eb2553d10d63dc912b99f8fd0d675721"
    assert event_id_from_notes("no id here") == ""
    assert event_id_from_notes(None) == ""


def test_the_observation_time_comes_from_the_provenance_not_the_clock():
    """`harvest_historical_btts` files rows by the time it ASKED, which is
    harmless at a three-hour lead and a lie on a snapshot meant to be a close."""
    assert observed_at(_prov()).startswith("2026-09-05T12:00")
    assert observed_at({"generated_at": "not a time"}) == ""
    assert observed_at({}) == ""


def test_a_snapshot_without_a_readable_time_records_nothing():
    assert snapshot_rows(_staged([("btts", "yes", -110, "X")]), {}).empty


def test_unpriced_rows_are_dropped_rather_than_recorded_as_zero():
    staged = _staged([("btts", "yes", -110, "X"), ("btts", "no", None, "Y")])
    assert len(snapshot_rows(staged, _prov())) == 1


def test_appending_the_same_snapshot_twice_adds_nothing():
    """A retry after a failed push must not duplicate history."""
    snap = snapshot_rows(_staged([("btts", "yes", -110, "X")]), _prov())
    once = append_snapshot(load_feed(Path("/nonexistent")), snap)
    twice = append_snapshot(once, snap)
    assert len(once) == len(twice) == 1


def test_a_later_observation_of_the_same_price_is_kept_as_its_own_row():
    """The feed is a history, not a current-price table."""
    first = snapshot_rows(_staged([("btts", "yes", -110, "X")]), _prov("2026-09-05T09:00:00+00:00"))
    later = snapshot_rows(_staged([("btts", "yes", -105, "X")]), _prov("2026-09-05T12:00:00+00:00"))
    assert len(append_snapshot(append_snapshot(load_feed(Path("/none")), first), later)) == 2


# --- live CLV ---------------------------------------------------------------


def _card(market="btts", selection="yes", odds=-110, kickoff="2026-09-05T14:00:00+00:00",
          event="eb2553d10d63dc912b99f8fd0d675721", generated="2026-09-05T08:00:00+00:00"):
    return {
        "card_generated": True,
        "generated_at": generated,
        "best_bets": [{
            "home_team": "H", "away_team": "A", "market": market, "selection": selection,
            "american_odds": odds, "suggested_units": 0.25,
            "kickoff_time": kickoff, "provider_event_id": event,
        }],
    }


def _feed(rows, when="2026-09-05T13:40:00+00:00"):
    return snapshot_rows(_staged(rows), _prov(when))


NOW = pd.Timestamp("2026-09-06T00:00:00Z")


def test_a_price_that_shortened_after_the_pick_is_positive_clv():
    """Positive means the market moved toward the bet."""
    frame = build_live_clv([_card(odds=+120)], _feed([("btts", "yes", -110, "X")]), now=NOW)
    row = frame.iloc[0]
    assert row.state == CAPTURED and row.clv_points_best > 0


def test_a_price_that_drifted_is_negative_clv():
    frame = build_live_clv([_card(odds=-150)], _feed([("btts", "yes", +110, "X")]), now=NOW)
    assert frame.iloc[0].clv_points_best < 0


def test_the_lead_time_is_recorded_so_a_late_reading_cannot_pose_as_a_close():
    frame = build_live_clv([_card()], _feed([("btts", "yes", -110, "X")], when="2026-09-05T09:00:00+00:00"), now=NOW)
    assert frame.iloc[0].lead_minutes == pytest.approx(300.0)


def test_an_observation_after_kickoff_is_never_used():
    """GitHub delays crons by hours; a late snapshot must be ignored, not trusted."""
    frame = build_live_clv([_card()], _feed([("btts", "yes", -110, "X")], when="2026-09-05T15:00:00+00:00"), now=NOW)
    assert frame.iloc[0].state == NO_LATER_PRICE


def test_an_observation_before_the_pick_is_never_used():
    frame = build_live_clv([_card()], _feed([("btts", "yes", -110, "X")], when="2026-09-05T07:00:00+00:00"), now=NOW)
    assert frame.iloc[0].state == NO_LATER_PRICE


def test_the_best_price_across_books_is_the_like_for_like_comparator():
    """The card takes the best price, so the close it is judged against is too."""
    feed = _feed([("btts", "yes", -130, "X"), ("btts", "yes", -105, "Y")])
    row = build_live_clv([_card(odds=-110)], feed, now=NOW).iloc[0]
    assert row.closing_american_odds == -105


def test_the_consensus_comparator_is_computed_and_is_stricter():
    """Best-of-books is always longer than the fair midpoint, so comparing
    against best flatters CLV. Both are reported and both are named."""
    feed = _feed([("btts", "yes", -105, "X"), ("btts", "no", -105, "X")])
    row = build_live_clv([_card(odds=-110)], feed, now=NOW).iloc[0]
    assert row.clv_points_consensus is not None
    assert row.clv_points_consensus < row.clv_points_best


def test_a_fixture_that_has_not_kicked_off_is_its_own_state():
    frame = build_live_clv([_card()], _feed([("btts", "yes", -110, "X")]), now=pd.Timestamp("2026-09-05T10:00:00Z"))
    assert frame.iloc[0].state == NOT_PLAYED


def test_a_card_archived_before_kickoffs_were_recorded_says_so():
    """42 picks predate the join key. That is a known gap, not a blank cell."""
    frame = build_live_clv([_card(kickoff=None)], _feed([("btts", "yes", -110, "X")]), now=NOW)
    assert frame.iloc[0].state == NO_KICKOFF


def test_picks_join_on_the_event_id_not_on_team_names():
    """Team names are normalised differently by every source and the same
    pairing recurs every season."""
    feed = _feed([("btts", "yes", -105, "X")])
    feed.loc[:, "home_team"] = "Totally Different"
    row = build_live_clv([_card()], feed, now=NOW).iloc[0]
    assert row.state == CAPTURED


def test_corners_are_capturable_which_is_the_whole_point():
    """No source retains corner prices historically, so no corner rule can ever
    be profit-backtested — and corners are 23 of the first 42 best bets. Either
    the price is observed before kick-off or that market is unmeasurable."""
    frame = build_live_clv(
        [_card(market="corners_total_9_5", selection="over", odds=+100)],
        _feed([("corners_total_9_5", "over", -110, "X")]),
        now=NOW,
    )
    assert frame.iloc[0].state == CAPTURED and frame.iloc[0].clv_points_best > 0


def test_the_summary_counts_what_is_missing_as_loudly_as_what_is_not():
    frame = build_live_clv([_card(), _card(market="corners_1x2", selection="home", kickoff=None)],
                           _feed([("btts", "yes", -105, "X")]), now=NOW)
    summary = summarize_live_clv(frame)
    assert set(summary.columns) >= {"picks", "captured", "kickoff_unknown", "no_later_price"}
    assert int(summary["kickoff_unknown"].sum()) == 1


def test_an_empty_record_says_so_rather_than_implying_a_verdict():
    frame = build_live_clv([_card(kickoff=None)], load_feed(Path("/none")), now=NOW)
    text = render_live_clv(frame, summarize_live_clv(frame))
    assert "No closing observations yet" in text
    assert "not a judgement about the model" in text  # the gap must read as a gap


def test_the_report_names_both_comparators():
    frame = build_live_clv([_card()], _feed([("btts", "yes", -105, "X")]), now=NOW)
    text = render_live_clv(frame, summarize_live_clv(frame))
    assert "clv_points_best" in text and "clv_points_consensus" in text
    assert "best price across books" in text and "de-vigged consensus" in text


def test_the_refresh_produces_the_live_clv_report():
    """It has to run on its own each matchday, or the record never accumulates."""
    import tempfile
    from epl_betting_lab.reports.refresh_all import refresh_all_reports

    out = Path(tempfile.mkdtemp())
    result = refresh_all_reports(output_dir=out)
    step = next(s for s in result["steps"] if s["step"] == "live_clv")
    assert step["status"] == "ok", step.get("error")
    assert (out / "live_clv_report.md").is_file()
    assert (out / "live_clv_bets.csv").is_file()
