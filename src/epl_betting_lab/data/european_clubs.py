"""Names, hand-written, for the clubs that link the European pools.

The Champions League results that bridge one country's ratings to another's come
from openfootball; the domestic matches those ratings are fitted on come from
Football-Data. The two name their clubs differently, and often enough
openfootball names the same club two ways across seasons.

**Every entry below was written and checked by hand, and that is the point.**

Normalising the names and matching what falls out proposes
`Paris Saint-Germain FC` -> `Paris FC`. Paris FC is a different club, recently
promoted, which happens to be the only French side left once "Saint-Germain" is
treated as an affix. On 46 appearances the pool would have rated Paris
Saint-Germain as Paris FC, every European tie involving them would have been
mispriced, and nothing would have raised anything: a wrong name does not fail,
it silently rates the wrong club. `providers/team_names.py` refuses fuzzy
matching for the same reason and this follows it.

A club that is not here stays unmapped, and `models/poisson_goals.py` refuses to
price a club it has no rating for, so the failure is loud. Thirty of the 104
clubs in these seasons play in countries Football-Data does not publish —
Ukraine, Austria, Czechia, Denmark, Serbia and twenty-four more — and no entry
can help them. They are unrateable, and their ties are left out rather than
guessed at.
"""

from __future__ import annotations

#: openfootball's name -> Football-Data's name, within one country.
#:
#: Many-to-one on purpose: openfootball is not self-consistent across seasons
#: ("Bayern München" and "FC Bayern München", "Paris Saint-Germain" and
#: "Paris Saint-Germain FC"), so both spellings map to the one domestic name.
EUROPEAN_CLUB_NAMES: dict[str, dict[str, str]] = {
    "ENG": {
        "Liverpool FC": "Liverpool",
        "Chelsea FC": "Chelsea",
        "Arsenal FC": "Arsenal",
        "Aston Villa FC": "Aston Villa",
        "Manchester City": "Man City",
        "Manchester City FC": "Man City",
        "Manchester United": "Man United",
        "Manchester United FC": "Man United",
        "Newcastle United FC": "Newcastle",
        "Tottenham Hotspur": "Tottenham",
        "Tottenham Hotspur FC": "Tottenham",
    },
    "ESP": {
        "FC Barcelona": "Barcelona",
        "Real Madrid CF": "Real Madrid",
        # Football-Data writes both Madrid clubs "Ath": Ath Madrid is Atlético,
        # Ath Bilbao is Athletic Club. Easy to swap and impossible to notice.
        "Club Atlético de Madrid": "Ath Madrid",
        "Atlético Madrid": "Ath Madrid",
        "Athletic Club": "Ath Bilbao",
        "Sevilla FC": "Sevilla",
        "Villarreal CF": "Villarreal",
        "Valencia CF": "Valencia",
        "Real Sociedad de Fútbol": "Sociedad",
        "Girona FC": "Girona",
    },
    "GER": {
        "Borussia Dortmund": "Dortmund",
        "Bayern München": "Bayern Munich",
        "FC Bayern München": "Bayern Munich",
        "Bayer 04 Leverkusen": "Leverkusen",
        "Bayer Leverkusen": "Leverkusen",
        "Eintracht Frankfurt": "Ein Frankfurt",
        "Bor. Mönchengladbach": "M'gladbach",
        "VfB Stuttgart": "Stuttgart",
        "VfL Wolfsburg": "Wolfsburg",
        "1. FC Union Berlin": "Union Berlin",
    },
    "ITA": {
        "SSC Napoli": "Napoli",
        "AC Milan": "Milan",
        "FC Internazionale Milano": "Inter",
        "Atalanta BC": "Atalanta",
        "Juventus FC": "Juventus",
        "SS Lazio": "Lazio",
        "Lazio Roma": "Lazio",
        "Bologna FC 1909": "Bologna",
    },
    "FRA": {
        # The entry this module exists for. Paris FC is a different club.
        "Paris Saint-Germain": "Paris SG",
        "Paris Saint-Germain FC": "Paris SG",
        "Lille OSC": "Lille",
        "Olympique Marseille": "Marseille",
        "Olympique de Marseille": "Marseille",
        "Olympique Lyonnais": "Lyon",
        "Stade Brestois 29": "Brest",
        "Stade Rennais": "Rennes",
        "Racing Club de Lens": "Lens",
    },
    "POR": {
        "FC Porto": "Porto",
        "SL Benfica": "Benfica",
        "Sport Lisboa e Benfica": "Benfica",
        "Sporting CP": "Sp Lisbon",
        "Sporting Clube de Portugal": "Sp Lisbon",
        "Sporting Clube de Braga": "Sp Braga",
    },
    "NED": {
        "AFC Ajax": "Ajax",
        "PSV": "PSV Eindhoven",
        "Feyenoord Rotterdam": "Feyenoord",
    },
    "BEL": {
        "Club Brugge KV": "Club Brugge",
        "Royale Union Saint-Gilloise": "St. Gilloise",
        "KRC Genk": "Genk",
        "Royal Antwerp FC": "Antwerp",
    },
    "SCO": {
        "Celtic FC": "Celtic",
        "Rangers FC": "Rangers",
    },
    "TUR": {
        "Galatasaray SK": "Galatasaray",
        "Beşiktaş": "Besiktas",
        # Football-Data's "Buyuksehyr" is İstanbul Başakşehir, named for the
        # club's former Büyükşehir Belediyespor. Nothing about the strings says so.
        "İstanbul Başakşehir": "Buyuksehyr",
    },
    "MCO": {
        # Monaco plays in Ligue 1; openfootball files it under its own country.
        "AS Monaco FC": "Monaco",
        "AS Monaco": "Monaco",
    },
    "GRE": {
        "Olympiakos Piraeus": "Olympiakos",
        "PAE Olympiakos SFP": "Olympiakos",
    },
}


def domestic_name(club: str, country: str) -> str | None:
    """Football-Data's name for a club, or None if it was never written down.

    None rather than the input: returning the unmapped name would let it flow
    into a rating lookup and miss, which is the same outcome by a longer road.
    """
    if country not in EUROPEAN_CLUB_NAMES:
        return None
    mapped = EUROPEAN_CLUB_NAMES[country].get(club)
    if mapped is not None:
        return mapped
    # Some names already agree — "Juventus", "Porto", "Celtic" in some seasons.
    # Those need no entry, and inventing one for them would be noise.
    return club
