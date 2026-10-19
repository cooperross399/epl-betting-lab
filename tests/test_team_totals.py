"""Team totals: priced, parsed, carded, settled and shown on the board.

Cooper, 2026-10-19: "yes build team totals". They were left out because a book
sets a different line per team on one fixture -- Arsenal at 2.5, Coventry at
0.5 -- so a single line in the market name could not match. That is the same
mistake `total_2_5` was excluded for: it looked only at the featured market.
The alternate ladder (`alternate_team_totals`) carries every line, so each
market here is one team at one line -- `team_total_home_1_5` -- and the
completeness gate judges each on its own. A line a book does not post leaves
that market incomplete, never priced from a neighbouring line.

Nothing here spends a credit until the reviewed policy approves a team-total
market: the per-event request asks for the team-total keys only then.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, TeamStrength
from epl_betting_lab.providers.odds_api_staging_provider import (
    DEFAULT_EVENT_MARKETS,
    TEAM_TOTAL_PROVIDER_MARKETS,
    TEAM_TOTAL_REQUEST_MARKETS,
    OddsApiStagingProvider,
    _normalize_provider_events,
)
from epl_betting_lab.reports.card_scoreboard import settle, settleable_markets
from epl_betting_lab.strategies.team_totals import (
    TEAM_TOTAL_MARKETS,
    approved_team_total_markets,
    evaluate_team_totals,
)

ROOT = Path(__file__).resolve().parents[1]
GENERATED = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
SIX = [
    f"team_total_{side}_{line}"
    for side in ("home", "away")
    for line in ("0_5", "1_5", "2_5")
]


def test_six_markets_one_team_one_line_each() -> None:
    assert sorted(TEAM_TOTAL_MARKETS) == sorted(SIX)
    for market in SIX:
        assert MARKET_SELECTIONS[market] == ("over", "under")


def _model() -> PoissonGoalsModel:
    model = PoissonGoalsModel()
    model.avg_home_goals, model.avg_away_goals = 1.5, 1.2
    model.team_strengths = {
        "Arsenal": TeamStrength(1.4, 0.8),
        "Coventry": TeamStrength(0.8, 1.2),
    }
    return model


def test_the_model_prices_each_side_on_its_own_goals() -> None:
    row = _model().match_probabilities("Arsenal", "Coventry")
    for side in ("home", "away"):
        for line in ("0_5", "1_5", "2_5"):
            over = row[f"team_total_{side}_over_{line}"]
            under = row[f"team_total_{side}_under_{line}"]
            assert over + under == pytest.approx(1.0, abs=2e-4)
    assert row["team_total_home_over_0_5"] > row["team_total_home_over_1_5"] > row["team_total_home_over_2_5"]
    # Arsenal are the stronger attack against the weaker defence.
    assert row["team_total_home_over_1_5"] > row["team_total_away_over_1_5"]


def _event(markets: list[dict]) -> list[dict]:
    return [{
        "id": "ev1",
        "commence_time": "2026-10-25T14:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Coventry City",
        "bookmakers": [{"key": "fanduel", "title": "FanDuel", "markets": markets}],
    }]


def _ladder(key: str = "alternate_team_totals") -> dict:
    outcomes = []
    for team, line, over, under in (
        ("Arsenal", 1.5, -150, 120), ("Arsenal", 2.5, 160, -200),
        ("Coventry City", 0.5, -110, -110), ("Coventry City", 3.5, 900, -2000),
    ):
        outcomes.append({"name": "Over", "description": team, "price": over, "point": line})
        outcomes.append({"name": "Under", "description": team, "price": under, "point": line})
    return {"key": key, "outcomes": outcomes}


def test_the_ladder_becomes_one_market_per_team_and_line() -> None:
    odds, _, _, _ = _normalize_provider_events(_event([_ladder()]), generated_at=GENERATED)
    got = {(r.market, r.selection): r.american_odds for r in odds.itertuples()}
    assert got[("team_total_home_1_5", "over")] == -150
    assert got[("team_total_home_2_5", "under")] == -200
    assert got[("team_total_away_0_5", "over")] == -110
    # 3.5 is on nobody's card: dropped, never mapped to a neighbour.
    assert not any("3_5" in market for market, _ in got)
    assert ("team_total_away_1_5", "over") not in got


def test_the_featured_market_parses_the_same_way() -> None:
    odds, _, _, _ = _normalize_provider_events(_event([_ladder("team_totals")]), generated_at=GENERATED)
    assert set(odds.market) == {"team_total_home_1_5", "team_total_home_2_5", "team_total_away_0_5"}


def test_a_team_the_fixture_does_not_name_stops_the_run() -> None:
    bad = {"key": "team_totals", "outcomes": [
        {"name": "Over", "description": "Chelsea", "price": 100, "point": 1.5},
    ]}
    with pytest.raises(Exception, match="Chelsea"):
        _normalize_provider_events(_event([bad]), generated_at=GENERATED)


def test_nothing_asks_for_team_totals_until_the_policy_approves_one(tmp_path: Path) -> None:
    for key in TEAM_TOTAL_PROVIDER_MARKETS:
        assert key not in DEFAULT_EVENT_MARKETS
    held = tmp_path / "held.json"
    held.write_text(json.dumps({"provider_allowlist_entries": {}}), encoding="utf-8")
    provider = OddsApiStagingProvider(environment={}, policy_path=held)
    assert not set(TEAM_TOTAL_PROVIDER_MARKETS) & set(provider.event_markets)

    shipped = ROOT / "data" / "manual" / "staging_provider_policy.json"
    payload = json.loads(shipped.read_text(encoding="utf-8"))
    entry = next(iter(payload["provider_allowlist_entries"].values()))
    entry["required_markets"] = [
        market for market in entry["required_markets"] if market not in TEAM_TOTAL_MARKETS
    ] + ["team_total_home_1_5"]
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps(payload), encoding="utf-8")
    assert approved_team_total_markets(approved) == ["team_total_home_1_5"]
    provider = OddsApiStagingProvider(environment={}, policy_path=approved)
    assert set(TEAM_TOTAL_REQUEST_MARKETS) <= set(provider.event_markets)
    # The ladder carries every line the card prices; the featured market adds
    # nothing a bettable book posts that the ladder lacks (probe, 2026-10-19).
    assert "team_totals" not in provider.event_markets
    # An explicit market list is the caller's choice and is left alone.
    explicit = OddsApiStagingProvider(environment={}, policy_path=approved, event_markets=("btts",))
    assert explicit.event_markets == ("btts",)


def test_the_shipped_policy_approves_all_six() -> None:
    """Approved by Cooper on PR #371 (2026-10-19)."""
    assert approved_team_total_markets() == list(TEAM_TOTAL_MARKETS)


