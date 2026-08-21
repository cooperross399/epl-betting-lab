"""Per-market provider allowlisting: a market must be reviewed, not inherited."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.automated_card_input import (
    _policy_disabled_markets,
    save_automated_card_input,
)
from epl_betting_lab.staging_provider_policy import load_staging_provider_policy


FIXTURES = [
    ("2026-08-21", "Arsenal", "Coventry"),
    ("2026-08-22", "Hull", "Man United"),
]
SELECTIONS = {
    "1x2": ("home", "draw", "away"),
    "total_2_5": ("over", "under"),
    "btts": ("yes", "no"),
}


def _policy(tmp_path: Path, **overrides) -> Path:
    payload = {
        "allowed_provider_names": ["the_odds_api"],
        "allowed_provider_types": ["odds_api"],
        "allow_unknown_providers": False,
        "allow_missing_provenance": False,
        "max_receipt_age_hours": 12,
        "max_provider_run_age_hours": 12,
        "timezone": "America/New_York",
        "thursday_cutoff_time": "10:00",
    }
    payload.update(overrides)
    path = tmp_path / "staging_provider_policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _staging(tmp_path: Path, markets) -> tuple[Path, Path]:
    rows = []
    for date, home, away in FIXTURES:
        for market in markets:
            for selection in SELECTIONS[market]:
                rows.append(
                    {
                        "date": date,
                        "home_team": home,
                        "away_team": away,
                        "market": market,
                        "selection": selection,
                        "american_odds": "-110",
                        "closing_american_odds": "",
                        "book": "BookA",
                        "notes": "",
                    }
                )
    odds = tmp_path / "odds.csv"
    fixtures = tmp_path / "fixtures.csv"
    pd.DataFrame(rows).to_csv(odds, index=False)
    pd.DataFrame(FIXTURES, columns=["date", "home_team", "away_team"]).to_csv(
        fixtures, index=False
    )
    return odds, fixtures


# --- policy parsing --------------------------------------------------------


def test_absent_allowed_markets_means_no_restriction(tmp_path: Path) -> None:
    policy = load_staging_provider_policy(
        _policy(tmp_path), repository_root=tmp_path
    )

    assert policy["allowed_markets"] is None
    assert policy["status"] != "Policy malformed"


def test_allowed_markets_is_parsed_and_lowercased(tmp_path: Path) -> None:
    policy = load_staging_provider_policy(
        _policy(tmp_path, allowed_markets=["1X2", "BTTS"]),
        repository_root=tmp_path,
    )

    assert policy["allowed_markets"] == ["1x2", "btts"]
    assert policy["status"] != "Policy malformed"


def test_malformed_allowed_markets_is_a_policy_blocker(tmp_path: Path) -> None:
    policy = load_staging_provider_policy(
        _policy(tmp_path, allowed_markets="1x2"), repository_root=tmp_path
    )

    assert policy["status"] == "Policy malformed"
    assert any("allowed_markets" in item for item in policy["blockers"])


# --- disabled-market derivation -------------------------------------------


def test_markets_outside_the_allowlist_are_disabled(tmp_path: Path) -> None:
    """Every known market that is not listed, not one particular one.

    This asserted the literal ["total_2_5"], so adding a market to the project
    broke it — which read as a regression when it was the gate working. What
    matters is that anything unlisted is disabled, however many there are.
    """
    from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

    allowed = ["1x2", "btts"]
    path = _policy(tmp_path, allowed_markets=allowed)

    disabled = set(_policy_disabled_markets(path))
    assert disabled == set(MARKET_SELECTIONS) - set(allowed)
    assert disabled, "an allowlist that disables nothing is not a gate"


def test_no_allowlist_now_approves_nothing(tmp_path: Path) -> None:
    """This deliberately reverses. It used to disable nothing.

    "No allowlist means no restriction" was safe by coincidence: the project
    priced exactly the three markets the policy had approved, so there was
    nothing an open default could let through. Once the project could price
    markets nobody had reviewed, that same default would have made each one
    eligible the moment it was added — approval by omission.
    """
    from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

    disabled = set(_policy_disabled_markets(_policy(tmp_path)))

    assert disabled == set(MARKET_SELECTIONS)


def test_missing_policy_file_disables_nothing(tmp_path: Path) -> None:
    assert _policy_disabled_markets(tmp_path / "absent.json") == []


def test_unreadable_policy_disables_nothing(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    assert _policy_disabled_markets(path) == []


# --- end-to-end card input -------------------------------------------------


def test_card_input_excludes_a_market_the_policy_does_not_allow(
    tmp_path: Path,
) -> None:
    """Totals complete in the data but absent from the policy: still excluded."""
    odds, fixtures = _staging(tmp_path, ("1x2", "total_2_5", "btts"))
    policy = _policy(tmp_path, allowed_markets=["1x2", "btts"])

    result = save_automated_card_input(
        staging_odds_path=odds,
        staging_fixtures_path=fixtures,
        output_dir=tmp_path,
        card_input_path=tmp_path / "card.csv",
        policy_path=policy,
        disabled_markets=(),
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )
    summary = result["summary"]

    assert set(summary["included_markets"]) == {"1x2", "btts"}
    assert "total_2_5" in summary["excluded_markets"]
    # Every unlisted market, not one particular one - see the note on
    # test_markets_outside_the_allowlist_are_disabled.
    assert "total_2_5" in summary["policy_disabled_markets"]
    assert "1x2" not in summary["policy_disabled_markets"]
    assert "btts" not in summary["policy_disabled_markets"]

    written = pd.read_csv(result["card_input"])
    assert "total_2_5" not in set(written["market"])


def test_policy_allowlist_admits_the_markets_it_lists(tmp_path: Path) -> None:
    odds, fixtures = _staging(tmp_path, ("1x2", "btts"))
    policy = _policy(tmp_path, allowed_markets=["1x2", "btts"])

    result = save_automated_card_input(
        staging_odds_path=odds,
        staging_fixtures_path=fixtures,
        output_dir=tmp_path,
        card_input_path=tmp_path / "card.csv",
        policy_path=policy,
        disabled_markets=(),
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )

    assert set(result["summary"]["included_markets"]) == {"1x2", "btts"}


def test_an_unlisted_market_cannot_join_by_becoming_complete(
    tmp_path: Path,
) -> None:
    """The point of per-market allowlisting: completeness alone is not consent."""
    odds, fixtures = _staging(tmp_path, ("1x2", "total_2_5", "btts"))
    policy = _policy(tmp_path, allowed_markets=["1x2"])

    result = save_automated_card_input(
        staging_odds_path=odds,
        staging_fixtures_path=fixtures,
        output_dir=tmp_path,
        card_input_path=tmp_path / "card.csv",
        policy_path=policy,
        disabled_markets=(),
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )
    summary = result["summary"]

    assert summary["included_markets"] == ["1x2"]
    assert {"total_2_5", "btts"} <= set(summary["excluded_markets"])
    assert "1x2" not in summary["excluded_markets"]


# --- the gate must close when it cannot find its rules ----------------------
#
# An absent top-level `allowed_markets` meant "no restriction". That was safe by
# coincidence: the project priced exactly the three markets the policy had
# approved. It stopped being safe the moment the project could price markets
# nobody had reviewed — a market added in code would have become eligible on
# its own, which is precisely what adding markets must never do.


def _payload(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_missing_allowlist_falls_back_to_the_reviewed_provider_entry(
    tmp_path: Path,
) -> None:
    from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

    path = _payload(
        tmp_path,
        {
            "provider_allowlist_entries": {
                "the_odds_api": {"required_markets": ["1x2", "btts"]}
            }
        },
    )

    disabled = set(_policy_disabled_markets(path))

    assert disabled == set(MARKET_SELECTIONS) - {"1x2", "btts"}


def test_a_policy_naming_no_markets_at_all_approves_nothing(
    tmp_path: Path,
) -> None:
    """A gate that cannot find its rules must close, not open."""
    from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

    path = _payload(tmp_path, {"provider_allowlist_entries": {}})

    assert set(_policy_disabled_markets(path)) == set(MARKET_SELECTIONS)


def test_a_policy_with_no_entries_key_approves_nothing(tmp_path: Path) -> None:
    from epl_betting_lab.market_eligibility import MARKET_SELECTIONS

    path = _payload(tmp_path, {"max_provider_run_age_hours": 12})

    assert set(_policy_disabled_markets(path)) == set(MARKET_SELECTIONS)


def test_the_top_level_allowlist_still_wins_when_present(tmp_path: Path) -> None:
    path = _payload(
        tmp_path,
        {
            "allowed_markets": ["1x2"],
            "provider_allowlist_entries": {
                "the_odds_api": {"required_markets": ["1x2", "btts"]}
            },
        },
    )

    assert "btts" in _policy_disabled_markets(path)


def test_several_providers_contribute_their_reviewed_markets(
    tmp_path: Path,
) -> None:
    path = _payload(
        tmp_path,
        {
            "provider_allowlist_entries": {
                "the_odds_api": {"required_markets": ["1x2"]},
                "manual_reviewed": {"required_markets": ["btts"]},
            }
        },
    )

    disabled = set(_policy_disabled_markets(path))

    assert "1x2" not in disabled
    assert "btts" not in disabled


def test_the_shipped_policy_approves_only_the_reviewed_markets() -> None:
    """The real file, not a fixture: this is what a live run will use.

    The reviewed scope covers all eight priced markets since 2026-08-21:
    approved on PR #224 and bound to human acceptance receipt
    odds_api-20260821T114655-0400-20ffa5677988. A market missing from the
    policy's required_markets would silently drop off the card, so an empty
    disabled set is the assertion, not an absence of one.
    """
    disabled = set(_policy_disabled_markets(None))

    assert disabled == set()
