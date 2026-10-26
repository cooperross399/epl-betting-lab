"""How the Beyond the Premier League picks have done, graded against ESPN finals.

The section has recorded every selection it staked since it started
(`archive/extra_cards/<date>/<time>/extra_competitions_card.json`), and
`beyond_clv` has read them for closing-line value. Nothing asked whether one
won: the Premier League record is built from Football-Data, which carries no
cup or European fixture, and the card printed "recorded and not yet scored -
nothing settles them" under it on every run.

ESPN's keyless scoreboards carry every final of each competition the section
bets, with the score and both sides' corners. The selections are settled by
the Premier League card's own rules through the same `build_scoreboard`, so
the first record to name a selection is the price graded, a push is a bet, and
a fixture not yet played is pending rather than lost.

Two things are left ungraded on purpose:

- **A tie that went to extra time.** Every market here settles on ninety
  minutes, and ESPN's final score includes extra time. Counted as
  unsettleable, apart from pending, so it neither waits forever nor guesses.
  The EFL Cup goes straight to penalties, so its shootout scores are ninety-
  minute scores.
- **A club ESPN names differently from the record.** The record carries the
  ratings' names (Football-Data's); ESPN's go through the reviewed
  `ESPN_CLUB_NAMES`. A pick on a club neither map agrees on stays "played,
  waiting on results data", which says it is the feed and not the match.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.data.european_clubs import espn_name
from epl_betting_lab.providers.team_names import normalize_team_name
from epl_betting_lab.reports.card_scoreboard import Scoreboard, build_scoreboard

#: ESPN's league slug for each competition the section can bet.
ESPN_LEAGUES = {
    "UCL": "uefa.champions",
    "UEL": "uefa.europa",
    "UECL": "uefa.europa.conf",
    "EFLC": "eng.league_cup",
    "UNL": "uefa.nations",
}
COMPETITION_NAMES = {
    "UCL": "UEFA Champions League",
    "UEL": "UEFA Europa League",
    "UECL": "UEFA Europa Conference League",
    "EFLC": "EFL Cup (Carabao)",
    "UNL": "UEFA Nations League",
}
SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"
    "?dates={year}&limit=1000"
)
#: Competitions settled after a shootout with no extra time before it.
SHOOTOUT_AFTER_NINETY = frozenset({"EFLC"})

REPORT_FILENAME = "beyond_record.md"
DETAIL_FILENAME = "beyond_record_bets.csv"
SUMMARY_FILENAME = "beyond_record.json"

Fetch = Callable[[str, Sequence[int]], list[Mapping[str, Any]]]


class BeyondResultsError(RuntimeError):
    """ESPN could not be read."""


def default_fetch(competition: str, years: Sequence[int]) -> list[Mapping[str, Any]]:
    # urllib's own User-Agent on purpose: site.api.espn.com refuses
    # descriptive agents (see web/settle_results.py).
    payloads = []
    for year in years:
        url = SCOREBOARD.format(league=ESPN_LEAGUES[competition], year=year)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed host
                payloads.append(json.load(response))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise BeyondResultsError(f"ESPN could not be read at {url}: {exc}") from exc
    return payloads


def _name(raw: object, competition: str) -> str:
    name = " ".join(str(raw or "").split())
    if competition == "UNL":
        return name  # National teams: the record and ESPN both use the country.
    mapped = espn_name(name)
    return normalize_team_name(mapped) if competition == "EFLC" else mapped


def _sides(event: Mapping[str, Any]) -> tuple[Mapping, Mapping] | None:
    competition = (event.get("competitions") or [{}])[0]
    sides = {c.get("homeAway"): c for c in competition.get("competitors", []) or []}
    if not sides.get("home") or not sides.get("away"):
        return None
    return sides["home"], sides["away"]


def _went_to_extra_time(event: Mapping[str, Any], competition: str) -> bool:
    status = str((((event.get("status") or {}).get("type")) or {}).get("name") or "")
    if "AET" in status:
        return True
    return "PEN" in status and competition not in SHOOTOUT_AFTER_NINETY


def _completed(event: Mapping[str, Any]) -> bool:
    return bool((((event.get("status") or {}).get("type")) or {}).get("completed"))


def extra_time_fixtures(payload: Mapping[str, Any], competition: str) -> set[tuple[str, str]]:
    found = set()
    for event in payload.get("events", []) or []:
        sides = _sides(event)
        if sides and _completed(event) and _went_to_extra_time(event, competition):
            found.add(tuple(_name((s.get("team") or {}).get("displayName"), competition) for s in sides))
    return found


def _stat(side: Mapping[str, Any], name: str) -> int | None:
    for stat in side.get("statistics", []) or []:
        if stat.get("name") == name:
            try:
                return int(float(stat.get("displayValue")))
            except (TypeError, ValueError):
                return None
    return None


def _corners(sides: tuple[Mapping, Mapping]) -> list[int | None]:
    """Both sides' corners, or blanks when ESPN recorded no statistics.

    ESPN writes "0" for every statistic of a match it holds none for, and
    zero corners would settle every under as a win. Zero corners and zero
    shots for both sides is that pattern, never a match.
    """
    corners = [_stat(side, "wonCorners") for side in sides]
    shots = [_stat(side, "totalShots") for side in sides]
    if corners == [0, 0] and shots in ([0, 0], [None, None]):
        return [None, None]
    return corners


def finals_from_scoreboard(payload: Mapping[str, Any], competition: str) -> pd.DataFrame:
    """Ninety-minute finals as the rows `build_scoreboard` reads."""
    rows = []
    for event in payload.get("events", []) or []:
        sides = _sides(event)
        if not sides or not _completed(event) or _went_to_extra_time(event, competition):
            continue
        when = pd.to_datetime(event.get("date"), errors="coerce", utc=True)
        try:
            goals = [int(float(s.get("score"))) for s in sides]
        except (TypeError, ValueError):
            continue
        if pd.isna(when):
            continue
        corners = _corners(sides)
        rows.append({
            "date": pd.Timestamp(when.date()),
            "home_team": _name((sides[0].get("team") or {}).get("displayName"), competition),
            "away_team": _name((sides[1].get("team") or {}).get("displayName"), competition),
            "home_goals": goals[0],
            "away_goals": goals[1],
            "HC": corners[0] if corners[0] is not None else float("nan"),
            "AC": corners[1] if corners[1] is not None else float("nan"),
            "HY": float("nan"),
            "AY": float("nan"),
        })
    columns = ["date", "home_team", "away_team", "home_goals", "away_goals", "HC", "AC", "HY", "AY"]
    return pd.DataFrame(rows, columns=columns)


@dataclass
class BeyondRecord:
    by_competition: dict[str, Scoreboard] = field(default_factory=dict)
    error: str = ""

    @property
    def total(self) -> Scoreboard:
        board = Scoreboard()
        for part in self.by_competition.values():
            board.scored.extend(part.scored)
            for counter in ("pending", "awaiting_results", "kickoff_unknown", "void", "unsettleable"):
                setattr(board, counter, getattr(board, counter) + getattr(part, counter))
        return board


def _cards_by_competition(records: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Each record as one card per competition, the shape `build_scoreboard` reads."""
    cards: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for row in record.get("selections") or []:
            if isinstance(row, Mapping) and row.get("competition") in ESPN_LEAGUES:
                grouped.setdefault(str(row["competition"]), []).append(row)
        for competition, rows in grouped.items():
            cards.setdefault(competition, []).append({
                "card_generated": True,
                "generated_at": record.get("generated_at", ""),
                "best_bets": rows,
            })
    return cards


