"""Reviewed provider-to-project team-name mappings.

The Odds API returns full club names ("Manchester City"); this project's fixture
and historical files use short names ("Man City"). Without a mapping, every long
name reads as an unmapped team and provider fixtures never match project
fixtures.

Every entry here is a deliberate, reviewed alias. This module performs no fuzzy
matching, no substring guessing, and no automatic stripping of suffixes: an
unknown name is returned unchanged so it stays visibly unmapped rather than
being silently coerced onto the wrong club. Adding a club is a reviewed code
change, which is the point.

Canonical names are the ones already used by `data/manual/upcoming_fixtures.csv`
and `data/processed/epl_historical_matches.csv`.
"""

from __future__ import annotations

from collections.abc import Iterable


#: Canonical project names, taken from the existing fixture and history files.
CANONICAL_TEAM_NAMES: frozenset[str] = frozenset(
    {
        "Arsenal",
        "Aston Villa",
        "Bournemouth",
        "Brentford",
        "Brighton",
        "Burnley",
        "Chelsea",
        "Coventry",
        "Crystal Palace",
        "Everton",
        "Fulham",
        "Hull",
        "Ipswich",
        "Leeds",
        "Leicester",
        "Liverpool",
        "Luton",
        "Man City",
        "Man United",
        "Newcastle",
        "Norwich",
        "Nott'm Forest",
        "Sheffield United",
        "Southampton",
        "Sunderland",
        "Tottenham",
        "Watford",
        "West Ham",
        "Wolves",
    }
)


#: Reviewed alias -> canonical project name. Keys are matched case-insensitively.
#: Ordered by club for reviewability; every entry was checked against the
#: canonical set above.
PROVIDER_TEAM_ALIASES: dict[str, str] = {
    # Explicitly requested Odds API long names.
    "brighton and hove albion": "Brighton",
    "coventry city": "Coventry",
    "hull city": "Hull",
    "manchester city": "Man City",
    "manchester united": "Man United",
    "newcastle united": "Newcastle",
    "nottingham forest": "Nott'm Forest",
    "tottenham hotspur": "Tottenham",
    # Additional long forms The Odds API and comparable feeds commonly emit.
    "afc bournemouth": "Bournemouth",
    "arsenal fc": "Arsenal",
    "brentford fc": "Brentford",
    "brighton & hove albion": "Brighton",
    "burnley fc": "Burnley",
    "chelsea fc": "Chelsea",
    "crystal palace fc": "Crystal Palace",
    "everton fc": "Everton",
    "fulham fc": "Fulham",
    "ipswich town": "Ipswich",
    "leeds united": "Leeds",
    "leicester city": "Leicester",
    "liverpool fc": "Liverpool",
    "luton town": "Luton",
    "manchester utd": "Man United",
    "newcastle utd": "Newcastle",
    "norwich city": "Norwich",
    "nottm forest": "Nott'm Forest",
    "nottingham forest fc": "Nott'm Forest",
    "sheffield utd": "Sheffield United",
    "southampton fc": "Southampton",
    "sunderland afc": "Sunderland",
    "spurs": "Tottenham",
    "tottenham hotspur fc": "Tottenham",
    "west ham united": "West Ham",
    "wolverhampton": "Wolves",
    "wolverhampton wanderers": "Wolves",
}


def _lookup_key(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).casefold()


def normalize_team_name(value: object) -> str:
    """Map a provider team name onto its canonical project name.

    Unknown names are returned with whitespace tidied but otherwise unchanged,
    so they remain visibly unmapped instead of being coerced onto a wrong club.
    """
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        return ""
    key = cleaned.casefold()
    if key in PROVIDER_TEAM_ALIASES:
        return PROVIDER_TEAM_ALIASES[key]
    for canonical in CANONICAL_TEAM_NAMES:
        if canonical.casefold() == key:
            return canonical
    return cleaned


def is_canonical_team_name(value: object) -> bool:
    """True when the name already matches a canonical project name."""
    key = _lookup_key(value)
    return any(canonical.casefold() == key for canonical in CANONICAL_TEAM_NAMES)


def is_mapped_team_name(value: object) -> bool:
    """True when the name is canonical or has a reviewed alias."""
    return is_canonical_team_name(value) or _lookup_key(value) in PROVIDER_TEAM_ALIASES


def unmapped_team_names(values: Iterable[object]) -> list[str]:
    """Return the distinct names that have no reviewed mapping, sorted."""
    unmapped: dict[str, str] = {}
    for value in values:
        cleaned = " ".join(str(value or "").split())
        if not cleaned or is_mapped_team_name(cleaned):
            continue
        unmapped.setdefault(cleaned.casefold(), cleaned)
    return sorted(unmapped.values())
