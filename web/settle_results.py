#!/usr/bin/env python3
"""Settle yesterday's frozen board into results.json. Sport-agnostic on the outside;
the finals come from ESPN's public scoreboard for the sport named in site.json.

    python web/settle_results.py --data dist/data --sport epl|cbb [--date YYYY-MM-DD]

Reads every frozen board under history/, takes each fixture that kicked off on
the settle date as it was FIRST published, fetches that date's finals, grades
each projection and pick, and writes results.json. The board is never edited.
The NHL lab settles inside build_site_json.py and does not use this file.

The selection is by the fixture's own `kickoff`, NOT by the board filed under
the settle date -- see `first_published`, which is where that cost the record
every pick it has ever published.

It also sums the season (`season_record`): every day a published fixture
kicked off, each settled once and kept under history/settled/<date>.json, which
rides in the same board-history artifact as the frozen boards. That season is
written into results.json as `seasonRecord` and onto board.json's `record`
(picks, straightUp, totals, leans, season, and the Due List's `dueList`), and
only once a day has settled: a tally nobody has made is absent, never 0-0.
Best bets are `picks`; leans are graded the same way and kept in `leans`.

EPL boards carry the Due List (`games[].drought`). Each entry is graded from
the match summary's squads: `actual` goals or assists and win/loss when he
played, `void` when he did not. Nothing is bet: since 2026-10-31 an entry
with a staged price is tracked as if `DUE_STAKE` (0.25u) were, as the NHL
site does (`units`); one without a price is graded but not posted.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import unicodedata

#: NO custom User-Agent, deliberately, and this is the opposite of the rule the
#: NHL lab pins for api-web.nhle.com. That host refuses urllib's default and
#: accepts any string; site.api.espn.com is in front of a WAF that does the
#: reverse -- it answers `Python-urllib/3.x` with 200 and returns 403 Access
#: Denied for a descriptive agent AND for a Chrome string alike. Measured
#: 2026-09-23, three trials, both sports, stable.
#:
#: So a polite, identifying agent is exactly what breaks this, which is the
#: wrong way round from every other fetch in these repositories and is why it
#: is written down rather than left to whoever reads the next 403.
#: `test_the_settlement_fetch_sends_no_custom_user_agent` holds it.
ESPN = {
    "epl": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={d}&limit=100",
    "cbb": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={d}&groups=50&limit=400",
}


#: The per-match summary, which is the only place the corner counts are. The
#: scoreboard above carries the score and nothing else, so a corner pick costs
#: one extra request for its own fixture -- free, no provider credit, same host
#: and same User-Agent rule as the scoreboard.
#:
#: Without it the public record cannot report on a single BET. Every one of the
#: five bets on the 2026-10-10 board is a corner market; the two `draw_no_bet`
#: picks are leans and the two `double_chance` picks are passes. A record that
#: graded only what it could reach would have published a model record made
#: entirely of leans, on a page that advertises bets.
#:
#: cbb is absent deliberately: there are no corners in basketball, and
#: `corner_counts` returns None for any sport not listed.
SUMMARY = {
    "epl": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary?event={e}",
}

#: `corners_total_10_5` -> 10.5. Parsed rather than held in a table, so a line
#: the card starts quoting cannot leave this file behind. The lab's own copy of
#: this rule is `card_scoreboard.CORNER_MARKETS`; the two are deliberately
#: separate because this script is stdlib-only and shipped to four repos, and
#: neither is a test of the other.
CORNERS_TOTAL = re.compile(r"^corners_total_(\d+)_(\d+)$")

#: `team_total_away_0_5` -> the side and the half line. EPL only.
TEAM_TOTAL = re.compile(r"^team_total_(home|away)_(\d+)_(\d+)$")


def fetch(url, timeout: int = 30):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.load(r)


def match_summary(sport: str, event_id: str) -> dict | None:
    """One match's ESPN summary, or None when the sport has none or the feed did not answer.

    Never raises. The corner counts and the Due List's player lines both come
    from it, and settlement asks for it at most once per fixture.
    """
    template = SUMMARY.get(sport)
    if not template:
        return None
    try:
        payload = fetch(template.format(e=event_id), timeout=15)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def corner_counts(sport: str, event_id: str) -> dict | None:
    """Corners won by each side, or None if the feed does not plainly say.

    Never raises, and never substitutes a zero. A missing statistic read as
    zero would settle `Under 10.5 corners` as a win every time the feed was
    down, which is a fabricated result in the direction of the card. Both
    sides must be present or the pick stays ungraded and is counted as such.
    """
    return corners_from(match_summary(sport, event_id))


def corners_from(payload: dict | None) -> dict | None:
    """`corner_counts` on a summary already in hand."""
    if not isinstance(payload, dict):
        return None
    out: dict[str, int] = {}
    for team in ((payload.get("boxscore") or {}).get("teams") or []):
        side = str(team.get("homeAway") or "").lower()
        if side not in ("home", "away"):
            continue
        for stat in (team.get("statistics") or []):
            if stat.get("name") != "wonCorners":
                continue
            try:
                out[side] = int(str(stat.get("displayValue")).strip())
            except (TypeError, ValueError):
                pass
    return out if {"home", "away"} <= set(out) else None


def finals(sport: str, day: date) -> dict:
    out = {}
    for ev in fetch(ESPN[sport].format(d=f"{day:%Y%m%d}")).get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        st = ((ev.get("status") or {}).get("type") or {})
        if not st.get("completed"):
            continue
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        try:
            out[str(ev["id"])] = {"home": int(sides["home"]["score"]), "away": int(sides["away"]["score"]),
                                  "finish": "OT" if (st.get("detail") or "").upper().find("OT") >= 0 else "REG"}
        except (KeyError, ValueError, TypeError):
            continue
    return out


def side_named(label: str, g: dict, teams: dict) -> str | None:
    """Which side a selection label names, or None if it cannot be told.

    The two halves speak different vocabularies. `selection_label` writes the
    team NAME it was handed -- "Newcastle draw no bet", "Notre Dame -4",
    "Kansas ML" -- while the board carries abbreviations: BRE, ND, KU. As
    shipped this compared the one to the other, `label.startswith(abbr)`,
    which is False for every real label, so CBB graded every side pick as the
    away side and EPL leaned on a second arm, `g.get("_homeName", "") in
    label`. Nothing anywhere writes `_homeName`, so that arm read
    `"" in label` -- true of every string -- and every EPL draw-no-bet graded
    as a home pick whichever side was taken. Both failures are silent and land
    in the published record.

    Longest match wins, so a name that is a prefix of the other side's cannot
    claim it. Returning None leaves the pick ungraded: a settled record with a
    hole in it can be repaired, and one confidently settled for the opponent
    cannot.
    """
    best, found = 0, None
    for role in ("home", "away"):
        abbr = ((g.get(role) or {}).get("abbr") or "")
        entry = teams.get(abbr) or {}
        for cand in (entry.get("name"), entry.get("short"), abbr):
            if not cand:
                continue
            c = str(cand).lower()
            if label.startswith(c) and len(c) > best:
                best, found = len(c), role
    return found


def grade_corners(market: str, label: str, g: dict, teams: dict, counts: dict) -> str | None:
    """Settle a corner pick, on the same rule the lab settles its own record by.

    `card_scoreboard.settle` is the authority and this follows it exactly:
    `corners_1x2` is a THREE-way market -- `market_eligibility` lists it as
    ("home", "draw", "away") -- so an equal corner count is the draw outcome
    and a side selection loses rather than pushing. The totals are half lines,
    so a push is impossible by construction; the branch is still written,
    because a whole-number line would otherwise settle as a loss in silence.
    """
    home, away = counts["home"], counts["away"]
    hit = CORNERS_TOTAL.match(market)
    if hit:
        line = float(f"{hit.group(1)}.{hit.group(2)}")
        total = home + away
        if total == line:
            return "push"
        return "win" if ("over" in label) == (total > line) else "loss"
    if market == "corners_1x2":
        side = side_named(label, g, teams)
        if side is None:
            return None
        return "win" if (side == "home") == (home > away) else "loss"
    return None


def grade_pick(sport, pick, g, hf, af, teams=None, corners=None):
    if not pick or pick.get("kind", "bet") not in ("bet", "lean"):
        return None
    m, label = (pick.get("market") or "").lower(), (pick.get("label") or "").lower()
    tot = hf + af
    teams = teams or {}
    if m.startswith("corners"):
        # Left ungraded when the counts did not arrive, never guessed.
        return grade_corners(m, label, g, teams, corners) if corners else None
    if sport == "epl":
        team_total = TEAM_TOTAL.match(m)
        if team_total:
            # The market names the side and the line; the label says over or
            # under. A half line cannot push.
            goals = hf if team_total.group(1) == "home" else af
            line = float(f"{team_total.group(2)}.{team_total.group(3)}")
            words = f" {label} "
            if (" over " in words) == (" under " in words):
                return None
            return "win" if (" over " in words) == (goals > line) else "loss"
        if m.startswith("total"):
            return "win" if ("over" in label) == (tot > 2.5) else "loss"
        if m == "btts":
            yes = hf > 0 and af > 0
            return "win" if ("both teams score" in label) == yes else "loss"
        if m == "draw_no_bet":
            if hf == af:
                return "void"
            side = side_named(label, g, teams)
            if side is None:
                return None
            return "win" if (side == "home") == (hf > af) else "loss"
        # Corners are handled above. `double_chance` is reachable from the
        # score alone and is left here only because every double-chance pick
        # the card has published is a `pass`, which never reaches this
        # function; a rule written for rows that do not exist is a rule
        # nothing checks.
        return None
    if sport == "cbb":
        margin = hf - af
        if m == "moneyline":
            side = side_named(label, g, teams)
            if side is None:
                return None
            return "win" if (side == "home") == (margin > 0) else "loss"
        if m == "spread":
            side = side_named(label, g, teams)
            if side is None:
                return None
            home = side == "home"
            line = float(pick.get("line") or (g.get("spread") or {}).get("current") or 0)
            adj = margin + line if home else -margin - line
            return "win" if adj > 0 else "loss" if adj < 0 else "push"
        if m == "total":
            line = float(pick.get("line") or (g.get("total") or {}).get("current") or 0)
            return "push" if tot == line else "win" if ("over" in label) == (tot > line) else "loss"
    return None


#: A frozen board is named `<date>.json`, or `<date>_<slot>.json` for a sport
#: with several cards a day. `history/index.json` and `history/lines/` sit
#: alongside them and are not boards.
BOARD_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_\w+)?\.json$")


def frozen_boards(hist: Path) -> list[dict]:
    """Every frozen board, oldest publication first.

    Ordered on `generatedAt` rather than on the filename. The filename is the
    date the board was filed under, and this repository has filed the same
    board under two different dates at once -- `build_board_json.py` used
    today's date while `site_history.py` used the window start -- so only
    `generatedAt` says which opinion was actually published first.
    """
    out: list[dict] = []
    for path in sorted(hist.glob("*.json")):
        if not BOARD_NAME.match(path.name):
            continue
        try:
            board = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(board, dict):
            out.append(board)
    out.sort(key=lambda b: str(b.get("generatedAt") or ""))
    return out


def first_published(boards: list[dict], day: date) -> tuple[dict, str | None]:
    """Each fixture that kicked off on `day`, as it was FIRST published.

    The board is a FORWARD window. The copy frozen on 2026-09-28 carried the
    2026-10-10 through 2026-10-12 fixtures, and so did all seven of its
    neighbours. This step used to read the single board filed under the settle
    date and grade it against that date's finals, which compared ten fixtures
    still to come against the results of a day they were not played on. It
    matched none of them, every time: `results.json` has carried
    `picks 0-0-0` since the page went up, under the notice "The games were
    played but no final was available when this ran" -- of games eleven days
    away. Not one published pick has ever been graded.

    A fixture's own `kickoff` is the only field that says when it was played,
    so that is what selects it, and it is looked for across every frozen board
    rather than one. That also reaches the rest of a multi-day window: a board
    filed under its window start spans three dates here, and only the first of
    them could ever have matched even once the filing was consistent.

    First publication wins, which is the convention `live_clv`'s
    `first_recommendations` already uses. The pick that was advertised first is
    the one the record owes an answer for, and a board frozen later -- after a
    price moved, or after the model changed its mind -- must not be able to
    quietly replace it.
    """
    found: dict[str, tuple[dict, dict]] = {}
    window: str | None = None
    for board in boards:
        teams = board.get("teams") or {}
        for game in board.get("games", []):
            if str(game.get("kickoff") or "")[:10] != day.isoformat():
                continue
            gid = str(game.get("id"))
            if gid in found:
                continue
            found[gid] = (game, teams)
            if window is None:
                window = board.get("windowLabel")
    ordered = dict(
        sorted(found.items(), key=lambda kv: (str(kv[1][0].get("kickoff") or ""), kv[0]))
    )
    return ordered, window


#: What a scoreboard fetch can raise. A day whose finals cannot be read is not
#: settled, and the season says so (`missingNights`) rather than counting it 0–0.
FETCH_ERRORS = (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError, ValueError)

#: The Due List's two categories, as the board's `games[].drought` names them,
#: and the ESPN summary statistic each settles on. `totalGoals` excludes own
#: goals, which is what an anytime-goalscorer line settles on
#: (`providers/espn_player_logs`, which builds the list from the same feed).
DUE_STATS = {"goals": "totalGoals", "assists": "goalAssists"}

#: The NHL lab's rule (2026-10-09), brought to EPL on 2026-10-31: the Due List
#: is tracked as if this were bet on every entry at its staged price. Nothing
#: is bet, and none of it reaches the card. An entry with no price, a void or
#: an ungraded entry carries no units ("not posted").
DUE_STAKE = 0.25


def _name_key(name: object) -> str:
    return " ".join(str(name or "").split()).casefold()


def _stat_value(stats: dict, name: str) -> float | None:
    try:
        value = stats.get(name)
        return None if value is None or str(value).strip() == "" else float(value)
    except (TypeError, ValueError):
        return None


def player_lines(payload: dict | None) -> dict | None:
    """Both matchday squads from a summary: side -> players, or None if the feed does not hold both.

    Each player is {id, name, stats}. A squad member who never came on is kept
    (`appearances` 0), because "did not play" is a grade here, not a gap.
    """
    rosters = (payload or {}).get("rosters") if isinstance(payload, dict) else None
    if not isinstance(rosters, list) or len(rosters) != 2:
        return None
    out: dict[str, list] = {}
    for roster in rosters:
        if not isinstance(roster, dict):
            return None
        side = str(roster.get("homeAway") or "").lower()
        if side not in ("home", "away"):
            return None
        players = []
        for player in roster.get("roster") or []:
            if not isinstance(player, dict):
                continue
            athlete = player.get("athlete") or {}
            stats = {s.get("name"): s.get("value") for s in player.get("stats") or [] if isinstance(s, dict)}
            players.append({"id": str(athlete.get("id") or ""), "name": _name_key(athlete.get("displayName")), "stats": stats})
        out[side] = players
    return out if set(out) == {"home", "away"} else None


def grade_due_entry(entry: dict, g: dict, lines: dict | None) -> dict:
    """One Due List entry, graded against what the player did in that match.

    `void` when he did not play: not in his club's matchday squad, or in it
    and never on the pitch. `actual` is his goals (or assists) when he played.
    Nothing is bet; `units` is the 0.25u tracking line when a price was
    staged, else None. An entry the feed cannot answer for (no
    squads yet, his side not on this fixture, a statistic missing) is left
    ungraded, `result: null`, and never guessed.
    """
    home, away = (g.get("home") or {}).get("abbr"), (g.get("away") or {}).get("abbr")
    team = entry.get("team")
    side = "home" if team == home else "away" if team == away else None
    line = entry.get("line") if isinstance(entry.get("line"), (int, float)) else 0.5
    market = str(entry.get("market") or "goals")
    price = entry.get("price")
    row = {
        "player": entry.get("player", ""), "team": team or "",
        "opp": (away if side == "home" else home if side == "away" else "") or "",
        "market": market, "line": line, "drought": entry.get("drought"),
        "price": price if isinstance(price, (int, float)) and not isinstance(price, bool) else None,
        "book": entry.get("book") or "", "heavyJuice": bool(entry.get("heavyJuice")),
        "actual": None, "result": None, "units": None,
    }
    if entry.get("lastSeason") is not None:
        row["lastSeason"] = entry.get("lastSeason")
    stat = DUE_STATS.get(market)
    if side is None or lines is None or stat is None:
        return row
    squad = lines.get(side) or []
    pid = str(entry.get("playerId") or "")
    found = next((p for p in squad if pid and p["id"] == pid), None)
    if found is None:
        name = _name_key(entry.get("player"))
        found = next((p for p in squad if name and p["name"] == name), None)
    if found is None:
        row["result"] = "void"
        return row
    appeared = _stat_value(found["stats"], "appearances")
    if appeared is None:
        return row
    if appeared <= 0:
        row["result"] = "void"
        return row
    value = _stat_value(found["stats"], stat)
    if value is None:
        return row
    row["actual"] = int(value)
    row["result"] = "push" if value == line else "win" if value > line else "loss"
    if row["price"] is not None:
        row["units"] = _profit(DUE_STAKE, row["price"], row["result"])
    return row


def due_tallies(rows: list) -> dict:
    """A day's Due List in W-L-P, with what is still ungraded. A void (the
    player did not play) is counted under `void`, apart from the record."""
    out = {"w": 0, "l": 0, "p": 0, "void": 0, "byMarket": {m: {"w": 0, "l": 0} for m in DUE_STATS}, "pending": 0,
           "stake": DUE_STAKE, "units": 0.0, "staked": 0}
    for r in rows:
        if not isinstance(r, dict):
            continue
        units = r.get("units")
        if isinstance(units, (int, float)) and not isinstance(units, bool) and r.get("result") in ("win", "loss", "push"):
            out["units"] = round(out["units"] + float(units), 4)
            out["staked"] += 1
        res = r.get("result")
        if res is None:
            out["pending"] += 1
            continue
        if res == "void":
            out["void"] += 1
            continue
        if res not in ("win", "loss", "push"):
            continue
        out[{"win": "w", "loss": "l", "push": "p"}[res]] += 1
        split = out["byMarket"].get(r.get("market"))
        if split is not None and res in ("win", "loss"):
            split["w" if res == "win" else "l"] += 1
    return out


#: The props card's markets as the board names them (build_board_json.
#: PROP_MARKET_KEYS) and the ESPN summary statistic each settles on. A tuple is
#: summed: a booking is any card, so a straight red is booked too. Tackles are
#: not in ESPN's summary; they come from the FPL logs (`load_fpl_logs`).
PROP_STATS = {
    "shots": ("totalShots",),
    "shots_on_target": ("shotsOnTarget",),
    "goals": ("totalGoals",),
    "assists": ("goalAssists",),
    "booked": ("yellowCards", "redCards"),
    "sent_off": ("redCards",),
    "goalie_saves": ("saves",),
}
FPL_PROP_STATS = {"tackles": "tackles"}


def _plain_key(name: object) -> str:
    """`_name_key` with accents folded: the props feed writes "Odegaard" for ESPN's "Ødegaard"."""
    text = unicodedata.normalize("NFKD", _name_key(name).replace("ø", "o").replace("æ", "ae").replace("ß", "ss"))
    return "".join(c for c in text if not unicodedata.combining(c))


