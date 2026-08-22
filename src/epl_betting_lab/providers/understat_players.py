"""Player match logs from Understat, so player props can be modelled and
settled.

The provider sells player-prop prices (confirmed live and historically by
probe on 2026-08-22), but pricing a prop needs a per-player rate and settling
one needs a per-player result, and nothing in this repository knows a player
exists: Football-Data ships match-level columns only. Understat fills that
gap. Two endpoints cover everything:

- ``POST /getLeagueData/EPL/{season}`` — all 380 matches with ids and dates
- ``POST /main/getMatchData/{match_id}`` — per-player rosters (minutes,
  goals, assists, shots, cards, substitutions) and every shot with its result

**Shots on target are derived, not reported.** Understat records each shot's
result (``Goal``, ``SavedShot``, ``MissedShots``, ``BlockedShot``,
``ShotOnPost``, ``OwnGoal``); on-target here means ``Goal`` or ``SavedShot``.
That is close to, but not identical to, the Opta counts books settle SOT
props against — shots saved after a deflection are the usual disagreement.
Any SOT backtest built on this carries that caveat and must say so.

**This module fetches public pages politely and nothing else.** A delay
between requests is enforced, already-fetched matches are never re-fetched,
and no odds, picks, bets, or settlement are involved. Understat is a
data-reading dependency exactly as Football-Data is; it has no API key and no
quota, which is also why every fetch is cached to disk — the cache, not the
site, is the working data source.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


UNDERSTAT_BASE_URL = "https://understat.com"

#: Understat shot results that count as on target. Blocked shots and shots
#: against the woodwork do not; that is the standard definition, and the
#: module docstring carries the Opta caveat.
ON_TARGET_RESULTS = frozenset({"Goal", "SavedShot"})

#: One row per player per appearance. Long-form, matching the repository's
#: other processed datasets.
LOG_FIELDS = (
    "season",
    "date",
    "match_id",
    "team",
    "opponent",
    "venue",
    "player",
    "player_id",
    "position",
    "minutes",
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "yellow_cards",
    "red_cards",
    "first_goal_minute",
)

#: Understat requester: takes a URL, returns decoded JSON or raises.
UnderstatRequester = Callable[[str], Any]


class UnderstatError(RuntimeError):
    """Raised when Understat answers with something other than the data."""


def _default_requester(url: str) -> Any:
    import requests

    response = requests.post(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise UnderstatError(f"Understat answered HTTP {response.status_code} for {url}.")
    try:
        return response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise UnderstatError(f"Understat returned non-JSON for {url}.") from exc


def _as_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class LeagueMatch:
    """One fixture in a season: enough identity to fetch and to join."""

    match_id: str
    date: str
    home_team: str
    away_team: str
    is_result: bool


def fetch_league_matches(
    season: str,
    *,
    requester: UnderstatRequester | None = None,
    base_url: str = UNDERSTAT_BASE_URL,
) -> list[LeagueMatch]:
    """Every match of an EPL season, played or not.

    Seasons use Understat naming: "2025" is 2025/26.
    """
    request = requester or _default_requester
    payload = request(f"{base_url}/getLeagueData/EPL/{season}")
    dates = payload.get("dates") if isinstance(payload, Mapping) else None
    if not isinstance(dates, list):
        raise UnderstatError(
            f"Understat league data for season {season} has no match list."
        )
    matches: list[LeagueMatch] = []
    for item in dates:
        if not isinstance(item, Mapping):
            continue
        home = item.get("h") or {}
        away = item.get("a") or {}
        matches.append(
            LeagueMatch(
                match_id=str(item.get("id", "")).strip(),
                date=str(item.get("datetime", "")).strip()[:10],
                home_team=str(home.get("title", "")).strip(),
                away_team=str(away.get("title", "")).strip(),
                is_result=bool(item.get("isResult")),
            )
        )
    return [m for m in matches if m.match_id]


def _on_target_by_roster(shots: object) -> dict[str, int]:
    """Shots on target per roster entry, from the shot-level records."""
    counts: dict[str, int] = {}
    sides = (
        [shots.get("h"), shots.get("a")]
        if isinstance(shots, Mapping)
        else [shots]
    )
    for side in sides:
        if not isinstance(side, list):
            continue
        for shot in side:
            if not isinstance(shot, Mapping):
                continue
            if str(shot.get("result", "")).strip() not in ON_TARGET_RESULTS:
                continue
            player_id = str(shot.get("player_id", "")).strip()
            if player_id:
                counts[player_id] = counts.get(player_id, 0) + 1
    return counts


def _first_goal_minutes(shots: object) -> dict[str, int]:
    """Each scorer's earliest goal minute. Own goals are not the scorer's."""
    firsts: dict[str, int] = {}
    sides = (
        [shots.get("h"), shots.get("a")]
        if isinstance(shots, Mapping)
        else [shots]
    )
    for side in sides:
        if not isinstance(side, list):
            continue
        for shot in side:
            if not isinstance(shot, Mapping):
                continue
            if str(shot.get("result", "")).strip() != "Goal":
                continue
            player_id = str(shot.get("player_id", "")).strip()
            minute = _as_int(shot.get("minute"))
            if player_id and (
                player_id not in firsts or minute < firsts[player_id]
            ):
                firsts[player_id] = minute
    return firsts


def build_match_log_rows(
    match: LeagueMatch,
    match_data: Mapping[str, Any],
    *,
    season: str,
) -> list[dict[str, object]]:
    """One row per player who appeared, from one match's Understat data."""
    rosters = match_data.get("rosters")
    if not isinstance(rosters, Mapping):
        raise UnderstatError(f"Match {match.match_id} has no rosters.")
    on_target = _on_target_by_roster(match_data.get("shots"))
    first_goals = _first_goal_minutes(match_data.get("shots"))

    rows: list[dict[str, object]] = []
    for side, team, opponent in (
        ("h", match.home_team, match.away_team),
        ("a", match.away_team, match.home_team),
    ):
        entries = rosters.get(side)
        if not isinstance(entries, Mapping):
            continue
        for entry in entries.values():
            if not isinstance(entry, Mapping):
                continue
            minutes = _as_int(entry.get("time"))
            if minutes <= 0:
                # An unused substitute has no appearance to log; a prop on a
                # player who never entered is voided by the book, not lost.
                continue
            player_id = str(entry.get("player_id", "")).strip()
            first_goal = first_goals.get(player_id)
            rows.append(
                {
                    "season": season,
                    "date": match.date,
                    "match_id": match.match_id,
                    "team": team,
                    "opponent": opponent,
                    "venue": "home" if side == "h" else "away",
                    "player": str(entry.get("player", "")).strip(),
                    "player_id": player_id,
                    "position": str(entry.get("position", "")).strip(),
                    "minutes": minutes,
                    "goals": _as_int(entry.get("goals")),
                    "assists": _as_int(entry.get("assists")),
                    "shots": _as_int(entry.get("shots")),
                    "shots_on_target": on_target.get(player_id, 0),
                    "yellow_cards": _as_int(entry.get("yellow_card")),
                    "red_cards": _as_int(entry.get("red_card")),
                    "first_goal_minute": "" if first_goal is None else first_goal,
                }
            )
    return rows


