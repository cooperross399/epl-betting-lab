"""Transcribing the same approval twice must not produce a different record."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from epl_betting_lab.config import PROJECT_ROOT


def _module():
    spec = importlib.util.spec_from_file_location(
        "_create_receipt",
        PROJECT_ROOT / "scripts" / "create_receipt_from_github_approval.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _approval(**overrides: object) -> dict[str, object]:
    approval: dict[str, object] = {
        "pr_number": 224,
        "source_kind": "comment",
        "source_id": 90210,
        "reviewer_github_login": "cooperross399",
        "approved_at": "2026-08-21T15:46:30+00:00",
        "provider_name": "the_odds_api",
        "approved_markets": ["1x2", "btts"],
        "evidence_checksums_sha256": {"automated_card_input.json": "a" * 64},
        "verified_at": "2026-08-21T15:50:00+00:00",
    }
    approval.update(overrides)
    return approval


def _write_receipt(tmp_path: Path, approval: dict[str, object]) -> Path:
    path = tmp_path / "provider_human_acceptance_receipt.json"
    path.write_text(
        json.dumps(
            {
                "receipt_id": "odds_api-20260821T114655-0400-20ffa5677988",
                "github_approval": approval,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_the_same_approval_finds_the_stored_receipt(tmp_path: Path) -> None:
    module = _module()
    stored_approval = _approval()
    _write_receipt(tmp_path, stored_approval)

    # A re-verification of the same human act binds fresh evidence checksums
    # and a fresh verification time; neither changes which approval it was.
    rerun = _approval(
        evidence_checksums_sha256={"automated_card_input.json": "b" * 64},
        verified_at="2026-08-21T16:10:00+00:00",
    )

    existing = module._existing_receipt_for(rerun, tmp_path)

    assert existing is not None
    assert existing["receipt_id"] == "odds_api-20260821T114655-0400-20ffa5677988"


def test_a_different_approval_does_not_match(tmp_path: Path) -> None:
    module = _module()
    _write_receipt(tmp_path, _approval())

    for change in (
        {"source_id": 90211},
        {"approved_at": "2026-08-21T16:00:00+00:00"},
        {"reviewer_github_login": "someone-else"},
        {"approved_markets": ["1x2", "btts", "total_2_5"]},
        {"pr_number": 225},
    ):
        assert module._existing_receipt_for(_approval(**change), tmp_path) is None


def test_missing_or_unbound_receipts_do_not_match(tmp_path: Path) -> None:
    module = _module()

    assert module._existing_receipt_for(_approval(), tmp_path) is None

    path = tmp_path / "provider_human_acceptance_receipt.json"
    path.write_text(json.dumps({"receipt_id": "no-binding"}), encoding="utf-8")
    assert module._existing_receipt_for(_approval(), tmp_path) is None