def load_fpl_logs(path: Path | None) -> dict:
    """The props card's FPL per-match logs, keyed (date, team, player); empty if absent.

    Each row is one appearance (minutes above zero), as `providers/fpl_players`
    writes it. Read with the stdlib because this script is shipped without the lab.
    """
    out: dict = {}
    if path is None or not Path(path).is_file():
        return out
    try:
        with Path(path).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                key = (str(row.get("date") or "")[:10], _name_key(row.get("team")), _plain_key(row.get("player")))
                out[key] = row
    except (OSError, UnicodeError, csv.Error):
        return {}
    return out


def _payout(price: object, units: float) -> float | None:
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price == 0:
        return None
    return units * (price / 100.0 if price > 0 else 100.0 / abs(price))


def published_props(boards: list[dict], playing: dict) -> list[dict]:
    """Each prop row on a fixture in `playing`, as it was FIRST published (the same rule as the team pick)."""
    seen: dict = {}
    for board in boards:
        block = board.get("props")
        if not isinstance(block, dict):
            continue
        for row in block.get("rows") or []:
            if not isinstance(row, dict) or str(row.get("gameId")) not in playing:
                continue
            key = (str(row.get("gameId")), _plain_key(row.get("player")), row.get("market"), row.get("side"), row.get("line"))
            seen.setdefault(key, row)
    return list(seen.values())


