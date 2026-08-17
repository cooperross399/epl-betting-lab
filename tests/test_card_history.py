"""Card history: a diff between runs must be a diff, not a recommendation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from epl_betting_lab.reports.card_history import (
    archive_card,
    build_card_comparison,
    render_card_comparison,
    save_card_comparison,
)


FIRST = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)
SECOND = FIRST + timedelta(hours=6)


def _pick(market="1x2", selection="home", price=150.0, book="FanDuel", **extra) -> dict:
    row = {
        "home_team": "Arsenal",
        "away_team": "Coventry",
        "market": market,
        "selection": selection,
        "american_odds": price,
        "book": book,
        "confidence_tier": "B",
    }
    row.update(extra)
    return row


def _card(best=(), leans=(), passes=()) -> dict:
    return {
        "card_generated": True,
        "best_bets": list(best),
        "leans": list(leans),
        "passes_or_avoids": list(passes),
    }


def _write_card(outputs: Path, card: dict) -> None:
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / "automated_card.json").write_text(json.dumps(card), encoding="utf-8")


def _archive_two(outputs: Path, first: dict, second: dict) -> None:
    _write_card(outputs, first)
    archive_card(output_dir=outputs, now=FIRST)
    _write_card(outputs, second)
    archive_card(output_dir=outputs, now=SECOND)


# --- archiving -------------------------------------------------------------


def test_archiving_writes_a_timestamped_copy(tmp_path: Path) -> None:
    _write_card(tmp_path, _card(best=[_pick()]))

    result = archive_card(output_dir=tmp_path, now=FIRST)

    assert result["archived"] is True
    assert "2026-08-17" in result["path"]
    assert (tmp_path / result["path"]).is_file()


def test_archiving_without_a_card_is_reported_not_raised(tmp_path: Path) -> None:
    result = archive_card(output_dir=tmp_path, now=FIRST)

    assert result["archived"] is False
    assert "reason" in result


def test_archiving_twice_keeps_both_runs(tmp_path: Path) -> None:
    _archive_two(tmp_path, _card(best=[_pick()]), _card(best=[_pick(price=120.0)]))

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    assert summary["archived_card_count"] == 2


# --- comparison ------------------------------------------------------------


def test_a_new_selection_is_reported_as_added(tmp_path: Path) -> None:
    _archive_two(
        tmp_path,
        _card(best=[_pick()]),
        _card(best=[_pick(), _pick(market="btts", selection="yes")]),
    )

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    assert len(summary["added"]) == 1
    assert "btts" in summary["added"][0]["label"]
    assert summary["removed"] == []


def test_a_dropped_selection_is_reported_as_removed(tmp_path: Path) -> None:
    _archive_two(
        tmp_path,
        _card(best=[_pick(), _pick(market="btts", selection="yes")]),
        _card(best=[_pick()]),
    )

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    assert len(summary["removed"]) == 1
    assert "btts" in summary["removed"][0]["label"]


def test_a_selection_moving_between_sections_is_reported(tmp_path: Path) -> None:
    """Best bet becoming a pass is exactly what a reader needs to notice."""
    _archive_two(tmp_path, _card(best=[_pick()]), _card(passes=[_pick()]))

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    moved = summary["moved_section"]
    assert len(moved) == 1
    assert moved[0]["from_section"] == "best_bets"
    assert moved[0]["to_section"] == "passes_or_avoids"


def test_price_movement_is_reported_separately_from_selection_change(
    tmp_path: Path,
) -> None:
    """A pick that merely got worse is not a pick that was dropped."""
    _archive_two(tmp_path, _card(best=[_pick(price=150.0)]), _card(best=[_pick(price=120.0)]))

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    assert summary["added"] == []
    assert summary["removed"] == []
    assert len(summary["price_changed"]) == 1
    assert summary["price_changed"][0]["from_price"] == 150.0
    assert summary["price_changed"][0]["to_price"] == 120.0


def test_a_book_change_is_carried_with_the_price_change(tmp_path: Path) -> None:
    _archive_two(
        tmp_path,
        _card(best=[_pick(price=150.0, book="FanDuel")]),
        _card(best=[_pick(price=160.0, book="DraftKings")]),
    )

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    change = summary["price_changed"][0]
    assert change["from_book"] == "FanDuel"
    assert change["to_book"] == "DraftKings"


def test_identical_cards_report_no_change(tmp_path: Path) -> None:
    card = _card(best=[_pick()])
    _archive_two(tmp_path, card, card)

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    assert summary["added"] == []
    assert summary["removed"] == []
    assert summary["price_changed"] == []
    assert summary["unchanged_count"] == 1
    assert any("identical" in note for note in summary["notes"])


def test_a_single_archive_is_not_comparable(tmp_path: Path) -> None:
    _write_card(tmp_path, _card(best=[_pick()]))
    archive_card(output_dir=tmp_path, now=FIRST)

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    assert summary["comparable"] is False
    assert summary["added"] == []
    assert any("at least two" in note.lower() for note in summary["notes"])


def test_no_archives_at_all_is_reported_not_raised(tmp_path: Path) -> None:
    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    assert summary["comparable"] is False
    assert summary["archived_card_count"] == 0


# --- it is a diff, not advice ----------------------------------------------


def test_the_comparison_makes_no_recommendation(tmp_path: Path) -> None:
    _archive_two(tmp_path, _card(best=[_pick()]), _card(best=[_pick(price=120.0)]))

    summary = build_card_comparison(output_dir=tmp_path, now=SECOND)

    assert summary["safety"]["recommendation_made"] is False
    assert summary["safety"]["card_regenerated"] is False
    assert summary["safety"]["provider_contacted"] is False


def test_rendered_report_states_it_reports_change_not_value(tmp_path: Path) -> None:
    _archive_two(tmp_path, _card(best=[_pick()]), _card(best=[_pick(price=120.0)]))

    text = render_card_comparison(
        build_card_comparison(output_dir=tmp_path, now=SECOND)
    )

    assert "reports change, not value" in text


def test_the_comparison_never_rewrites_the_current_card(tmp_path: Path) -> None:
    card = _card(best=[_pick()])
    _archive_two(tmp_path, card, card)
    before = (tmp_path / "automated_card.json").read_bytes()

    save_card_comparison(output_dir=tmp_path, now=SECOND)

    assert (tmp_path / "automated_card.json").read_bytes() == before


def test_save_writes_both_outputs(tmp_path: Path) -> None:
    _archive_two(tmp_path, _card(best=[_pick()]), _card(best=[_pick()]))

    result = save_card_comparison(output_dir=tmp_path, now=SECOND)

    assert Path(result["json"]).name == "automated_card_comparison.json"
    assert Path(result["markdown"]).name == "automated_card_comparison.md"
