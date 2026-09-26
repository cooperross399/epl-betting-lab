"""The one object that lets a receipt be written for an approval decision.

An approval receipt is the artifact that turns "Cooper said yes on GitHub" into
something the rest of the repository trusts. Before this module, the function
that built one took the reviewer's name as an ordinary string argument, so any
code that could call it could mint an approval in Cooper's name without GitHub
ever being consulted. A public constructor on the evidence *is* the hole; the
`isinstance` check in front of it protects nothing when anyone can build the
instance.

So :class:`ApprovalGrant` refuses to construct unless it is handed a token that
only the verifying module holds, and the token can be claimed exactly once, at
import time, by the first module to ask. That makes the plausible attack —
rebinding the token to an object the attacker controls and then constructing a
grant — fail loudly instead of silently succeeding.

WHAT THIS DOES NOT COVER, because a guard that overstates itself is worse than
none. Python has no private state: code running in this interpreter can read
`github_approval._GRANT_TOKEN` and construct a grant with it. This module
raises the cost of forging an approval from "call a public function with a
string" to "reach into another module's namespace", and nothing more. The
defence that does not depend on module privacy is the read-time verification in
`epl_betting_lab.reports.automated_card_input`, which re-reads the receipt and
its evidence every time the card is built, and the merge-time gate, which
re-fetches the approval from live GitHub.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass
from types import MappingProxyType
from typing import Any, Mapping


class ApprovalGrantError(RuntimeError):
    """Raised when a grant is constructed without the verifier's token."""


_TOKEN: object | None = None
_CLAIMED = False


def claim_grant_token(token: object) -> None:
    """Register the object that may construct grants. Callable once.

    The verifying module calls this at import time with an object it keeps to
    itself. A second call raises, so a later import cannot swap the token for
    one the caller controls.
    """
    global _TOKEN, _CLAIMED
    if _CLAIMED:
        raise ApprovalGrantError(
            "The approval grant token has already been claimed. Only the "
            "GitHub approval verifier may claim it, and only once."
        )
    if token is None:
        raise ApprovalGrantError("The approval grant token may not be None.")
    _TOKEN = token
    _CLAIMED = True


@dataclass(frozen=True)
class ApprovalGrant:
    """Proof that a GitHub approval was fetched and verified in this process.

    `details` is the verifier's full, non-secret result — the same mapping the
    receipt transcribes. It is wrapped read-only so a holder cannot widen the
    market scope after the fact.
    """

    reviewer_github_login: str
    provider_name: str
    pr_number: int
    approved_markets: tuple[str, ...]
    details: Mapping[str, Any]
    token: InitVar[object] = None

    def __post_init__(self, token: object) -> None:
        if _TOKEN is None or token is not _TOKEN:
            raise ApprovalGrantError(
                "An ApprovalGrant may only be created by the GitHub approval "
                "verifier. Verify a real approval instead of constructing one."
            )
        if not self.reviewer_github_login.strip():
            raise ApprovalGrantError("A grant must name the reviewer.")
        if not self.approved_markets:
            raise ApprovalGrantError("A grant must name at least one market.")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))
        object.__setattr__(
            self, "approved_markets", tuple(self.approved_markets)
        )