def grade_prop(row: dict, g: dict, teams: dict, lines: dict | None, fpl: dict, day: date) -> dict:
    """One published prop, graded against what the player did.

    `void` when he was in his side's squad and never came on (the stake comes
    back). A player the feed does not name, a statistic it does not carry, or
    tackles with no FPL row are left `result: None` and never guessed: a name
    that fails to match is not proof he did not play.
    """
    out = {**row, "actual": None, "result": None, "profitUnits": None}
    home, away = (g.get("home") or {}).get("abbr"), (g.get("away") or {}).get("abbr")
    side = "home" if row.get("team") == home else "away" if row.get("team") == away else None
    market, line = str(row.get("market") or ""), row.get("line")
    if side is None or lines is None or not isinstance(line, (int, float)):
        return out
    want = _plain_key(row.get("player"))
    found = next((p for p in lines.get(side) or [] if _plain_key(p["name"]) == want), None)
    if found is None:
        return out
    appeared = _stat_value(found["stats"], "appearances")
    if appeared is None:
        return out
    if appeared <= 0:
        out.update(result="void", profitUnits=0.0)
        return out
    value: float | None = None
    if market in PROP_STATS:
        parts = [_stat_value(found["stats"], name) for name in PROP_STATS[market]]
        value = None if any(v is None for v in parts) else sum(parts)
    elif market in FPL_PROP_STATS:
        team_name = (teams.get(row.get("team")) or {}).get("name") or ""
        logged = fpl.get((day.isoformat(), _name_key(team_name), want))
        if logged is not None:
            try:
                value = float(logged.get(FPL_PROP_STATS[market]))
            except (TypeError, ValueError):
                value = None
    if value is None:
        return out
    over = str(row.get("side") or "over").lower() != "under"
    res = "push" if value == line else "win" if (value > line) == over else "loss"
    units = row.get("units") if isinstance(row.get("units"), (int, float)) else 0.0
    won = _payout(row.get("price"), float(units))
    out.update(actual=int(value), result=res,
               profitUnits=0.0 if res == "push" else (-float(units) if res == "loss" else won))
    return out


