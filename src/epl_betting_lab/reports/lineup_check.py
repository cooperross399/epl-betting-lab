"""The card's picks against the confirmed lineups, read shortly before kick-off.

Every pick is made hours or days before the teams are named. ESPN's keyless
match summary carries each side's starting eleven and bench once the club
announces them, about an hour before kick-off. This reads them for the
fixtures about to start and says, per pick:

- a player prop whose player is on the bench or not in the squad: **do not
  bet**. A shots or tackles over on a substitute is mostly a losing ticket, and
  books void only a player who never comes on.
- a team pick on a side that changed four or more of its last league starting
  eleven: **check it**. The ratings were made on the side that usually plays.

Nothing here prices anything, buys anything or changes a stake on its own. It
withdraws props from the public board and writes the check beside the card;
a team pick stays where it is with the rotation named.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from epl_betting_lab.data.espn_results import EspnResultsError, default_requester
from epl_betting_lab.providers.team_names import normalize_team_name

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={day}"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary?event={event}"

REPORT_FILENAME = "lineup_check.md"
SUMMARY_FILENAME = "lineup_check.json"

#: Starting-eleven changes from the side's previous league match that make a
#: team pick worth a second look.
ROTATION_FLAG = 4

STARTING = "starting"
BENCH = "on the bench"
NOT_IN_SQUAD = "not in the squad"
NOT_OUT = "lineups not out yet"

Requester = Callable[[str], Any]


def player_key(name: object) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.casefold().replace("-", " ").replace(".", " ").replace("'", "")
    return " ".join(text.split())


@dataclass
class Lineup:
    starters: list[str] = field(default_factory=list)
    bench: list[str] = field(default_factory=list)


def lineups_from_summary(payload: Mapping[str, Any]) -> dict[str, Lineup]:
    """Team -> named eleven and bench. Empty until the clubs announce them."""
    out: dict[str, Lineup] = {}
    for roster in payload.get("rosters") or []:
        players = roster.get("roster") or []
        if not players:
            continue
        team = normalize_team_name((roster.get("team") or {}).get("displayName", ""))
        lineup = Lineup()
        for entry in players:
            name = str((entry.get("athlete") or {}).get("displayName") or "").strip()
            if not name:
                continue
            (lineup.starters if entry.get("starter") else lineup.bench).append(name)
        if lineup.starters:
            out[team] = lineup
    return out


def _find(name: str, names: Sequence[str]) -> bool:
    """The props card's token rule: one name's words inside the other's."""
    tokens = frozenset(player_key(name).split())
    if not tokens:
        return False
    for other in names:
        theirs = frozenset(player_key(other).split())
        if theirs and (theirs <= tokens or tokens <= theirs):
            return True
    return False


def player_state(player: str, lineup: Lineup | None) -> str:
    if lineup is None:
        return NOT_OUT
    if _find(player, lineup.starters):
        return STARTING
    if _find(player, lineup.bench):
        return BENCH
    return NOT_IN_SQUAD


def changes(current: Lineup, previous: Lineup | None) -> int | None:
    """How many of today's eleven did not start the side's previous match."""
    if previous is None or not previous.starters:
        return None
    return sum(1 for name in current.starters if not _find(name, previous.starters))


@dataclass
class LineupCheck:
    checked_at: str
    props: list[dict[str, Any]] = field(default_factory=list)
    team_picks: list[dict[str, Any]] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def withdrawn(self) -> list[dict[str, Any]]:
        return [p for p in self.props if p["state"] in (BENCH, NOT_IN_SQUAD)]

    @property
    def rotated(self) -> list[dict[str, Any]]:
        return [t for t in self.team_picks if (t.get("changes") or 0) >= ROTATION_FLAG]

    def to_json(self) -> dict[str, Any]:
        return {**asdict(self), "withdrawn": self.withdrawn, "rotated": self.rotated}


def _kickoff(value: object) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _due(picks: Sequence[Mapping[str, Any]], now: datetime, hours: float) -> list[Mapping[str, Any]]:
    """Picks whose fixture starts within the window, or kicked off minutes ago."""
    start, end = now - timedelta(minutes=30), now + timedelta(hours=hours)
    return [
        p for p in picks
        if (k := _kickoff(p.get("kickoff_time") or p.get("commence_time"))) and start <= k <= end
    ]


def _events_for(days: set[str], fetch: Requester) -> dict[tuple[str, str], tuple[str, str]]:
    """(home, away) -> (event id, kickoff) for the league's fixtures on those days."""
    events: dict[tuple[str, str], tuple[str, str]] = {}
    for day in sorted(days):
        payload = fetch(SCOREBOARD.format(day=day))
        for event in payload.get("events") or []:
            sides = {
                c.get("homeAway"): normalize_team_name((c.get("team") or {}).get("displayName", ""))
                for c in ((event.get("competitions") or [{}])[0].get("competitors") or [])
            }
            if sides.get("home") and sides.get("away"):
                events[(sides["home"], sides["away"])] = (str(event.get("id")), str(event.get("date")))
    return events


