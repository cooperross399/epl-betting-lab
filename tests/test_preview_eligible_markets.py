"""The allowlist preview must propose the reviewed market scope, not the adapter's."""

from __future__ import annotations

import json
from pathlib import Path

from epl_betting_lab.reports.provider_allowlist_pr_preview import (
    _eligible_markets_from_evidence,
    _provider_markets_and_limitations,
)


class _Adapter:
    """Stands in for the odds_api adapter's bulk-endpoint configuration."""

    def public_configuration(self) -> dict:
        return {"featured_markets_requested": ["h2h", "totals"]}


def _card_input(tmp_path: Path, eligible) -> Path:
    (tmp_path / "automated_card_input.json").write_text(
        json.dumps({"eligibility": {"eligible_markets": list(eligible)}}),
        encoding="utf-8",
    )
    return tmp_path


def test_reviewed_eligibility_wins_over_the_adapter_request_list(
    tmp_path: Path,
) -> None:
    """The bug this fixes: the adapter asks for h2h+totals, which maps to
    1x2+total_2_5 - granting totals and omitting BTTS, the opposite of what
    was reviewed."""
    _card_input(tmp_path, ["1x2", "btts"])

    markets, _ = _provider_markets_and_limitations(_Adapter(), tmp_path)

    assert markets == ["1x2", "btts"]
    assert "total_2_5" not in markets


def test_excluded_market_is_named_in_the_limitations(tmp_path: Path) -> None:
    _card_input(tmp_path, ["1x2", "btts"])

    _, limitations = _provider_markets_and_limitations(_Adapter(), tmp_path)

    assert any("total_2_5" in item and "not allowlisted" in item for item in limitations)
    assert any("never be fabricated" in item for item in limitations)


def test_gates_are_always_restated_as_a_limitation(tmp_path: Path) -> None:
    _card_input(tmp_path, ["1x2", "btts"])

    _, limitations = _provider_markets_and_limitations(_Adapter(), tmp_path)

    assert any("does not bypass staging validation" in item for item in limitations)


def test_a_single_eligible_market_narrows_the_proposal(tmp_path: Path) -> None:
    _card_input(tmp_path, ["1x2"])

    markets, limitations = _provider_markets_and_limitations(_Adapter(), tmp_path)

    assert markets == ["1x2"]
    assert any("btts" in item for item in limitations)
    assert any("total_2_5" in item for item in limitations)


def test_missing_evidence_falls_back_to_the_adapter_configuration(
    tmp_path: Path,
) -> None:
    """Without reviewed evidence there is nothing better to use."""
    markets, _ = _provider_markets_and_limitations(_Adapter(), tmp_path)

    assert markets == ["1x2", "total_2_5"]


def test_unreadable_evidence_falls_back_safely(tmp_path: Path) -> None:
    (tmp_path / "automated_card_input.json").write_text("{not json", encoding="utf-8")

    assert _eligible_markets_from_evidence(tmp_path) == []


def test_empty_eligible_list_falls_back(tmp_path: Path) -> None:
    _card_input(tmp_path, [])

    markets, _ = _provider_markets_and_limitations(_Adapter(), tmp_path)

    assert markets == ["1x2", "total_2_5"]


def test_eligible_markets_are_lowercased(tmp_path: Path) -> None:
    _card_input(tmp_path, ["1X2", "BTTS"])

    assert _eligible_markets_from_evidence(tmp_path) == ["1x2", "btts"]
