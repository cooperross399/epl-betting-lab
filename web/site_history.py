#!/usr/bin/env python3
"""Site history for one lab's board. Sport-agnostic. Run right after the board is built:

    python web/site_history.py --data dist/data [--slot morning]

Does three things, all inside --data:
  1. Freezes today's board the first time it is built (history/<date>[_<slot>].json)
     and never overwrites it. That frozen copy is the published opinion.
  2. Appends the current market values to history/lines/<date>.json, one point per
     build, and injects the series into board.json as `lineHistory[gameId][key]`
     so the page can draw the movement.
  3. Rewrites history/index.json, newest first, with game and best-bet counts.

The workflow restores the previous run's history artifact into --data/history before
this runs and uploads it again afterwards, so the series survive between builds.
Nothing here fetches odds, spends a credit, or places a bet.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

#: series key -> candidate paths into a game dict, first numeric hit wins.
SERIES = {
    "ml_home": [("moneyline", "current", "home")],
    "pl_price": [("puckLine", "price")],
    "spread": [("spread", "current")],
    "total": [("total", "current")],
    "total_over": [("total", "over")],
    "btts_yes": [("btts", "yes")],
    "dnb_home": [("drawNoBet", "home")],
}


def dig(d, path):
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d if isinstance(d, (int, float)) and not isinstance(d, bool) else None


def board_date(board: dict) -> str:
    for k in ("boardDate", "slateDate", "windowStart"):
        if board.get(k):
            return str(board[k])[:10]
    return datetime.now(timezone.utc).date().isoformat()


def load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def dump(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="dist/data")
    ap.add_argument("--slot", default="", help="Card slot suffix for sports with several cards a day.")
    args = ap.parse_args(argv)
    data = Path(args.data)
    board_path = data / "board.json"
    board = load(board_path, None)
    if board is None:
        print("no board.json; nothing to record")
        return 0
    date = board_date(board)
    slot = args.slot or board.get("cardSlot") or ""
    hist = data / "history"
    lines_path = hist / "lines" / f"{date}.json"

    # 2. line series
    lines = load(lines_path, {})
    stamp = board.get("generatedAt") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for g in board.get("games", []):
        gid = str(g.get("id"))
        series = lines.setdefault(gid, {})
        for key, paths in SERIES.items():
            v = next((x for x in (dig(g, p) for p in paths) if x is not None), None)
            if v is None:
                continue
            pts = series.setdefault(key, [])
            if not pts or pts[-1]["v"] != v:
                pts.append({"t": stamp, "v": v})
            elif pts[-1]["t"] != stamp:
                pts[-1] = {"t": stamp, "v": v}  # same value, newer confirmation
    dump(lines_path, lines)
    board["lineHistory"] = {gid: {k: v for k, v in s.items() if len(v) >= 2} for gid, s in lines.items()}
    board["lineHistory"] = {gid: s for gid, s in board["lineHistory"].items() if s}
    dump(board_path, board)

    # 1. freeze
    fname = f"{date}_{slot}.json" if slot else f"{date}.json"
    frozen = hist / fname
    if not frozen.exists():
        dump(frozen, board)
        print(f"froze {fname}")

    # 3. index
    entries = []
    for p in sorted(hist.glob("*.json")):
        if p.name == "index.json":
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:_(\w+))?\.json$", p.name)
        if not m:
            continue
        b = load(p, {})
        games = b.get("games", [])
        bets = sum(1 for g in games if isinstance(g.get("pick"), dict) and g["pick"].get("kind", "bet") == "bet")
        e = {"date": m.group(1), "file": p.name, "games": len(games), "bets": bets}
        if m.group(2):
            e["slot"] = m.group(2)
        if b.get("phase") == "preseason":
            e["note"] = "exhibition"
        entries.append(e)
    entries.sort(key=lambda e: (e["date"], e.get("slot", "")), reverse=True)
    dump(hist / "index.json", {"generatedAt": stamp, "dates": entries})
    print(f"history: {len(entries)} boards indexed; lines recorded for {len(lines)} games. No bet was placed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