@dataclass
class FetchResult:
    """What one fetch run did, so the operator can see it was polite."""

    matches_seen: int = 0
    matches_fetched: int = 0
    already_had: int = 0
    not_played_yet: int = 0
    rows: list[dict[str, object]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def fetch_player_match_logs(
    seasons: Sequence[str],
    *,
    requester: UnderstatRequester | None = None,
    base_url: str = UNDERSTAT_BASE_URL,
    already_fetched: Iterable[str] = (),
    sleep_seconds: float = 1.0,
    sleeper: Callable[[float], None] | None = None,
) -> FetchResult:
    """Fetch every played match's player logs, skipping what is held.

    `already_fetched` is match ids; a match is fetched exactly once across
    runs. `sleeper` is injectable so tests need not wait.
    """
    request = requester or _default_requester
    if sleeper is None:
        import time

        sleeper = time.sleep
    held = {str(item).strip() for item in already_fetched}
    result = FetchResult()
    for season in seasons:
        matches = fetch_league_matches(
            season, requester=request, base_url=base_url
        )
        result.matches_seen += len(matches)
        for match in matches:
            if not match.is_result:
                result.not_played_yet += 1
                continue
            if match.match_id in held:
                result.already_had += 1
                continue
            try:
                match_data = request(
                    f"{base_url}/main/getMatchData/{match.match_id}"
                )
                rows = build_match_log_rows(match, match_data, season=season)
            except UnderstatError as exc:
                result.errors.append(str(exc))
                continue
            result.rows.extend(rows)
            result.matches_fetched += 1
            held.add(match.match_id)
            if sleep_seconds > 0:
                sleeper(sleep_seconds)
    return result