def prop_tallies(rows: list) -> dict:
    """A day's staked props in W-L-P and units. Leans and voids are in none of them."""
    out = {"w": 0, "l": 0, "p": 0, "units": 0.0, "ungraded": 0}
    for r in rows:
        if not isinstance(r, dict) or r.get("kind", "bet") != "bet":
            continue
        res = r.get("result")
        if res is None:
            out["ungraded"] += 1
            continue
        if res not in ("win", "loss", "push"):
            continue
        out[{"win": "w", "loss": "l", "push": "p"}[res]] += 1
        if isinstance(r.get("profitUnits"), (int, float)):
            out["units"] += r["profitUnits"]
    out["units"] = round(out["units"], 4)
    return out


def settle_day(sport: str, day: date, boards: list[dict], fpl_logs: dict | None = None) -> tuple[dict, bool]:
    """One day's results.json body, and whether anything on it is still to be read.

    Raises one of FETCH_ERRORS when that day's scoreboard cannot be fetched;
    the caller decides what that means for the page and for the season.
    """
    season = next((str(b.get("season") or "") for b in reversed(boards) if b.get("season")), "")
    base: dict = {"resultsDate": day.isoformat(), "teams": {}, "games": [], "season": season}
    playing, window = first_published(boards, day)
    if not playing:
        # Said plainly, because the old wording for this case claimed the
        # opposite: "The games were played but no final was available." No
        # fixture in the record kicked off, which the record alone establishes
        # -- so this needs no scoreboard and must not blame one.
        base.update(
            windowLabel=window,
            notice=f"No fixture in the published record kicked off on {day.isoformat()}, so there is nothing to settle.",
            summary={},
        )
        return base, False
    fin = finals(sport, day)
    games, picks, leans = [], {"w": 0, "l": 0, "p": 0}, {"w": 0, "l": 0, "p": 0}
    su, ats, tots = {"w": 0, "l": 0}, {"w": 0, "l": 0, "p": 0}, {"w": 0, "l": 0, "p": 0}
    teams_out: dict = {}
    ungraded = 0
    due_rows: list | None = None
    # Props are board-level, not per game: each published row, first price wins.
    published = published_props(boards, playing) if sport == "epl" else []
    props_by_game: dict = {}
    for p in published:
        props_by_game.setdefault(str(p.get("gameId")), []).append(p)
    prop_rows: list = []
    for gid, (g, teams) in playing.items():
        f = fin.get(gid)
        if not f:
            continue
        hf, af = f["home"], f["away"]
        pick = g.get("pick")
        # One extra request, only for a fixture whose pick or Due List needs
        # it, and never two for the same fixture.
        summary: dict = {}

        def payload(gid=gid, summary=summary):
            if "v" not in summary:
                summary["v"] = match_summary(sport, gid)
            return summary["v"]

        corners = None
        if str((pick or {}).get("market") or "").lower().startswith("corners"):
            corners = corners_from(payload())
        res = grade_pick(sport, pick, g, hf, af, teams, corners)
        kind = (pick or {}).get("kind", "bet")
        if pick and kind in ("bet", "lean") and res is None:
            # A published pick the record cannot answer for. Counted, because
            # a record that silently drops what it could not settle reports a
            # win rate for a subset it never names.
            ungraded += 1
        # `res` is "win"/"loss"/"push"/"void"/None; the tallies are keyed
        # "w"/"l"/"p". `if res in picks` tested the grade against the KEYS,
        # so it was never true and the tally never ran: every results.json
        # this script wrote carried picks 0-0-0. A lean is graded the same
        # way and tallied apart: it was recorded, never staked, and is never
        # in `picks`.
        if res in ("win", "loss", "push"):
            tally = leans if kind == "lean" else picks
            tally[{"win": "w", "loss": "l", "push": "p"}[res]] += 1
        row = {"id": g["id"], "home": {"abbr": g["home"]["abbr"], "final": hf}, "away": {"abbr": g["away"]["abbr"], "final": af}, "finish": f["finish"],
               "pick": {**pick, "result": res} if pick and res else None}
        if sport == "epl":
            row["home"]["projGoals"], row["away"]["projGoals"] = g["home"].get("projGoals"), g["away"].get("projGoals")
            hp, dp, ap_ = g["home"].get("winProb"), g.get("drawProb"), g["away"].get("winProb")
            row["projResult"] = max((("home", hp or 0), ("draw", dp or 0), ("away", ap_ or 0)), key=lambda x: x[1])[0]
            out = "home" if hf > af else "away" if hf < af else "draw"
            # The favoured side is the model's 1X2 favourite, draw included:
            # a draw is a loss unless the draw was favoured. A fixture the
            # model published no probabilities for has no favourite, and is
            # not counted as though it favoured the home side.
            if all(isinstance(x, (int, float)) for x in (hp, dp, ap_)):
                su["w" if out == row["projResult"] else "l"] += 1
            over_p = (g.get("total") or {}).get("overProb")
            if isinstance(over_p, (int, float)):
                tots["w" if (over_p > 0.5) == (hf + af > 2.5) else "l"] += 1
            row["markets"] = {"total": {"line": 2.5, "overProb": over_p}, "btts": {"yesProb": (g.get("btts") or {}).get("yesProb")}}
            if "drought" in g:
                due_rows = due_rows if due_rows is not None else []
                entries = [e for e in g.get("drought") or [] if isinstance(e, dict)]
                lines = player_lines(payload()) if entries else None
                due_rows.extend(grade_due_entry(e, g, lines) for e in entries)
        else:
            row["home"]["projPts"], row["away"]["projPts"] = g["home"].get("projPts"), g["away"].get("projPts")
            hp = g["home"].get("winProb")
            row["projWinner"] = g["home"]["abbr"] if (hp or 0.5) >= 0.5 else g["away"]["abbr"]
            winner = g["home"]["abbr"] if hf > af else g["away"]["abbr"]
            if isinstance(hp, (int, float)):
                su["w" if winner == row["projWinner"] else "l"] += 1
            sp, tt = g.get("spread") or {}, g.get("total") or {}
            row["markets"] = {"spread": {"line": sp.get("current"), "proj": sp.get("proj")}, "total": {"line": tt.get("current"), "proj": tt.get("proj")}}
            if isinstance(sp.get("proj"), (int, float)) and isinstance(sp.get("current"), (int, float)):
                model_home = sp["proj"] < sp["current"]
                adj = (hf - af) + sp["current"]
                ats["p" if adj == 0 else "w" if (adj > 0) == model_home else "l"] += 1
            if isinstance(tt.get("proj"), (int, float)) and isinstance(tt.get("current"), (int, float)):
                t = hf + af
                tots["p" if t == tt["current"] else "w" if (tt["proj"] > tt["current"]) == (t > tt["current"]) else "l"] += 1
        if sport == "epl" and gid in props_by_game:
            lines = player_lines(payload())
            prop_rows.extend(grade_prop(p, g, teams, lines, fpl_logs or {}, day) for p in props_by_game[gid])
        teams_out.update(teams)
        games.append(row)
    summary_out = {"picks": picks, "leans": leans, "ungraded": ungraded}
    if sport == "epl":
        # `result` is the key this file has always published; `straightUp`
        # is the same tally under the name every lab's season record uses.
        summary_out.update(result=su, straightUp=dict(su), totals={"w": tots["w"], "l": tots["l"]})
    else:
        summary_out.update(straightUp=su, ats=ats, totals=tots)
    base.update(windowLabel=window, notice=None if games else "The games were played but no final was available when this ran; the next build settles them.",
                summary=summary_out, teams=teams_out, games=games)
    waiting = len(games) < len(playing) or ungraded > 0
    # What the Track record, Game and All results pages read of this day:
    # each settled fixture's final beside the chances the board froze, and
    # every graded best bet at the card's stake. Built from the same rows
    # as the tallies above, so the pages and the strip cannot disagree.
    lines = published_lines(boards, playing)
    base["graded"] = {
        row["id"]: graded_entry(playing[row["id"]][0], row["home"]["final"], row["away"]["final"], row["finish"],
                                (row.get("pick") or {}).get("result") if row.get("pick") else None, lines)
        for row in games if row["id"] in playing
    }
    base["bets"] = bet_rows(day, games, playing, prop_rows)
    if due_rows is not None:
        tallies = due_tallies(due_rows)
        due = {"rows": due_rows}
        if tallies["w"] + tallies["l"] + tallies["p"]:
            due["summary"] = {k: tallies[k] for k in ("w", "l", "p")}
        base["dueList"] = due
        waiting = waiting or tallies["pending"] > 0
    if published:
        # A row whose fixture has no final yet is not here; a later build settles it.
        tallies = prop_tallies(prop_rows)
        base["props"] = {"status": "ok", "note": "", "rows": prop_rows, "summary": tallies}
        waiting = waiting or tallies["ungraded"] > 0 or len(prop_rows) < len(published)
    return base, waiting


