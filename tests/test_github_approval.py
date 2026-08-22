"""GitHub-UI approval verification: one way to pass, many ways to fail closed."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from epl_betting_lab.reports.github_approval import (
    APPROVAL_PHRASE,
    GitHubApprovalError,
    approval_template,
    evidence_checksums,
    parse_approval_block,
    verify_github_approval,
)


NOW = datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc)
APPROVED_AT = NOW - timedelta(hours=1)
PR = 115
HEAD = "abc123def456"


def _body(
    *,
    phrase: str = APPROVAL_PHRASE,
    pr: int | None = PR,
    provider: str = "the_odds_api",
    markets: str = "1x2, btts",
) -> str:
    lines = [phrase]
    if pr is not None:
        lines.append(f"pr: {pr}")
    if provider:
        lines.append(f"provider: {provider}")
    if markets:
        lines.append(f"markets: {markets}")
    return "\n".join(lines)


def _activity(
    *,
    author: str = "cooperross399",
    body: str | None = None,
    kind: str = "review",
    submitted: datetime = APPROVED_AT,
    commit_id: str = HEAD,
    pr_number: int = PR,
) -> dict:
    entry = {
        "user": {"login": author},
        "body": body if body is not None else _body(),
        "id": 1,
    }
    activity: dict = {
        "pr_number": pr_number,
        "repository": "cooperross399/epl-betting-lab",
        "head_sha": HEAD,
        "reviews": [],
        "comments": [],
    }
    if kind == "review":
        entry.update(
            {
                "submitted_at": submitted.isoformat(),
                "commit_id": commit_id,
                "state": "APPROVED",
            }
        )
        activity["reviews"] = [entry]
    else:
        entry["created_at"] = submitted.isoformat()
        activity["comments"] = [entry]
    return activity


def _evidence(tmp_path: Path, *, generated_at: datetime | None = None) -> Path:
    stamp = (generated_at or (APPROVED_AT - timedelta(hours=1))).isoformat()
    for name in (
        "provider_acceptance_checklist.json",
        "provider_shadow_verification.json",
        "automated_card_input.json",
    ):
        (tmp_path / name).write_text(
            json.dumps({"generated_at": stamp, "name": name}), encoding="utf-8"
        )
    return tmp_path


def _verify(activity: dict, tmp_path: Path, **kwargs):
    params = dict(pr_number=PR, output_dir=tmp_path, now=NOW)
    params.update(kwargs)
    return verify_github_approval(activity, **params)


# --- the happy path --------------------------------------------------------


def test_valid_review_approval_verifies(tmp_path: Path) -> None:
    _evidence(tmp_path)

    approval = _verify(_activity(), tmp_path)

    assert approval["decision"] == "approved_for_allowlist_pr"
    assert approval["reviewer_github_login"] == "cooperross399"
    assert approval["pr_number"] == PR
    assert approval["provider_name"] == "the_odds_api"
    assert approval["approved_markets"] == ["1x2", "btts"]
    assert approval["excluded_markets"] == [
        "corners_1x2",
        "corners_total_10_5",
        "corners_total_9_5",
        "double_chance",
        "draw_no_bet",
        "player_assists",
        "player_goal_scorer_anytime",
        "player_shots",
        "player_shots_on_target",
        "total_2_5",
    ]
    assert approval["source_kind"] == "review"
    assert approval["evidence_checksums_sha256"]


def test_valid_comment_approval_verifies(tmp_path: Path) -> None:
    _evidence(tmp_path)

    approval = _verify(_activity(kind="comment"), tmp_path)

    assert approval["source_kind"] == "comment"
    assert approval["reviewer_github_login"] == "cooperross399"


def test_approval_binds_every_required_field(tmp_path: Path) -> None:
    _evidence(tmp_path)

    approval = _verify(_activity(), tmp_path)

    for field in (
        "pr_number",
        "provider_name",
        "approved_markets",
        "excluded_markets",
        "evidence_checksums_sha256",
        "reviewer_github_login",
        "approved_at",
        "decision",
    ):
        assert field in approval and approval[field] not in (None, "", [])


# --- failure modes ---------------------------------------------------------


def test_missing_phrase_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)
    body = _body(phrase="looks good to me")

    with pytest.raises(GitHubApprovalError, match=APPROVAL_PHRASE):
        _verify(_activity(body=body), tmp_path)


def test_wrong_reviewer_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match="allowed reviewer"):
        _verify(_activity(author="someone-else"), tmp_path)


def test_wrong_provider_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)
    body = _body(provider="some_other_provider")

    with pytest.raises(GitHubApprovalError, match="provider"):
        _verify(_activity(body=body), tmp_path)


def test_missing_provider_declaration_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)
    body = _body(provider="")

    with pytest.raises(GitHubApprovalError, match="must declare `provider:`"):
        _verify(_activity(body=body), tmp_path)


def test_missing_markets_declaration_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)
    body = _body(markets="")

    with pytest.raises(GitHubApprovalError, match="must declare `markets:`"):
        _verify(_activity(body=body), tmp_path)


def test_totals_beyond_the_reviewed_scope_is_refused(tmp_path: Path) -> None:
    """A market cannot sneak into an approval the reviewed scope omits."""
    _evidence(tmp_path)
    body = _body(markets="1x2, btts, total_2_5")

    with pytest.raises(GitHubApprovalError, match="reviewed scope"):
        _verify(_activity(body=body), tmp_path)


def test_expanded_reviewed_scope_verifies_when_the_approval_matches(
    tmp_path: Path,
) -> None:
    """Since the 2026-08-19 reopening, every priced market is approvable —
    provided the approval names exactly the reviewed scope."""
    _evidence(tmp_path)
    scope = (
        "1x2",
        "btts",
        "total_2_5",
        "double_chance",
        "draw_no_bet",
        "corners_1x2",
        "corners_total_9_5",
        "corners_total_10_5",
    )
    body = _body(markets=", ".join(scope))

    approval = _verify(
        _activity(body=body), tmp_path, expected_markets=scope
    )

    assert approval["approved_markets"] == sorted(scope)


def test_a_forbidden_market_is_still_refused(
    tmp_path: Path, monkeypatch
) -> None:
    """The exclusion mechanism outlives the empty list: a market placed back
    in FORBIDDEN_MARKETS is refused even when the scope expects it."""
    import epl_betting_lab.reports.github_approval as module

    monkeypatch.setattr(
        module, "FORBIDDEN_MARKETS", frozenset({"total_2_5"})
    )
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match="excluded market"):
        _verify(_activity(), tmp_path, expected_markets=("1x2", "total_2_5"))


def test_narrower_market_scope_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)
    body = _body(markets="1x2")

    with pytest.raises(GitHubApprovalError, match="grants"):
        _verify(_activity(body=body), tmp_path)


def test_unapprovable_market_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)
    body = _body(markets="1x2, corners")

    with pytest.raises(GitHubApprovalError):
        _verify(_activity(body=body), tmp_path)


def test_wrong_pr_in_the_body_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)
    body = _body(pr=999)

    with pytest.raises(GitHubApprovalError, match="names PR"):
        _verify(_activity(body=body), tmp_path)


def test_activity_from_a_different_pr_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match="Activity is for PR"):
        _verify(_activity(pr_number=999), tmp_path)


def test_stale_approval_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path, generated_at=NOW - timedelta(days=30))

    with pytest.raises(GitHubApprovalError, match="stale"):
        _verify(
            _activity(submitted=NOW - timedelta(days=10)),
            tmp_path,
            max_age_hours=72,
        )


def test_future_dated_approval_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match="future"):
        _verify(_activity(submitted=NOW + timedelta(hours=5)), tmp_path)


def test_new_provider_evidence_after_the_approval_is_refused(tmp_path: Path) -> None:
    """Approving, then fetching new provider data, must invalidate the approval."""
    _evidence(tmp_path, generated_at=NOW - timedelta(minutes=5))

    with pytest.raises(GitHubApprovalError, match="Provider evidence changed"):
        _verify(_activity(), tmp_path)


def test_regenerating_derived_reports_does_not_invalidate_the_approval(
    tmp_path: Path,
) -> None:
    """The gate regenerates the checklist and bundle on every run.

    Measuring staleness against those would make the gate invalidate the very
    approval it is verifying, seconds after it was given.
    """
    _evidence(tmp_path)
    for name in ("provider_acceptance_checklist.json",
                 "provider_allowlist_evidence_bundle.json"):
        (tmp_path / name).write_text(
            json.dumps({"generated_at": NOW.isoformat(), "regenerated": True}),
            encoding="utf-8",
        )

    approval = _verify(_activity(), tmp_path)

    assert approval["approved_markets"] == ["1x2", "btts"]
    # The regenerated artifacts are still checksummed into the receipt.
    assert "provider_acceptance_checklist.json" in approval["evidence_checksums_sha256"]


def test_substantive_and_derived_artifacts_are_disjoint() -> None:
    from epl_betting_lab.reports.github_approval import (
        DERIVED_ARTIFACTS,
        EVIDENCE_ARTIFACTS,
        SUBSTANTIVE_ARTIFACTS,
    )

    assert set(SUBSTANTIVE_ARTIFACTS).isdisjoint(DERIVED_ARTIFACTS)
    assert set(SUBSTANTIVE_ARTIFACTS) | DERIVED_ARTIFACTS == set(EVIDENCE_ARTIFACTS)
    # A shadow run must remain a staleness trigger.
    assert "provider_shadow_verification.json" in SUBSTANTIVE_ARTIFACTS


def test_review_of_a_superseded_commit_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match="older commit"):
        _verify(_activity(commit_id="stale-sha"), tmp_path)


def test_missing_evidence_is_refused(tmp_path: Path) -> None:
    with pytest.raises(GitHubApprovalError, match="No evidence artifacts"):
        _verify(_activity(), tmp_path)


def test_no_activity_at_all_is_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)
    empty = {"pr_number": PR, "reviews": [], "comments": [], "head_sha": HEAD}

    with pytest.raises(GitHubApprovalError):
        _verify(empty, tmp_path)


def test_phrase_inside_a_quoted_block_by_wrong_author_is_refused(
    tmp_path: Path,
) -> None:
    """Someone quoting the phrase must not approve on the reviewer's behalf."""
    _evidence(tmp_path)
    activity = _activity(author="bot-account", body="> " + _body())

    with pytest.raises(GitHubApprovalError, match="allowed reviewer"):
        _verify(activity, tmp_path)


