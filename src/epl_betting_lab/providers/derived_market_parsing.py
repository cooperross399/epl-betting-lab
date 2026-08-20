"""Turn provider outcome names into project selections.

Written against a live probe, not against a guess. The Odds API names these
outcomes after the teams, not after positions, so the same market reads
differently for every fixture:

    double_chance   "Arsenal or Draw", "Coventry City or Draw",
                    "Arsenal or Coventry City"
    draw_no_bet     "Arsenal", "Coventry City"
    corners_1x2     "Arsenal", "Coventry City", "Draw"
    corners totals  "Over"/"Under" with the line carried in `point`

Two consequences follow, and both are the reason this is a module rather than a
few lines inline.

Resolving a name needs the fixture's own team names, so the provider's spelling
has to match the fixture's. "Coventry City" against "Coventry" is not a parse
failure to shrug at — it silently drops one side of a market, leaving a card
that looks complete and is missing a bet. So an unrecognised name raises rather
than returning None.

And a totals line arrives per outcome, so a market key with the line baked into
it — corners_total_9_5 — only matches outcomes whose point is 9.5. The rest of
the ladder is ignored on purpose: taking whatever line the book happened to
send would silently price a different bet from the one the model priced.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class UnrecognizedOutcomeError(ValueError):
    """A provider outcome that cannot be mapped to a project selection."""


def _norm(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _names(*values: object) -> set[str]:
    """Every spelling that should count as this team.

    The provider writes "Coventry City" where the project writes "Coventry", so
    matching on the project name alone rejects a real outcome. The h2h path
    already compared both the provider label and the reviewed alias; these
    markets have to do the same or they drop a side of every fixture whose
    names differ.
    """
    from epl_betting_lab.providers.team_names import normalize_team_name

    spellings: set[str] = set()
    for value in values:
        text = _norm(value)
        if not text:
            continue
        spellings.add(text)
        spellings.add(_norm(normalize_team_name(str(value))))
    return spellings


def double_chance_selection(
    outcome_name: str,
    home_team: str,
    away_team: str,
    provider_home_team: str = "",
    provider_away_team: str = "",
) -> str:
    """"Arsenal or Draw" -> "home_or_draw"."""
    name = _norm(outcome_name)
    home = _names(home_team, provider_home_team)
    away = _names(away_team, provider_away_team)
    parts = {part.strip() for part in name.split(" or ")}
    if len(parts) != 2:
        raise UnrecognizedOutcomeError(
            f"Double chance outcome {outcome_name!r} is not two outcomes joined "
            "by ' or '."
        )
    has_home = bool(home & parts)
    has_away = bool(away & parts)
    has_draw = "draw" in parts
    if has_home and has_draw:
        return "home_or_draw"
    if has_away and has_draw:
        return "draw_or_away"
    if has_home and has_away:
        return "home_or_away"
    raise UnrecognizedOutcomeError(
        f"Double chance outcome {outcome_name!r} does not name "
        f"{home_team!r} or {away_team!r}. A provider spelling that does not "
        "match the fixture drops one side of the market."
    )


def team_selection(
    outcome_name: str,
    home_team: str,
    away_team: str,
    provider_home_team: str = "",
    provider_away_team: str = "",
) -> str:
    """A team name, or "Draw", to "home" / "away" / "draw"."""
    name = _norm(outcome_name)
    if name in {"draw", "tie"}:
        return "draw"
    if name in _names(home_team, provider_home_team):
        return "home"
    if name in _names(away_team, provider_away_team):
        return "away"
    raise UnrecognizedOutcomeError(
        f"Outcome {outcome_name!r} is neither a draw nor one of "
        f"{home_team!r} / {away_team!r}."
    )


def total_selection(outcome_name: str) -> str:
    """"Over" / "Under", lowercased."""
    name = _norm(outcome_name)
    if name in {"over", "under"}:
        return name
    raise UnrecognizedOutcomeError(
        f"Totals outcome {outcome_name!r} is neither Over nor Under."
    )


def matches_line(outcome: Mapping[str, Any], line: float) -> bool:
    """Is this outcome on the exact line the market names?

    A book sends a whole ladder of lines in one market. Taking whichever
    arrived would price a different bet from the one the model priced, so
    anything off the named line is skipped rather than approximated.
    """
    point = outcome.get("point")
    if point is None:
        return False
    try:
        return abs(float(point) - float(line)) < 1e-9
    except (TypeError, ValueError):
        return False


#: market -> how to read one of its outcomes.
def selection_for(
    market: str,
    outcome: Mapping[str, Any],
    home_team: str,
    away_team: str,
    provider_home_team: str = "",
    provider_away_team: str = "",
) -> str | None:
    """The project selection for one provider outcome, or None if it is off-line.

    Raises when the outcome cannot be understood at all, because a silently
    dropped selection is a card that looks complete and is missing a bet.
    """
    name = str(outcome.get("name", ""))
    if market == "double_chance":
        return double_chance_selection(
            name, home_team, away_team, provider_home_team, provider_away_team
        )
    if market in {"draw_no_bet", "corners_1x2"}:
        return team_selection(
            name, home_team, away_team, provider_home_team, provider_away_team
        )
    if market.startswith("corners_total_") or market == "total_2_5":
        line = 2.5 if market == "total_2_5" else float(
            market.rsplit("_", 2)[-2] + "." + market.rsplit("_", 1)[-1]
        )
        if not matches_line(outcome, line):
            return None
        return total_selection(name)
    raise UnrecognizedOutcomeError(f"No parser for market {market!r}.")
