"""The status page is what a person actually reads, so it must not mislead."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epl_betting_lab.reports.browser_status import (
    build_status_html,
    save_status_html,
)


NOW = datetime(2026, 8, 17, 21, 30, tzinfo=timezone.utc)
KEY_SHAPED = "abcdef01" * 4


def _write(outputs: Path, name: str, payload: dict) -> None:
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / name).write_text(json.dumps(payload), encoding="utf-8")


def _pick(**overrides) -> dict:
    base = {
        "home_team": "Man City",
        "away_team": "Bournemouth",
        "market": "btts",
        "selection": "no",
        "confidence_tier": "B",
        "calibrated_model_prob": 0.52,
        "calibrated_edge": 0.041,
        "american_odds": 146.0,
        "book": "FanDuel",
        "suggested_units": 0.25,
    }
    base.update(overrides)
    return base


def _ready(outputs: Path, **overrides) -> None:
    card = {
        "card_ready": True,
        "card_status": "Ready",
        "manual_odds_entry_required": False,
        "included_markets": ["1x2", "btts"],
        "excluded_markets": ["total_2_5"],
        "best_bets": [_pick()],
        "leans": [_pick(market="1x2", selection="home", confidence_tier="C")],
        "passes_or_avoids": [],
        "blockers": [],
        "next_action": "Review the card.",
    }
    card.update(overrides)
    _write(outputs, "epl_card_task.json", card)
    _write(outputs, "epl_model_task.json", {"epl_card_ready": True, "blockers": []})
    _write(
        outputs,
        "automated_card.json",
        {
            "card_generated": True,
            "excluded_markets": ["total_2_5"],
            "exclusion_note": "Excluded markets are never passes or no-value calls.",
            "excluded_market_details": [
                {
                    "market": "total_2_5",
                    "usable_for_picks": False,
                    "reason": "covers 8 of 10 fixtures",
                }
            ],
        },
    )
    _write(
        outputs,
        "epl_settle_preview_task.json",
        {
            "mode": "Preview only",
            "open_bet_count": 0,
            "settled_bet_count": 0,
            "would_settle_count": 0,
            "preview_note": "Preview only.",
        },
    )


# --- it must be self-contained --------------------------------------------


def test_page_has_no_external_resources(tmp_path: Path) -> None:
    """It must open offline from a file:// URL."""
    _ready(tmp_path)

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert 'src="http' not in html
    assert 'href="http' not in html
    assert "@import" not in html
    assert "<script" not in html


def test_page_declares_a_charset_and_viewport(tmp_path: Path) -> None:
    _ready(tmp_path)

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert 'charset="utf-8"' in html
    assert "viewport" in html


# --- it must not leak ------------------------------------------------------


def test_a_clean_set_of_reports_produces_a_page_with_no_credential(
    tmp_path: Path,
) -> None:
    """The page adds no exposure of its own.

    It renders report text verbatim, so it cannot scrub a credential that a
    report already leaked - that is the secrets guard's job, upstream. What it
    must guarantee is that it introduces nothing key-shaped by itself.
    """
    _ready(tmp_path)

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert KEY_SHAPED not in html
    assert "apiKey" not in html
    assert "EPL_ODDS_API_KEY" not in html


def test_report_values_are_escaped_not_injected(tmp_path: Path) -> None:
    """Team and book names are data. Markup in them must not become markup."""
    _ready(tmp_path)
    _write(
        tmp_path,
        "epl_card_task.json",
        {
            "card_ready": True,
            "manual_odds_entry_required": False,
            "included_markets": ["1x2"],
            "excluded_markets": [],
            "best_bets": [_pick(home_team="<script>alert(1)</script>")],
            "leans": [],
            "passes_or_avoids": [],
            "blockers": [],
        },
    )

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --- it must be honest -----------------------------------------------------


def test_a_blocked_card_is_not_shown_as_a_card_with_no_value(
    tmp_path: Path,
) -> None:
    """The distinction the whole project turns on."""
    _ready(tmp_path)
    _write(
        tmp_path,
        "epl_card_task.json",
        {
            "card_ready": False,
            "blockers": ["Provider not trusted"],
            "included_markets": [],
            "excluded_markets": ["total_2_5"],
            "best_bets": [],
            "leans": [],
            "passes_or_avoids": [],
        },
    )

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert "No card was produced" in html
    assert "not a card with no value" in html
    assert "Provider not trusted" in html


def test_a_ready_card_renders_its_picks(tmp_path: Path) -> None:
    _ready(tmp_path)

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert "Man City" in html
    assert "FanDuel" in html
    assert "Best bets" in html


def test_excluded_market_reason_is_shown(tmp_path: Path) -> None:
    _ready(tmp_path)

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert "total_2_5" in html
    assert "covers 8 of 10 fixtures" in html
    assert "never passes or no-value calls" in html


def test_the_page_states_bets_are_never_placed(tmp_path: Path) -> None:
    _ready(tmp_path)

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert "no bet is ever placed" in html.lower()
    assert "settlement is never applied" in html.lower()


def test_missing_reports_render_a_blocked_page_not_a_crash(tmp_path: Path) -> None:
    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert "No card was produced" in html
    assert "Blocked" in html


def test_unreadable_report_is_survived(tmp_path: Path) -> None:
    (tmp_path / "epl_card_task.json").write_text("{not json", encoding="utf-8")

    html = build_status_html(output_dir=tmp_path, now=NOW)

    assert "<html" in html


# --- output ----------------------------------------------------------------


def test_save_writes_a_single_html_file(tmp_path: Path) -> None:
    _ready(tmp_path)

    result = save_status_html(output_dir=tmp_path, now=NOW)

    assert Path(result["html"]).name == "status.html"
    assert Path(result["html"]).is_file()
    assert result["bytes"] > 0


def test_output_is_deterministic_for_a_fixed_timestamp(tmp_path: Path) -> None:
    _ready(tmp_path)

    first = build_status_html(output_dir=tmp_path, now=NOW)
    second = build_status_html(output_dir=tmp_path, now=NOW)

    assert first == second
