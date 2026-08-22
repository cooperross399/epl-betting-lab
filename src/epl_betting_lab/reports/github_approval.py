"""Terminal-free human approval for provider allowlist PRs.

The Provider Policy PR Gate requires a human acceptance receipt. Producing that
receipt used to mean running a Terminal command with `--reviewer-name`, which is
both a chore and a weak attestation: whoever runs the command types the name.

This module takes the attestation from GitHub instead. A PR review or comment
authored by the approving account, containing an explicit approval block, is the
human act. The automation only *verifies* it and transcribes it into the receipt
the gate expects — it can neither author the approval nor stand in for it,
because the author identity comes from GitHub's API.

Everything fails closed. A missing phrase, an unexpected author, the wrong PR,
the wrong provider, an unapproved market, evidence that changed after the
approval, or an approval older than the freshness window all refuse to produce a
receipt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
from epl_betting_lab.providers.player_props_staging import PROP_EVENT_MARKETS


#: The exact token that marks a comment or review as an approval.
APPROVAL_PHRASE = "APPROVED_FOR_ALLOWLIST_PR"

#: Only this GitHub account may approve. A list, but deliberately a short one.
ALLOWED_REVIEWERS: tuple[str, ...] = ("cooperross399",)

#: The provider this flow may approve.
EXPECTED_PROVIDER = "the_odds_api"

#: Markets an approval may grant: exactly the markets the project can price.
#: Match markets come from the market registry; player-prop markets from the
#: props staging list — both single sources, so this flow and the cards can
#: never disagree about what a market is. Approvable is not approved — every
#: scope still needs the human approval block and evidence this module
#: verifies.
APPROVABLE_MARKETS: frozenset[str] = frozenset(MARKET_SELECTIONS) | frozenset(
    PROP_EVENT_MARKETS
)

#: Markets that must never appear in an approval while they are excluded.
#:
#: `total_2_5` sat here from 2026-08-17, when the complete 2.5 line appeared
#: to exist only at books without an account. That finding was reversed on
#: 2026-08-19 — `alternate_totals` carries the line at BetRivers and FanDuel
#: on every fixture — so totals awaits policy approval like any other market
#: and no market is currently forbidden. The mechanism stays: put a market
#: here to make it unapprovable while an exclusion decision is in force.
FORBIDDEN_MARKETS: frozenset[str] = frozenset()

#: How long an approval stays usable.
DEFAULT_MAX_APPROVAL_AGE_HOURS = 72.0

#: Artifacts whose content the approval is bound to. All are checksummed into
#: the receipt for the audit record.
EVIDENCE_ARTIFACTS = (
    "provider_acceptance_checklist.json",
    "provider_allowlist_evidence_bundle.json",
    "provider_shadow_verification.json",
    "automated_card_input.json",
)

#: Artifacts the gate itself regenerates deterministically on every run. Their
#: `generated_at` moves each time without the underlying evidence changing, so
#: comparing an approval against them would make every approval instantly
#: "stale" - the gate would invalidate the approval it was verifying.
DERIVED_ARTIFACTS = frozenset(
    {
        "provider_acceptance_checklist.json",
        "provider_allowlist_evidence_bundle.json",
    }
)

#: Artifacts that only change when real provider work happens: a shadow run, or
#: a rebuild of the card input. These are what staleness is measured against, so
#: fetching new provider data after an approval still invalidates it.
SUBSTANTIVE_ARTIFACTS = tuple(
    name for name in EVIDENCE_ARTIFACTS if name not in DERIVED_ARTIFACTS
)


class GitHubApprovalError(RuntimeError):
    """Raised when an approval cannot be verified. Always fail closed."""


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _parse_time(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_pr_activity(pr_number: int, *, repository: str = "") -> dict[str, Any]:
    """Read the PR's reviews, comments, and head SHA from GitHub.

    Shells out to `gh`, which uses the operator's existing authentication. The
    result is plain data so tests can supply it directly.
    """

    def _api(path: str) -> Any:
        target = f"repos/{repository}/{path}" if repository else path
        result = subprocess.run(
            ["gh", "api", target, "--paginate"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitHubApprovalError(
                f"GitHub API call failed for `{target}`: {result.stderr.strip()[:200]}"
            )
        try:
            return json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise GitHubApprovalError(
                f"GitHub API returned unreadable JSON for `{target}`."
            ) from exc

    if not repository:
        raise GitHubApprovalError("A repository in owner/name form is required.")

    pull = _api(f"pulls/{pr_number}")
    reviews = _api(f"pulls/{pr_number}/reviews")
    comments = _api(f"issues/{pr_number}/comments")
    head = pull.get("head", {}) if isinstance(pull, Mapping) else {}
    return {
        "pr_number": pr_number,
        "repository": repository,
        "head_sha": _clean(head.get("sha")),
        "reviews": reviews if isinstance(reviews, list) else [],
        "comments": comments if isinstance(comments, list) else [],
    }


def _candidate_entries(activity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalise reviews and comments into one shape."""
    entries: list[dict[str, Any]] = []
    for review in activity.get("reviews", []) or []:
        if not isinstance(review, Mapping):
            continue
        entries.append(
            {
                "kind": "review",
                "author": _clean((review.get("user") or {}).get("login")),
                "body": _clean(review.get("body")),
                "submitted_at": _clean(review.get("submitted_at")),
                "commit_id": _clean(review.get("commit_id")),
                "state": _clean(review.get("state")),
                "id": review.get("id"),
            }
        )
    for comment in activity.get("comments", []) or []:
        if not isinstance(comment, Mapping):
            continue
        entries.append(
            {
                "kind": "comment",
                "author": _clean((comment.get("user") or {}).get("login")),
                "body": _clean(comment.get("body")),
                "submitted_at": _clean(comment.get("created_at")),
                "commit_id": "",
                "state": "",
                "id": comment.get("id"),
            }
        )
    return entries


