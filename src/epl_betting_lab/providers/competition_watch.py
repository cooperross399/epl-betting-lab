"""Competitions this project would price, and whether the provider has them yet.

Written after asking for the CONCACAF Nations League and concluding, from one
reading of the provider's sports list, that it "is not sold at all". That was
overstated. The competition has not been played since March 2025 — the 2026
World Cup, hosted across CONCACAF, took the calendar — so there were no
fixtures to sell. A listing answers "is there coverage today", and absence in it
has at least three causes that look identical:

    the provider does not carry this competition, ever
    the competition is between editions and will return
    the competition has been cancelled or renamed

None of those is distinguishable from the others by looking once, and the
difference decides whether to wait or to go and buy prices elsewhere. What IS
distinguishable is a change: a competition that was absent last week and is
present today has started, and that is worth being told about on the run that
notices rather than the month somebody thinks to look.

So this module keeps a register of what the card would want, matched against
whatever the provider currently lists. Matching is by name pattern and not by
sport key on purpose: a key that has never been listed cannot be written down,
and the CONCACAF Nations League has never been listed. A pattern can wait for
it.

Nothing here fetches anything or decides anything. It reads a listing somebody
else already paid for — `/v4/sports`, the free endpoint the credential check
already calls — and reports three facts: wanted and collected, wanted and newly
available, wanted and still absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class WantedCompetition:
    """A competition the card would price if it could."""

    code: str
    name: str
    #: Matched case-insensitively against the provider's title. A pattern
    #: rather than a key because a competition never listed has no key to
    #: write down.
    pattern: str
    #: Why it is not already wired, in a sentence a reader can act on.
    status: str


#: What this project wants and does not yet collect.
#:
#: Deliberately not a list of everything the provider sells. Each entry is a
#: competition someone asked for, with the reason it is not wired, so the
#: report answers "is the thing I asked about available yet" rather than
#: printing a catalogue.
WANTED: tuple[WantedCompetition, ...] = (
    WantedCompetition(
        code="CNL",
        name="CONCACAF Nations League",
        pattern=r"concacaf.*nations league",
        status=(
            "Asked for on 2026-09-23. Not in the provider's list, and not "
            "played since March 2025 — CONCACAF's calendar went to the 2026 "
            "World Cup it hosted. The rating pool already covers all 41 of its "
            "teams, so this needs prices and nothing else."
        ),
    ),
    WantedCompetition(
        code="CNLQ",
        name="CONCACAF Nations League qualification",
        pattern=r"concacaf.*nations league.*qualif",
        status="Same as the Nations League itself; last played March 2019.",
    ),
)


def _title(entry: Mapping[str, Any]) -> str:
    return str(entry.get("title", ""))


def _key(entry: Mapping[str, Any]) -> str:
    return str(entry.get("key", ""))


def find_wanted(
    listing: Sequence[Mapping[str, Any]],
    *,
    wanted: Iterable[WantedCompetition] = WANTED,
    collected: Iterable[str] = (),
) -> dict[str, list[dict[str, Any]]]:
    """Sort a provider listing into what is available, new, and still absent.

    `collected` is the set of sport keys already being fetched, so a
    competition that arrived and was wired does not keep being announced.
    """
    already = set(collected)
    wanted = list(wanted)
    available: list[dict[str, Any]] = []
    matched_codes: set[str] = set()

    # Entry-first, and the most specific pattern wins. "concacaf.*nations
    # league" matches "CONCACAF Nations League Qualification" as happily as the
    # competition itself, so a want-first loop reports the main competition as
    # available the moment its qualifying round is listed — which is the one
    # thing this register exists to get right. Specificity is the length of the
    # pattern: the qualifying entry's pattern is a strict extension of the
    # other, so it is longer whenever it applies. A lookahead would also work
    # and is easier to get subtly wrong; this ordering is checkable by reading.
    for entry in listing:
        title = _title(entry)
        hits = [w for w in wanted if re.search(w.pattern, title, re.IGNORECASE)]
        if not hits:
            continue
        want = max(hits, key=lambda w: len(w.pattern))
        matched_codes.add(want.code)
        available.append(
            {
                "code": want.code,
                "name": want.name,
                "key": _key(entry),
                "title": title,
                "active": bool(entry.get("active", False)),
                "collected": _key(entry) in already,
            }
        )

    absent = [
        {"code": w.code, "name": w.name, "status": w.status}
        for w in wanted
        if w.code not in matched_codes
    ]
    return {"available": available, "absent": absent}


def render_watch(found: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[str]:
    """Lines for a CI log. Loud only when something changed."""
    lines: list[str] = []
    arrived = [item for item in found.get("available", ()) if not item["collected"]]
    if arrived:
        lines.append("A competition this project asked for is now being sold:")
        for item in arrived:
            season = "in season" if item["active"] else "listed, out of season"
            lines.append(f"  {item['name']} -> {item['key']} ({season})")
        lines.append(
            "  Wire it into SPORT_KEYS in scripts/collect_extra_competitions.py "
            "to start collecting. Prices cannot be recovered later."
        )
    for item in found.get("available", ()):
        if item["collected"]:
            lines.append(f"Already collected: {item['name']} -> {item['key']}")
    for item in found.get("absent", ()):
        lines.append(f"Still not sold: {item['name']}. {item['status']}")
    return lines
