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
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
from epl_betting_lab.providers.player_props_staging import PROP_EVENT_MARKETS
from epl_betting_lab.reports.approval_grant import (
    ApprovalGrant,
    ApprovalGrantError,
    claim_grant_token,
)


#: The exact token that marks a comment or review as an approval.
APPROVAL_PHRASE = "APPROVED_FOR_ALLOWLIST_PR"

#: The exact token that withdraws an approval. Before this existed, only the
#: newest entry CARRYING THE APPROVAL PHRASE was considered, so a later comment
#: saying "I withdraw that approval" was invisible to the verifier and the
#: withdrawn approval kept verifying until it aged out. An explicit token wins
#: when it is the newest thing an allowed reviewer said.
REVOCATION_PHRASE = "REVOKED_FOR_ALLOWLIST_PR"

#: The only GitHub review state this flow treats as an approval.
#:
#: The state used to be transcribed into the receipt and used for nothing, so a
#: review GitHub itself reported as DISMISSED -- withdrawn -- verified exactly
#: like an APPROVED one, as did CHANGES_REQUESTED, PENDING and COMMENTED. A
#: comment carries no state at all; that is why the empty string is handled
#: separately below rather than added here.
ACCEPTED_REVIEW_STATES: frozenset[str] = frozenset({"APPROVED"})

#: Review states refused by name, so the refusal says which one it saw rather
#: than "not accepted". Any state outside both sets is refused too.
REFUSED_REVIEW_STATES: tuple[str, ...] = (
    "DISMISSED",
    "CHANGES_REQUESTED",
    "PENDING",
    "COMMENTED",
)

#: Absolute locations a real `gh` may live at.
#:
#: The fetch used to name the client by bare command name and let the shell
#: search PATH for it, so a forty-line fake earlier on PATH answered every call
#: with whatever JSON it liked and defeated the whole mechanism without
#: touching a line of this repository. Resolution never consults PATH now.
#: `tests/test_approval_cannot_be_forged.py` greps this module for that shape,
#: so the old call is described here rather than spelled -- a comment that
#: spells it trips the guard.
TRUSTED_GH_PATHS: tuple[str, ...] = (
    "/opt/homebrew/bin/gh",
    "/usr/local/bin/gh",
    "/usr/bin/gh",
    "/bin/gh",
    "/home/linuxbrew/.linuxbrew/bin/gh",
    "/snap/bin/gh",
)

#: PATH handed to `gh`, so a shim cannot reach it through its own subprocesses
#: (a credential helper, `git`) either.
TRUSTED_SUBPROCESS_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

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

#: How long an approval stays usable. Also the ceiling: `--max-age-hours` used
#: to be an unbounded float, and 999999 transcribed a five-hundred-hour-old
#: approval into a fresh receipt. A caller may ask for less, never for more.
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


#: The object that may construct an :class:`ApprovalGrant`. Claimed here, at
#: import time, and never returned by any function in this module. See
#: `approval_grant.py` for what this does and does not buy.
_GRANT_TOKEN = object()
claim_grant_token(_GRANT_TOKEN)


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _unquoted_lines(body: str) -> list[str]:
    """The body's own lines, with every blockquoted line dropped.

    GitHub renders a leading `>` as a quotation of someone else's text. The
    parser used to strip `> ` along with bullet markers, so a comment reading
    "REVOKED. Ignore this: > APPROVED_FOR_ALLOWLIST_PR / > pr: 224 / ..."
    parsed as a brand new approval. A quoted line is a record of what was said,
    never a fresh act.
    """
    return [line for line in body.splitlines() if not line.lstrip().startswith(">")]


def _says(body: str, phrase: str) -> bool:
    """True when `phrase` appears outside every quoted block."""
    return any(phrase in line for line in _unquoted_lines(body))


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


def trusted_subprocess_env() -> dict[str, str]:
    """The environment `gh` runs under: the caller's, minus an attacker PATH."""
    env = dict(os.environ)
    env["PATH"] = TRUSTED_SUBPROCESS_PATH
    return env


