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
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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


def fetch(url, timeout: int = 30):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.load(r)


def corner_counts(sport: str, event_id: str) -> dict | None:
    """Corners won by each side, or None if the feed does not plainly say.

    Never raises, and never substitutes a zero. A missing statistic read as
    zero would settle `Under 10.5 corners` as a win every time the feed was
    down, which is a fabricated result in the direction of the card. Both
    sides must be present or the pick stays ungraded and is counted as such.
    """
    template = SUMMARY.get(sport)
    if not template:
        return None
    try:
        payload = fetch(template.format(e=event_id), timeout=15)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="dist/data")
    ap.add_argument("--sport", required=True, choices=list(ESPN))
    ap.add_argument("--date", default="")
    args = ap.parse_args(argv)
    data = Path(args.data)
    day = date.fromisoformat(args.date) if args.date else (datetime.now(timezone.utc) - timedelta(days=1)).date()
    boards = frozen_boards(data / "history")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    base = {"generatedAt": now, "resultsDate": day.isoformat(), "teams": {}, "games": []}
    season = next((str(b.get("season") or "") for b in reversed(boards) if b.get("season")), "")
    if not boards:
        base.update(season="", notice="No board has been published yet, so there is nothing to settle.", summary={})
        (data / "results.json").write_text(json.dumps(base, indent=1), encoding="utf-8")
        print("nothing to settle")
        return 0
    playing, window = first_published(boards, day)
    if not playing:
        # Said plainly, because the old wording for this case claimed the
        # opposite: "The games were played but no final was available." No
        # fixture in the record kicked off, which the record alone establishes
        # -- so this needs no scoreboard and must not blame one.
        base.update(
            season=season, windowLabel=window,
            notice=f"No fixture in the published record kicked off on {day.isoformat()}, so there is nothing to settle.",
            summary={},
        )
        (data / "results.json").write_text(json.dumps(base, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"no published fixture kicked off on {day}. No bet was placed.")
        return 0
    try:
        fin = finals(args.sport, day)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
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
        base.update(
            season=season,
            notice=f"Yesterday's results could not be settled: the scoreboard feed answered {type(exc).__name__} ({exc}). The board above is unaffected; settlement is retried on the next build.",
            summary={},
        )
        (data / "results.json").write_text(json.dumps(base, indent=1), encoding="utf-8")
        print(f"settlement skipped: {type(exc).__name__}: {exc}")
        return 0
    games, picks, su, ats, tots = [], {"w": 0, "l": 0, "p": 0}, {"w": 0, "l": 0}, {"w": 0, "l": 0, "p": 0}, {"w": 0, "l": 0, "p": 0}
    teams_out: dict = {}
    ungraded = 0
    for gid, (g, teams) in playing.items():
        f = fin.get(gid)
        if not f:
            continue
        hf, af = f["home"], f["away"]
        pick = g.get("pick")
        # One extra request, and only for a fixture whose pick needs it.
        corners = None
        if str((pick or {}).get("market") or "").lower().startswith("corners"):
            corners = corner_counts(args.sport, gid)
        res = grade_pick(args.sport, pick, g, hf, af, teams, corners)
        if pick and pick.get("kind", "bet") in ("bet", "lean") and res is None:
            # A published pick the record cannot answer for. Counted, because
            # a record that silently drops what it could not settle reports a
            # win rate for a subset it never names.
            ungraded += 1
        # `res` is "win"/"loss"/"push"/"void"/None; `picks` is keyed
        # "w"/"l"/"p". `if res in picks` tested the grade against the KEYS,
        # so it was never true and the tally never ran: every results.json
        # this script has written carries picks 0-0-0, and the public
        # Results page prints "Model picks 0–0–0" in its headline strip on
        # the same screen that prints Win beside each individual pick.
        # The mapping dict on the next line shows what the guard meant.
        if res in ("win", "loss", "push"):
            picks[{"win": "w", "loss": "l", "push": "p"}[res]] += 1
        row = {"id": g["id"], "home": {"abbr": g["home"]["abbr"], "final": hf}, "away": {"abbr": g["away"]["abbr"], "final": af}, "finish": f["finish"],
               "pick": {**pick, "result": res} if pick and res else None}
        if args.sport == "epl":
            row["home"]["projGoals"], row["away"]["projGoals"] = g["home"].get("projGoals"), g["away"].get("projGoals")
            hp, dp, ap_ = g["home"].get("winProb"), g.get("drawProb"), g["away"].get("winProb")
            row["projResult"] = max((("home", hp or 0), ("draw", dp or 0), ("away", ap_ or 0)), key=lambda x: x[1])[0]
            out = "home" if hf > af else "away" if hf < af else "draw"
            su["w" if out == row["projResult"] else "l"] += 1
            over_p = (g.get("total") or {}).get("overProb")
            if isinstance(over_p, (int, float)):
                tots["w" if (over_p > 0.5) == (hf + af > 2.5) else "l"] += 1
            row["markets"] = {"total": {"line": 2.5, "overProb": over_p}, "btts": {"yesProb": (g.get("btts") or {}).get("yesProb")}}
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
        teams_out.update(teams)
        games.append(row)
    summary = {"picks": picks, "ungraded": ungraded}
    if args.sport == "epl":
        summary.update(result=su, totals={"w": tots["w"], "l": tots["l"]})
    else:
        summary.update(straightUp=su, ats=ats, totals=tots)
    base.update(season=season, windowLabel=window, notice=None if games else "The games were played but no final was available when this ran; the next build settles them.",
                summary=summary, teams=teams_out, games=games)
    (data / "results.json").write_text(json.dumps(base, indent=1, ensure_ascii=False), encoding="utf-8")
    print(
        f"settled {len(games)} of {len(playing)} fixture(s) that kicked off on {day}: "
        f"picks {picks['w']}-{picks['l']}-{picks['p']}, {ungraded} ungraded. "
        "No bet was placed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
