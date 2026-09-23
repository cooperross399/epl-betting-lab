"""The odds provider's name for a national team, mapped to the archive's.

Same job as `PROVIDER_CLUB_NAMES` in `data/european_clubs.py`, same reason: a
name the pool has never seen is refused, and a fixture is declined while both
its teams sit in the pool under a different spelling. Twelve of eighteen
Champions League fixtures were declined that way once.

**Kept separate from the club map on purpose.** Merging them would put two
vocabularies in one dictionary, and this project has already had a word mean
two things in two tables and grade a third of a month's bets for the wrong
side. No club here is called "Spain", but nothing would stop one being added.

**Deliberately seeded empty.** The archive spells these "Czech Republic",
"Republic of Ireland", "Turkey", "Bosnia and Herzegovina". A provider may spell
them "Czechia", "Ireland", "Türkiye" — or may not. Writing a guess here does
not fail loudly: it silently maps a real fixture onto the wrong country's
rating, which is worse than declining it. So entries are added only from names
actually observed in the price feed, and until then an unmatched spelling is
reported by the card as an unrateable fixture, naming the exact string the
provider sent. That report is the input to this file.
"""

from __future__ import annotations

#: Provider spelling -> the spelling used by the results archive.
#:
#: Every entry must be justified by a name seen in `price_feed_extra.csv`.
PROVIDER_TEAM_NAMES: dict[str, str] = {}


def archive_name(team: str) -> str:
    """The archive's name for a team, or the name unchanged.

    Falling through is what makes the map small: a provider that already agrees
    with the archive — which is most of them, since both use country names —
    needs no entry, and a team that is genuinely unrateable stays visibly so.
    """
    return PROVIDER_TEAM_NAMES.get(team, team)
