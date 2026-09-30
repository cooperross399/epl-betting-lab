"""A scope this flow can never grant must not be handed an approval to paste.

`create_receipt_from_github_approval.py` printed the approval block on every
failure. Two of those failures are structural rather than transient: a market
outside `APPROVABLE_MARKETS`, and a market held in `FORBIDDEN_MARKETS`. For
those, the command printed `BLOCKED:` and then, four lines later, "Paste this
into a PR review or comment to approve:" followed by a block naming the very
markets it had just refused.

PR #318 sat in exactly that state. It allowlists `cards_total_3_5` and
`cards_total_4_5` at the policy layer and deliberately does not register them
in `market_eligibility.MARKET_SELECTIONS`, which is what `APPROVABLE_MARKETS`
is built from -- so the approval the tool offered could never have produced a
receipt. Posting it would have put a public comment on the PR granting a scope
that fails closed every time it is read, on the instruction of the tool that
refused it.

The check reads the same two sources the verifier does. It does not match the
verifier's message text: that text and the condition drift apart, and three
guards in this repository have passed by matching the very string they were
meant to guard against.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "create_receipt_from_github_approval.py"

from epl_betting_lab.reports.github_approval import (  # noqa: E402
    APPROVABLE_MARKETS,
    APPROVAL_PHRASE,
)

#: The scope on PR #318. Not in the registry, so not approvable.
CARDS = ("cards_total_3_5", "cards_total_4_5")


def _module():
    spec = importlib.util.spec_from_file_location("mk_receipt", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*markets: str, extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    """The real command, because the exit code is what the operator acts on.

    Not piped. A pipe reports the last command's status, and this repository
    has taken five false greens and one false red from exactly that.
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--pr", "318", "--markets", ",".join(markets), *extra],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
        env={"PYTHONPATH": str(PROJECT_ROOT / "src"), "PATH": "/usr/bin:/bin"},
    )


def test_the_cards_scope_is_not_approvable_at_all() -> None:
    """The premise. If this ever fails the rest of the file is testing nothing."""
    assert not set(CARDS) <= APPROVABLE_MARKETS, (
        "the cards markets became approvable; if they were registered in "
        "MARKET_SELECTIONS then a provider key and a settlement rule exist for "
        "them, and this file's fixture must move to a market that is still out"
    )


def test_an_unapprovable_scope_is_offered_no_block_to_paste() -> None:
    done = _run(*CARDS)
    assert done.returncode == 2, f"expected a closed refusal, got {done.returncode}"
    assert APPROVAL_PHRASE not in done.stdout, (
        "the command refused the scope and then printed an approval block for "
        "it; posting that is a public comment granting a scope that fails closed"
    )
    assert "no approval that would work" in done.stdout


def test_the_refusal_says_what_would_make_the_market_approvable() -> None:
    """A refusal that names no remedy sends the reader back to the same paste."""
    out = _run(*CARDS).stdout
    assert "MARKET_SELECTIONS" in out
    assert "card_scoreboard.settle" in out, "the settlement half is not named"
    assert "provider market" in out, "the pricing half is not named"


def test_print_template_refuses_the_same_scope() -> None:
    """The other door into the same mistake.

    `--print-template` printed unconditionally, so it would hand over the block
    even while the flow could not use it.
    """
    done = _run(*CARDS, extra=("--print-template",))
    assert done.returncode == 2
    assert APPROVAL_PHRASE not in done.stdout


def test_an_approvable_scope_still_gets_its_template() -> None:
    """The refusal must not swallow the case the command exists for."""
    approvable = sorted(APPROVABLE_MARKETS)[:2]
    done = _run(*approvable, extra=("--print-template",))
    assert done.returncode == 0, done.stdout + done.stderr
    assert APPROVAL_PHRASE in done.stdout
    for market in approvable:
        assert market in done.stdout


def test_the_check_reads_the_registry_not_the_error_text() -> None:
    """Pinned against the guard-matches-its-own-message failure.

    `_cannot_be_approved` must derive its answer from `APPROVABLE_MARKETS` and
    `FORBIDDEN_MARKETS`, so that a reworded verifier message cannot silently
    turn the refusal off.
    """
    module = _module()
    unapprovable, forbidden = module._cannot_be_approved(list(CARDS))
    assert unapprovable == sorted(CARDS)
    assert forbidden == []

    ok = sorted(APPROVABLE_MARKETS)[:1]
    assert module._cannot_be_approved(ok) == ([], [])
