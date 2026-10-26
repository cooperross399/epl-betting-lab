"""Per-match tackles and goalkeeper saves from Fantasy Premier League.

The provider prices `player_tackles_alternate`, `player_goalie_saves` and
`player_goalie_saves_alternate` (event-markets listing, 2026-10-19), and the
Understat logs carry neither stat. Fantasy Premier League publishes both for
every player in every match of the current season, keyless, from Opta — the
same supplier books settle against:

- ``GET /api/bootstrap-static/`` — every player, team and position
- ``GET /api/element-summary/{id}/`` — one player's match history this
  season (`history`) and his season totals in earlier ones (`history_past`)

Only the current season is per match; earlier seasons are totals. Those are
kept as `prior`, extra minutes of evidence for a player's rate, never as
appearances, because they carry no opponent, venue or date.

A player's team is the club FPL lists him at now. A player who moved in the
winter window carries his new club on his old appearances, which costs the
opponent factor a little and nothing else.

This module reads public pages and nothing else: no odds, no picks, no
settlement, no credential.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.providers.team_names import normalize_team_name


FPL_BASE_URL = "https://fantasy.premierleague.com/api"

FPL_LOGS_FILENAME = "fpl_match_logs.csv"
FPL_PRIOR_FILENAME = "fpl_prior.csv"
FPL_AVAILABILITY_FILENAME = "fpl_availability.csv"

#: Each player's fitness as FPL publishes it: status `a` available, `d`
#: doubtful, `i` injured, `s` suspended, `u` unavailable, `n` not eligible;
#: the chance of playing the next round in percent (blank when no flag).
#: The last four say how much he matters to his club (the match context
#: weighs an attacker by his expected goal involvement and a defender by his
#: minutes); a file written before they were added reads as zero for each.
AVAILABILITY_FIELDS = (
    "player", "player_id", "team", "status", "chance_next_round", "news",
    "position", "minutes", "total_points", "expected_goal_involvements",
)

LOG_FIELDS = (
    "date",
    "match_id",
    "team",
    "opponent",
    "venue",
    "player",
    "player_id",
    "position",
    "minutes",
    "tackles",
    "saves",
    "yellow_cards",
    "red_cards",
)

PRIOR_FIELDS = ("player", "player_id", "minutes", "tackles", "saves")

Requester = Callable[[str], Any]


class FplError(RuntimeError):
    """Raised when FPL answers in a shape this reader cannot trust."""


def _int(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _name(element: Mapping[str, Any]) -> str:
    return " ".join(
        f"{element.get('first_name', '')} {element.get('second_name', '')}".split()
    )


def _lookups(bootstrap: Mapping[str, Any]) -> tuple[dict, dict, dict]:
    teams = {
        team.get("id"): normalize_team_name(str(team.get("name", "")))
        for team in bootstrap.get("teams") or []
    }
    positions = {
        kind.get("id"): str(kind.get("singular_name_short", ""))
        for kind in bootstrap.get("element_types") or []
    }
    elements = {
        element.get("id"): element for element in bootstrap.get("elements") or []
    }
    return teams, positions, elements


def build_fpl_logs(
    bootstrap: Mapping[str, Any], summaries: Mapping[Any, Mapping[str, Any]]
) -> pd.DataFrame:
    """One row per player per appearance this season (minutes above zero)."""
    teams, positions, elements = _lookups(bootstrap)
    rows: list[dict[str, object]] = []
    for player_id, summary in summaries.items():
        element = elements.get(player_id) or elements.get(_int(player_id))
        if not element:
            continue
        team = teams.get(element.get("team"), "")
        for match in summary.get("history") or []:
            minutes = _int(match.get("minutes"))
            if minutes <= 0:
                continue
            rows.append(
                {
                    "date": str(match.get("kickoff_time", ""))[:10],
                    "match_id": str(match.get("fixture", "")),
                    "team": team,
                    "opponent": teams.get(match.get("opponent_team"), ""),
                    "venue": "home" if match.get("was_home") else "away",
                    "player": _name(element),
                    "player_id": str(element.get("id", "")),
                    "position": positions.get(element.get("element_type"), ""),
                    "minutes": minutes,
                    "tackles": _int(match.get("tackles")),
                    "saves": _int(match.get("saves")),
                    "yellow_cards": _int(match.get("yellow_cards")),
                    "red_cards": _int(match.get("red_cards")),
                }
            )
    return pd.DataFrame(rows, columns=list(LOG_FIELDS))


def build_fpl_availability(bootstrap: Mapping[str, Any]) -> pd.DataFrame:
    """Every player's status, chance of playing the next round, and the news behind it."""
    teams, positions, _ = _lookups(bootstrap)
    rows = []
    for element in bootstrap.get("elements") or []:
        chance = element.get("chance_of_playing_next_round")
        try:
            xgi = float(element.get("expected_goal_involvements") or 0.0)
        except (TypeError, ValueError):
            xgi = 0.0
        rows.append({
            "player": _name(element),
            "player_id": str(element.get("id", "")),
            "team": teams.get(element.get("team"), ""),
            "status": str(element.get("status") or ""),
            "chance_next_round": None if chance is None else _int(chance),
            "news": " ".join(str(element.get("news") or "").split()),
            "position": positions.get(element.get("element_type"), ""),
            "minutes": _int(element.get("minutes")),
            "total_points": _int(element.get("total_points")),
            "expected_goal_involvements": round(xgi, 2),
        })
    return pd.DataFrame(rows, columns=list(AVAILABILITY_FIELDS))


