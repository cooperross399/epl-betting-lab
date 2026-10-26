#!/usr/bin/env python3
"""The EPL site's extra feeds, built after the board and the day's settlement:

    python web/build_site_pages.py --lab . --out dist/data

* `record.json`   Calibration of the published match-result chances against
                  finals, the model against the no-vig 1X2 market (Brier),
                  the over-2.5 and both-teams-to-score chances the same way,
                  and whether the 1X2 line moved toward our picks. Read by
                  Record.dc.html and Game.dc.html.
* `tracker.json`  Every graded best bet at the stake the card carried, summed
                  by group, market, prop type, team, player, price band and
                  month. Read by Tracker.dc.html.
* `season.json`   The table as it stands, from the season's played fixtures,
                  and where each club projects to finish: every remaining
                  fixture played out thousands of times on the board's own
                  goal expectations. Read by Season.dc.html.

Everything here reads what `web/settle_results.py` kept under
`history/settled/<day>.json` (`graded` and `bets`) and what the board's own
fit says today. Nothing fetches odds, spends a credit or places a bet; the
season feed asks ESPN's public scoreboard for the fixtures and finals, the
same feed the board is built from.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: The 1X2 favourite's chance, filed by bucket. A three-way favourite starts
#: lower than a two-way one, so the buckets start at 30%.
RECORD_BUCKETS = ((0.30, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.70), (0.70, 1.01))

#: Over 2.5 and both-teams-to-score are filed in 5-point buckets, merged
#: upward until each holds at least this many games.
MARKET_BUCKET_WIDTH = 0.05
MARKET_BUCKET_MIN_GAMES = 10

#: A three-way forecast that says 1/3, 1/3, 1/3 scores this; lower is better.
BRIER_BASELINE = round(2.0 / 3.0, 4)

#: A line that moved less than this in implied probability is "flat".
FLAT_MOVE = 0.005

TRACKER_GROUPS = {"team": "Team picks", "props": "Player props"}

PRICE_BANDS = (
    ("−200 and shorter", None, -200), ("−199 to −111", -199, -111), ("−110 to +110", -110, 110),
    ("+111 to +199", 111, 199), ("+200 and longer", 200, None),
)

#: A team pick frozen before its stake was recorded counts at this many units, and is marked.
TEAM_PICK_DEFAULT_UNITS = 1.0

#: The season's months, for the fixture list the table and the simulation read.
SEASON_START = date(2026, 8, 1)
SEASON_END = date(2027, 5, 31)
SIMULATIONS = 5000


def _board_module():
    """`web/build_board_json.py`, loaded beside this file: the fixture feed, the
    club table and the board's fit, so the season reads the same numbers."""
    spec = importlib.util.spec_from_file_location("build_board_json_for_pages", HERE / "build_board_json.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wilson(wins: int, n: int, z: float = 1.96) -> list[float]:
    if n <= 0:
        return [0.0, 1.0]
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def _implied(price: object) -> float | None:
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price == 0:
        return None
    return 100.0 / (price + 100.0) if price > 0 else abs(price) / (abs(price) + 100.0)


def _num(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# ---------- the settled record ----------

def settled_nights(hist: Path) -> list[tuple[str, dict]]:
    """Every kept night, oldest first: (day, night)."""
    out = []
    for p in sorted((hist / "settled").glob("????-??-??.json")):
        try:
            night = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(night, dict):
            out.append((p.stem, night))
    return out


def _buckets(rows: list[tuple[float, bool]], edges) -> list[dict]:
    out = []
    for low, high in edges:
        hit = [(p, won) for p, won in rows if low <= p < high]
        if not hit:
            out.append({"low": low, "high": min(high, 1.0), "games": 0, "predicted": None, "actual": None, "interval": None})
            continue
        wins = sum(1 for _, won in hit if won)
        out.append({"low": low, "high": min(high, 1.0), "games": len(hit),
                    "predicted": round(sum(p for p, _ in hit) / len(hit), 3),
                    "actual": round(wins / len(hit), 3), "interval": _wilson(wins, len(hit))})
    return out


def _market_buckets(rows: list[tuple[float, bool]]) -> list[dict]:
    """5-point buckets over the chance given, merged upward until each holds enough games."""
    if not rows:
        return []
    lo = math.floor(min(p for p, _ in rows) / MARKET_BUCKET_WIDTH) * MARKET_BUCKET_WIDTH
    edges, start = [], lo
    while start < 1.0:
        edges.append((round(start, 2), round(start + MARKET_BUCKET_WIDTH, 2)))
        start += MARKET_BUCKET_WIDTH
    raw = [b for b in _buckets(rows, edges) if b["games"]]
    merged: list[dict] = []
    for b in raw:
        if merged and merged[-1]["games"] < MARKET_BUCKET_MIN_GAMES:
            last = merged[-1]
            n = last["games"] + b["games"]
            wins = round(last["actual"] * last["games"]) + round(b["actual"] * b["games"])
            merged[-1] = {"low": last["low"], "high": b["high"], "games": n,
                          "predicted": round((last["predicted"] * last["games"] + b["predicted"] * b["games"]) / n, 3),
                          "actual": round(wins / n, 3), "interval": _wilson(wins, n)}
        else:
            merged.append(dict(b))
    if len(merged) > 1 and merged[-1]["games"] < MARKET_BUCKET_MIN_GAMES:
        last, prev = merged.pop(), merged.pop()
        n = last["games"] + prev["games"]
        wins = round(last["actual"] * last["games"]) + round(prev["actual"] * prev["games"])
        merged.append({"low": prev["low"], "high": last["high"], "games": n,
                       "predicted": round((last["predicted"] * last["games"] + prev["predicted"] * prev["games"]) / n, 3),
                       "actual": round(wins / n, 3), "interval": _wilson(wins, n)})
    return merged


def _outcome(entry: dict) -> str | None:
    hf, af = entry.get("home"), entry.get("away")
    if not (_num(hf) and _num(af)):
        return None
    return "home" if hf > af else "away" if hf < af else "draw"


def track_record(hist: Path, now: str) -> dict:
    """record.json from the kept nights' `graded` entries."""
    nights = settled_nights(hist)
    fav_rows: list[tuple[float, bool]] = []
    brier_model: list[float] = []
    brier_market: list[float] = []
    over_rows: list[tuple[float, bool]] = []
    btts_rows: list[tuple[float, bool]] = []
    movement = {"toward": 0, "against": 0, "flat": 0, "picks": 0}
    games = 0
    counted_nights = 0
    due = {"w": 0, "l": 0, "p": 0}
    for _day, night in nights:
        graded = night.get("graded")
        if not isinstance(graded, dict) or not graded:
            continue
        night_games = 0
        for entry in graded.values():
            if not isinstance(entry, dict):
                continue
            out = _outcome(entry)
            if out is None:
                continue
            probs = entry.get("probs")
            if isinstance(probs, list) and len(probs) == 3 and all(_num(p) for p in probs):
                night_games += 1
                sides = ("home", "draw", "away")
                fav = max(range(3), key=lambda i: probs[i])
                fav_rows.append((float(probs[fav]), out == sides[fav]))
                truth = [1.0 if out == s else 0.0 for s in sides]
                market = entry.get("market")
                if isinstance(market, list) and len(market) == 3 and all(_num(m) for m in market):
                    brier_model.append(sum((p - t) ** 2 for p, t in zip(probs, truth)))
                    brier_market.append(sum((m - t) ** 2 for m, t in zip(market, truth)))
            hf, af = entry["home"], entry["away"]
            if _num(entry.get("overProb")):
                over_rows.append((float(entry["overProb"]), hf + af > 2.5))
            if _num(entry.get("bttsProb")):
                btts_rows.append((float(entry["bttsProb"]), hf > 0 and af > 0))
            pick, ml = entry.get("pick"), entry.get("mlHome")
            if isinstance(pick, dict) and str(pick.get("market") or "").lower() == "1x2" and pick.get("side") in ("home", "away") \
                    and isinstance(ml, list) and len(ml) == 2:
                first, last = _implied(ml[0]), _implied(ml[1])
                if first is not None and last is not None:
                    change = last - first
                    movement["picks"] += 1
                    if abs(change) < FLAT_MOVE:
                        movement["flat"] += 1
                    elif (change > 0) == (pick["side"] == "home"):
                        movement["toward"] += 1
                    else:
                        movement["against"] += 1
        if night_games:
            counted_nights += 1
            games += night_games
        night_due = night.get("dueList")
        if isinstance(night_due, dict):
            for k in ("w", "l", "p"):
                due[k] += int(night_due.get(k) or 0)
    brier = None
    if brier_model:
        brier = {"games": len(brier_model), "model": round(sum(brier_model) / len(brier_model), 4),
                 "market": round(sum(brier_market) / len(brier_market), 4), "baseline": BRIER_BASELINE}
    markets = {}
    if over_rows:
        markets["over25"] = {"games": len(over_rows), "buckets": _market_buckets(over_rows)}
    if btts_rows:
        markets["btts"] = {"games": len(btts_rows), "buckets": _market_buckets(btts_rows)}
    out = {
        "generatedAt": now, "nights": counted_nights, "games": games,
        "buckets": _buckets(fav_rows, RECORD_BUCKETS), "brier": brier, "movement": movement, "markets": markets,
    }
    entries = due["w"] + due["l"]
    if entries:
        out["dueList"] = {"entries": entries, "hitRate": round(due["w"] / entries, 4), "voids": due["p"]}
    return out


# ---------- every graded bet ----------

def _tally(rows: list[dict]) -> dict:
    out = {"w": 0, "l": 0, "p": 0, "bets": len(rows), "staked": 0.0, "units": 0.0}
    for r in rows:
        out[{"win": "w", "loss": "l"}.get(r.get("result"), "p")] += 1
        out["staked"] += float(r.get("staked") or 0)
        out["units"] += float(r.get("units") or 0)
    out["staked"], out["units"] = round(out["staked"], 4), round(out["units"], 4)
    out["returnPct"] = round(100 * out["units"] / out["staked"], 1) if out["staked"] else 0.0
    return out


def _grouped(rows: list[dict], key_fn, label_fn) -> list[dict]:
    groups: dict = {}
    for r in rows:
        keys = key_fn(r)
        for k in ([keys] if not isinstance(keys, list) else keys):
            if k in (None, ""):
                continue
            g = groups.setdefault(k, {"key": k, "label": label_fn(k, r), "rows": []})
            g["rows"].append(r)
    out = [{"key": g["key"], "label": g["label"], **_tally(g["rows"])} for g in groups.values()]
    out.sort(key=lambda g: (-g["units"], g["label"]))
    return out


def _price_band(price: object) -> str | None:
    if not _num(price):
        return None
    for label, lo, hi in PRICE_BANDS:
        if (lo is None or price >= lo) and (hi is None or price <= hi):
            return label
    return None


def tracker(hist: Path, now: str) -> dict:
    """tracker.json from the kept nights' `bets` rows, newest first."""
    rows: list[dict] = []
    nights = 0
    for _day, night in settled_nights(hist):
        bets = night.get("bets")
        if not isinstance(bets, list):
            continue
        kept = [b for b in bets if isinstance(b, dict) and b.get("result") in ("win", "loss", "push") and _num(b.get("staked"))]
        if kept:
            nights += 1
        rows.extend(kept)
    rows.sort(key=lambda r: (str(r.get("date")), str(r.get("kickoff") or ""), str(r.get("label") or "")), reverse=True)
    dates = sorted({str(r.get("date")) for r in rows})
    team_rows = [r for r in rows if r.get("group") == "team"]
    prop_rows = [r for r in rows if r.get("group") == "props"]
    month_name = lambda k: datetime.strptime(k, "%Y-%m").strftime("%B %Y")  # noqa: E731
    return {
        "generatedAt": now, "nights": nights,
        "firstDate": dates[0] if dates else None, "lastDate": dates[-1] if dates else None,
        "teamPickDefaultUnits": TEAM_PICK_DEFAULT_UNITS, "dueStake": None,
        "overall": _tally(rows),
        "byGroup": [{"key": k, "label": label, **_tally([r for r in rows if r.get("group") == k])}
                    for k, label in TRACKER_GROUPS.items() if any(r.get("group") == k for r in rows)],
        "byMarket": _grouped(team_rows, lambda r: f"team:{r.get('market')}", lambda k, r: str(r.get("market"))),
        "byPropType": _grouped(prop_rows, lambda r: f"{r.get('market')}:{r.get('side') or ''}",
                               lambda k, r: f"{r.get('propType') or r.get('market')} {r.get('side') or ''}".strip()),
        "byTeam": _grouped(rows, lambda r: list(r.get("teams") or []) if r.get("group") == "team" else [r.get("team")],
                           lambda k, r: k),
        "byPlayer": _grouped(prop_rows, lambda r: r.get("player"), lambda k, r: f"{k} ({r.get('team')})"),
        "byPrice": _grouped(rows, lambda r: _price_band(r.get("price")), lambda k, r: k),
        "byMonth": _grouped(rows, lambda r: str(r.get("date"))[:7], lambda k, r: month_name(k)),
        "rows": rows,
    }


# ---------- the season ----------

def season_table(fixtures: list[dict], team_entry) -> tuple[dict, list[dict]]:
    """The table from the played fixtures, and the fixtures still to play."""
    table: dict = {}
    remaining: list[dict] = []

    def row(fd: str) -> dict:
        abbr, entry = team_entry(fd)
        return table.setdefault(abbr, {"abbr": abbr, "name": entry["name"], "fd": fd, "played": 0, "won": 0, "drawn": 0,
                                       "lost": 0, "gf": 0, "ga": 0, "gd": 0, "points": 0})

    for f in fixtures:
        h, a = row(f["home"]["fd"]), row(f["away"]["fd"])
        hg, ag = f.get("homeGoals"), f.get("awayGoals")
        if f.get("state") == "post" and _num(hg) and _num(ag):
            for side, mine, theirs in ((h, hg, ag), (a, ag, hg)):
                side["played"] += 1
                side["gf"] += int(mine)
                side["ga"] += int(theirs)
                side["gd"] = side["gf"] - side["ga"]
                side["won" if mine > theirs else "drawn" if mine == theirs else "lost"] += 1
                side["points"] += 3 if mine > theirs else 1 if mine == theirs else 0
        elif f.get("state") != "post":
            remaining.append(f)
    return table, remaining


def _rank(table: dict) -> list[str]:
    return sorted(table, key=lambda k: (-table[k]["points"], -table[k]["gd"], -table[k]["gf"], table[k]["name"]))


def simulate_season(table: dict, remaining: list[dict], project, *, sims: int = SIMULATIONS, seed: int = 2026) -> dict:
    """Every remaining fixture played out `sims` times on the board's own goal
    expectations (Poisson goals each side), the table re-ranked each time.

    A fixture the model cannot price (an unrated club) is played as a draw
    of 1–1 every time, and counted in `unpriced`, rather than guessed at.
    """
    abbrs = list(table)
    index = {a: i for i, a in enumerate(abbrs)}
    priced, unpriced = [], 0
    for f in remaining:
        h, a = f["home"]["fd"], f["away"]["fd"]
        pr = project(h, a) if project is not None else None
        hi, ai = index.get(f["_home_abbr"]), index.get(f["_away_abbr"])
        if hi is None or ai is None:
            continue
        if pr and _num(pr.get("eh")) and _num(pr.get("ea")):
            priced.append((hi, ai, float(pr["eh"]), float(pr["ea"])))
        else:
            unpriced += 1
            priced.append((hi, ai, None, None))
    n = len(abbrs)
    base_pts = [table[a]["points"] for a in abbrs]
    base_gd = [table[a]["gd"] for a in abbrs]
    base_gf = [table[a]["gf"] for a in abbrs]
    finishes = [[0] * n for _ in range(n)]  # finishes[team][rank]
    points_sims: list[list[int]] = [[] for _ in range(n)]
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - the lab ships numpy with pandas
        np = None
    if np is not None and priced:
        rng = np.random.default_rng(seed)
        pts = np.tile(np.array(base_pts, dtype=np.int64), (sims, 1))
        gd = np.tile(np.array(base_gd, dtype=np.int64), (sims, 1))
        gf = np.tile(np.array(base_gf, dtype=np.int64), (sims, 1))
        for hi, ai, eh, ea in priced:
            if eh is None:
                hg = ag = np.ones(sims, dtype=np.int64)
            else:
                hg, ag = rng.poisson(eh, sims), rng.poisson(ea, sims)
            pts[:, hi] += np.where(hg > ag, 3, np.where(hg == ag, 1, 0))
            pts[:, ai] += np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
            gd[:, hi] += hg - ag
            gd[:, ai] += ag - hg
            gf[:, hi] += hg
            gf[:, ai] += ag
        score = pts * 1_000_000 + (gd + 1000) * 1000 + gf
        order = np.argsort(-score, axis=1, kind="stable")
        ranks = np.empty_like(order)
        rows = np.arange(sims)[:, None]
        ranks[rows, order] = np.arange(n)[None, :]
        for t in range(n):
            counts = np.bincount(ranks[:, t], minlength=n)
            finishes[t] = [int(c) for c in counts]
            points_sims[t] = pts[:, t].tolist()
    else:
        rnd = random.Random(seed)

        def poisson(lam: float) -> int:
            limit, k, p = math.exp(-lam), 0, 1.0
            while True:
                p *= rnd.random()
                if p <= limit:
                    return k
                k += 1

        for _ in range(sims):
            pts, gd, gf = list(base_pts), list(base_gd), list(base_gf)
            for hi, ai, eh, ea in priced:
                hg, ag = (1, 1) if eh is None else (poisson(eh), poisson(ea))
                pts[hi] += 3 if hg > ag else 1 if hg == ag else 0
                pts[ai] += 3 if ag > hg else 1 if hg == ag else 0
                gd[hi] += hg - ag
                gd[ai] += ag - hg
                gf[hi] += hg
                gf[ai] += ag
            order = sorted(range(n), key=lambda t: (-pts[t], -gd[t], -gf[t], abbrs[t]))
            for r, t in enumerate(order):
                finishes[t][r] += 1
                points_sims[t].append(pts[t])
    out = {}
    for t, abbr in enumerate(abbrs):
        p = sorted(points_sims[t]) or [base_pts[t]]
        q = lambda frac: p[min(len(p) - 1, int(frac * len(p)))]  # noqa: E731
        f = finishes[t]
        total = max(1, sum(f))
        out[abbr] = {
            "projPoints": round(sum(p) / len(p), 1), "p10": int(q(0.10)), "p90": int(q(0.90)),
            "projRank": round(sum((r + 1) * c for r, c in enumerate(f)) / total, 1),
            "title": round(f[0] / total, 4), "top4": round(sum(f[:4]) / total, 4), "top6": round(sum(f[:6]) / total, 4),
            "relegation": round(sum(f[max(0, n - 3):]) / total, 4),
        }
    return {"teams": out, "unpriced": unpriced, "simulations": sims}


def season_feed(lab: Path, today: date, now: str, *, board_module=None, fetch=None, sims: int = SIMULATIONS) -> dict:
    """season.json: the table and each club's projected finish."""
    B = board_module or _board_module()
    fetch_fixtures = fetch or B.fetch_fixtures
    fixtures, failed = fetch_fixtures(B.month_codes(SEASON_START, SEASON_END))
    # The window's unplayed fixtures are the season's remaining ones; a
    # fixture ESPN has not scheduled yet is not in the feed and is not
    # simulated, which the page says when the count is short of 380.
    table, remaining = season_table(fixtures, B.team_entry)
    for f in remaining:
        f["_home_abbr"], f["_away_abbr"] = B.team_entry(f["home"]["fd"])[0], B.team_entry(f["away"]["fd"])[0]
    project, model_note = B.load_model(lab)
    sim = simulate_season(table, remaining, project, sims=sims) if remaining and table else {"teams": {}, "unpriced": 0, "simulations": 0}
    played = sum(1 for f in fixtures if f.get("state") == "post" and _num(f.get("homeGoals")))
    teams = []
    for rank, abbr in enumerate(_rank(table), start=1):
        t = table[abbr]
        entry = {k: t[k] for k in ("abbr", "name", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points")}
        entry["rank"] = rank
        entry["remaining"] = sum(1 for f in remaining if abbr in (f["_home_abbr"], f["_away_abbr"]))
        entry.update(sim["teams"].get(abbr) or {})
        teams.append(entry)
    notes = []
    if failed:
        notes.append("The schedule feed did not answer for " + ", ".join(failed) + ", so the table and the projection may be short of fixtures.")
    if project is None:
        notes.append("The goals model could not be fitted in this run (" + model_note + "), so no finish is projected.")
    elif model_note:
        notes.append(model_note)
    if sim["unpriced"]:
        notes.append(f"{sim['unpriced']} remaining fixtures involve a club the model has no rating for and are played as 1–1 draws in the simulation.")
    if len(fixtures) < 380:
        notes.append(f"ESPN lists {len(fixtures)} of the season's 380 fixtures so far; the rest join the projection as they are scheduled.")
    return {
        "generatedAt": now, "season": B.SEASON, "through": today.isoformat(),
        "played": played, "remaining": len(remaining), "simulations": sim["simulations"],
        "projected": project is not None and bool(remaining),
        "notice": " ".join(notes) or None, "teams": teams,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lab", default=".")
    ap.add_argument("--out", default="dist/data")
    ap.add_argument("--date", default="")
    ap.add_argument("--sims", type=int, default=SIMULATIONS)
    ap.add_argument("--skip-season", action="store_true", help="Write record.json and tracker.json only (no network).")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    today = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    hist = out / "history"
    record = track_record(hist, now)
    (out / "record.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    track = tracker(hist, now)
    (out / "tracker.json").write_text(json.dumps(track, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"record: {record['games']} games over {record['nights']} nights; tracker: {track['overall']['bets']} graded bets.")
    if not args.skip_season:
        try:
            season = season_feed(Path(args.lab).resolve(), today, now, sims=args.sims)
        except Exception as exc:  # the season page must never take the deploy down
            season = {"generatedAt": now, "season": "", "through": today.isoformat(), "played": 0, "remaining": 0,
                      "simulations": 0, "projected": False, "teams": [],
                      "notice": f"The season table could not be built this run ({type(exc).__name__}: {exc})."}
            print(f"season: {season['notice']}")
        else:
            print(f"season: {season['played']} played, {season['remaining']} to play, {season['simulations']} simulations.")
        (out / "season.json").write_text(json.dumps(season, indent=1, ensure_ascii=False), encoding="utf-8")
    print("No odds were fetched, no credit was spent, and no bet is ever placed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
