"""Shared presentation rules for rendered picks.

Three surfaces render the same card — the job summary, the card markdown, and
the browser status page — and each had grown its own inline formatting. The
result was that a price stored as ``146.0`` printed as ``146.0``, which is not
how an American price is written and reads as a decimal price to anyone
scanning quickly. ``weekly_card`` already got this right; the rule lives here
now so all four agree.

This module is presentation only. It changes no probability, no edge, no tier,
no stake, and no section assignment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


EM_DASH = "—"

# A row the model marked BETTABLE but ranked below the staking threshold, so
# its suggested stake is zero. See `split_stakeable`.
NOT_STAKEABLE_LABEL = "Ranked but not stakeable (0u)"

NOT_STAKEABLE_NOTE = (
    "These cleared the bettable screen but ranked below the staking threshold, "
    "so the model suggests **0 units**. They are listed for transparency, not "
    "as plays: a zero-unit row is not a small bet, it is no bet."
)

# Same sentence for surfaces that render text rather than markdown.
NOT_STAKEABLE_PLAIN_NOTE = NOT_STAKEABLE_NOTE.replace("**", "")


def format_american_odds(value: object, *, missing: str = EM_DASH) -> str:
    """Render an American price the way a sportsbook writes it: ``+146``/``-106``.

    Accepts the float the reports store, the string a CSV round-trip produces,
    and an already-signed string. Anything genuinely unparseable is returned as
    written rather than silently blanked, because an odd price is worth seeing.
    """
    if value is None:
        return missing
    if isinstance(value, bool):
        return missing
    if isinstance(value, (int, float)):
        number: float | None = float(value)
    else:
        text = str(value).strip()
        if not text:
            return missing
        try:
            number = float(text.replace("+", "", 1) if text.startswith("+") else text)
        except ValueError:
            return text
    if number != number or number in (float("inf"), float("-inf")):  # NaN/inf
        return missing
    if number == 0:
        return missing
    return f"{int(round(number)):+d}"


def is_stakeable(row: Mapping[str, Any]) -> bool:
    """True when the model suggests a non-zero stake for this row."""
    units = row.get("suggested_units")
    if units is None or units == "":
        # No sizing information at all: treat as stakeable rather than quietly
        # demoting a pick because a field was absent.
        return True
    try:
        return float(units) > 0
    except (TypeError, ValueError):
        return True


def split_stakeable(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Separate rows the model would stake from rows it sized at zero.

    ``section`` and ``confidence_tier`` are two different axes: a row can be
    BETTABLE (so it lands in "Best bets") while its ranking score puts it in the
    ``Pass/Avoid`` tier at 0 units. Printing both facts in one table let the
    heading speak louder than the stake, so a "Pass/Avoid" row read as a best
    bet. Splitting the display keeps both facts visible without touching either.
    """
    stakeable = [row for row in rows if is_stakeable(row)]
    not_stakeable = [row for row in rows if not is_stakeable(row)]
    return stakeable, not_stakeable