# ---------- the season ----------

#: Where each settled day is kept, inside the history the publish workflow
#: restores and uploads (dist/data/history), so the season reads an old day
#: once instead of re-fetching its finals every morning.
SETTLED_DIR = "settled"

SEASON_KEYS = ("straightUp", "picks", "leans", "totals")

#: How long a day with something still unread (a fixture with no final, an
#: ungraded pick, a Due List entry with no stat) is settled again each run
#: rather than kept. The NHL lab's DUE_LIST_PATIENCE_DAYS, for the same reason:
#: a postponed match must not hold a day out of the cache forever.
PATIENCE_DAYS = 14


def night_record(results: dict) -> dict:
    """What the season keeps of one settled day.

    `graded` (one entry per settled fixture: the final, the pick's grade and
    the frozen chances, for the Track record and Game pages) and `bets`
    (every graded best bet at the stake the card carried, for All results)
    ride along since 2026-10-26. A night kept before then lacks them and is
    settled once more by `season_record`, which is the only reason a kept
    night is ever re-read from the scoreboard.
    """
    night = {"games": len(results.get("games") or []), "summary": results.get("summary") or {}}
    due = results.get("dueList")
    if isinstance(due, dict):
        night["dueList"] = due_tallies(due.get("rows") or [])
    props = results.get("props")
    if isinstance(props, dict):
        night["props"] = prop_tallies(props.get("rows") or [])
    if isinstance(results.get("graded"), dict):
        night["graded"] = results["graded"]
    if isinstance(results.get("bets"), list):
        night["bets"] = results["bets"]
    return night


