"""Which bookmakers may price a bet, and which are only a reference.

The card recommends the best price across bookmakers. That is the right rule
while every bookmaker on the list is one Cooper can actually bet at, and a
dangerous one the moment it is not: a recommendation at a price he cannot take
is worse than no recommendation, because it looks like the others.

Adding the provider's `eu` region makes that concrete. It returns Pinnacle —
the sharpest book there is, and the reference every sharp-money signal is
measured against — along with other European books. Pinnacle is not available
to him. So the same fetch now carries prices that must never be staked and
prices that must be recorded, and the difference has to be enforced somewhere
rather than assumed.

Three roles, and a book is in exactly one:

**Bettable.** May be recommended and staked. The best price among these is the
card's price.

**Reference.** Recorded, shown beside the card's price, never staked. Pinnacle
moves on sharp money and recreational books drift toward it, so seeing the
sharp line next to your own book's answers "take it now or wait" — which is
what it is for. It is not an instruction and it is not a price on offer.

**Unknown.** Anything the provider returns that is in neither list. Reported
rather than silently dropped: a new US book appearing and being quietly ignored
would cost real value and leave no trace, which is the failure mode this whole
project keeps rediscovering.
"""

from __future__ import annotations

from collections.abc import Iterable

#: Books Cooper can actually bet at. Every one has been seen in a live `us`
#: fetch. Adding to this list is a decision about where he holds money, not a
#: technical one — it belongs to him, not to a heuristic.
BETTABLE_BOOKS: frozenset[str] = frozenset({
    "BetMGM",
    "BetOnline.ag",
    "BetRivers",
    "BetUS",
    "Bovada",
    "Caesars",
    "DraftKings",
    "FanDuel",
    "Fanatics",
    "LowVig.ag",
    "MyBookie.ag",
})

#: Shown, never staked. Pinnacle is the reason the `eu` region is fetched at
#: all: it is the sharp reference that makes reverse line movement measurable,
#: and it is the line a recreational book drifts toward.
REFERENCE_BOOKS: frozenset[str] = frozenset({"Pinnacle"})


def _normalise(name: object) -> str:
    return "" if name is None else str(name).strip()


def is_bettable(book: object) -> bool:
    return _normalise(book) in BETTABLE_BOOKS


def is_reference(book: object) -> bool:
    return _normalise(book) in REFERENCE_BOOKS


def unknown_books(books: Iterable[object]) -> list[str]:
    """Books the provider returned that are in neither list, deduplicated.

    Surfaced in the card input report. A new US book is money left on the
    table; a new European one is noise. Either way the answer is to say so.
    """
    seen = {
        _normalise(book)
        for book in books
        if _normalise(book)
        and not is_bettable(book)
        and not is_reference(book)
    }
    return sorted(seen)