def resolve_gh() -> str:
    """The absolute path of a real `gh`, or refuse.

    PATH is never consulted. A candidate must be a regular executable file at
    one of :data:`TRUSTED_GH_PATHS`, must still be one after symlinks are
    resolved, must not resolve to anything inside this repository, and must
    answer `--version` the way `gh` does. A shim that satisfies all four has
    had to be installed into a system directory, which is a different and much
    larger compromise than dropping a file on PATH.
    """
    project_root = PROJECT_ROOT.resolve()
    seen: list[str] = []
    for raw in TRUSTED_GH_PATHS:
        candidate = Path(raw)
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        resolved = Path(os.path.realpath(candidate))
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            continue
        if resolved == project_root or project_root in resolved.parents:
            raise GitHubApprovalError(
                f"`{raw}` resolves to `{resolved}`, inside this repository. "
                "A GitHub client shipped in the tree it vouches for is not a "
                "witness."
            )
        seen.append(str(resolved))
        try:
            probe = subprocess.run(
                [str(resolved), "--version"],
                capture_output=True,
                text=True,
                env=trusted_subprocess_env(),
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GitHubApprovalError(
                f"`{resolved}` could not be run: {type(exc).__name__}."
            ) from exc
        if probe.returncode != 0 or not probe.stdout.strip().lower().startswith(
            "gh version"
        ):
            raise GitHubApprovalError(
                f"`{resolved}` did not identify itself as the GitHub CLI. "
                "Refusing to take an approval from it."
            )
        return str(resolved)
    raise GitHubApprovalError(
        "No GitHub CLI was found at a trusted absolute location "
        f"({', '.join(TRUSTED_GH_PATHS)}). PATH is deliberately not consulted: "
        "a `gh` earlier on PATH would be able to invent the approval this "
        "module exists to verify."
        + (f" Checked and rejected: {seen}." if seen else "")
    )


def fetch_pr_activity(pr_number: int, *, repository: str = "") -> dict[str, Any]:
    """Read the PR's reviews, comments, and head SHA from GitHub.

    Runs a `gh` resolved at a trusted absolute location -- never through PATH
    -- using the operator's existing authentication.
    """

    gh = resolve_gh()

    def _api(path: str) -> Any:
        target = f"repos/{repository}/{path}" if repository else path
        result = subprocess.run(
            [gh, "api", target, "--paginate"],
            capture_output=True,
            text=True,
            env=trusted_subprocess_env(),
            timeout=120,
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

    Bullets and case are tolerated; blockquoted lines are not read at all. A
    `> ` prefix is GitHub quoting someone else, and quoting an approval is not
    giving one -- see :func:`_unquoted_lines`.
    """
    declared: dict[str, Any] = {"provider": "", "markets": [], "pr": None}
    for raw_line in _unquoted_lines(body):
        line = raw_line.strip().lstrip("-* ").strip()
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


def missing_evidence_artifacts(output_dir: Path | None = None) -> list[str]:
    """Expected evidence artifacts that are absent or unreadable.

    :func:`evidence_checksums` skips what it cannot read, and the only check on
    its result used to be "is the dict non-empty". Deleting two of the four
    artifacts therefore produced an approval bound to two, with nothing in the
    receipt or the output saying the binding had narrowed. An approval that
    silently covers less evidence than it claims is the failure this exists to
    stop.
    """
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    present = evidence_checksums(outputs)
    return [name for name in EVIDENCE_ARTIFACTS if name not in present]


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

    `activity` is an argument so the rules can be tested against every shape of
    PR without a network. That makes this function UNABLE TO MINT A RECEIPT on
    purpose: it returns plain data, and the receipt writer will not take plain
    data. Use :func:`verified_approval_for_pr`, which fetches its own activity,
    when a receipt is the point.
    """
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expected = {item.strip().lower() for item in expected_markets}
    reviewers = {item.strip().lower() for item in allowed_reviewers}

    # The window is a ceiling, not a suggestion. It was an unbounded float, so
    # `--max-age-hours 999999` transcribed a five-hundred-hour-old approval.
    try:
        max_age_hours = float(max_age_hours)
    except (TypeError, ValueError):
        raise GitHubApprovalError(
            "The freshness window must be a number of hours."
        ) from None
    if max_age_hours <= 0:
        raise GitHubApprovalError("The freshness window must be positive.")
    if max_age_hours > DEFAULT_MAX_APPROVAL_AGE_HOURS:
        raise GitHubApprovalError(
            f"A freshness window of {max_age_hours:g}h was asked for; the "
            f"ceiling is {DEFAULT_MAX_APPROVAL_AGE_HOURS:g}h. A caller may ask "
            "for a shorter window, never a longer one."
        )

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

    # Both phrases are looked for outside quoted blocks only, and both are
    # considered together: an approval that a later comment withdrew is not an
    # approval, and only reading the newest entry that happens to CARRY THE
    # APPROVAL PHRASE would never see the withdrawal.
    spoken = [
        entry
        for entry in _candidate_entries(activity)
        if _says(entry["body"], APPROVAL_PHRASE)
        or _says(entry["body"], REVOCATION_PHRASE)
    ]
    entries = [
        entry for entry in spoken if _says(entry["body"], APPROVAL_PHRASE)
    ]
    if not entries:
        raise GitHubApprovalError(
            f"No unquoted review or comment on PR #{pr_number} contains "
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

    # A revocation by an allowed reviewer that is newer than the approval ends
    # it. Ties go to the revocation: withdrawing consent must never need to be
    # the later of two timestamps that are the same.
    revocations = [
        item
        for item in spoken
        if item["author"].lower() in reviewers
        and _says(item["body"], REVOCATION_PHRASE)
        and _clean(item["submitted_at"]) >= _clean(entry["submitted_at"])
    ]
    if revocations:
        revocations.sort(
            key=lambda item: _clean(item["submitted_at"]), reverse=True
        )
        newest = revocations[0]
        raise GitHubApprovalError(
            f"The approval on PR #{pr_number} was withdrawn: "
            f"`{REVOCATION_PHRASE}` in a {newest['kind']} by "
            f"{newest['author'] or 'unknown'} at "
            f"{_clean(newest['submitted_at']) or 'an unreadable time'}. "
            "Re-approve if the withdrawal was a mistake."
        )

    submitted = _parse_time(entry["submitted_at"])
    if submitted is None:
        raise GitHubApprovalError("The approval has no readable timestamp.")

    # The state was recorded into the receipt and checked against nothing, so
    # a review GitHub itself reports as DISMISSED -- one it says was withdrawn
    # -- verified exactly like an APPROVED one.
    state = _clean(entry["state"]).upper()
    if entry["kind"] == "review":
        if state in REFUSED_REVIEW_STATES:
            raise GitHubApprovalError(
                f"The review is in state {state}, which GitHub does not report "
                "as an approval. Submit a review in state APPROVED, or leave "
                "the approval block as a comment."
            )
        if state not in ACCEPTED_REVIEW_STATES:
            raise GitHubApprovalError(
                f"The review is in state `{state or 'unset'}`; only "
                f"{sorted(ACCEPTED_REVIEW_STATES)} is accepted."
            )
    elif state:
        # Comments carry no state. One that does is not a comment this module
        # fetched, so it is not something to reason about.
        raise GitHubApprovalError(
            f"A comment carries no review state, but this one claims `{state}`."
        )

    age_hours = (moment - submitted).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        raise GitHubApprovalError(
            f"The approval is stale: {age_hours:.1f}h old, limit "
            f"{max_age_hours:.0f}h. Re-approve on the current evidence."
        )
    if age_hours < -0.25:
        raise GitHubApprovalError("The approval timestamp is in the future.")

    declared = parse_approval_block(entry["body"])

    if declared["pr"] is None:
        raise GitHubApprovalError(
            "The approval must declare `pr:` so it binds to one pull request. "
            "Without it the block binds to whichever PR the verifier is "
            "pointed at."
        )
    if int(declared["pr"]) != int(pr_number):
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
    absent = missing_evidence_artifacts(output_dir)
    if absent:
        raise GitHubApprovalError(
            "The approval would bind to "
            f"{len(checksums)} of {len(EVIDENCE_ARTIFACTS)} evidence "
            f"artifacts; these are absent or unreadable: {absent}. An approval "
            "that covers less than it claims is refused rather than narrowed."
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


def verified_approval_for_pr(
    pr_number: int,
    *,
    repository: str,
    provider_name: str = EXPECTED_PROVIDER,
    expected_markets: Sequence[str] = ("1x2", "btts"),
    output_dir: Path | None = None,
    max_age_hours: float = DEFAULT_MAX_APPROVAL_AGE_HOURS,
    now: datetime | None = None,
) -> ApprovalGrant:
    """Fetch the PR's activity from GitHub, verify it, and return a grant.

    This is the ONLY way to obtain an :class:`ApprovalGrant`, and a grant is
    the only thing that lets an approval receipt be written.

    :func:`verify_github_approval` takes the activity as an argument, which is
    exactly right for testing the rules and exactly wrong for minting a
    receipt: a hand-written mapping is indistinguishable from a fetched one, so
    a caller who could choose the activity could choose the approval. That is
    why the pure verifier returns plain data and this function -- which fetches
    its own activity and accepts none from anybody -- returns the grant.
    """
    repository = _clean(repository)
    if not repository:
        raise GitHubApprovalError("A repository in owner/name form is required.")

    activity = fetch_pr_activity(pr_number, repository=repository)
    approval = verify_github_approval(
        activity,
        pr_number=pr_number,
        provider_name=provider_name,
        expected_markets=expected_markets,
        output_dir=output_dir,
        max_age_hours=max_age_hours,
        now=now,
    )
    try:
        return ApprovalGrant(
            reviewer_github_login=str(approval["reviewer_github_login"]),
            provider_name=str(approval["provider_name"]),
            pr_number=int(approval["pr_number"]),
            approved_markets=tuple(approval["approved_markets"]),
            details=approval,
            token=_GRANT_TOKEN,
        )
    except ApprovalGrantError as exc:  # pragma: no cover - defence in depth
        raise GitHubApprovalError(f"The approval could not be granted: {exc}") from exc


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


#: The receipt the whole flow exists to produce.
RECEIPT_FILENAME = "provider_human_acceptance_receipt.json"

#: Bound artifacts whose checksum can honestly be re-checked when the card is
#: built, rather than every artifact the receipt names.
#:
#: The other three are rewritten between the approval and the card, so
#: requiring them to match would refuse every real approval -- and a gate that
#: refuses everything is a gate that gets deleted. Read on origin/main at
#: ee8e318 rather than assumed: `provider_shadow_verification.json` is
#: rewritten by `scripts/run_provider_shadow_verification.py` and
#: `automated_card_input.json` by `scripts/refresh_all_reports.py`, and
#: `.github/workflows/matchday-refresh.yml` runs both before the card is
#: built; `provider_allowlist_evidence_bundle.json` is rebuilt over the policy
#: change in the same PR that records the approval, and the committed copy
#: already differs from the checksum the shipped receipt names.
#:
#: `provider_acceptance_checklist.json` is the one nothing in the card path
#: touches, and it is also the document the reviewer actually reviewed.
READ_TIME_VERIFIED_ARTIFACTS: tuple[str, ...] = (
    "provider_acceptance_checklist.json",
)


def _receipt_state_problem(source_kind: str, state: str) -> str:
    """The same state rule the verifier applies, re-applied at read time."""
    if source_kind == "review":
        if state in REFUSED_REVIEW_STATES:
            return f"the recorded review state is {state}"
        if state not in ACCEPTED_REVIEW_STATES:
            return f"the recorded review state `{state or 'unset'}` is not an approval"
    elif source_kind == "comment":
        if state:
            return f"a comment cannot carry review state `{state}`"
    else:
        return f"the approval source kind `{source_kind or 'unset'}` is unknown"
    return ""


def approved_markets_from_receipt(
    output_dir: Path | None = None,
    *,
    allowed_reviewers: Sequence[str] = ALLOWED_REVIEWERS,
    expected_receipt_id: str = "",
    expected_provider_name: str = "",
) -> tuple[frozenset[str], list[str]]:
    """Markets a verified receipt on disk actually grants, and why not.

    The read path used to stop at "does the receipt file exist". It never
    parsed the JSON, never looked at the reviewer, and never re-checked a
    single checksum the receipt printed -- so a forged receipt beside a
    hand-edited policy entry was indistinguishable from a real approval to
    everything downstream of it. The merge-time gate catches that at merge; it
    does nothing for a file written straight into `data/outputs/` on a machine
    where the card is built.

    Returns `(markets, problems)`. `problems` empty means the receipt verified;
    otherwise `markets` is empty and every reason is listed. Never raises: the
    caller disables markets, and a crash in the card build would be a worse
    failure than a card with no picks.

    `allowed_reviewers` defaults to the module constant and is not reachable
    from any environment variable, git config, CLI flag or config file.
    """
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    path = outputs / RECEIPT_FILENAME
    problems: list[str] = []
    empty: frozenset[str] = frozenset()

    if not path.is_file():
        return empty, [f"no human acceptance receipt at `{path.name}`"]
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return empty, [f"the receipt could not be read: {type(exc).__name__}"]
    if not isinstance(receipt, Mapping):
        return empty, ["the receipt is not a JSON object"]

    reviewers = {item.strip().lower() for item in allowed_reviewers}

    if _clean(receipt.get("decision")) != "approved_for_allowlist_pr":
        problems.append(
            f"the receipt decision is `{_clean(receipt.get('decision')) or 'missing'}`"
        )
    if _clean(receipt.get("reviewer_name")).lower() not in reviewers:
        problems.append(
            "the receipt reviewer "
            f"`{_clean(receipt.get('reviewer_name')) or 'missing'}` is not an "
            "allowed reviewer"
        )
    if expected_receipt_id and _clean(receipt.get("receipt_id")) != _clean(
        expected_receipt_id
    ):
        problems.append(
            "the policy names receipt "
            f"`{_clean(expected_receipt_id)}` but the receipt on disk is "
            f"`{_clean(receipt.get('receipt_id')) or 'unidentified'}`"
        )

    approval = receipt.get("github_approval")
    if not isinstance(approval, Mapping):
        problems.append("the receipt records no verified GitHub approval")
        return empty, problems

    if _clean(approval.get("approval_phrase")) != APPROVAL_PHRASE:
        problems.append("the recorded approval phrase is not the approval phrase")
    if _clean(approval.get("decision")) != "approved_for_allowlist_pr":
        problems.append("the recorded GitHub decision is not an approval")
    login = _clean(approval.get("reviewer_github_login"))
    if login.lower() not in reviewers:
        problems.append(
            f"the approving GitHub account `{login or 'missing'}` is not an "
            "allowed reviewer"
        )
    state_problem = _receipt_state_problem(
        _clean(approval.get("source_kind")).lower(),
        _clean(approval.get("review_state")).upper(),
    )
    if state_problem:
        problems.append(state_problem)
    try:
        pr_number = int(approval.get("pr_number"))
    except (TypeError, ValueError):
        pr_number = 0
    if pr_number <= 0:
        problems.append("the approval names no pull request")
    if expected_provider_name and _clean(
        approval.get("provider_name")
    ).lower() != _clean(expected_provider_name).lower():
        problems.append(
            "the approval is for provider "
            f"`{_clean(approval.get('provider_name')) or 'missing'}`, not "
            f"`{_clean(expected_provider_name)}`"
        )

    raw_markets = approval.get("approved_markets")
    markets: frozenset[str] = frozenset()
    if not isinstance(raw_markets, (list, tuple)) or not raw_markets:
        problems.append("the approval grants no markets")
    else:
        markets = frozenset(
            _clean(item).lower() for item in raw_markets if _clean(item)
        )
        if not markets:
            problems.append("the approval grants no readable market names")

    table = approval.get("evidence_checksums_sha256")
    if not isinstance(table, Mapping):
        problems.append("the approval binds no evidence checksums")
        table = {}
    else:
        unbound = [
            name for name in EVIDENCE_ARTIFACTS if not _clean(table.get(name))
        ]
        if unbound:
            problems.append(f"the approval binds no checksum for {unbound}")
        malformed = sorted(
            name
            for name, value in table.items()
            if not _SHA256_HEX.fullmatch(_clean(value).lower())
        )
        if malformed:
            problems.append(f"the bound checksums for {malformed} are not sha256")

    # The receipt states the checklist checksum twice, in two shapes. A receipt
    # assembled by hand tends to fill in one of them.
    stated = receipt.get("evidence")
    if isinstance(stated, Mapping) and isinstance(
        stated.get("checklist"), Mapping
    ):
        one = _clean(stated["checklist"].get("checksum_sha256")).lower()
        two = _clean(table.get("provider_acceptance_checklist.json")).lower()
        if one and two and one != two:
            problems.append(
                "the receipt states two different checksums for the acceptance "
                "checklist"
            )

    for name in READ_TIME_VERIFIED_ARTIFACTS:
        bound = _clean(table.get(name)).lower()
        artifact = outputs / name
        if not artifact.is_file():
            problems.append(f"the bound evidence artifact `{name}` is gone")
            continue
        try:
            actual = sha256(artifact.read_bytes()).hexdigest()
        except OSError:
            problems.append(f"the bound evidence artifact `{name}` is unreadable")
            continue
        if bound and actual != bound:
            problems.append(
                f"`{name}` has changed since the approval was given"
            )

    if problems:
        return empty, problems
    return markets, []