def build_beyond_record(
    records: Sequence[Mapping[str, Any]],
    payloads: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    now: datetime | None = None,
) -> BeyondRecord:
    result = BeyondRecord()
    for competition, cards in _cards_by_competition(records).items():
        frames = [finals_from_scoreboard(p, competition) for p in payloads.get(competition, [])]
        finals = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(
            not f.empty for f in frames) else finals_from_scoreboard({}, competition)
        finals = finals.drop_duplicates(subset=["date", "home_team", "away_team"])
        board = build_scoreboard(cards, finals, now=now)
        extra = set().union(*(extra_time_fixtures(p, competition) for p in payloads.get(competition, [])))
        for entry in board.scored:
            # Played, and not gradeable from a score that includes extra time.
            if not entry.fixture_date and (entry.home_team, entry.away_team) in extra \
                    and board.awaiting_results > 0:
                board.awaiting_results -= 1
                board.unsettleable += 1
        result.by_competition[competition] = board
    return result


def _years(records: Sequence[Mapping[str, Any]]) -> dict[str, list[int]]:
    years: dict[str, set[int]] = {}
    for record in records:
        for row in record.get("selections") or []:
            if not isinstance(row, Mapping) or row.get("competition") not in ESPN_LEAGUES:
                continue
            stamp = pd.to_datetime(row.get("kickoff_time") or record.get("generated_at"),
                                   errors="coerce", utc=True)
            if not pd.isna(stamp):
                years.setdefault(str(row["competition"]), set()).add(stamp.year)
    return {competition: sorted(found) for competition, found in years.items()}


