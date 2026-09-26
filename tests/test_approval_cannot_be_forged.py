"""Nine ways a receipt was minted without a genuine GitHub approval.

Each test here reproduces one of them. Every one of these passed -- that is,
produced a valid receipt or a verified approval -- before the change that
accompanies this file. The threat model is not a stranger on the internet: it
is code running on this machine with the operator's own credentials, including
an agent. "Only forgeable by someone who can run code here" describes the
attack, not a mitigation.

What is deliberately NOT claimed: nothing here makes forgery impossible. Python
has no private state, so code in this interpreter can reach the construction
token in `github_approval`. These tests raise the cost of each route and, for
the routes that run through the card, close them at read time -- which is the
one place a forger cannot avoid, because the card has to read the receipt to
use it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import argparse
import ast
import importlib.util
import inspect
import json
import os
import re
import stat
import textwrap
from pathlib import Path

import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.market_eligibility import MARKET_SELECTIONS
from epl_betting_lab.reports import github_approval
from epl_betting_lab.reports.approval_grant import (
    ApprovalGrant,
    ApprovalGrantError,
    claim_grant_token,
)
from epl_betting_lab.reports.automated_card_input import (
    _receipt_unbacked_markets,
    save_automated_card_input,
)
from epl_betting_lab.reports.github_approval import (
    ALLOWED_REVIEWERS,
    APPROVAL_PHRASE,
    DEFAULT_MAX_APPROVAL_AGE_HOURS,
    EVIDENCE_ARTIFACTS,
    REFUSED_REVIEW_STATES,
    REVOCATION_PHRASE,
    GitHubApprovalError,
    approved_markets_from_receipt,
    fetch_pr_activity,
    verified_approval_for_pr,
    verify_github_approval,
)
from epl_betting_lab.reports.provider_human_acceptance_receipt import (
    APPROVAL_DECISION,
    ProviderHumanAcceptanceReceiptError,
    build_provider_human_acceptance_receipt,
)

from approval_grants import policy_with_receipt, write_receipt_file

NOW = datetime(2026, 8, 17, 20, 0, tzinfo=timezone.utc)
APPROVED_AT = NOW - timedelta(hours=1)
PR = 115
HEAD = "abc123def456"


def _code_only(function) -> str:
    """A function's source with every docstring removed, via `ast`.

    Comments never survive a parse. Docstrings do, and these functions describe
    the attacks they refuse -- so a naive grep over the source finds the
    description and calls it the defect.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)
        ):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


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


def _evidence(tmp_path: Path) -> Path:
    stamp = (APPROVED_AT - timedelta(hours=1)).isoformat()
    for name in EVIDENCE_ARTIFACTS:
        (tmp_path / name).write_text(
            json.dumps({"generated_at": stamp, "name": name}), encoding="utf-8"
        )
    return tmp_path


def _activity(
    *,
    kind: str = "review",
    body: str | None = None,
    state: str = "APPROVED",
    submitted: datetime = APPROVED_AT,
    author: str = "cooperross399",
    extra: list[dict] | None = None,
) -> dict:
    entry = {
        "user": {"login": author},
        "body": body if body is not None else _body(),
        "id": 1,
    }
    activity: dict = {
        "pr_number": PR,
        "repository": "cooperross399/epl-betting-lab",
        "head_sha": HEAD,
        "reviews": [],
        "comments": [],
    }
    if kind == "review":
        entry.update(
            {
                "submitted_at": submitted.isoformat(),
                "commit_id": HEAD,
                "state": state,
            }
        )
        activity["reviews"] = [entry]
    else:
        entry["created_at"] = submitted.isoformat()
        activity["comments"] = [entry]
    if extra:
        activity["comments"] = list(activity["comments"]) + extra
    return activity


def _verify(activity: dict, tmp_path: Path, **kwargs):
    params = dict(pr_number=PR, output_dir=tmp_path, now=NOW)
    params.update(kwargs)
    return verify_github_approval(activity, **params)


# --- 1. a `gh` earlier on PATH ---------------------------------------------


