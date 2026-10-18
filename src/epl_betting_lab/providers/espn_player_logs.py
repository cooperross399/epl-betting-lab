"""Per-player Premier League match logs from ESPN's public soccer endpoints.

The Due List (`epl_betting_lab.due_list`) needs, for every player, every
league match he was in the squad for and whether he scored in it. Understat
carries that too (`providers.understat_players`), but it costs one politely
spaced request per match and is not reachable from every environment this lab
runs in; ESPN is keyless, already read by the board and the kickoff filter, and
answers quickly. Two endpoints cover everything:

- ``scoreboard?dates=YYYY&limit=1000`` — every league match in a calendar
  year, each tagged with its season (``season.year`` 2025 is 2025/26). The
  documented range form ``?dates=A-B`` answers HTTP 400 on the soccer
  endpoint, so a season is read as its two calendar years and filtered.
- ``summary?event=ID`` — both matchday squads, each player with
  ``appearances`` (1 if he got on the pitch), ``totalGoals`` and
  ``ownGoals``. ``totalGoals`` does not count own goals, which is what an
  anytime-goalscorer bet settles on.

**A player in the squad who never came on is kept, with ``appeared`` 0.**
The drought counts only appearances, but the squad list is what tells a fit
player left on the bench from one who was not there at all, and the Due List
uses that to flag a player who has dropped out of his club's squads.

Reads no odds, prices nothing, spends no credit, places no bet.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any


ESPN_SOCCER = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1"
USER_AGENT = "epl-betting-lab/1.0 (+https://github.com/cooperross399/epl-betting-lab)"

#: One row per player per matchday squad.
LOG_FIELDS = (
    "season",
    "date",
    "event_id",
    "team",
    "opponent",
    "venue",
    "player_id",
    "player",
    "position",
    "starter",
    "appeared",
    "goals",
    "own_goals",
)

#: Takes a URL, returns decoded JSON or raises.
Requester = Callable[[str], Any]


class EspnError(RuntimeError):
    """ESPN answered with something other than the data."""


def default_requester(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed host
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise EspnError(f"ESPN could not be read at {url}: {exc}") from exc


@dataclass(frozen=True)
class LeagueEvent:
    """One league fixture: enough identity to fetch it and to list it."""

    event_id: str
    kickoff: str
    season: int
    home: str
    away: str
    completed: bool


def _events_from_scoreboard(payload: Mapping) -> list[LeagueEvent]:
    out: list[LeagueEvent] = []
    for ev in payload.get("events", []) or []:
        comp = (ev.get("competitions") or [{}])[0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", []) or []}
        status = ((ev.get("status") or {}).get("type") or {})
        season = (ev.get("season") or {}).get("year")
        if season is None or not ev.get("id"):
            continue
        out.append(
            LeagueEvent(
                event_id=str(ev["id"]),
                kickoff=str(ev.get("date") or ""),
                season=int(season),
                home=str(((sides.get("home") or {}).get("team") or {}).get("displayName", "")),
                away=str(((sides.get("away") or {}).get("team") or {}).get("displayName", "")),
                completed=bool(status.get("completed")),
            )
        )
    return out


def season_events(season: int, *, request: Requester = default_requester) -> list[LeagueEvent]:
    """Every league fixture of `season` (2025 is 2025/26), played or not, in kickoff order."""
    seen: dict[str, LeagueEvent] = {}
    for year in (season, season + 1):
        payload = request(f"{ESPN_SOCCER}/scoreboard?dates={year}&limit=1000")
        for event in _events_from_scoreboard(payload):
            if event.season == season:
                seen[event.event_id] = event
    return sorted(seen.values(), key=lambda e: (e.kickoff, e.event_id))


def _stat(player: Mapping, name: str) -> int:
    for stat in player.get("stats", []) or []:
        if stat.get("name") == name:
            try:
                return int(float(stat.get("value") or 0))
            except (TypeError, ValueError):
                return 0
    return 0


def match_rows(summary: Mapping, event: LeagueEvent) -> list[dict[str, Any]]:
    """The squad rows of one played match. A summary without both squads yields none."""
    rosters = summary.get("rosters") or []
    if len(rosters) != 2:
        return []
    names = {r.get("homeAway"): str((r.get("team") or {}).get("displayName", "")) for r in rosters}
    rows: list[dict[str, Any]] = []
    for roster in rosters:
        side = roster.get("homeAway")
        team = names.get(side, "")
        opponent = names.get("away" if side == "home" else "home", "")
        for player in roster.get("roster", []) or []:
            athlete = player.get("athlete") or {}
            if not athlete.get("id"):
                continue
            rows.append(
                {
                    "season": event.season,
                    "date": event.kickoff[:10],
                    "event_id": event.event_id,
                    "team": team,
                    "opponent": opponent,
                    "venue": side or "",
                    "player_id": str(athlete["id"]),
                    "player": str(athlete.get("displayName") or ""),
                    "position": str((player.get("position") or {}).get("abbreviation", "")),
                    "starter": int(bool(player.get("starter"))),
                    "appeared": int(_stat(player, "appearances") > 0),
                    "goals": _stat(player, "totalGoals"),
                    "own_goals": _stat(player, "ownGoals"),
                }
            )
    return rows


@dataclass
class FetchResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    events: list[LeagueEvent] = field(default_factory=list)
    fetched: int = 0
    failed: list[str] = field(default_factory=list)


def fetch_logs(
    seasons: Iterable[int],
    *,
    request: Requester = default_requester,
    skip_event_ids: Iterable[str] = (),
    workers: int = 8,
) -> FetchResult:
    """Squad rows for every played match of `seasons`, plus every fixture listed.

    A match whose summary cannot be read is named in `failed` and contributes
    no rows; it is never filled in. A drought read across a missing match is
    understated, never overstated, because the match is absent rather than
    recorded as a blank.
    """
    result = FetchResult()
    skip = {str(e) for e in skip_event_ids}
    for season in seasons:
        result.events.extend(season_events(int(season), request=request))
    wanted = [e for e in result.events if e.completed and e.event_id not in skip]

    def one(event: LeagueEvent) -> tuple[LeagueEvent, list[dict[str, Any]] | None]:
        try:
            summary = request(f"{ESPN_SOCCER}/summary?event={event.event_id}")
        except EspnError:
            return event, None
        rows = match_rows(summary, event)
        return event, rows if rows else None

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for event, rows in pool.map(one, wanted):
            if rows is None:
                result.failed.append(event.event_id)
                continue
            result.rows.extend(rows)
            result.fetched += 1
    return result
