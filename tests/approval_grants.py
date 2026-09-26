"""Real approval grants and real receipts, for tests that need one.

There is no back door here. :func:`grant` gets its grant the only way anything
can: by pointing the verifier at a pull request and letting it fetch, parse and
check the approval. What the test controls is what GitHub answers, which is
what a test of this flow is supposed to control.

:func:`write_receipt_file` writes the receipt shape the card's read-time check
verifies, into a directory the test owns. It never touches `data/outputs`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

from epl_betting_lab.reports import github_approval
from epl_betting_lab.reports.github_approval import (
    APPROVAL_PHRASE,
    EVIDENCE_ARTIFACTS,
    verified_approval_for_pr,
)

REPOSITORY = "cooperross399/epl-betting-lab"
REVIEWER = "cooperross399"
PR = 224
HEAD = "7cccb31532fb4865f0d2d79eea496d48d76e33fa"
PROVIDER = "the_odds_api"


def approval_body(
    *,
    pr: int = PR,
    provider: str = PROVIDER,
    markets: tuple[str, ...] = ("1x2", "btts"),
) -> str:
    return "\n".join(
        [
            APPROVAL_PHRASE,
            f"pr: {pr}",
            f"provider: {provider}",
            f"markets: {', '.join(markets)}",
        ]
    )


def _evidence_time(outputs: Path) -> datetime:
    """The newest `generated_at` already in the directory, or a long time ago."""
    newest = datetime(2000, 1, 1, tzinfo=timezone.utc)
    for path in outputs.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        raw = str(payload.get("generated_at") or "")
        if not raw:
            continue
        try:
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        newest = max(newest, stamp.astimezone(timezone.utc))
    return newest


def write_evidence(outputs: Path) -> datetime:
    """Fill in whichever expected evidence artifacts are not there yet."""
    outputs.mkdir(parents=True, exist_ok=True)
    stamp = _evidence_time(outputs)
    for name in EVIDENCE_ARTIFACTS:
        path = outputs / name
        if path.is_file():
            continue
        path.write_text(
            json.dumps({"generated_at": stamp.isoformat(), "name": name}),
            encoding="utf-8",
        )
    return stamp


def grant(
    monkeypatch,
    outputs: Path,
    *,
    markets: tuple[str, ...] = ("1x2", "btts"),
    provider: str = PROVIDER,
    pr: int = PR,
):
    """A genuine ApprovalGrant, obtained by verifying a genuine-shaped approval."""
    evidence_at = write_evidence(outputs)
    submitted = evidence_at + timedelta(minutes=1)
    now = submitted + timedelta(minutes=1)
    activity = {
        "pr_number": pr,
        "repository": REPOSITORY,
        "head_sha": HEAD,
        "reviews": [],
        "comments": [
            {
                "user": {"login": REVIEWER},
                "body": approval_body(pr=pr, provider=provider, markets=markets),
                "created_at": submitted.isoformat(),
                "id": 5372090952,
            }
        ],
    }
    monkeypatch.setattr(
        github_approval,
        "fetch_pr_activity",
        lambda pr_number, *, repository: activity,
    )
    return verified_approval_for_pr(
        pr,
        repository=REPOSITORY,
        provider_name=provider,
        expected_markets=markets,
        output_dir=outputs,
        now=now,
    )


def write_receipt_file(
    outputs: Path,
    *,
    markets: tuple[str, ...] = ("1x2", "btts"),
    receipt_id: str = "odds_api-20260821T114655-0400-20ffa5677988",
    reviewer: str = REVIEWER,
    provider: str = PROVIDER,
    pr: int = PR,
    decision: str = "approved_for_allowlist_pr",
    source_kind: str = "comment",
    review_state: str = "",
    **overrides: object,
) -> Path:
    """A receipt the read-time check accepts, written into a test directory."""
    write_evidence(outputs)
    checksums = {
        name: sha256((outputs / name).read_bytes()).hexdigest()
        for name in EVIDENCE_ARTIFACTS
    }
    approval: dict[str, object] = {
        "approval_phrase": APPROVAL_PHRASE,
        "decision": decision,
        "pr_number": pr,
        "repository": REPOSITORY,
        "reviewer_github_login": reviewer,
        "source_kind": source_kind,
        "source_id": 5372090952,
        "review_state": review_state,
        "approved_at": "2026-08-21T15:46:30+00:00",
        "head_sha": HEAD,
        "provider_name": provider,
        "approved_markets": sorted(markets),
        "evidence_checksums_sha256": checksums,
    }
    approval.update(overrides)
    payload = {
        "receipt_id": receipt_id,
        "decision": decision,
        "reviewer_name": reviewer,
        "provider_name": provider,
        "evidence": {
            "checklist": {
                "checksum_sha256": checksums["provider_acceptance_checklist.json"]
            }
        },
        "github_approval": approval,
    }
    path = outputs / "provider_human_acceptance_receipt.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def policy_with_receipt(
    path: Path,
    *,
    markets: tuple[str, ...] = ("1x2", "btts"),
    receipt_id: str = "odds_api-20260821T114655-0400-20ffa5677988",
    provider: str = PROVIDER,
    **extra: object,
) -> Path:
    """A provider policy whose allowlist entry names a receipt."""
    payload: dict[str, object] = {
        "allowed_markets": list(markets),
        "provider_allowlist_entries": {
            provider: {
                "allowlist_status": "allowed",
                "provider_name": provider,
                "evidence_receipt_id": receipt_id,
                "required_markets": list(markets),
            }
        },
    }
    payload.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
