#!/usr/bin/env python3
"""Settle yesterday's frozen board into results.json. Sport-agnostic on the outside;
the finals come from ESPN's public scoreboard for the sport named in site.json.

    python web/settle_results.py --data dist/data --sport epl|cbb [--date YYYY-MM-DD]

Reads history/<date>.json (the board as published), fetches finals, grades each
game's projection and pick, writes results.json. The board is never edited.
The NHL lab settles inside build_site_json.py and does not use this file.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UA = "maverick-hightower-site/1.0 (+https://maverickhightower.com)"
ESPN = {
    "epl": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates={d}&limit=100",
    "cbb": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={d}&groups=50&limit=400",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return json.load(r)


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


def grade_pick(sport, pick, g, hf, af, teams=None):
    if not pick or pick.get("kind", "bet") not in ("bet", "lean"):
        return None
    m, label = (pick.get("market") or "").lower(), (pick.get("label") or "").lower()
    tot = hf + af
    teams = teams or {}
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
        return None  # corners / double chance need feeds the site does not have; left ungraded
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="dist/data")
    ap.add_argument("--sport", required=True, choices=list(ESPN))
    ap.add_argument("--date", default="")
    args = ap.parse_args(argv)
    data = Path(args.data)
    day = date.fromisoformat(args.date) if args.date else (datetime.now(timezone.utc) - timedelta(days=1)).date()
    hist = data / "history"
    frozen = sorted(hist.glob(f"{day.isoformat()}*.json"))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    base = {"generatedAt": now, "resultsDate": day.isoformat(), "teams": {}, "games": []}
    if not frozen:
        base.update(season="", notice=f"No board was published for {day.isoformat()}, so there is nothing to settle.", summary={})
        (data / "results.json").write_text(json.dumps(base, indent=1), encoding="utf-8")
        print("nothing to settle")
        return 0
    board = json.loads(frozen[0].read_text(encoding="utf-8"))
    fin = finals(args.sport, day)
    games, picks, su, ats, tots = [], {"w": 0, "l": 0, "p": 0}, {"w": 0, "l": 0}, {"w": 0, "l": 0, "p": 0}, {"w": 0, "l": 0, "p": 0}
    for g in board.get("games", []):
        f = fin.get(str(g.get("id")))
        if not f:
            continue
        hf, af = f["home"], f["away"]
        pick = g.get("pick")
        res = grade_pick(args.sport, pick, g, hf, af, board.get("teams") or {})
        if res in picks:
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
        games.append(row)
    summary = {"picks": picks}
    if args.sport == "epl":
        summary.update(result=su, totals={"w": tots["w"], "l": tots["l"]})
    else:
        summary.update(straightUp=su, ats=ats, totals=tots)
    base.update(season=board.get("season", ""), windowLabel=board.get("windowLabel"), notice=None if games else "The games were played but no final was available when this ran; the next build settles them.",
                summary=summary, teams=board.get("teams", {}), games=games)
    (data / "results.json").write_text(json.dumps(base, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"settled {len(games)} of {len(board.get('games', []))} games for {day}. No bet was placed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