def parse_approval_block(body: str) -> dict[str, Any]:
    """Extract the declared provider, markets, and PR from an approval body.

    Declaring them in the comment is what makes the approval *specific*. An
    approval that merely says the phrase would bind to whatever the repository
    happened to contain at verification time.
    """
    declared: dict[str, Any] = {"provider": "", "markets": [], "pr": None}
    for raw_line in body.splitlines():
        line = raw_line.strip().lstrip("-*> ").strip()
        lowered = line.lower()
        if lowered.startswith("provider:"):
            declared["provider"] = line.split(":", 1)[1].strip().lower()
        elif lowered.startswith("markets:"):
            values = line.split(":", 1)[1]
            declared["markets"] = [
                item.strip().lower()
                for item in values.replace(";", ",").split(",")
                if item.strip()
            ]
        elif lowered.startswith("pr:"):
            digits = "".join(
                char for char in line.split(":", 1)[1] if char.isdigit()
            )
            declared["pr"] = int(digits) if digits else None
    return declared


def evidence_checksums(output_dir: Path | None = None) -> dict[str, str]:
    """SHA-256 of each evidence artifact the approval is bound to."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    checksums: dict[str, str] = {}
    for name in EVIDENCE_ARTIFACTS:
        path = outputs / name
        if not path.is_file():
            continue
        try:
            checksums[name] = sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
    return checksums


def _latest_evidence_time(output_dir: Path | None = None) -> datetime | None:
    """Newest `generated_at` across the substantive evidence artifacts.

    Deliberately ignores artifacts the gate regenerates itself; see
    :data:`DERIVED_ARTIFACTS`.
    """
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    newest: datetime | None = None
    for name in SUBSTANTIVE_ARTIFACTS:
        path = outputs / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        stamp = _parse_time(payload.get("generated_at"))
        if stamp and (newest is None or stamp > newest):
            newest = stamp
    return newest


def verify_github_approval(
    activity: Mapping[str, Any],
    *,
    pr_number: int,
    provider_name: str = EXPECTED_PROVIDER,
    expected_markets: Sequence[str] = ("1x2", "btts"),
    allowed_reviewers: Sequence[str] = ALLOWED_REVIEWERS,
    output_dir: Path | None = None,
    max_age_hours: float = DEFAULT_MAX_APPROVAL_AGE_HOURS,
    now: datetime | None = None,
    require_head_match: bool = True,
) -> dict[str, Any]:
    """Verify a GitHub approval and return its bound, non-secret details.

    Raises :class:`GitHubApprovalError` on every failure mode rather than
    returning a partial result, so no caller can accidentally treat an
    unverified approval as verified.
    """
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expected = {item.strip().lower() for item in expected_markets}
    reviewers = {item.strip().lower() for item in allowed_reviewers}

    if expected & FORBIDDEN_MARKETS:
        raise GitHubApprovalError(
            "Refusing to verify an approval scope containing an excluded "
            f"market: {sorted(expected & FORBIDDEN_MARKETS)}."
        )
    if not expected <= APPROVABLE_MARKETS:
        raise GitHubApprovalError(
            f"Markets {sorted(expected - APPROVABLE_MARKETS)} are not approvable "
            "through this flow."
        )

    activity_pr = activity.get("pr_number")
    if activity_pr is not None and int(activity_pr) != int(pr_number):
        raise GitHubApprovalError(
            f"Activity is for PR #{activity_pr}, not PR #{pr_number}."
        )

    entries = [
        entry
        for entry in _candidate_entries(activity)
        if APPROVAL_PHRASE in entry["body"]
    ]
    if not entries:
        raise GitHubApprovalError(
            f"No review or comment on PR #{pr_number} contains "
            f"`{APPROVAL_PHRASE}`."
        )

    by_allowed = [
        entry for entry in entries if entry["author"].lower() in reviewers
    ]
    if not by_allowed:
        authors = sorted({entry["author"] for entry in entries if entry["author"]})
        raise GitHubApprovalError(
            f"`{APPROVAL_PHRASE}` was present but not from an allowed reviewer. "
            f"Saw: {authors or ['unknown']}; allowed: {sorted(reviewers)}."
        )

    # Most recent valid-looking approval wins.
    by_allowed.sort(key=lambda entry: _clean(entry["submitted_at"]), reverse=True)
    entry = by_allowed[0]

    submitted = _parse_time(entry["submitted_at"])
    if submitted is None:
        raise GitHubApprovalError("The approval has no readable timestamp.")

    age_hours = (moment - submitted).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        raise GitHubApprovalError(
            f"The approval is stale: {age_hours:.1f}h old, limit "
            f"{max_age_hours:.0f}h. Re-approve on the current evidence."
        )
    if age_hours < -0.25:
        raise GitHubApprovalError("The approval timestamp is in the future.")

    declared = parse_approval_block(entry["body"])

    if declared["pr"] is not None and int(declared["pr"]) != int(pr_number):
        raise GitHubApprovalError(
            f"The approval names PR #{declared['pr']}, not PR #{pr_number}."
        )
    if not declared["provider"]:
        raise GitHubApprovalError(
            "The approval must declare `provider:` so it binds to one provider."
        )
    if declared["provider"] != provider_name.strip().lower():
        raise GitHubApprovalError(
            f"The approval names provider `{declared['provider']}`, expected "
            f"`{provider_name}`."
        )
    if not declared["markets"]:
        raise GitHubApprovalError(
            "The approval must declare `markets:` so it binds to a market scope."
        )

    declared_markets = set(declared["markets"])
    forbidden = declared_markets & FORBIDDEN_MARKETS
    if forbidden:
        raise GitHubApprovalError(
            f"The approval includes excluded market(s) {sorted(forbidden)}. "
            "Totals are not approvable while incomplete."
        )
    if declared_markets != expected:
        raise GitHubApprovalError(
            f"The approval grants {sorted(declared_markets)} but the reviewed "
            f"scope is {sorted(expected)}."
        )

    if require_head_match and entry["kind"] == "review":
        head_sha = _clean(activity.get("head_sha"))
        commit_id = _clean(entry["commit_id"])
        if head_sha and commit_id and head_sha != commit_id:
            raise GitHubApprovalError(
                "The review approved an older commit; the PR has changed since. "
                "Re-approve the current head."
            )

    evidence_time = _latest_evidence_time(output_dir)
    if evidence_time and evidence_time > submitted:
        raise GitHubApprovalError(
            "Provider evidence changed after the approval was given "
            f"(evidence {evidence_time.isoformat()} > approval "
            f"{submitted.isoformat()}). Re-approve on the current evidence."
        )

    checksums = evidence_checksums(output_dir)
    if not checksums:
        raise GitHubApprovalError(
            "No evidence artifacts were found to bind the approval to."
        )

    return {
        "approval_phrase": APPROVAL_PHRASE,
        "decision": "approved_for_allowlist_pr",
        "pr_number": int(pr_number),
        "repository": _clean(activity.get("repository")),
        "reviewer_github_login": entry["author"],
        "source_kind": entry["kind"],
        "source_id": entry["id"],
        "review_state": entry["state"],
        "approved_at": submitted.isoformat(),
        "approval_age_hours": round(age_hours, 2),
        "head_sha": _clean(activity.get("head_sha")),
        "commit_id": _clean(entry["commit_id"]),
        "provider_name": provider_name,
        "approved_markets": sorted(declared_markets),
        # Every priced market this approval does not grant, so the receipt
        # names what was withheld as well as what was given.
        "excluded_markets": sorted(
            (APPROVABLE_MARKETS - declared_markets) | FORBIDDEN_MARKETS
        ),
        "evidence_checksums_sha256": checksums,
        "evidence_generated_at": evidence_time.isoformat() if evidence_time else "",
        "verified_at": moment.isoformat(),
    }


def approval_template(
    pr_number: int,
    *,
    provider_name: str = EXPECTED_PROVIDER,
    markets: Sequence[str] = ("1x2", "btts"),
) -> str:
    """The exact text to paste into a GitHub review or comment."""
    return "\n".join(
        [
            APPROVAL_PHRASE,
            f"pr: {pr_number}",
            f"provider: {provider_name}",
            f"markets: {', '.join(markets)}",
        ]
    )


def policy_checksum(policy_path: Path | None = None) -> str:
    path = (
        MANUAL_DIR / "staging_provider_policy.json"
        if policy_path is None
        else Path(policy_path)
    )
    if not path.is_file():
        return ""
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