def _shim(tmp_path: Path, stdout: str) -> Path:
    directory = tmp_path / "shim"
    directory.mkdir()
    path = directory / "gh"
    path.write_text(
        "#!/bin/sh\ncat <<'JSON'\n" + stdout + "\nJSON\n", encoding="utf-8"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_a_gh_earlier_on_path_cannot_answer_for_github(
    tmp_path: Path, monkeypatch
) -> None:
    """The whole mechanism used to rest on `subprocess.run(["gh", ...])`.

    A shim on PATH answered every call with whatever it liked, so the approval
    the module verified was the approval the shim invented -- with no change to
    a single line of this repository.
    """
    shim = _shim(tmp_path, json.dumps({"head": {"sha": HEAD}}))
    monkeypatch.setenv("PATH", f"{shim.parent}{os.pathsep}{os.environ['PATH']}")
    # No trusted location holds a `gh`, so there is nothing legitimate to find.
    monkeypatch.setattr(github_approval, "TRUSTED_GH_PATHS", ())

    with pytest.raises(GitHubApprovalError, match="PATH is deliberately not"):
        fetch_pr_activity(PR, repository="cooperross399/epl-betting-lab")


def test_a_shim_at_a_trusted_location_must_still_be_gh(
    tmp_path: Path, monkeypatch
) -> None:
    shim = _shim(tmp_path, "{}")
    monkeypatch.setattr(github_approval, "TRUSTED_GH_PATHS", (str(shim),))

    with pytest.raises(GitHubApprovalError, match="did not identify itself"):
        github_approval.resolve_gh()


def test_a_gh_inside_this_repository_is_refused(monkeypatch) -> None:
    """A client shipped in the tree it vouches for is not a witness.

    The candidate has to live inside PROJECT_ROOT for the check to mean
    anything, so this writes a scratch directory there and removes it again.
    """
    scratch = PROJECT_ROOT / ".gh-refusal-scratch"
    inside = scratch / "gh"
    monkeypatch.setattr(github_approval, "TRUSTED_GH_PATHS", (str(inside),))
    scratch.mkdir(parents=True, exist_ok=True)
    inside.write_text("#!/bin/sh\necho gh version 2.0.0\n", encoding="utf-8")
    inside.chmod(inside.stat().st_mode | stat.S_IXUSR)
    try:
        with pytest.raises(GitHubApprovalError, match="inside this repository"):
            github_approval.resolve_gh()
    finally:
        inside.unlink()
        scratch.rmdir()


def test_no_github_call_is_made_through_a_bare_gh() -> None:
    """A grep, because the fix is a property of the source and not of a run."""
    bare = re.compile(r"subprocess\.run\(\s*\[\s*[\"']gh[\"']")
    for relative in (
        "src/epl_betting_lab/reports/github_approval.py",
        "scripts/create_receipt_from_github_approval.py",
    ):
        source = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert not bare.search(source), relative


# --- 2. the evidence object was publicly constructible ---------------------


def test_an_approval_grant_cannot_be_hand_built() -> None:
    with pytest.raises(ApprovalGrantError):
        ApprovalGrant(
            reviewer_github_login="cooperross399",
            provider_name="the_odds_api",
            pr_number=PR,
            approved_markets=("1x2", "btts"),
            details={},
        )
    with pytest.raises(ApprovalGrantError):
        ApprovalGrant(
            reviewer_github_login="cooperross399",
            provider_name="the_odds_api",
            pr_number=PR,
            approved_markets=("1x2", "btts"),
            details={},
            token=object(),
        )


def test_the_grant_token_cannot_be_reclaimed() -> None:
    """Rebinding the token to an object the attacker controls must fail loudly."""
    with pytest.raises(ApprovalGrantError, match="already been claimed"):
        claim_grant_token(object())


def test_an_approval_receipt_refuses_a_look_alike_grant(tmp_path: Path) -> None:
    class Impostor:
        reviewer_github_login = "cooperross399"
        provider_name = "the_odds_api"
        pr_number = PR
        approved_markets = ("1x2", "btts")
        details: dict = {}

    with pytest.raises(ProviderHumanAcceptanceReceiptError, match="needs a verified"):
        build_provider_human_acceptance_receipt(
            "odds_api",
            "cooperross399",
            APPROVAL_DECISION,
            approval_grant=Impostor(),  # type: ignore[arg-type]
            output_dir=tmp_path,
        )


def test_a_reviewer_name_alone_cannot_mint_an_approval(tmp_path: Path) -> None:
    """The original hole, in one line: the strongest claim in the repository
    was a string whoever called the function typed."""
    with pytest.raises(ProviderHumanAcceptanceReceiptError, match="needs a verified"):
        build_provider_human_acceptance_receipt(
            "odds_api",
            "cooperross399",
            APPROVAL_DECISION,
            output_dir=tmp_path,
        )


def test_the_terminal_receipt_command_offers_no_approval_decision() -> None:
    spec = importlib.util.spec_from_file_location(
        "_terminal_receipt",
        PROJECT_ROOT / "scripts" / "create_provider_human_acceptance_receipt.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert APPROVAL_DECISION not in module.TERMINAL_DECISIONS
    assert module.TERMINAL_DECISIONS


# --- 3. the activity was caller-supplied -----------------------------------


def test_the_minting_path_accepts_no_activity_from_a_caller() -> None:
    parameters = inspect.signature(verified_approval_for_pr).parameters

    assert "activity" not in parameters
    assert "activity_json" not in parameters


def test_the_pure_verifier_returns_data_that_cannot_mint(tmp_path: Path) -> None:
    """A fabricated mapping is indistinguishable from a fetched one. So the
    function that takes one may only ever return plain data."""
    _evidence(tmp_path)

    approval = _verify(_activity(), tmp_path)

    assert isinstance(approval, dict)
    assert not isinstance(approval, ApprovalGrant)
    with pytest.raises(ProviderHumanAcceptanceReceiptError):
        build_provider_human_acceptance_receipt(
            "odds_api",
            approval["reviewer_github_login"],
            APPROVAL_DECISION,
            approval_grant=approval,  # type: ignore[arg-type]
            output_dir=tmp_path,
        )


def test_an_activity_file_cannot_write_a_receipt(tmp_path: Path, capsys) -> None:
    spec = importlib.util.spec_from_file_location(
        "_create_receipt_cli",
        PROJECT_ROOT / "scripts" / "create_receipt_from_github_approval.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    activity_file = tmp_path / "activity.json"
    activity_file.write_text(json.dumps(_activity()), encoding="utf-8")
    args = argparse.Namespace(
        pr=PR,
        repository="cooperross399/epl-betting-lab",
        provider="odds_api",
        provider_name="the_odds_api",
        markets="1x2,btts",
        max_age_hours=DEFAULT_MAX_APPROVAL_AGE_HOURS,
        activity_json=activity_file,
        output_dir=tmp_path,
        write_receipt=True,
        print_template=False,
    )
    module.parse_args = lambda: args

    assert module.main() == 2
    assert "cannot write a receipt" in capsys.readouterr().out
    assert not (tmp_path / "provider_human_acceptance_receipt.json").exists()


# --- 4. the review state was never checked ---------------------------------


@pytest.mark.parametrize("state", REFUSED_REVIEW_STATES)
def test_a_review_in_a_refused_state_is_not_an_approval(
    tmp_path: Path, state: str
) -> None:
    """DISMISSED is a review GitHub itself says was withdrawn. It verified."""
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match=state):
        _verify(_activity(state=state), tmp_path)


def test_a_review_with_no_state_is_not_an_approval(tmp_path: Path) -> None:
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match="unset"):
        _verify(_activity(state=""), tmp_path)


# --- 5. revocation, and a revocation that read as an approval --------------


def test_a_newer_revocation_ends_the_approval(tmp_path: Path) -> None:
    _evidence(tmp_path)
    activity = _activity(
        extra=[
            {
                "user": {"login": "cooperross399"},
                "body": f"{REVOCATION_PHRASE}\nI withdraw that approval.",
                "created_at": (APPROVED_AT + timedelta(minutes=30)).isoformat(),
                "id": 2,
            }
        ]
    )

    with pytest.raises(GitHubApprovalError, match="was withdrawn"):
        _verify(activity, tmp_path)


def test_an_older_revocation_does_not_end_a_later_approval(tmp_path: Path) -> None:
    _evidence(tmp_path)
    activity = _activity(
        extra=[
            {
                "user": {"login": "cooperross399"},
                "body": REVOCATION_PHRASE,
                "created_at": (APPROVED_AT - timedelta(hours=2)).isoformat(),
                "id": 2,
            }
        ]
    )

    assert _verify(activity, tmp_path)["approved_markets"] == ["1x2", "btts"]


def test_a_quoted_approval_inside_a_revocation_is_not_an_approval(
    tmp_path: Path,
) -> None:
    """The parser stripped `> ` along with bullet markers, so a comment that
    QUOTED the approval in order to withdraw it parsed as a fresh approval."""
    _evidence(tmp_path)
    quoted = "\n".join(
        ["REVOKED. Ignore this:"] + [f"> {line}" for line in _body().splitlines()]
    )

    with pytest.raises(GitHubApprovalError, match=APPROVAL_PHRASE):
        _verify(_activity(kind="comment", body=quoted), tmp_path)


# --- 6. the freshness window was caller-controlled ------------------------


def test_a_caller_cannot_widen_the_freshness_window(tmp_path: Path) -> None:
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match="the ceiling is"):
        _verify(_activity(), tmp_path, max_age_hours=999999)


