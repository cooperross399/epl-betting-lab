"""Prices for a round the fixture slate does not list yet do not block the card.

On 2026-11-27 Football-Data's fixtures feed listed only the weekend round
(27-29 November, ten fixtures) while the odds provider already priced the
midweek round (1-3 December). The selected window joins the two rounds (a
two-day gap), so the midweek prices reached the card input, validation found
no fixture for them (`fixture_not_found`, rows 312-316) and the whole Premier
League card was blocked: ten fixtures that were listed lost their picks
because five that were not had prices.

A pairing of two clubs the slate DOES list, on a fixture it does not, is a
round the feed has not published yet. Those rows are set aside and named on
the card. A team the slate does not know at all is a mapping fault and is
still left for validation to block, and so is a card input with nothing on
the slate, which is a stale slate (2026-09-01).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports import automated_card
from epl_betting_lab.reports.automated_card import render_automated_card


def _write(outputs: Path, name: str, payload: dict) -> None:
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / name).write_text(json.dumps(payload), encoding="utf-8")


def _evidence(outputs: Path) -> None:
    _write(
        outputs,
        "automated_card_input.json",
        {
            "card_input_written": True,
            "row_count": 4,
            "manual_entry_required": False,
            "eligibility": {
                "eligible_markets": ["1x2"],
                "excluded_markets": [],
                "markets": [],
            },
        },
    )
    _write(
        outputs,
        "provider_shadow_verification.json",
        {
            "staging_validation": {"verdict": "Ready", "handoff_eligible": True},
            "provider_policy": {"provider_allowed": True},
        },
    )


WEEKEND = [
    ("2026-11-28", "Arsenal", "Chelsea"),
    ("2026-11-29", "Liverpool", "Everton"),
]
MIDWEEK = [("2026-12-02", "Chelsea", "Liverpool")]


def _card_input(path: Path, fixtures) -> Path:
    rows = [
        {
            "date": day,
            "home_team": home,
            "away_team": away,
            "market": "1x2",
            "selection": "home",
            "american_odds": "120",
            "closing_american_odds": "",
            "book": "FanDuel",
            "notes": "",
        }
        for day, home, away in fixtures
    ]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _slate(path: Path, fixtures) -> Path:
    pd.DataFrame(
        [{"date": d, "home_team": h, "away_team": a} for d, h, a in fixtures]
    ).to_csv(path, index=False)
    return path


def _run(tmp_path: Path, monkeypatch, *, priced, listed):
    _evidence(tmp_path)
    card_input = _card_input(tmp_path / "card_input.csv", priced)
    slate = _slate(tmp_path / "upcoming_fixtures.csv", listed)
    seen: dict[str, pd.DataFrame] = {}
    picks = tmp_path / "picks.csv"
    pd.DataFrame(columns=["section", "home_team", "away_team", "market"]).to_csv(
        picks, index=False
    )

    def fake_report(**kwargs):
        seen["odds"] = pd.read_csv(kwargs["current_odds_path"], dtype=str)
        return {"csv": str(picks), "markdown": str(picks)}

    monkeypatch.setattr(automated_card, "run_thursday_best_bets_report", fake_report)
    monkeypatch.setattr(automated_card, "_provider_allowlisted_now", lambda *a, **k: True)
    summary = automated_card.build_automated_card(
        output_dir=tmp_path,
        card_input_path=card_input,
        fixtures_path=slate,
        staging_fixtures_path=tmp_path / "absent_staging.csv",
    )
    return summary, seen.get("odds")


def test_a_midweek_round_the_feed_has_not_listed_is_set_aside(tmp_path, monkeypatch):
    summary, odds = _run(tmp_path, monkeypatch, priced=WEEKEND + MIDWEEK, listed=WEEKEND)

    assert summary["card_generated"] is True
    pairs = set(zip(odds["home_team"], odds["away_team"]))
    assert pairs == {("Arsenal", "Chelsea"), ("Liverpool", "Everton")}
    assert summary["fixtures_not_on_slate"] == ["Chelsea v Liverpool (2026-12-02)"]
    text = render_automated_card(summary)
    assert "Chelsea v Liverpool (2026-12-02)" in text
    # The original card input is left as it was: nothing is rewritten in place.
    original = pd.read_csv(tmp_path / "card_input.csv", dtype=str)
    assert len(original) == 3


def test_a_team_the_slate_does_not_know_is_still_left_for_validation(
    tmp_path, monkeypatch
):
    unknown = [("2026-11-30", "Arsenal", "Nowhere Rovers")]
    summary, odds = _run(tmp_path, monkeypatch, priced=WEEKEND + unknown, listed=WEEKEND)

    assert "Nowhere Rovers" in set(odds["away_team"])
    assert summary.get("fixtures_not_on_slate", []) == []


def test_a_stale_slate_with_nothing_priced_on_it_is_left_for_validation(
    tmp_path, monkeypatch
):
    old = [("2026-11-01", "Chelsea", "Arsenal"), ("2026-11-02", "Everton", "Liverpool")]
    summary, odds = _run(tmp_path, monkeypatch, priced=WEEKEND, listed=old)

    assert len(odds) == 2
    assert summary.get("fixtures_not_on_slate", []) == []


def test_the_card_comment_names_what_was_set_aside(tmp_path):
    from epl_betting_lab.reports.card_notification import build_notification

    _write(
        tmp_path,
        "soccer_card_task.json",
        {"card_ready": True, "best_bets": [], "leans": []},
    )
    _write(
        tmp_path,
        "automated_card.json",
        {
            "card_generated": True,
            "fixtures_not_on_slate": ["Chelsea v Liverpool (2026-12-02)"],
        },
    )
    note = build_notification(output_dir=tmp_path)

    assert "Chelsea v Liverpool (2026-12-02)" in note["body"]
