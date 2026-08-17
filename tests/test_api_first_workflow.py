"""API-first workflow: market eligibility, provider-derived card input, no manual entry."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.market_eligibility import (
    DEFAULT_DISABLED_MARKETS,
    DISABLED,
    ELIGIBLE,
    INCOMPLETE,
    UNAVAILABLE,
    evaluate_market_eligibility,
)
from epl_betting_lab.reports.automated_card_input import (
    ProtectedPathError,
    build_automated_card_input,
    save_automated_card_input,
)
from epl_betting_lab.reports.provider_trust_packet import build_provider_trust_packet


WINDOW_FIXTURES = [
    ("2026-08-21", "Arsenal", "Coventry"),
    ("2026-08-22", "Hull", "Man United"),
    ("2026-08-23", "Man City", "Bournemouth"),
]
OUTSIDE_FIXTURE = ("2026-08-29", "Liverpool", "Nott'm Forest")


def _fixtures(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "home_team", "away_team"])


def _odds(rows, markets=("1x2", "total_2_5"), books=("BookA",)) -> pd.DataFrame:
    selections = {
        "1x2": ("home", "draw", "away"),
        "total_2_5": ("over", "under"),
        "btts": ("yes", "no"),
    }
    records = []
    for match_date, home, away in rows:
        for market in markets:
            for selection in selections[market]:
                for book in books:
                    records.append(
                        {
                            "date": match_date,
                            "home_team": home,
                            "away_team": away,
                            "market": market,
                            "selection": selection,
                            "american_odds": "-110",
                            "closing_american_odds": "",
                            "book": book,
                            "notes": "",
                        }
                    )
    return pd.DataFrame(records)


def _evaluate(odds, fixtures, **kwargs):
    defaults = dict(
        mapping_verified=True, validation_passed=True, freshness_passed=True
    )
    defaults.update(kwargs)
    return evaluate_market_eligibility(odds, fixtures, **defaults)


# --- eligibility states ----------------------------------------------------


def test_full_coverage_market_is_eligible() -> None:
    report = _evaluate(_odds(WINDOW_FIXTURES, markets=("1x2",)), _fixtures(WINDOW_FIXTURES))

    market = next(m for m in report.markets if m.market == "1x2")
    assert market.status == ELIGIBLE
    assert market.usable is True
    assert market.fixtures_covered == 3


def test_market_missing_some_fixtures_is_incomplete_not_partially_used() -> None:
    odds = pd.concat(
        [
            _odds(WINDOW_FIXTURES, markets=("1x2",)),
            _odds(WINDOW_FIXTURES[:2], markets=("total_2_5",)),
        ]
    )
    report = _evaluate(odds, _fixtures(WINDOW_FIXTURES))

    totals = next(m for m in report.markets if m.market == "total_2_5")
    assert totals.status == INCOMPLETE
    assert totals.usable is False
    assert totals.fixtures_covered == 2
    assert len(totals.missing_fixtures) == 1


def test_market_with_no_rows_is_unavailable_not_zero_priced() -> None:
    report = _evaluate(
        _odds(WINDOW_FIXTURES, markets=("1x2",)),
        _fixtures(WINDOW_FIXTURES),
        disabled_markets=(),
    )

    btts = next(m for m in report.markets if m.market == "btts")
    assert btts.status == UNAVAILABLE
    assert btts.row_count == 0
    assert btts.as_dict()["fabricated"] is False
    assert "no price was invented" in btts.reason


def test_btts_is_disabled_by_default() -> None:
    report = _evaluate(
        _odds(WINDOW_FIXTURES, markets=("1x2", "btts")), _fixtures(WINDOW_FIXTURES)
    )

    btts = next(m for m in report.markets if m.market == "btts")
    assert "btts" in DEFAULT_DISABLED_MARKETS
    assert btts.status == DISABLED
    assert btts.usable is False


def test_excluded_markets_are_never_presented_as_passes() -> None:
    report = _evaluate(_odds(WINDOW_FIXTURES, markets=("1x2",)), _fixtures(WINDOW_FIXTURES))
    payload = report.as_dict()

    assert "btts" in payload["excluded_markets"]
    assert "pass" in payload["note"].lower()
    for market in payload["markets"]:
        assert market["fabricated"] is False
        if not market["usable_for_picks"]:
            assert market["status"] in {INCOMPLETE, UNAVAILABLE, DISABLED}


def test_gate_failure_disqualifies_every_market() -> None:
    report = _evaluate(
        _odds(WINDOW_FIXTURES, markets=("1x2",)),
        _fixtures(WINDOW_FIXTURES),
        mapping_verified=False,
    )

    assert report.any_eligible is False
    assert report.gate_failures


def test_only_the_selected_window_is_considered() -> None:
    fixtures = _fixtures(WINDOW_FIXTURES + [OUTSIDE_FIXTURE])
    # Provider covers the window fully but not the later round.
    report = _evaluate(_odds(WINDOW_FIXTURES, markets=("1x2",)), fixtures)

    market = next(m for m in report.markets if m.market == "1x2")
    assert market.fixtures_expected == 3
    assert market.status == ELIGIBLE


# --- card input ------------------------------------------------------------


def test_card_input_uses_eligible_markets_only() -> None:
    odds = pd.concat(
        [
            _odds(WINDOW_FIXTURES, markets=("1x2",)),
            _odds(WINDOW_FIXTURES[:2], markets=("total_2_5",)),
        ]
    )
    fixtures = _fixtures(WINDOW_FIXTURES)
    report = _evaluate(odds, fixtures)

    frame, _ = build_automated_card_input(odds, fixtures, eligibility=report)

    assert set(frame["market"]) == {"1x2"}
    assert "total_2_5" not in set(frame["market"])
    assert len(frame) == 9  # 3 fixtures x 3 selections


def test_card_input_never_contains_btts_while_unavailable() -> None:
    odds = _odds(WINDOW_FIXTURES, markets=("1x2",))
    fixtures = _fixtures(WINDOW_FIXTURES)
    report = _evaluate(odds, fixtures)

    frame, _ = build_automated_card_input(odds, fixtures, eligibility=report)

    assert "btts" not in set(frame["market"])


def test_card_input_picks_best_real_quote_and_never_synthesises() -> None:
    odds = _odds(WINDOW_FIXTURES[:1], markets=("1x2",), books=("BookA", "BookB"))
    odds.loc[odds["book"] == "BookB", "american_odds"] = "+150"
    fixtures = _fixtures(WINDOW_FIXTURES[:1])
    report = _evaluate(odds, fixtures)

    frame, _ = build_automated_card_input(odds, fixtures, eligibility=report)

    # +150 beats -110, and the winning row keeps its real book attribution.
    assert set(frame["american_odds"]) == {"+150"} or "150" in set(frame["american_odds"])
    assert set(frame["book"]) == {"BookB"}


def test_card_input_is_empty_when_no_market_is_eligible() -> None:
    fixtures = _fixtures(WINDOW_FIXTURES)
    odds = _odds(WINDOW_FIXTURES, markets=("btts",))
    report = _evaluate(odds, fixtures)

    frame, notes = build_automated_card_input(odds, fixtures, eligibility=report)

    assert frame.empty
    assert any("No market is eligible" in note for note in notes)


def test_card_input_refuses_to_write_into_protected_manual_dir(tmp_path: Path) -> None:
    from epl_betting_lab.config import MANUAL_DIR

    with pytest.raises(ProtectedPathError):
        save_automated_card_input(
            card_input_path=MANUAL_DIR / "current_odds.csv",
            output_dir=tmp_path,
        )


def test_save_writes_outside_manual_and_reports_no_manual_entry(
    tmp_path: Path,
) -> None:
    staging_odds = tmp_path / "odds.csv"
    staging_fixtures = tmp_path / "fixtures.csv"
    _odds(WINDOW_FIXTURES, markets=("1x2",)).to_csv(staging_odds, index=False)
    _fixtures(WINDOW_FIXTURES).to_csv(staging_fixtures, index=False)

    result = save_automated_card_input(
        staging_odds_path=staging_odds,
        staging_fixtures_path=staging_fixtures,
        output_dir=tmp_path,
        card_input_path=tmp_path / "card_input.csv",
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )
    summary = result["summary"]

    assert summary["status"] == "Card input ready"
    assert summary["manual_entry_required"] is False
    assert summary["safety"]["odds_fabricated"] is False
    assert summary["safety"]["protected_files_written"] is False
    assert summary["included_markets"] == ["1x2"]
    assert Path(result["card_input"]).is_file()


def test_no_manual_odds_file_is_required_anywhere_in_the_flow(tmp_path: Path) -> None:
    """The whole point: the flow completes with no manual template present."""
    staging_odds = tmp_path / "odds.csv"
    staging_fixtures = tmp_path / "fixtures.csv"
    _odds(WINDOW_FIXTURES, markets=("1x2",)).to_csv(staging_odds, index=False)
    _fixtures(WINDOW_FIXTURES).to_csv(staging_fixtures, index=False)

    assert not (tmp_path / "current_odds.csv").exists()

    result = save_automated_card_input(
        staging_odds_path=staging_odds,
        staging_fixtures_path=staging_fixtures,
        output_dir=tmp_path,
        card_input_path=tmp_path / "card_input.csv",
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )

    assert result["summary"]["card_input_written"] is True
    assert not (tmp_path / "current_odds.csv").exists()


def test_reports_contain_no_secret_values(tmp_path: Path) -> None:
    staging_odds = tmp_path / "odds.csv"
    staging_fixtures = tmp_path / "fixtures.csv"
    _odds(WINDOW_FIXTURES, markets=("1x2",)).to_csv(staging_odds, index=False)
    _fixtures(WINDOW_FIXTURES).to_csv(staging_fixtures, index=False)

    result = save_automated_card_input(
        staging_odds_path=staging_odds,
        staging_fixtures_path=staging_fixtures,
        output_dir=tmp_path,
        card_input_path=tmp_path / "card_input.csv",
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )

    for key in ("json", "markdown"):
        text = Path(result[key]).read_text(encoding="utf-8")
        for needle in ("apiKey", "EPL_ODDS_API_KEY=", "api_key="):
            assert needle not in text


# --- trust packet ----------------------------------------------------------


def test_trust_packet_never_claims_allowlisted_when_policy_says_otherwise(
    tmp_path: Path,
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"allowed_provider_names": ["manual_reviewed"]}), encoding="utf-8"
    )

    summary = build_provider_trust_packet(output_dir=tmp_path, policy_path=policy)

    assert summary["currently_allowlisted"] is False
    assert summary["safety"]["provider_allowlisted"] is False
    assert summary["safety"]["policy_edited"] is False
    assert any(
        "Explicit human approval" in item
        for item in summary["outstanding_requirements"]
    )


def test_trust_packet_reports_remaining_runs(tmp_path: Path) -> None:
    (tmp_path / "provider_acceptance_checklist.json").write_text(
        json.dumps(
            {
                "verdict": "Not trusted",
                "completed_live_run_count": 2,
                "minimum_required_runs": 3,
            }
        ),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"allowed_provider_names": []}), encoding="utf-8")

    summary = build_provider_trust_packet(output_dir=tmp_path, policy_path=policy)

    assert summary["acceptance"]["runs_remaining"] == 1
    assert summary["ready_for_human_approval"] is False


def test_trust_packet_does_not_write_the_policy_file(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    original = json.dumps({"allowed_provider_names": ["manual_reviewed"]})
    policy.write_text(original, encoding="utf-8")

    build_provider_trust_packet(output_dir=tmp_path, policy_path=policy)

    assert policy.read_text(encoding="utf-8") == original