def test_a_priced_line_is_graded_against_the_model() -> None:
    projections = pd.DataFrame([_model().match_probabilities("Arsenal", "Coventry")])
    odds = pd.DataFrame([
        {"home_team": "Arsenal", "away_team": "Coventry", "market": "team_total_home_1_5",
         "selection": "over", "american_odds": 150, "book": "FanDuel"},
        {"home_team": "Arsenal", "away_team": "Coventry", "market": "team_total_home_1_5",
         "selection": "under", "american_odds": -190, "book": "FanDuel"},
    ])
    graded = evaluate_team_totals(projections, odds)
    assert set(graded.selection) == {"over", "under"}
    over = graded[graded.selection == "over"].iloc[0]
    assert over.raw_model_prob == pytest.approx(projections.iloc[0]["team_total_home_over_1_5"], abs=1e-4)
    assert over.book == "FanDuel"


@pytest.mark.parametrize(
    "market, selection, home, away, won",
    [
        ("team_total_home_1_5", "over", 2, 0, True),
        ("team_total_home_1_5", "over", 1, 5, False),
        ("team_total_home_1_5", "under", 1, 5, True),
        ("team_total_away_0_5", "over", 0, 1, True),
        ("team_total_away_2_5", "under", 4, 3, False),
    ],
)
def test_settled_on_that_team_alone(market, selection, home, away, won) -> None:
    assert market in settleable_markets()
    assert settle(market, selection, home, away) is won


def _web(name: str):
    spec = importlib.util.spec_from_file_location(f"tt_{name}", ROOT / "web" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_board_names_the_team_and_the_line() -> None:
    board = _web("build_board_json")
    row = {"market": "team_total_away_0_5", "selection": "over"}
    assert board.selection_label(row, "Arsenal", "Coventry") == "Coventry over 0.5 goals"
    assert board.selection_label({"market": "team_total_home_2_5", "selection": "under"},
                                 "Arsenal", "Coventry") == "Arsenal under 2.5 goals"


@pytest.mark.parametrize(
    "market, label, hf, af, verdict",
    [
        ("team_total_away_0_5", "coventry over 0.5 goals", 3, 1, "win"),
        ("team_total_away_0_5", "coventry over 0.5 goals", 3, 0, "loss"),
        ("team_total_home_2_5", "arsenal under 2.5 goals", 2, 4, "win"),
    ],
)
def test_the_public_record_grades_team_totals(market, label, hf, af, verdict) -> None:
    pick = {"kind": "bet", "market": market, "label": label}
    assert _web("settle_results").grade_pick("epl", pick, {}, hf, af, {}) == verdict


def test_the_card_builder_prices_team_totals() -> None:
    """Every market the card can price is evaluated in one list; team totals
    join it on the goal-count ratings the 2.5 line and BTTS use."""
    source = (ROOT / "src" / "epl_betting_lab" / "dashboard_actions.py").read_text(encoding="utf-8")
    assert "evaluate_team_totals(totals_projections, odds" in source


def test_the_evidence_refresh_can_ask_for_team_totals_before_approval() -> None:
    """The allowlist preview proposes only markets the card input found
    eligible, and team totals are not fetched until approved. So the evidence
    refresh carries an opt-in that asks for the ladder once, prints the
    eligibility to the log, and skips the prop fetch it does not need."""
    import subprocess
    import sys

    text = (ROOT / ".github" / "workflows" / "provider-evidence-refresh.yml").read_text(encoding="utf-8")
    assert "team_totals:" in text
    assert "--with-team-totals" in text
    assert "inputs.team_totals && '--with-team-totals'" in text
    help_text = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_provider_shadow_verification.py"), "--help"],
        capture_output=True, text=True, env={"PYTHONPATH": str(ROOT / "src")}, check=True,
    ).stdout
    assert "--with-team-totals" in help_text