# --- helpers ---------------------------------------------------------------


def test_parse_approval_block_reads_declared_fields() -> None:
    parsed = parse_approval_block(_body())

    assert parsed["provider"] == "the_odds_api"
    assert parsed["markets"] == ["1x2", "btts"]
    assert parsed["pr"] == PR


def test_parse_tolerates_markdown_bullets_and_case() -> None:
    body = "\n".join(
        [APPROVAL_PHRASE, "- PR: 115", "* Provider: The_Odds_API", "> markets: 1X2; BTTS"]
    )
    parsed = parse_approval_block(body)

    assert parsed["pr"] == 115
    assert parsed["provider"] == "the_odds_api"
    assert parsed["markets"] == ["1x2", "btts"]


def test_template_contains_everything_the_verifier_requires() -> None:
    text = approval_template(PR)

    assert APPROVAL_PHRASE in text
    assert f"pr: {PR}" in text
    assert "provider: the_odds_api" in text
    assert "markets: 1x2, btts" in text
    assert "total_2_5" not in text


def test_template_round_trips_through_the_verifier(tmp_path: Path) -> None:
    _evidence(tmp_path)

    approval = _verify(_activity(body=approval_template(PR)), tmp_path)

    assert approval["approved_markets"] == ["1x2", "btts"]


def test_evidence_checksums_change_when_evidence_changes(tmp_path: Path) -> None:
    _evidence(tmp_path)
    before = evidence_checksums(tmp_path)

    (tmp_path / "provider_acceptance_checklist.json").write_text(
        json.dumps({"generated_at": APPROVED_AT.isoformat(), "changed": True}),
        encoding="utf-8",
    )
    after = evidence_checksums(tmp_path)

    assert before != after


def test_the_verifier_never_writes_anything(tmp_path: Path) -> None:
    _evidence(tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    _verify(_activity(), tmp_path)

    after = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert before == after


def test_most_recent_approval_wins(tmp_path: Path) -> None:
    _evidence(tmp_path)
    activity = _activity()
    activity["comments"] = [
        {
            "user": {"login": "cooperross399"},
            "body": _body(markets="1x2"),
            "created_at": (APPROVED_AT - timedelta(hours=5)).isoformat(),
            "id": 2,
        }
    ]

    approval = _verify(activity, tmp_path)

    # The newer, correct review wins over the older, narrower comment.
    assert approval["approved_markets"] == ["1x2", "btts"]