def test_a_five_hundred_hour_old_approval_stays_refused(tmp_path: Path) -> None:
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError):
        _verify(
            _activity(submitted=NOW - timedelta(hours=500)),
            tmp_path,
            max_age_hours=DEFAULT_MAX_APPROVAL_AGE_HOURS,
        )


def test_the_command_line_refuses_a_window_past_the_ceiling() -> None:
    spec = importlib.util.spec_from_file_location(
        "_create_receipt_window",
        PROJECT_ROOT / "scripts" / "create_receipt_from_github_approval.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._freshness_window("24") == 24.0
    for bad in ("999999", "0", "-1", "soon"):
        with pytest.raises(argparse.ArgumentTypeError):
            module._freshness_window(bad)


# --- 7. the evidence binding narrowed silently ----------------------------


def test_deleting_evidence_refuses_rather_than_narrowing(tmp_path: Path) -> None:
    """Two artifacts deleted produced an approval bound to the rest, with
    nothing anywhere saying the binding had narrowed."""
    _evidence(tmp_path)
    (tmp_path / "provider_shadow_verification.json").unlink()
    (tmp_path / "automated_card_input.json").unlink()

    with pytest.raises(GitHubApprovalError, match="absent or unreadable"):
        _verify(_activity(), tmp_path)


def test_a_complete_binding_names_every_expected_artifact(tmp_path: Path) -> None:
    _evidence(tmp_path)

    approval = _verify(_activity(), tmp_path)

    assert set(approval["evidence_checksums_sha256"]) == set(EVIDENCE_ARTIFACTS)


# --- 8. the `pr:` line was optional ---------------------------------------


def test_an_approval_that_names_no_pr_is_refused(tmp_path: Path) -> None:
    """Without it the block binds to whichever PR the verifier is pointed at."""
    _evidence(tmp_path)

    with pytest.raises(GitHubApprovalError, match="must declare `pr:`"):
        _verify(_activity(body=_body(pr=None)), tmp_path)


def test_the_same_block_verifies_against_two_different_prs_without_the_line(
    tmp_path: Path,
) -> None:
    """The consequence, stated as a test: the refusal above is what stops one
    approval block from being reused on a pull request nobody reviewed."""
    _evidence(tmp_path)
    activity = _activity(body=_body(pr=None))
    activity["pr_number"] = None

    for pr in (PR, PR + 1):
        with pytest.raises(GitHubApprovalError, match="must declare `pr:`"):
            _verify(activity, tmp_path, pr_number=pr)


# --- 9. the read path never read the receipt -----------------------------


def test_a_forged_receipt_grants_nothing_at_read_time(tmp_path: Path) -> None:
    write_receipt_file(tmp_path, markets=("1x2", "btts"), reviewer="an-agent")

    markets, problems = approved_markets_from_receipt(tmp_path)

    assert markets == frozenset()
    assert any("not an allowed reviewer" in item for item in problems)


def test_a_missing_receipt_grants_nothing(tmp_path: Path) -> None:
    markets, problems = approved_markets_from_receipt(tmp_path)

    assert markets == frozenset()
    assert problems


def test_a_hand_edited_policy_cannot_widen_the_receipt(tmp_path: Path) -> None:
    """A forged receipt plus a hand-edited policy entry used to be enough."""
    write_receipt_file(tmp_path, markets=("1x2",))
    policy = policy_with_receipt(
        tmp_path / "policy.json", markets=("1x2", "btts", "total_2_5")
    )

    disabled, notes = _receipt_unbacked_markets(policy, tmp_path)

    assert set(disabled) == {"btts", "total_2_5"}
    assert any("not an approval" in note for note in notes)


def test_changed_evidence_bytes_disable_every_market(tmp_path: Path) -> None:
    write_receipt_file(tmp_path, markets=("1x2", "btts"))
    policy = policy_with_receipt(tmp_path / "policy.json", markets=("1x2", "btts"))
    (tmp_path / "provider_acceptance_checklist.json").write_text(
        json.dumps({"generated_at": "2026-08-21T00:00:00+00:00", "tampered": True}),
        encoding="utf-8",
    )

    disabled, notes = _receipt_unbacked_markets(policy, tmp_path)

    assert set(disabled) == {"1x2", "btts"}
    assert any("has changed since the approval" in note for note in notes)


def test_a_receipt_for_another_approval_is_refused(tmp_path: Path) -> None:
    write_receipt_file(tmp_path, markets=("1x2", "btts"), receipt_id="somebody-elses")
    policy = policy_with_receipt(tmp_path / "policy.json", markets=("1x2", "btts"))

    disabled, notes = _receipt_unbacked_markets(policy, tmp_path)

    assert set(disabled) == {"1x2", "btts"}
    assert any("the policy names receipt" in note for note in notes)


def test_a_dismissed_review_recorded_in_a_receipt_is_refused(tmp_path: Path) -> None:
    write_receipt_file(
        tmp_path,
        markets=("1x2", "btts"),
        source_kind="review",
        review_state="DISMISSED",
    )

    markets, problems = approved_markets_from_receipt(tmp_path)

    assert markets == frozenset()
    assert any("DISMISSED" in item for item in problems)


def test_the_card_declines_a_market_no_receipt_approves(tmp_path: Path) -> None:
    """End to end: the card, not just the helper."""
    import pandas as pd

    fixtures = [("2026-08-21", "Arsenal", "Coventry")]
    rows = [
        {
            "date": date,
            "home_team": home,
            "away_team": away,
            "market": market,
            "selection": selection,
            "american_odds": "-110",
            "closing_american_odds": "",
            "book": "FanDuel",
            "notes": "",
        }
        for date, home, away in fixtures
        for market, selections in (("btts", ("yes", "no")),)
        for selection in selections
    ]
    odds_path = tmp_path / "odds.csv"
    fixtures_path = tmp_path / "fixtures.csv"
    pd.DataFrame(rows).to_csv(odds_path, index=False)
    pd.DataFrame(fixtures, columns=["date", "home_team", "away_team"]).to_csv(
        fixtures_path, index=False
    )
    # The policy claims BTTS; the receipt approves only 1X2.
    write_receipt_file(tmp_path, markets=("1x2",))
    policy = policy_with_receipt(tmp_path / "policy.json", markets=("btts",))

    summary = save_automated_card_input(
        staging_odds_path=odds_path,
        staging_fixtures_path=fixtures_path,
        output_dir=tmp_path,
        card_input_path=tmp_path / "card.csv",
        policy_path=policy,
        disabled_markets=(),
        mapping_verified=True,
        validation_passed=True,
        freshness_passed=True,
    )["summary"]

    assert "btts" not in summary["included_markets"]
    assert "btts" in summary["excluded_markets"]


def test_the_shipped_receipt_still_backs_the_shipped_policy() -> None:
    """The live file, not a fixture. Eight markets are allowlisted in
    production; a change that silences the card is not a security improvement.
    """
    from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR

    disabled, notes = _receipt_unbacked_markets(
        MANUAL_DIR / "staging_provider_policy.json", OUTPUTS_DIR
    )

    assert disabled == [], notes
    assert notes == []

    markets, problems = approved_markets_from_receipt(OUTPUTS_DIR)
    assert problems == []
    assert markets == set(MARKET_SELECTIONS)


# --- what already held, and must keep holding ----------------------------


def test_the_reviewer_allow_list_is_unreachable_from_configuration() -> None:
    """No environment variable, git config, CLI flag or config file may reach
    the reviewer. The allow-list is a constant in the source or it is nothing.
    """
    source = (
        PROJECT_ROOT / "src/epl_betting_lab/reports/github_approval.py"
    ).read_text(encoding="utf-8")
    start = source.index("ALLOWED_REVIEWERS")
    line = source[start : source.index("\n", start)]

    assert line == 'ALLOWED_REVIEWERS: tuple[str, ...] = ("cooperross399",)'
    assert ALLOWED_REVIEWERS == ("cooperross399",)

    # The only environment this module reads is the PATH it hands to `gh`.
    # Nothing that decides who approved may look at the environment at all.
    # Read as CODE, with docstrings and comments removed: the prose in these
    # functions names the routes it refuses, and prose must not fail a grep for
    # them.
    for function in (
        verify_github_approval,
        approved_markets_from_receipt,
        verified_approval_for_pr,
    ):
        body = _code_only(function)
        for reachable in ("environ", "getenv", "git config", "ConfigParser"):
            assert reachable not in body, (function.__name__, reachable)


def test_nothing_here_writes_into_the_real_receipts_directory(tmp_path: Path) -> None:
    from epl_betting_lab.config import OUTPUTS_DIR

    before = sorted(path.name for path in OUTPUTS_DIR.glob("provider_human_*"))
    write_receipt_file(tmp_path, markets=("1x2", "btts"))
    after = sorted(path.name for path in OUTPUTS_DIR.glob("provider_human_*"))

    assert before == after
