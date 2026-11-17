"""The card's "What changed" names only selections the card prints.

The comparison indexes three sections, and the card prints two of them, and
only their staked rows. On 2026-11-16 the card said "Added: Bournemouth v
Nott'm Forest total_2_5 over" and "Moved section: Chelsea v Leeds total_2_5
under" above tables that held neither: one was a new pass, the other had moved
from a pass to a zero-stake lean. A reader looking for the added bet could not
find it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from epl_betting_lab.reports.card_history import archive_card, build_card_comparison
from epl_betting_lab.reports.card_notification import build_notification


FIRST = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
SECOND = FIRST + timedelta(hours=6)


def _pick(home="Arsenal", market="1x2", selection="home", units=0.1) -> dict:
    return {"home_team": home, "away_team": "Coventry", "market": market,
            "selection": selection, "american_odds": 150.0, "book": "FanDuel",
            "confidence_tier": "C", "calibrated_edge": 0.05, "suggested_units": units}


def _card(best=(), leans=(), passes=()) -> dict:
    return {"card_generated": True, "best_bets": list(best), "leans": list(leans),
            "passes_or_avoids": list(passes)}


def _compare(tmp_path: Path, first: dict, second: dict) -> dict:
    for card, moment in ((first, FIRST), (second, SECOND)):
        (tmp_path / "automated_card.json").write_text(json.dumps(card), encoding="utf-8")
        archive_card(output_dir=tmp_path, now=moment)
    return build_card_comparison(output_dir=tmp_path, now=SECOND)


def test_each_changed_row_says_whether_the_card_shows_it(tmp_path):
    summary = _compare(
        tmp_path,
        _card(best=[_pick("Hull")], passes=[_pick("Chelsea")]),
        _card(best=[_pick("Leeds")], leans=[_pick("Chelsea", units=0)], passes=[_pick("Hull")]),
    )
    added = {row["label"].split(" v ")[0]: row for row in summary["added"]}
    assert added["Leeds"]["shown"] is True
    moved = {row["label"].split(" v ")[0]: row for row in summary["moved_section"]}
    assert (moved["Hull"]["from_shown"], moved["Hull"]["to_shown"]) == (True, False)
    assert (moved["Chelsea"]["from_shown"], moved["Chelsea"]["to_shown"]) == (False, False)


def _body(tmp_path: Path, comparison: dict) -> str:
    (tmp_path / "soccer_card_task.json").write_text(json.dumps({
        "card_ready": True, "included_markets": ["1x2"], "excluded_markets": [],
        "best_bets": [_pick("Leeds")], "leans": [],
    }), encoding="utf-8")
    (tmp_path / "automated_card.json").write_text(
        json.dumps({"card_generated": True, "root_blocker": ""}), encoding="utf-8")
    (tmp_path / "automated_card_comparison.json").write_text(json.dumps(comparison), encoding="utf-8")
    return build_notification(output_dir=tmp_path, now=SECOND)["body"]


def test_a_change_the_card_does_not_print_is_not_named(tmp_path):
    body = _body(tmp_path, {
        "comparable": True,
        "added": [{"label": "Bournemouth v Nott'm Forest total_2_5 over", "shown": False},
                  {"label": "Leeds v Coventry 1x2 home", "shown": True}],
        "removed": [{"label": "Liverpool v Man United corners_1x2 home", "shown": False}],
        "moved_section": [
            {"label": "Chelsea v Leeds total_2_5 under", "from_shown": False, "to_shown": False,
             "from_section": "passes_or_avoids", "to_section": "leans"},
            {"label": "Hull v Brighton 1x2 draw", "from_shown": True, "to_shown": False,
             "from_section": "best_bets", "to_section": "passes_or_avoids"},
            {"label": "Wolves v Fulham btts yes", "from_shown": False, "to_shown": True,
             "from_section": "passes_or_avoids", "to_section": "best_bets"},
            {"label": "Spurs v Everton 1x2 away", "from_shown": True, "to_shown": True,
             "from_section": "leans", "to_section": "best_bets"},
        ],
        "price_changed": [], "unchanged_count": 3,
    })
    assert "Bournemouth" not in body
    assert "Liverpool v Man United" not in body
    assert "Chelsea v Leeds" not in body
    assert "**Added:** Leeds v Coventry 1x2 home" in body
    assert "**Dropped:** Hull v Brighton 1x2 draw" in body
    assert "**Added:** Wolves v Fulham btts yes" in body
    assert "**Moved:** Spurs v Everton 1x2 away (lean to best bet)" in body
    assert "Moved section" not in body