def _previous_lineup(team: str, before: datetime, fetch: Requester) -> Lineup | None:
    """The team's starting eleven in its previous league match, within three weeks."""
    for back in range(1, 22):
        day = (before - timedelta(days=back)).strftime("%Y%m%d")
        payload = fetch(SCOREBOARD.format(day=day))
        for event in payload.get("events") or []:
            if not (((event.get("status") or {}).get("type") or {}).get("completed")):
                continue
            names = [
                normalize_team_name((c.get("team") or {}).get("displayName", ""))
                for c in ((event.get("competitions") or [{}])[0].get("competitors") or [])
            ]
            if team in names:
                return lineups_from_summary(fetch(SUMMARY.format(event=event.get("id")))).get(team)
    return None


def build_lineup_check(
    props: Sequence[Mapping[str, Any]],
    team_picks: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    hours: float = 3.0,
    fetch: Requester = default_requester,
) -> LineupCheck:
    check = LineupCheck(checked_at=now.isoformat(timespec="minutes"))
    due_props, due_teams = _due(props, now, hours), _due(team_picks, now, hours)
    fixtures = {
        (normalize_team_name(p.get("home_team")), normalize_team_name(p.get("away_team")))
        for p in [*due_props, *due_teams]
    }
    if not fixtures:
        return check
    try:
        days = {
            k.strftime("%Y%m%d")
            for p in [*due_props, *due_teams]
            if (k := _kickoff(p.get("kickoff_time") or p.get("commence_time")))
        }
        events = _events_for(days, fetch)
        lineups: dict[tuple[str, str], dict[str, Lineup]] = {}
        for fixture in sorted(fixtures):
            if fixture in events:
                lineups[fixture] = lineups_from_summary(fetch(SUMMARY.format(event=events[fixture][0])))
                check.fixtures.append(f"{fixture[0]} v {fixture[1]}")
        for pick in due_props:
            fixture = (normalize_team_name(pick.get("home_team")), normalize_team_name(pick.get("away_team")))
            team = normalize_team_name(pick.get("team"))
            state = player_state(str(pick.get("player", "")), lineups.get(fixture, {}).get(team))
            check.props.append({
                "player": pick.get("player"), "team": team, "home_team": fixture[0],
                "away_team": fixture[1], "market": pick.get("market"),
                "selection": pick.get("selection"), "state": state,
            })
        previous: dict[str, Lineup | None] = {}
        for pick in due_teams:
            fixture = (normalize_team_name(pick.get("home_team")), normalize_team_name(pick.get("away_team")))
            sides = lineups.get(fixture) or {}
            row: dict[str, Any] = {
                "home_team": fixture[0], "away_team": fixture[1],
                "market": pick.get("market"), "selection": pick.get("selection"),
                "lineups_out": bool(sides), "changes": None, "rotated_team": "",
            }
            kickoff = _kickoff(pick.get("kickoff_time")) or now
            worst = None
            for team in fixture:
                if team not in sides:
                    continue
                if team not in previous:
                    previous[team] = _previous_lineup(team, kickoff, fetch)
                count = changes(sides[team], previous[team])
                if count is not None and (worst is None or count > worst[1]):
                    worst = (team, count)
            if worst:
                row["rotated_team"], row["changes"] = worst
            check.team_picks.append(row)
    except EspnResultsError as exc:
        check.error = str(exc)
    return check


def render(check: LineupCheck) -> str:
    lines = [f"## Lineup check, {check.checked_at.replace('T', ' ')} UTC", ""]
    if check.error:
        return "\n".join(lines + [f"ESPN could not be read, so nothing was checked: {check.error}", ""])
    if not check.props and not check.team_picks:
        return "\n".join(lines + ["No pick kicks off in the next three hours.", ""])
    if check.withdrawn:
        lines += ["**Do not bet these props: the player is not starting.**", ""]
        lines += [
            f"- {p['player']} ({p['team']}), {p['market']} {p['selection']}: {p['state']}"
            for p in check.withdrawn
        ]
        lines.append("")
    waiting = [p for p in check.props if p["state"] == NOT_OUT]
    starting = [p for p in check.props if p["state"] == STARTING]
    if starting:
        lines += [f"{len(starting)} prop(s) confirmed: the player starts.", ""]
    if waiting:
        lines += [f"{len(waiting)} prop(s) not checked: lineups not out yet.", ""]
    if check.rotated:
        lines += ["**Check these team picks: heavy rotation.**", ""]
        lines += [
            f"- {t['home_team']} v {t['away_team']}, {t['market']} {t['selection']}: "
            f"{t['rotated_team']} made {t['changes']} changes from their last league eleven"
            for t in check.rotated
        ]
        lines.append("")
    elif check.team_picks:
        lines += ["No team pick's side is heavily rotated.", ""]
    return "\n".join(lines)


def save_lineup_check(check: LineupCheck, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {"markdown": output_dir / REPORT_FILENAME, "json": output_dir / SUMMARY_FILENAME}
    paths["markdown"].write_text(render(check), encoding="utf-8")
    paths["json"].write_text(json.dumps(check.to_json(), indent=2, default=str), encoding="utf-8")
    return paths
