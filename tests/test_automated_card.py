"""Automated card generation: eligible markets only, never fabricated."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.automated_card import (
    _unit_suggestions,
    build_automated_card,
    render_automated_card,
    save_automated_card,
)
from epl_betting_lab.reports.scheduled_task_bridge import build_epl_card_task


def _write(outputs: Path, name: str, payload: dict) -> None:
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / name).write_text(json.dumps(payload), encoding="utf-8")


def _ready_evidence(outputs: Path, *, eligible=("1x2", "btts")) -> None:
    _write(
        outputs,
        "automated_card_input.json",
        {
            "card_input_written": True,
            "row_count": 50,
            "manual_entry_required": False,
            "eligibility": {
                "eligible_markets": list(eligible),
                "excluded_markets": ["total_2_5"],
                "unavailable_markets": [],
                "incomplete_markets": ["total_2_5"],
                "disabled_markets": [],
                "any_market_eligible": True,
                "markets": [
                    {
                        "market": "total_2_5",
                        "status": "incomplete",
                        "usable_for_picks": False,
                        "reason": "covers 8 of 10 fixtures",
                    }
                ],
            },
        },
    )
    _write(
        outputs,
        "provider_shadow_verification.json",
        {
            "staging_validation": {
                "verdict": "Ready for handoff",
                "handoff_eligible": True,
            },
            "provider_policy": {"provider_allowed": True},
        },
    )


# --- blocked states --------------------------------------------------------


def test_card_is_blocked_without_evidence(tmp_path: Path) -> None:
    summary = build_automated_card(output_dir=tmp_path)

    assert summary["card_generated"] is False
    assert summary["best_bets"] == []
    assert summary["leans"] == []
    assert summary["passes_or_avoids"] == []
    assert summary["unit_suggestions"] == []
    assert summary["blockers"]


def test_card_is_blocked_when_provider_is_not_allowlisted(tmp_path: Path) -> None:
    _ready_evidence(tmp_path)
    _write(
        tmp_path,
        "provider_shadow_verification.json",
        {
            "staging_validation": {
                "verdict": "Ready for handoff",
                "handoff_eligible": True,
            },
            "provider_policy": {"provider_allowed": False},
        },
    )

    summary = build_automated_card(output_dir=tmp_path)

    assert summary["card_generated"] is False
    assert any("allowlisted" in item for item in summary["blockers"])


def test_card_is_blocked_when_handoff_is_not_eligible(tmp_path: Path) -> None:
    _ready_evidence(tmp_path)
    _write(
        tmp_path,
        "provider_shadow_verification.json",
        {
            "staging_validation": {"verdict": "Needs fixes", "handoff_eligible": False},
            "provider_policy": {"provider_allowed": True},
        },
    )

    summary = build_automated_card(output_dir=tmp_path)

    assert summary["card_generated"] is False
    assert any("handoff" in item.lower() for item in summary["blockers"])


def test_card_is_blocked_when_no_market_is_eligible(tmp_path: Path) -> None:
    _ready_evidence(tmp_path, eligible=())

    summary = build_automated_card(output_dir=tmp_path)

    assert summary["card_generated"] is False
    assert any("No market is eligible" in item for item in summary["blockers"])


def test_blocked_card_markdown_says_nothing_was_produced(tmp_path: Path) -> None:
    text = render_automated_card(build_automated_card(output_dir=tmp_path))

    assert "No best bet, lean, pass, or stake was produced." in text


# --- exclusion semantics ---------------------------------------------------


def test_excluded_markets_are_not_no_value_calls(tmp_path: Path) -> None:
    _ready_evidence(tmp_path)
    summary = build_automated_card(output_dir=tmp_path)

    note = summary["exclusion_note"]
    assert "never presented as passes" in note
    assert "no-value" in note
    assert "total_2_5" in summary["excluded_markets"]
    # An excluded market must not appear among passes.
    assert all(
        item.get("market") != "total_2_5" for item in summary["passes_or_avoids"]
    )


def test_safety_flags_are_all_false(tmp_path: Path) -> None:
    safety = build_automated_card(output_dir=tmp_path)["safety"]

    assert safety["odds_fabricated"] is False
    assert safety["protected_files_written"] is False
    assert safety["bets_placed"] is False
    assert safety["settlement_applied"] is False
    assert safety["force_mode_used"] is False


def test_manual_odds_entry_is_never_required(tmp_path: Path) -> None:
    assert build_automated_card(output_dir=tmp_path)["manual_odds_entry_required"] is False


# --- unit suggestions ------------------------------------------------------


def test_unit_suggestions_reuse_the_pipeline_stake() -> None:
    """Staking comes from the existing pipeline, not a second model here."""
    picks = [
        {"home_team": "A", "away_team": "B", "market": "1x2", "selection": "home",
         "confidence_tier": "A", "suggested_units": 1.0, "book": "FanDuel"},
        {"home_team": "C", "away_team": "D", "market": "btts", "selection": "yes",
         "confidence_tier": "B", "suggested_units": 0.75, "book": "DraftKings"},
    ]

    suggestions = _unit_suggestions(picks)

    assert [item["suggested_units"] for item in suggestions] == [1.0, 0.75]
    assert [item["book"] for item in suggestions] == ["FanDuel", "DraftKings"]
    assert all("no second staking model" in item["basis"] for item in suggestions)


def test_missing_stake_gets_no_guessed_value() -> None:
    assert _unit_suggestions([{"home_team": "A", "away_team": "B"}]) == []
    assert (
        _unit_suggestions([{"home_team": "A", "suggested_units": None}]) == []
    )


def test_non_numeric_or_zero_stake_is_skipped() -> None:
    assert _unit_suggestions([{"suggested_units": "not-a-number"}]) == []
    assert _unit_suggestions([{"suggested_units": 0}]) == []
    assert _unit_suggestions([{"suggested_units": -1}]) == []


# --- bridge integration ----------------------------------------------------


def _bridge_evidence(outputs: Path, *, card_generated: bool) -> None:
    _ready_evidence(outputs)
    _write(
        outputs,
        "week1_launch_readiness.json",
        {
            "status": "Ready for weekly pipeline",
            "fixture_status": "Fresh (10 upcoming match(es))",
            "odds_completeness_percentage": 1.0,
            "missing_odds_count": 0,
            "invalid_odds_issue_count": 0,
            "validation_warning_count": 0,
            "slate_warnings": [],
        },
    )
    _write(
        outputs,
        "automated_card.json",
        {
            "card_generated": card_generated,
            "best_bets": [{"market": "1x2", "selection": "home"}] if card_generated else [],
            "leans": [{"market": "btts", "selection": "yes"}] if card_generated else [],
            "passes_or_avoids": [],
            "unit_suggestions": [],
        },
    )


def test_bridge_carries_picks_only_when_a_card_was_generated(tmp_path: Path) -> None:
    _bridge_evidence(tmp_path, card_generated=True)

    summary = build_epl_card_task(output_dir=tmp_path)

    assert summary["card_ready"] is True
    assert summary["automated_card_generated"] is True
    assert len(summary["best_bets"]) == 1
    assert len(summary["leans"]) == 1


def test_bridge_withholds_picks_when_no_card_was_generated(tmp_path: Path) -> None:
    _bridge_evidence(tmp_path, card_generated=False)

    summary = build_epl_card_task(output_dir=tmp_path)

    assert summary["automated_card_generated"] is False
    assert summary["best_bets"] == []
    assert summary["leans"] == []


def test_bridge_withholds_picks_when_gates_fail_even_if_card_exists(
    tmp_path: Path,
) -> None:
    """A generated card must not leak through a failed gate."""
    _bridge_evidence(tmp_path, card_generated=True)
    _write(
        tmp_path,
        "provider_shadow_verification.json",
        {
            "staging_validation": {"verdict": "Needs fixes", "handoff_eligible": False},
            "provider_policy": {"provider_allowed": False},
        },
    )

    summary = build_epl_card_task(output_dir=tmp_path)

    assert summary["card_ready"] is False
    assert summary["best_bets"] == []
    assert summary["picks_suppressed"] is True


def test_save_writes_both_outputs(tmp_path: Path) -> None:
    result = save_automated_card(output_dir=tmp_path)

    assert Path(result["json"]).name == "automated_card.json"
    assert Path(result["markdown"]).name == "automated_card.md"
    assert Path(result["json"]).is_file()


# --- live policy authority -------------------------------------------------


def _policy_file(tmp_path: Path, names) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"allowed_provider_names": list(names)}), encoding="utf-8")
    return path


def test_stale_report_cannot_outvote_the_live_policy(tmp_path: Path) -> None:
    """A report recorded provider_allowed=True, but the policy no longer lists it."""
    _ready_evidence(tmp_path)
    policy = _policy_file(tmp_path, ["manual_reviewed"])

    summary = build_automated_card(output_dir=tmp_path, policy_path=policy)

    assert summary["card_generated"] is False
    assert any("current staging provider policy" in item for item in summary["blockers"])


def test_missing_policy_file_blocks_the_card(tmp_path: Path) -> None:
    _ready_evidence(tmp_path)

    summary = build_automated_card(
        output_dir=tmp_path, policy_path=tmp_path / "absent.json"
    )

    assert summary["card_generated"] is False


def test_unreadable_policy_blocks_the_card(tmp_path: Path) -> None:
    _ready_evidence(tmp_path)
    policy = tmp_path / "broken.json"
    policy.write_text("{not json", encoding="utf-8")

    summary = build_automated_card(output_dir=tmp_path, policy_path=policy)

    assert summary["card_generated"] is False


def test_live_policy_listing_the_provider_clears_that_blocker(tmp_path: Path) -> None:
    _ready_evidence(tmp_path)
    policy = _policy_file(tmp_path, ["manual_reviewed", "the_odds_api"])

    summary = build_automated_card(output_dir=tmp_path, policy_path=policy)

    assert not any(
        "current staging provider policy" in item for item in summary["blockers"]
    )


# --- kickoff guard ---------------------------------------------------------


def _picks_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "thursday_best_bets.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _staging_fixtures(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "upcoming_fixtures_staging.csv"
    pd.DataFrame(
        rows, columns=["date", "home_team", "away_team", "commence_time"]
    ).to_csv(path, index=False)
    return path


def _pick_row(home: str, away: str, *, section: str = "Best bets") -> dict:
    return {
        "section": section,
        "home_team": home,
        "away_team": away,
        "market": "1x2",
        "selection": "home",
        "status": "OK",
        "confidence_tier": "A",
        "calibrated_model_prob": 0.55,
        "calibrated_edge": 0.05,
        "raw_model_prob": 0.56,
        "raw_edge": 0.06,
        "fair_american": -122,
        "american_odds": -110,
        "suggested_units": 1.0,
        "book": "FanDuel",
        "notes": "",
    }


def _generated_card(
    tmp_path: Path,
    monkeypatch,
    *,
    picks: list[dict],
    fixtures: list[dict],
    now,
) -> dict:
    from epl_betting_lab.reports import automated_card

    _ready_evidence(tmp_path, eligible=("1x2",))
    card_input = tmp_path / "card_input.csv"
    card_input.write_text("market,selection\n", encoding="utf-8")
    picks_csv = _picks_csv(tmp_path, picks)
    monkeypatch.setattr(
        automated_card,
        "run_thursday_best_bets_report",
        lambda **_k: {"csv": str(picks_csv), "markdown": str(picks_csv)},
    )
    monkeypatch.setattr(
        automated_card, "_provider_allowlisted_now", lambda *a, **k: True
    )
    return automated_card.build_automated_card(
        output_dir=tmp_path,
        card_input_path=card_input,
        staging_fixtures_path=_staging_fixtures(tmp_path, fixtures),
        now=now,
    )


def test_a_started_game_is_not_a_play(tmp_path: Path, monkeypatch) -> None:
    """A pick whose kickoff has passed moves out of best bets entirely."""
    from datetime import datetime, timezone

    summary = _generated_card(
        tmp_path,
        monkeypatch,
        picks=[_pick_row("Arsenal", "Chelsea"), _pick_row("Leeds", "Everton")],
        fixtures=[
            {
                "date": "2026-08-23",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "commence_time": "2026-08-23T15:00:00Z",
            },
            {
                "date": "2026-08-26",
                "home_team": "Leeds",
                "away_team": "Everton",
                "commence_time": "2026-08-26T19:00:00Z",
            },
        ],
        now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
    )

    assert summary["card_generated"] is True
    assert [item["home_team"] for item in summary["best_bets"]] == ["Leeds"]
    assert [item["home_team"] for item in summary["already_started"]] == ["Arsenal"]
    started = summary["already_started"][0]
    assert started["kickoff_status"] == "already started"
    assert started["original_section"] == "Best bets"
    assert started["kickoff_time"] == "2026-08-23T15:00:00+00:00"
    # The stake follows the play out of the card.
    assert [item["home_team"] for item in summary["unit_suggestions"]] == ["Leeds"]
    guard = summary["kickoff_guard"]
    assert guard["checked"] is True
    assert guard["already_started_count"] == 1
    assert guard["kickoff_unconfirmed_count"] == 0


def test_an_unconfirmable_kickoff_is_not_a_play(tmp_path: Path, monkeypatch) -> None:
    """No fixture row, no kickoff, no play — the safe side of ambiguity."""
    from datetime import datetime, timezone

    summary = _generated_card(
        tmp_path,
        monkeypatch,
        picks=[_pick_row("Arsenal", "Chelsea")],
        fixtures=[],
        now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
    )

    assert summary["best_bets"] == []
    assert summary["unit_suggestions"] == []
    assert summary["already_started"][0]["kickoff_status"] == "kickoff unconfirmed"
    assert summary["kickoff_guard"]["kickoff_unconfirmed_count"] == 1


def test_conflicting_kickoff_times_read_as_unconfirmed(
    tmp_path: Path, monkeypatch
) -> None:
    from datetime import datetime, timezone

    summary = _generated_card(
        tmp_path,
        monkeypatch,
        picks=[_pick_row("Arsenal", "Chelsea")],
        fixtures=[
            {
                "date": "2026-08-26",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "commence_time": "2026-08-26T15:00:00Z",
            },
            {
                "date": "2026-08-26",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "commence_time": "2026-08-26T19:00:00Z",
            },
        ],
        now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
    )

    assert summary["best_bets"] == []
    assert summary["already_started"][0]["kickoff_status"] == "kickoff unconfirmed"


def test_a_future_kickoff_stays_a_play(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timezone

    summary = _generated_card(
        tmp_path,
        monkeypatch,
        picks=[_pick_row("Arsenal", "Chelsea")],
        fixtures=[
            {
                "date": "2026-08-26",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "commence_time": "2026-08-26T19:00:00Z",
            }
        ],
        now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
    )

    assert [item["home_team"] for item in summary["best_bets"]] == ["Arsenal"]
    assert summary["already_started"] == []


def test_markdown_lists_started_games_outside_the_pick_sections(
    tmp_path: Path, monkeypatch
) -> None:
    from datetime import datetime, timezone

    from epl_betting_lab.reports.automated_card import render_automated_card

    summary = _generated_card(
        tmp_path,
        monkeypatch,
        picks=[_pick_row("Arsenal", "Chelsea")],
        fixtures=[
            {
                "date": "2026-08-23",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "commence_time": "2026-08-23T15:00:00Z",
            }
        ],
        now=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
    )
    text = render_automated_card(summary)

    assert "## Already started — no longer plays" in text
    assert "already started" in text
    # The started pick appears only in the quarantine table, not as a best bet.
    best_bets_section = text.split("## Already started")[0]
    assert "Arsenal" not in best_bets_section.split("## Best bets")[1]


def test_bridge_carries_the_already_started_list(tmp_path: Path) -> None:
    _bridge_evidence(tmp_path, card_generated=True)
    _write(
        tmp_path,
        "automated_card.json",
        {
            "card_generated": True,
            "best_bets": [],
            "leans": [],
            "passes_or_avoids": [],
            "unit_suggestions": [],
            "already_started": [
                {
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "market": "1x2",
                    "selection": "home",
                    "kickoff_status": "already started",
                }
            ],
        },
    )

    summary = build_epl_card_task(output_dir=tmp_path)

    assert summary["best_bets"] == []
    assert len(summary["already_started"]) == 1
    assert "never be presented" in summary["already_started_note"]


# --- book attribution ------------------------------------------------------


def test_strategy_evaluators_carry_the_sportsbook() -> None:
    """CLV needs to know which book priced the pick."""
    import pandas as pd

    from epl_betting_lab.strategies.ml_value import _book_of

    line = pd.DataFrame([{"american_odds": -110, "book": " DraftKings "}])
    assert _book_of(line) == "DraftKings"


def test_missing_book_becomes_blank_not_nan() -> None:
    import pandas as pd

    from epl_betting_lab.strategies.ml_value import _book_of

    assert _book_of(pd.DataFrame([{"american_odds": -110}])) == ""
    assert _book_of(pd.DataFrame([{"american_odds": -110, "book": None}])) == ""
    assert _book_of(pd.DataFrame(columns=["american_odds"])) == ""


def test_all_three_evaluators_expose_book_extraction() -> None:
    from epl_betting_lab.strategies import btts, ml_value, totals

    for module in (ml_value, totals, btts):
        assert hasattr(module, "_book_of"), module.__name__


def test_a_card_where_every_bet_is_the_same_size_says_so(tmp_path, monkeypatch):
    """A column of identical tiers must not read as a ranking that sizes bets.

    Every market the card can stake is capped at the floor: only `total_2_5` is
    profit-backtestable and the anchored rule caps that too, while A was never
    reached across 162 archived best bets. So the tier orders the card and does
    not size the bet, and eight rows of "C" with no explanation invites exactly
    the wrong reading.
    """
    from datetime import datetime, timezone

    from epl_betting_lab.reports.automated_card import render_automated_card

    picks = [
        {**_pick_row("Arsenal", "Chelsea"), "confidence_tier": "C", "suggested_units": 0.1},
        {**_pick_row("Everton", "Fulham"), "confidence_tier": "C", "suggested_units": 0.1},
    ]
    fixtures = [
        {"date": "2026-09-05", "home_team": h, "away_team": a,
         "commence_time": "2026-09-05T14:00:00Z", "provider_event_id": "1a2b3c4d"}
        for h, a in (("Arsenal", "Chelsea"), ("Everton", "Fulham"))
    ]
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    text = render_automated_card(
        _generated_card(tmp_path, monkeypatch, picks=picks, fixtures=fixtures, now=now)
    )

    assert "Every bet below is 0.1u" in text
    assert "does not size the bet" in text


def test_a_card_with_differing_stakes_gets_no_such_note(tmp_path, monkeypatch):
    """The note is a description of the card, not a slogan printed regardless."""
    from datetime import datetime, timezone

    from epl_betting_lab.reports.automated_card import render_automated_card

    picks = [
        {**_pick_row("Arsenal", "Chelsea"), "confidence_tier": "C", "suggested_units": 0.1},
        {**_pick_row("Everton", "Fulham"), "confidence_tier": "B", "suggested_units": 0.25},
    ]
    fixtures = [
        {"date": "2026-09-05", "home_team": h, "away_team": a,
         "commence_time": "2026-09-05T14:00:00Z", "provider_event_id": "1a2b3c4d"}
        for h, a in (("Arsenal", "Chelsea"), ("Everton", "Fulham"))
    ]
    now = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    text = render_automated_card(
        _generated_card(tmp_path, monkeypatch, picks=picks, fixtures=fixtures, now=now)
    )

    assert "Every bet below is" not in text