def _profit(units: float, price: object, result: str) -> float | None:
    """Flat-stake profit in units: the payout on a win, the stake on a loss, nothing on a push."""
    if result == "win":
        won = _payout(price, units)
        return None if won is None else round(won, 4)
    if result == "loss":
        return round(-units, 4)
    return 0.0


def _no_vig_1x2(prices: dict | None) -> list[float] | None:
    """The market's three chances with the margin scaled out, from the frozen 1X2 prices."""
    if not isinstance(prices, dict):
        return None
    implied = []
    for side in ("home", "draw", "away"):
        p = prices.get(side)
        if not isinstance(p, (int, float)) or isinstance(p, bool) or p == 0:
            return None
        implied.append(100.0 / (p + 100.0) if p > 0 else abs(p) / (abs(p) + 100.0))
    total = sum(implied)
    return [round(x / total, 4) for x in implied] if total > 0 else None


def _series_ends(board_lines: dict | None, gid: str, key: str) -> list | None:
    """The first and last value of one frozen line series, when it moved at all."""
    if not isinstance(board_lines, dict):
        return None
    series = (board_lines.get(gid) or {}).get(key) if isinstance(board_lines.get(gid), dict) else None
    if not isinstance(series, list) or len(series) < 2:
        return None
    first, last = series[0], series[-1]
    if not (isinstance(first, dict) and isinstance(last, dict)):
        return None
    if not all(isinstance(x.get("v"), (int, float)) for x in (first, last)):
        return None
    return [first["v"], last["v"]]


def published_lines(boards: list[dict], playing: dict) -> dict:
    """Each playing fixture's longest frozen line series, from whichever board carried it."""
    out: dict = {}
    for board in boards:
        lines = board.get("lineHistory")
        if not isinstance(lines, dict):
            continue
        for gid, series in lines.items():
            if str(gid) not in playing or not isinstance(series, dict):
                continue
            kept = out.setdefault(str(gid), {})
            for key, pts in series.items():
                if isinstance(pts, list) and len(pts) > len(kept.get(key) or []):
                    kept[key] = pts
    return out


def graded_entry(g: dict, hf: int, af: int, finish: str, res: str | None, lines: dict | None) -> dict:
    """One fixture as the Track record and Game pages read it: the final,
    the pick's grade, and the chances the board froze, never re-priced."""
    pick = g.get("pick") if isinstance(g.get("pick"), dict) else None
    home, away = g.get("home") or {}, g.get("away") or {}
    probs = [home.get("winProb"), g.get("drawProb"), away.get("winProb")]
    entry: dict = {
        "home": hf, "away": af, "finish": finish, "pickResult": res,
        "homeAbbr": home.get("abbr"), "awayAbbr": away.get("abbr"), "kickoff": g.get("kickoff"),
        "probs": probs if all(isinstance(p, (int, float)) for p in probs) else None,
        "market": _no_vig_1x2(g.get("matchResult")),
        "overProb": (g.get("total") or {}).get("overProb"),
        "bttsProb": (g.get("btts") or {}).get("yesProb"),
    }
    if pick:
        entry["pick"] = {k: pick.get(k) for k in ("kind", "market", "label", "side", "line", "price", "units")}
        entry["pick"]["result"] = res
    ml = _series_ends(lines, str(g.get("id")), "ml_home")
    if ml:
        entry["mlHome"] = ml
    return entry


