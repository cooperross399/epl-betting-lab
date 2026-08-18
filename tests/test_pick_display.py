"""Presentation rules for rendered picks.

Two defects motivated this module and are pinned here so they cannot come back:
a price stored as ``146.0`` printed as ``146.0`` rather than ``+146``, and a row
the model sized at 0 units was printed under the "Best bets" heading, where the
heading spoke louder than the stake.
"""

from __future__ import annotations

import json
from pathlib import Path

from epl_betting_lab.reports.automated_card import render_automated_card
from epl_betting_lab.reports.browser_status import build_status_html
from epl_betting_lab.reports.pick_display import (
    format_american_odds,
    is_stakeable,
    split_stakeable,
)
from epl_betting_lab.reports.run_summary import build_run_summary


def _flat(text: str) -> str:
    return " ".join(text.split())


def _pick(**overrides: object) -> dict[str, object]:
    row = {
        "home_team": "Arsenal",
        "away_team": "Coventry",
        "market": "1x2",
        "selection": "home",
        "confidence_tier": "B",
        "calibrated_model_prob": 0.5,
        "calibrated_edge": 0.05,
        "american_odds": 146.0,
        "book": "FanDuel",
        "suggested_units": 0.25,
    }
    row.update(overrides)
    return row


class TestFormatAmericanOdds:
    def test_positive_price_gets_an_explicit_plus(self) -> None:
        # The whole point: +146 is a price, 146.0 reads as a decimal price.
        assert format_american_odds(146.0) == "+146"

    def test_negative_price_keeps_its_sign(self) -> None:
        assert format_american_odds(-106.0) == "-106"

    def test_long_price_is_not_abbreviated(self) -> None:
        assert format_american_odds(1700.0) == "+1700"

    def test_string_from_a_csv_round_trip_is_accepted(self) -> None:
        assert format_american_odds("146.0") == "+146"
        assert format_american_odds("-106") == "-106"

    def test_already_signed_string_is_not_double_signed(self) -> None:
        assert format_american_odds("+146") == "+146"

    def test_missing_values_render_as_the_placeholder(self) -> None:
        assert format_american_odds(None) == "—"
        assert format_american_odds("") == "—"
        assert format_american_odds(float("nan")) == "—"
        assert format_american_odds(0) == "—"

    def test_placeholder_is_configurable_per_surface(self) -> None:
        assert format_american_odds(None, missing="-") == "-"

    def test_unparseable_text_is_shown_rather_than_hidden(self) -> None:
        # An odd price is worth seeing; silently blanking it loses information.
        assert format_american_odds("evens") == "evens"

    def test_a_bool_is_not_mistaken_for_a_price(self) -> None:
        assert format_american_odds(True) == "—"


class TestStakeableSplit:
    def test_zero_units_is_not_stakeable(self) -> None:
        assert is_stakeable(_pick(suggested_units=0.0)) is False

    def test_positive_units_is_stakeable(self) -> None:
        assert is_stakeable(_pick(suggested_units=0.1)) is True

    def test_missing_sizing_is_left_alone(self) -> None:
        # Absent sizing should not quietly demote a pick.
        assert is_stakeable(_pick(suggested_units=None)) is True
        assert is_stakeable(_pick(suggested_units="")) is True

    def test_unparseable_sizing_is_left_alone(self) -> None:
        assert is_stakeable(_pick(suggested_units="half")) is True

    def test_split_preserves_order_within_each_group(self) -> None:
        rows = [
            _pick(selection="a", suggested_units=0.5),
            _pick(selection="b", suggested_units=0.0),
            _pick(selection="c", suggested_units=0.1),
        ]
        stakeable, not_stakeable = split_stakeable(rows)
        assert [row["selection"] for row in stakeable] == ["a", "c"]
        assert [row["selection"] for row in not_stakeable] == ["b"]

    def test_split_drops_nothing(self) -> None:
        rows = [_pick(suggested_units=units) for units in (0.5, 0.0, 0.1, 0.0)]
        stakeable, not_stakeable = split_stakeable(rows)
        assert len(stakeable) + len(not_stakeable) == len(rows)


