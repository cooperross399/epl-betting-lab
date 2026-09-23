"""Competitions this project would price, and whether the provider has them yet.

Written after asking for the CONCACAF Nations League, and then corrected twice,
which is the whole lesson.

The first claim was that it "is not sold at all", from one reading of the
provider's sports list. The second was that it "has not been played since March
2025", from the results archive having no rows for it — and that one was an
absence-of-evidence error. The archive runs about a month behind (see
`data/international_results.py`): read on 2026-09-23 it ended 2026-08-26 and
contained no September fixtures of any kind, including the UEFA Nations League
matches this project was pricing 45 of that same day. It could not have shown a
September CONCACAF fixture whether or not one was played.

What is actually established is narrower: the provider does not list the
competition. Checked on 2026-09-22 and again on 2026-09-23, 67 soccer
competitions with `all=true`, no CONCACAF Nations League; a second free source
listing 190 competitions does not carry it either. Whether it is being played is
a question neither of those can answer.

A listing answers "is there coverage today", and absence in it has at least
three causes that look identical:

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
            "Asked for on 2026-09-23. Not in the provider's list — checked "
            "twice that day, 67 competitions with all=true, and a second free "
            "source listing 190 does not carry it either. Whether it is "
            "currently being played is NOT established: the results archive "
            "runs about a month behind and showed no September fixtures at "
            "all. The rating pool already covers all 41 of its teams, so this "
            "needs prices and nothing else."
        ),
    ),
    WantedCompetition(
        code="GOLD",
        name="CONCACAF Gold Cup",
        pattern=r"concacaf gold cup",
        status=(
            "Sold, and out of season — played June and July. Measured "
            "2026-09-23 and the verdict is COLLECT, DO NOT CARD. The tail "
            "screen it has to pass, it passes better than the Nations League: "
            "the strongest favourite the model produces over 175 matches is "
            "0.847, so nothing above 90%. What blocks it is the venue. 78% of "
            "its matches are neutral and the feed does not say which, so the "
            "card would shift the home side +9.4 points and the away side -8.8 "
            "on every one of them — 2.5x its own 3.5% edge threshold, one "
            "direction, undetectable. Passing neutral=True is not the fix "
            "either: realised home advantage on its neutral matches is +0.522 "
            "goals against the pool's +0.13, because 167 of 175 were played in "
            "the United States. Wire it for collection when it comes into "
            "season; do not add it to the card without a venue flag."
        ),
    ),
    WantedCompetition(
        code="CNLQ",
        name="CONCACAF Nations League qualification",
        pattern=r"concacaf.*nations league.*qualif",
        status=(
            "Same as the Nations League itself: absent from the provider's "
            "list, and the archive is too far behind to say whether it is "
            "being played."
        ),
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
