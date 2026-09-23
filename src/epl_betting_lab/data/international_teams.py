"""The odds provider's name for a national team, mapped to the archive's.

Same job as `PROVIDER_CLUB_NAMES` in `data/european_clubs.py`, same reason: a
name the pool has never seen is refused, and a fixture is declined while both
its teams sit in the pool under a different spelling. Twelve of eighteen
Champions League fixtures were declined that way once.

**Kept separate from the club map on purpose.** Merging them would put two
vocabularies in one dictionary, and this project has already had a word mean
two things in two tables and grade a third of a month's bets for the wrong
side. No club here is called "Spain", but nothing would stop one being added.

**Every entry was observed, none was guessed.** The guesses would have been
wrong in both directions. The archive spells them "Czech Republic", "Republic
of Ireland", "Turkey" and "North Macedonia", and a plausible guess was that the
provider says "Czechia", "Ireland" or "Türkiye" — it does not, it agrees on all
four. The one name it spells differently is the one nobody would have picked.
Of 52 national teams quoted for the 2026-27 Nations League, 51 matched the
archive unaided.

A wrong entry here does not fail loudly: it maps a real fixture onto another
country's rating, which is worse than declining it. So this file is written
from names seen in `price_feed_extra.csv`, and an unmatched spelling is
reported by the card as an unrateable fixture naming the exact string the
provider sent. That report is the input to this file.
"""

from __future__ import annotations

#: Provider spelling -> the spelling used by the results archive.
#:
#: Every entry must be justified by a name seen in `price_feed_extra.csv`.
PROVIDER_TEAM_NAMES: dict[str, str] = {
    # Observed 2026-09-22 across 1,162 Nations League price observations: the
    # provider writes an ampersand where the archive writes "and". The only
    # disagreement in 52 teams.
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}


def archive_name(team: str) -> str:
    """The archive's name for a team, or the name unchanged.

    Falling through is what makes the map small: a provider that already agrees
    with the archive — which is most of them, since both use country names —
    needs no entry, and a team that is genuinely unrateable stays visibly so.
    """
    return PROVIDER_TEAM_NAMES.get(team, team)