def _write_card(tmp_path: Path, best_bets: list[dict[str, object]]) -> None:
    (tmp_path / "epl_card_task.json").write_text(
        json.dumps(
            {
                "card_ready": True,
                "included_markets": ["1x2", "btts"],
                "excluded_markets": ["total_2_5"],
                "best_bets": best_bets,
                "leans": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "automated_card.json").write_text(
        json.dumps({"card_generated": True}), encoding="utf-8"
    )


class TestRunSummaryRendering:
    def test_prices_are_signed_in_the_job_summary(self, tmp_path: Path) -> None:
        _write_card(tmp_path, [_pick(american_odds=146.0)])
        summary = build_run_summary(output_dir=tmp_path)
        assert "| +146 |" in summary
        assert "146.0" not in summary

    def test_a_zero_unit_row_is_not_printed_as_a_best_bet(self, tmp_path: Path) -> None:
        _write_card(
            tmp_path,
            [
                _pick(selection="home", suggested_units=0.25),
                _pick(selection="draw", confidence_tier="Pass/Avoid", suggested_units=0.0),
            ],
        )
        summary = _flat(build_run_summary(output_dir=tmp_path))
        assert "Ranked but not stakeable (0u)" in summary
        # The staked pick appears above the split, the unstaked one below it.
        assert summary.index("| home |") < summary.index("Ranked but not stakeable")
        assert summary.index("Ranked but not stakeable") < summary.index("| draw |")

    def test_the_zero_unit_note_says_it_is_not_a_small_bet(self, tmp_path: Path) -> None:
        _write_card(tmp_path, [_pick(suggested_units=0.0)])
        summary = _flat(build_run_summary(output_dir=tmp_path))
        assert "not a small bet, it is no bet" in summary

    def test_no_extra_section_when_every_row_is_stakeable(self, tmp_path: Path) -> None:
        _write_card(tmp_path, [_pick(suggested_units=0.25)])
        assert "Ranked but not stakeable" not in build_run_summary(output_dir=tmp_path)

    def test_an_all_zero_section_still_reports_no_best_bets(self, tmp_path: Path) -> None:
        _write_card(tmp_path, [_pick(suggested_units=0.0)])
        summary = _flat(build_run_summary(output_dir=tmp_path))
        # Nothing is stakeable, so the reader must not be told there are best bets.
        assert "No best bets." in summary
        assert "Ranked but not stakeable (0u)" in summary


class TestCardMarkdownRendering:
    def _summary(self, best_bets: list[dict[str, object]]) -> str:
        return render_automated_card(
            {
                "card_generated": True,
                "window_label": "Matchweek 1",
                "best_bets": best_bets,
                "leans": [],
                "passes_or_avoids": [],
                "blockers": [],
                "included_markets": ["1x2"],
                "excluded_markets": [],
                "odds_source": "data/outputs/automated_card_input.json",
                "manual_odds_entry_required": False,
                "unit_suggestions": [],
                "exclusion_note": "",
            }
        )

    def test_prices_are_signed_in_the_card(self) -> None:
        assert "| +146 |" in self._summary([_pick(american_odds=146.0)])

    def test_negative_price_survives_the_card(self) -> None:
        assert "| -106 |" in self._summary([_pick(american_odds=-106.0)])

    def test_zero_unit_rows_are_split_out_of_the_card(self) -> None:
        text = _flat(
            self._summary(
                [
                    _pick(selection="home", suggested_units=0.25),
                    _pick(selection="draw", suggested_units=0.0),
                ]
            )
        )
        assert "Ranked but not stakeable (0u)" in text
        assert text.index("| home |") < text.index("Ranked but not stakeable")


class TestStatusPageRendering:
    def test_prices_are_signed_on_the_status_page(self, tmp_path: Path) -> None:
        _write_card(tmp_path, [_pick(american_odds=-106.0)])
        html = build_status_html(output_dir=tmp_path)
        assert ">-106<" in html

    def test_the_zero_unit_note_is_escaped_not_double_escaped(
        self, tmp_path: Path
    ) -> None:
        _write_card(tmp_path, [_pick(suggested_units=0.0)])
        html = build_status_html(output_dir=tmp_path)
        assert "Ranked but not stakeable (0u)" in html
        # The markdown emphasis must not leak into the HTML surface, and the
        # placeholder must not arrive pre-escaped.
        assert "**0 units**" not in html
        assert "&amp;mdash;" not in html