def bet_rows(day: date, results_games: list[dict], playing: dict, prop_rows: list[dict]) -> list[dict]:
    """Every graded best bet of the day at the stake the card carried: the
    rows All results sums. A lean, a void and an ungraded pick are not bets.
    A team pick frozen without a stake counts at one unit and says so."""
    rows: list[dict] = []
    for row in results_games:
        pick = row.get("pick") if isinstance(row.get("pick"), dict) else None
        if not pick or pick.get("kind", "bet") != "bet" or pick.get("result") not in ("win", "loss", "push"):
            continue
        g = (playing.get(str(row.get("id"))) or (None, None))[0] or {}
        units = pick.get("units")
        assumed = not isinstance(units, (int, float)) or isinstance(units, bool)
        staked = 1.0 if assumed else float(units)
        home, away = (row.get("home") or {}).get("abbr"), (row.get("away") or {}).get("abbr")
        side = pick.get("side")
        rows.append({
            "date": day.isoformat(), "group": "team", "market": pick.get("market"), "label": pick.get("label"),
            "team": home if side == "home" else away if side == "away" else None, "teams": [home, away],
            "side": side, "line": pick.get("line"), "price": pick.get("price"), "result": pick["result"],
            "staked": staked, "units": _profit(staked, pick.get("price"), pick["result"]),
            **({"stakeAssumed": True} if assumed else {}), "gameId": str(row.get("id")),
            "kickoff": g.get("kickoff"),
        })
    for p in prop_rows:
        if p.get("result") not in ("win", "loss", "push"):
            continue
        units = p.get("units")
        if not isinstance(units, (int, float)) or isinstance(units, bool):
            continue
        rows.append({
            "date": day.isoformat(), "group": "props", "market": p.get("market"), "propType": p.get("market"),
            "label": f"{p.get('player', '')} {p.get('side', '')} {p.get('line', '')}".strip(),
            "player": p.get("player"), "team": p.get("team"), "opp": p.get("opp"),
            "side": p.get("side"), "line": p.get("line"), "price": p.get("price"), "result": p["result"],
            "staked": float(units),
            "units": p.get("profitUnits") if isinstance(p.get("profitUnits"), (int, float)) else _profit(float(units), p.get("price"), p["result"]),
            "gameId": str(p.get("gameId")),
        })
    return rows


