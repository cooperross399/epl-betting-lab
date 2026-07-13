from __future__ import annotations

import pandas as pd

from epl_betting_lab.dashboard_portal import (
    HOME_PORTAL_SECTION,
    ODDS_IMPORT_STEPS,
    PORTAL_NAVIGATION_REQUEST_KEY,
    PORTAL_QUERY_PARAM,
    PORTAL_SECTION_STATE_KEY,
    PORTAL_SECTION_SLUGS,
    PORTAL_SECTIONS,
    SECTION_DESCRIPTIONS,
    apply_portal_navigation_request,
    apply_portal_query_navigation,
    build_ledger_portal_summary,
    portal_section_from_slug,
    portal_slug_from_section,
    request_portal_home_navigation,
    resolve_open_next_section,
)


def test_portal_sections_are_beginner_friendly_and_complete() -> None:
    assert PORTAL_SECTIONS == (
        "Home / Command Center",
        "Thursday Card",
        "Odds Import",
        "Performance Reports",
        "Bet Ledger",
        "Archives & Comparisons",
        "Tools / Diagnostics",
    )
    assert set(SECTION_DESCRIPTIONS) == set(PORTAL_SECTIONS)
    assert set(PORTAL_SECTION_SLUGS) == set(PORTAL_SECTIONS)
    assert PORTAL_QUERY_PARAM == "section"


def test_portal_query_slugs_are_stable_and_reversible() -> None:
    expected = {
        "Home / Command Center": "home",
        "Thursday Card": "thursday-card",
        "Odds Import": "odds-import",
        "Performance Reports": "performance",
        "Bet Ledger": "bet-ledger",
        "Archives & Comparisons": "archives",
        "Tools / Diagnostics": "tools",
    }

    assert PORTAL_SECTION_SLUGS == expected
    for section, slug in expected.items():
        assert portal_slug_from_section(section) == slug
        assert portal_section_from_slug(slug) == section


def test_odds_import_steps_preserve_the_safe_workflow_order() -> None:
    assert [step.number for step in ODDS_IMPORT_STEPS] == list(range(1, 10))
    assert [step.label for step in ODDS_IMPORT_STEPS] == [
        "Diagnose export",
        "Suggest profile",
        "Validate suggested profile",
        "Preview profile install",
        "Verify installed profile",
        "Rollback preview",
        "Convert export",
        "Preview current odds import",
        "View import audits",
    ]


def test_open_next_cues_map_to_portal_sections() -> None:
    assert resolve_open_next_section(
        "Thursday readiness refresh and Thursday best-bets report"
    ) == "Thursday Card"
    assert resolve_open_next_section("Odds import profile install") == "Odds Import"
    assert resolve_open_next_section(
        "Post-refresh Thursday review and Latest Thursday snapshot comparison"
    ) == "Archives & Comparisons"
    assert resolve_open_next_section("Tier performance report") == "Performance Reports"
    assert resolve_open_next_section("Bet ledger health check") == "Bet Ledger"
    assert resolve_open_next_section("Model projections and diagnostics") == "Tools / Diagnostics"


def test_open_next_archive_cue_takes_priority_over_thursday_readiness() -> None:
    cue = "Thursday readiness refresh and Recent Thursday report archives"

    assert resolve_open_next_section(cue) == "Archives & Comparisons"


def test_open_next_cue_has_safe_unknown_fallback() -> None:
    assert resolve_open_next_section(None) is None
    assert resolve_open_next_section("") is None
    assert resolve_open_next_section("Unexpected destination") is None


def test_navigation_request_changes_only_the_selected_section() -> None:
    state: dict[str, object] = {
        PORTAL_SECTION_STATE_KEY: "Home / Command Center",
        PORTAL_NAVIGATION_REQUEST_KEY: "Bet Ledger",
        "unrelated": "unchanged",
    }

    selected = apply_portal_navigation_request(state)

    assert selected == "Bet Ledger"
    assert state[PORTAL_SECTION_STATE_KEY] == "Bet Ledger"
    assert PORTAL_NAVIGATION_REQUEST_KEY not in state
    assert state["unrelated"] == "unchanged"


