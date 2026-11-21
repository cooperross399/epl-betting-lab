"""How big a bet is: the Due List ladder on a 1u base (2026-11-21).

Cooper, 2026-11-21: *"use the due list ladder style pricing but with 1u as the
main instead of .25u"* and *"records/profits on the website for EPL"*. The
same rule the CBB lab adopted the same day (its `models/sizing.py`, copied
here, not imported: the labs share no code).

| Price             | Stake                                              |
|:------------------|:---------------------------------------------------|
| up to +199        | 1u on a plus price, or enough to win 1u on a minus |
|                   | price (at -150, risk 1.5u to win 1u)               |
| +200 to +500      | 0.6u                                               |
| +501 to +1500     | 0.4u                                               |
| longer than +1500 | 0.2u                                               |

A push or a void returns 0 and is neither a win nor a loss. A pick with no
usable price is graded but staked nothing: a missing price stays missing.

A "straight up" call (the model's favoured 1X2 outcome) risks 1u FLAT under
+200, never "to win 1u", so a heavy favourite at -800 risks 1u to win 0.125u;
from +200 it follows the same ladder (`flat`).

The card keeps the proportions its tiers always had: tier C (every bet the
card has ever staked) was 0.1u and is now this ladder's size; B (0.25u) and
A (0.5u) are 2.5 and 5 times it (`card_units`).

`web/settle_results.py` and `web/build_site_pages.py` spell the same ladder
out (the publish scripts are standard library only and import nothing from
`src/`); `tests/test_the_1u_ladder.py` pins all three to the same numbers.
"""

from __future__ import annotations

import math

#: The stake up to +199: risked on a plus price, to win on a minus price.
BASE_UNITS = 1.0
#: (longest price in the bracket, stake); longer than the last is LONGEST_UNITS.
PRICE_BRACKETS: tuple[tuple[int, float], ...] = ((500, 0.6), (1500, 0.4))
LONGEST_UNITS = 0.2
#: From this price the ladder sets the stake.
LADDER_FROM = 200
STAKE_RULE = (
    "1u, to win 1u on a minus price; +200 to +500 0.6u, "
    "+501 to +1500 0.4u, longer than +1500 0.2u"
)
#: The card's tiers as multiples of the base. C was 0.1u, B 0.25u, A 0.5u
#: under the old rule, so the proportions hold.
TIER_MULTIPLIER = {"A": 5.0, "B": 2.5, "C": 1.0}


def _price(price: object) -> float | None:
    """A usable American price, or None. Between -100 and +100 is not one."""
    if isinstance(price, bool):
        return None
    try:
        p = float(price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(p) or -100 < p < 100:
        return None
    return p


def ladder_stake(price: object) -> float | None:
    """The ladder's stake at `price`: BASE_UNITS below +200, else the bracket.
    None without a usable price."""
    p = _price(price)
    if p is None:
        return None
    if p < LADDER_FROM:
        return BASE_UNITS
    for longest, stake in PRICE_BRACKETS:
        if p <= longest:
            return stake
    return LONGEST_UNITS


def risk(price: object) -> float | None:
    """Units risked on one bet at `price`: to win the stake on a minus price."""
    p = _price(price)
    stake = ladder_stake(p)
    if p is None or stake is None:
        return None
    return round(stake * abs(p) / 100.0 if p < 0 else stake, 4)


def graded(price: object, result: object) -> tuple[float, float] | None:
    """(units won or lost, units risked) for one graded bet, or None.

    None for no usable price (graded, never counted in units). A push or a
    void returns 0 and risks nothing in the record's denominator only when it
    is a void: a push risked the stake and got it back.
    """
    if result == "void":
        return (0.0, 0.0) if _price(price) is not None else None
    if result not in ("win", "loss", "push"):
        return None
    p = _price(price)
    stake = ladder_stake(p)
    if p is None or stake is None:
        return None
    at_risk = stake * abs(p) / 100.0 if p < 0 else stake
    win = stake if p < 0 else stake * p / 100.0
    profit = win if result == "win" else -at_risk if result == "loss" else 0.0
    return round(profit, 4), round(at_risk, 4)


def flat(price: object, result: object) -> tuple[float, float] | None:
    """(units, risked) for a straight-up call: the stake is RISKED at every
    price (1u under +200, the ladder from +200)."""
    if result not in ("win", "loss", "push"):
        return None
    p = _price(price)
    stake = ladder_stake(p)
    if p is None or stake is None:
        return None
    win = stake * 100.0 / abs(p) if p < 0 else stake * p / 100.0
    profit = win if result == "win" else -stake if result == "loss" else 0.0
    return round(profit, 4), round(stake, 4)


def card_units(tier: object, price: object) -> float:
    """The card's Units column: units to RISK on a staked tier at `price`.

    Zero for a lean, a pass or a row with no usable price."""
    mult = TIER_MULTIPLIER.get(str(tier))
    at_risk = risk(price)
    if mult is None or at_risk is None:
        return 0.0
    return round(mult * at_risk, 2)


def staked_units(price: object) -> float:
    """Units to risk on one staked pick at `price` (tier C); 0 without a price."""
    return card_units("C", price)