def _line(name: str, board: Scoreboard) -> str:
    settled = board.settled
    won = sum(1 for s in settled if s.won)
    pushed = sum(1 for s in settled if s.pushed)
    roi = board.roi
    return (
        f"| {name} | {len(settled)} | {won} | {pushed} | {board.profit_units:+.2f} | "
        + (f"{roi:+.1%}" if roi is not None else "-")
        + f" | {board.pending} | {board.awaiting_results} | {board.unsettleable} |"
    )


def render_beyond_record(result: BeyondRecord) -> list[str]:
    lines = ["# Beyond the Premier League: how the picks have done", ""]
    if result.error:
        lines += [f"Not graded this run: {result.error}", ""]
        return lines
    if not result.by_competition:
        return lines + ["No staked selection is on file yet.", ""]
    lines += [
        "| Competition | Settled | Won | Push | Units | ROI | Pending | Played, no result | Ungradeable |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for competition, board in sorted(result.by_competition.items()):
        lines.append(_line(COMPETITION_NAMES.get(competition, competition), board))
    lines.append(_line("**All**", result.total))
    lines += [
        "",
        "Graded against ESPN finals at the first price a record offered each "
        "pick, by the Premier League card's rules: a push is a bet, a fixture "
        "not yet played is pending. A tie that went to extra time is "
        "ungradeable, because the markets settle on ninety minutes. No edge is "
        "demonstrated here; a sample this size cannot show one.",
        "",
    ]
    return lines


def save_beyond_record(
    records: Sequence[Mapping[str, Any]],
    output_dir: Path | None = None,
    *,
    fetch: Fetch = default_fetch,
    now: datetime | None = None,
) -> BeyondRecord:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    outputs.mkdir(parents=True, exist_ok=True)
    moment = now or datetime.now(timezone.utc)
    payloads: dict[str, list[Mapping[str, Any]]] = {}
    try:
        for competition, years in _years(records).items():
            payloads[competition] = list(fetch(competition, years))
    except BeyondResultsError as exc:
        result = BeyondRecord(error=str(exc))
    else:
        result = build_beyond_record(records, payloads, now=moment)
    (outputs / REPORT_FILENAME).write_text("\n".join(render_beyond_record(result)), encoding="utf-8")
    if result.error:
        return result
    total = result.total
    (outputs / SUMMARY_FILENAME).write_text(json.dumps({
        "generated_at": moment.isoformat(),
        "settled": len(total.settled),
        "won": sum(1 for s in total.settled if s.won),
        "pushed": sum(1 for s in total.settled if s.pushed),
        "staked_units": round(total.staked_units, 4),
        "profit_units": round(total.profit_units, 4),
        "pending": total.pending,
        "awaiting_results": total.awaiting_results,
        "unsettleable": total.unsettleable,
    }, indent=2) + "\n", encoding="utf-8")
    rows = []
    for competition, board in result.by_competition.items():
        for entry in board.scored:
            rows.append({"competition": competition, **{
                k: getattr(entry, k) for k in (
                    "fixture_date", "home_team", "away_team", "market", "selection",
                    "american_odds", "stake_units", "first_seen", "won", "pushed", "profit_units")
            }})
    pd.DataFrame(rows).to_csv(outputs / DETAIL_FILENAME, index=False)
    return result