def test_navigation_request_discards_unknown_sections_and_repairs_bad_state() -> None:
    state = {
        PORTAL_SECTION_STATE_KEY: "Not a portal section",
        PORTAL_NAVIGATION_REQUEST_KEY: "Unknown destination",
    }

    selected = apply_portal_navigation_request(state)

    assert selected == "Home / Command Center"
    assert state == {PORTAL_SECTION_STATE_KEY: "Home / Command Center"}


def test_query_navigation_selects_bookmarked_section() -> None:
    state: dict[str, object] = {}

    selected = apply_portal_query_navigation(state, "odds-import")

    assert selected == "Odds Import"
    assert state[PORTAL_SECTION_STATE_KEY] == "Odds Import"


def test_query_navigation_home_fallbacks_are_strict() -> None:
    malformed_values = (None, "", "unknown", "odds import", ["odds-import"], {"section": "tools"})

    for value in malformed_values:
        state = {PORTAL_SECTION_STATE_KEY: "Performance Reports"}
        assert apply_portal_query_navigation(state, value) == "Home / Command Center"


def test_pending_open_next_request_overrides_old_query_value() -> None:
    state = {
        PORTAL_SECTION_STATE_KEY: "Home / Command Center",
        PORTAL_NAVIGATION_REQUEST_KEY: "Performance Reports",
    }

    selected = apply_portal_query_navigation(state, "home")

    assert selected == "Performance Reports"
    assert PORTAL_NAVIGATION_REQUEST_KEY not in state


def test_back_to_home_request_works_from_every_non_home_section() -> None:
    for section in PORTAL_SECTIONS[1:]:
        state: dict[str, object] = {
            PORTAL_SECTION_STATE_KEY: section,
            "unrelated": "unchanged",
        }

        destination = request_portal_home_navigation(state)

        assert destination == HOME_PORTAL_SECTION
        assert state[PORTAL_NAVIGATION_REQUEST_KEY] == HOME_PORTAL_SECTION
        assert apply_portal_navigation_request(state) == HOME_PORTAL_SECTION
        assert state[PORTAL_SECTION_STATE_KEY] == HOME_PORTAL_SECTION
        assert state["unrelated"] == "unchanged"


def test_back_to_home_request_repairs_malformed_navigation_state() -> None:
    state: dict[str, object] = {
        PORTAL_SECTION_STATE_KEY: ["not", "valid"],
        PORTAL_NAVIGATION_REQUEST_KEY: {"bad": "request"},
    }

    request_portal_home_navigation(state)

    assert apply_portal_navigation_request(state) == HOME_PORTAL_SECTION
    assert state == {PORTAL_SECTION_STATE_KEY: HOME_PORTAL_SECTION}


def test_ledger_portal_summary_handles_missing_ledger(tmp_path) -> None:
    summary = build_ledger_portal_summary(tmp_path / "bet_ledger.csv")

    assert summary.status == "Missing"
    assert summary.profit_units is None
    assert summary.pending_bets is None


def test_ledger_portal_summary_reports_units_roi_and_pending(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    pd.DataFrame([
        {
            "bet_id": "bet-1",
            "american_odds": 100,
            "stake_units": 0.5,
            "result": "win",
        },
        {
            "bet_id": "bet-2",
            "american_odds": -110,
            "stake_units": 0.25,
            "result": "pending",
        },
    ]).to_csv(ledger_path, index=False)

    summary = build_ledger_portal_summary(ledger_path)

    assert summary.status == "Ready"
    assert summary.record == "1-0-0"
    assert summary.profit_units == 0.5
    assert summary.roi == 1.0
    assert summary.pending_bets == 1


def test_ledger_portal_summary_handles_invalid_results(tmp_path) -> None:
    ledger_path = tmp_path / "bet_ledger.csv"
    pd.DataFrame([{"bet_id": "bad", "result": "maybe"}]).to_csv(ledger_path, index=False)

    summary = build_ledger_portal_summary(ledger_path)

    assert summary.status == "Needs review"
    assert summary.record == "Unavailable"
    assert "Unsupported result" in summary.message