def _kept_night(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        night = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return night if isinstance(night, dict) and isinstance(night.get("summary"), dict) else None


def _games_settled(night: dict) -> int:
    """How much a night record holds: the matches it graded (the `graded`
    entries where kept, else the `games` count)."""
    graded = night.get("graded")
    if isinstance(graded, dict) and graded:
        return len(graded)
    games = night.get("games")
    return len(games) if isinstance(games, list) else int(games or 0)


def kickoff_days(boards: list[dict], through: date) -> list[date]:
    """Every date a published fixture kicked off on, up to and including `through`."""
    days: set[date] = set()
    for board in boards:
        for game in board.get("games") or []:
            try:
                day = date.fromisoformat(str(game.get("kickoff") or "")[:10])
            except ValueError:
                continue
            if day <= through:
                days.add(day)
    return sorted(days)


def season_record(sport: str, day: date, hist: Path, boards: list[dict],
                  latest: dict | None, latest_waiting: bool, fpl_logs: dict | None = None) -> dict:
    """The season so far: every day a published fixture kicked off, settled and summed.

    `day` is the day this run settled and `latest` its results (None when its
    scoreboard could not be read). Every earlier day is read from
    `history/settled/<day>.json` when one is kept, and otherwise settled now;
    it is kept once it is at least two days old and nothing on it is still
    unread, or once it is PATIENCE_DAYS old. A day whose finals cannot be
    fetched, or whose fixtures have no final yet, is not counted as 0–0: it
    is left out and counted in `missingNights`, and the next run tries again.

    The four tallies are absent until a day has settled; so is `dueList`
    (`{w, l, p, void, nights, byMarket}`), which sums the graded Due List entries
    of every settled day whose board carried the list, with the 0.25u tracking
    line (`stake`, `units`, `staked`, `returnPct`). Nothing is bet, it is never
    a stake, and none of it is in `picks`; nor is a lean.
    """
    tally = {key: {"w": 0, "l": 0} if key == "straightUp" else {"w": 0, "l": 0, "p": 0} for key in SEASON_KEYS}
    due = {"w": 0, "l": 0, "p": 0, "void": 0, "nights": 0, "byMarket": {m: {"w": 0, "l": 0} for m in DUE_STATS},
           "stake": DUE_STAKE, "units": 0.0, "staked": 0}
    props = {"w": 0, "l": 0, "p": 0, "units": 0.0, "nights": 0}
    kept = hist / SETTLED_DIR
    nights, missing, first, last = 0, 0, None, None
    for d in kickoff_days(boards, day):
        cached = kept / f"{d.isoformat()}.json"
        waiting = False
        if d == day:
            if latest is None:
                missing += 1
                continue
            night, waiting = night_record(latest), latest_waiting
        else:
            night = _kept_night(cached)
            # A night kept before the pages' rows existed (no `bets`) is
            # settled once more so the Track record and All results reach
            # back to the first board; if its scoreboard will not answer
            # today, the kept tallies stand and the next run tries again.
            stale = night is not None and "bets" not in night
            if night is None or stale:
                try:
                    settled, waiting = settle_day(sport, d, boards, fpl_logs)
                except (*FETCH_ERRORS, KeyError, TypeError):
                    if night is None:
                        missing += 1
                        continue
                    waiting = False
                else:
                    fresh = night_record(settled)
                    if night is not None and _games_settled(fresh) < _games_settled(night):
                        # A scoreboard that answers with less than the kept night
                        # holds (an outage serving no finals for an old day) does
                        # not replace it: the kept tallies stand, and the next
                        # run tries again.
                        waiting = False
                    else:
                        night = fresh
                        patient = d > day - timedelta(days=PATIENCE_DAYS)
                        if d <= day - timedelta(days=1) and not (waiting and patient):
                            kept.mkdir(parents=True, exist_ok=True)
                            cached.write_text(json.dumps({"resultsDate": d.isoformat(), **night}, indent=1), encoding="utf-8")
                        waiting = waiting and patient
        write_graded(hist, d, night)
        night_due = night.get("dueList") if isinstance(night.get("dueList"), dict) else None
        if night_due and sum(int(night_due.get(k) or 0) for k in ("w", "l", "p", "void")):
            due["nights"] += 1
            for k in ("w", "l", "p", "void"):
                due[k] += int(night_due.get(k) or 0)
            # A night settled before 2026-10-31 carries no units: it adds
            # nothing to them and is not counted as staked.
            due["units"] = round(due["units"] + float(night_due.get("units") or 0.0), 4)
            due["staked"] += int(night_due.get("staked") or 0)
            for market, split in (night_due.get("byMarket") or {}).items():
                if market in due["byMarket"] and isinstance(split, dict):
                    for k in ("w", "l"):
                        due["byMarket"][market][k] += int(split.get(k) or 0)
        night_props = night.get("props") if isinstance(night.get("props"), dict) else None
        if night_props and sum(int(night_props.get(k) or 0) for k in ("w", "l", "p")):
            props["nights"] += 1
            for k in ("w", "l", "p"):
                props[k] += int(night_props.get(k) or 0)
            props["units"] = round(props["units"] + float(night_props.get("units") or 0.0), 4)
        if not night["games"]:
            # Fixtures kicked off and none has a final yet: not settled, and
            # said so, rather than a day that happened to go 0–0.
            if waiting:
                missing += 1
            continue
        nights += 1
        first = first or d.isoformat()
        last = d.isoformat()
        summary = night["summary"]
        for key in SEASON_KEYS:
            source = summary.get(key)
            if source is None and key == "straightUp":
                source = summary.get("result")
            for k, v in (source or {}).items():
                if k in tally[key]:
                    tally[key][k] += int(v)
    span = {"nights": nights, "firstDate": first, "lastDate": last, "missingNights": missing}
    season = {**tally, **span} if nights else dict(span)
    if due["nights"]:
        if due["staked"]:
            due["returnPct"] = round(100 * due["units"] / (DUE_STAKE * due["staked"]), 1)
        season["dueList"] = due
    if props["nights"]:
        season["props"] = props
    return season


GRADED_DIR = "graded"


def write_graded(hist: Path, d: date, night: dict) -> None:
    """history/graded/<day>.json, `{id: {home, away, finish, pickResult}}`:
    the final beside each frozen board, which the Game page reads for a past
    game. Written whenever the night carries finals; nothing on a night that
    does not, so an old file is never emptied by a day the feed missed."""
    graded = night.get("graded") if isinstance(night, dict) else None
    if not isinstance(graded, dict) or not graded:
        return
    out = {gid: {k: e.get(k) for k in ("home", "away", "finish", "pickResult")}
           for gid, e in graded.items() if isinstance(e, dict)}
    path = hist / GRADED_DIR / f"{d.isoformat()}.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        current = None
    if current == out:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")


def write_season(data: Path, results: dict, season: dict) -> None:
    """The season into results.json (`seasonRecord`) and onto the board's `record`.

    Nothing is written for a tally nobody has made: before a day has settled
    there is no `seasonRecord` and the board's record keeps only the keys it
    already carried, so the page shows a dash and "Not tallied yet", never 0–0.
    The props' season line (`record.props`) and the Due List's are written
    only once a night that carried them has settled, for the same reason.
    """
    if season.get("nights"):
        span = {k: season[k] for k in ("nights", "firstDate", "lastDate", "missingNights")}
        results["seasonRecord"] = {**{k: season[k] for k in SEASON_KEYS}, **span, "season": span,
                                   **({"dueList": season["dueList"]} if "dueList" in season else {})}
    if "dueList" in season and isinstance(results.get("dueList"), dict):
        results["dueList"]["season"] = season["dueList"]
    if "props" in season and isinstance(results.get("props"), dict):
        results["props"]["season"] = season["props"]
    board_path = data / "board.json"
    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    if not isinstance(board, dict):
        return
    record = board.get("record") if isinstance(board.get("record"), dict) else {}
    if season.get("nights"):
        record.update({k: season[k] for k in SEASON_KEYS})
        record["season"] = {k: v for k, v in season.items() if k != "dueList"}
    if "dueList" in season:
        # The 0.25u tracking line rides along, as on the NHL board.
        record["dueList"] = {k: season["dueList"][k] for k in ("w", "l", "p", "nights", "stake", "units", "staked", "returnPct")
                             if k in season["dueList"]}
    if "props" in season:
        # The board's "Props best bets · season" line, as the NHL board
        # carries it: the staked props' W-L-P, units and nights settled.
        record["props"] = {k: season["props"][k] for k in ("w", "l", "p", "units", "nights")}
    board["record"] = record
    board_path.write_text(json.dumps(board, indent=1, ensure_ascii=False), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="dist/data")
    ap.add_argument("--sport", required=True, choices=list(ESPN))
    ap.add_argument("--date", default="")
    ap.add_argument("--fpl-logs", default="", help="FPL per-match logs (tackles), from the props card; optional")
    args = ap.parse_args(argv)
    fpl = load_fpl_logs(Path(args.fpl_logs)) if args.fpl_logs else {}
    data = Path(args.data)
    day = date.fromisoformat(args.date) if args.date else (datetime.now(timezone.utc) - timedelta(days=1)).date()
    boards = frozen_boards(data / "history")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    base = {"generatedAt": now, "resultsDate": day.isoformat(), "teams": {}, "games": []}
    if not boards:
        base.update(season="", notice="No board has been published yet, so there is nothing to settle.", summary={})
        (data / "results.json").write_text(json.dumps(base, indent=1), encoding="utf-8")
        print("nothing to settle")
        return 0
    latest: dict | None
    try:
        latest, waiting = settle_day(args.sport, day, boards, fpl)
    except FETCH_ERRORS as exc:
        # Yesterday's settlement is not today's board. This step runs after the
        # board is built, and an unhandled raise here took the whole publish
        # down with it -- the 403 above did exactly that on 2026-09-23, so the
        # site served nothing rather than serving a board with one section
        # unavailable.
        #
        # The failure is written into results.json instead of swallowed,
        # because a settlement that quietly stops is indistinguishable from a
        # day with no games, and this page's whole claim is that the record is
        # settled from what was published.
        season = next((str(b.get("season") or "") for b in reversed(boards) if b.get("season")), "")
        base.update(
            season=season,
            notice=f"Yesterday's results could not be settled: the scoreboard feed answered {type(exc).__name__} ({exc}). The board above is unaffected; settlement is retried on the next build.",
            summary={},
        )
        latest, waiting = None, False
        results = base
        print(f"settlement skipped: {type(exc).__name__}: {exc}")
    else:
        results = {**base, **latest}
    try:
        season_so_far = season_record(args.sport, day, data / "history", boards, latest, waiting, fpl)
    except Exception as exc:  # the season line must never take the day's results or the deploy down
        print(f"the season record could not be summed: {type(exc).__name__}: {exc}")
    else:
        write_season(data, results, season_so_far)
    (data / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    if latest is not None:
        s = results.get("summary") or {}
        picks = s.get("picks") or {"w": 0, "l": 0, "p": 0}
        print(
            f"settled {len(results['games'])} fixture(s) that kicked off on {day}: "
            f"picks {picks['w']}-{picks['l']}-{picks['p']}, {s.get('ungraded', 0)} ungraded. "
            "No bet was placed."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