def build_fpl_prior(
    bootstrap: Mapping[str, Any],
    summaries: Mapping[Any, Mapping[str, Any]],
    *,
    season: str,
) -> pd.DataFrame:
    """Each player's totals for one earlier season (`2025/26`), if he played."""
    _, _, elements = _lookups(bootstrap)
    rows: list[dict[str, object]] = []
    for player_id, summary in summaries.items():
        element = elements.get(player_id) or elements.get(_int(player_id))
        if not element:
            continue
        for past in summary.get("history_past") or []:
            if str(past.get("season_name", "")) != season:
                continue
            if _int(past.get("minutes")) <= 0:
                continue
            rows.append(
                {
                    "player": _name(element),
                    "player_id": str(element.get("id", "")),
                    "minutes": _int(past.get("minutes")),
                    "tackles": _int(past.get("tackles")),
                    "saves": _int(past.get("saves")),
                }
            )
    return pd.DataFrame(rows, columns=list(PRIOR_FIELDS))


def previous_season_name(today: date) -> str:
    """FPL's label for the season before the one being played: `2025/26`."""
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start - 1}/{str(start)[2:]}"


def _default_requester(url: str) -> Any:
    import requests

    response = requests.get(
        url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30
    )
    if response.status_code != 200:
        raise FplError(f"FPL answered HTTP {response.status_code} for {url}.")
    return response.json()


@dataclass
class FplFetchResult:
    players_seen: int = 0
    players_fetched: int = 0
    logs: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=list(LOG_FIELDS)))
    prior: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=list(PRIOR_FIELDS)))
    errors: list[str] = field(default_factory=list)
    availability: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=list(AVAILABILITY_FIELDS))
    )


def fetch_fpl_player_data(
    *,
    requester: Requester | None = None,
    base_url: str = FPL_BASE_URL,
    today: date | None = None,
    workers: int = 4,
) -> FplFetchResult:
    """Every player who has played this season, his matches and last season.

    Players with no minutes this season are not asked for: they have no
    appearance to rate and no team sheet to be on.
    """
    request = requester or _default_requester
    bootstrap = request(f"{base_url}/bootstrap-static/")
    if not isinstance(bootstrap, Mapping) or not bootstrap.get("elements"):
        raise FplError("FPL's bootstrap carries no players.")
    result = FplFetchResult()
    played = [
        element.get("id")
        for element in bootstrap["elements"]
        if _int(element.get("minutes")) > 0
    ]
    result.players_seen = len(played)

    def one(player_id: Any) -> tuple[Any, Mapping[str, Any] | None, str]:
        try:
            summary = request(f"{base_url}/element-summary/{player_id}/")
        except Exception as exc:  # one player's failure never costs the rest
            return player_id, None, f"Player {player_id}: {exc}"
        if not isinstance(summary, Mapping):
            return player_id, None, f"Player {player_id}: not a JSON object."
        return player_id, summary, ""

    summaries: dict[Any, Mapping[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for player_id, summary, error in pool.map(one, played):
            if summary is None:
                result.errors.append(error)
                continue
            summaries[player_id] = summary
    result.players_fetched = len(summaries)
    result.logs = build_fpl_logs(bootstrap, summaries)
    result.availability = build_fpl_availability(bootstrap)
    result.prior = build_fpl_prior(
        bootstrap, summaries, season=previous_season_name(today or date.today())
    )
    return result


def write_fpl_data(result: FplFetchResult, directory: Path) -> tuple[Path, Path]:
    """Write the logs and the prior. Each run replaces both: FPL is the
    whole current season every time, so there is nothing to accumulate."""
    directory.mkdir(parents=True, exist_ok=True)
    logs_path = directory / FPL_LOGS_FILENAME
    prior_path = directory / FPL_PRIOR_FILENAME
    result.logs.to_csv(logs_path, index=False)
    result.prior.to_csv(prior_path, index=False)
    if not result.availability.empty:
        result.availability.to_csv(directory / FPL_AVAILABILITY_FILENAME, index=False)
    return logs_path, prior_path
