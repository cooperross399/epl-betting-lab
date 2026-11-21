#!/usr/bin/env python3
"""Site history for one lab's board. Sport-agnostic. Run right after the board is built:

    python web/site_history.py --data dist/data [--slot morning]

Does three things, all inside --data:
  1. Freezes today's board the first time it is built (history/<date>[_<slot>].json)
     and never overwrites what it froze. That frozen copy is the published opinion.
     A later build may only ADD to it, for fixtures not yet kicked off: prop rows
     and Due List entries or prices bought after the first build (`merge_late`).
  2. Appends the current market values to history/lines/<date>.json, one point per
     build, and injects the series into board.json as `lineHistory[gameId][key]`
     so the page can draw the movement. A series the builder already put on the
     board from the lab's own price captures is kept in place of the per-build one.
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
    "ml_home": [("moneyline", "current", "home"), ("matchResult", "home")],
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


def _not_started(game: dict, now: datetime) -> bool:
    """True while a fixture has not kicked off: by its own state, else its kickoff."""
    if game.get("started") or str(game.get("state") or "").lower() in ("in", "post") or game.get("completed") or game.get("final"):
        return False
    try:
        ko = datetime.fromisoformat(str(game.get("kickoff") or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    return ko > now


def _plain(name) -> str:
    return " ".join(str(name or "").casefold().split())


def merge_late(kept: dict, board: dict, stamp: str | None = None) -> dict:
    """Carry what the board gained after it was frozen into the frozen copy, before kick-off only.

    A board is frozen the first time its date is built, and the record grades
    only the frozen copy. Props and Due List prices are bought later in the
    week than the first build of a round, so until 2026-11-21 they never
    reached the frozen board and the site could grade no prop and post no Due
    List units. For a fixture that has NOT kicked off (by the current board's
    own state and kickoff), this adds:

      - prop rows the frozen board does not hold (same gameId, player, market,
        side, line), so the first one published still wins;
      - Due List entries the frozen game does not hold;
      - a price on a frozen Due List entry that had none.

    Nothing already frozen is changed: no row is replaced, no price moved, and
    a fixture that has started is never touched. Returns the counts added.
    """
    try:
        now = datetime.fromisoformat(str(stamp or "").replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    except ValueError:
        now = datetime.now(timezone.utc)
    now = max(now, datetime.now(timezone.utc))
    live = {str(g.get("id")): g for g in board.get("games") or [] if isinstance(g, dict)}
    open_ids = {gid for gid, g in live.items() if _not_started(g, now)}
    added = {"props": 0, "due entries": 0, "due prices": 0}

    rows = ((board.get("props") or {}).get("rows") if isinstance(board.get("props"), dict) else None) or []
    late = [r for r in rows if isinstance(r, dict) and str(r.get("gameId")) in open_ids]
    if late:
        block = kept.get("props") if isinstance(kept.get("props"), dict) else {}
        have = [r for r in block.get("rows") or [] if isinstance(r, dict)]
        keys = {(str(r.get("gameId")), _plain(r.get("player")), r.get("market"), r.get("side"), r.get("line")) for r in have}
        for r in late:
            key = (str(r.get("gameId")), _plain(r.get("player")), r.get("market"), r.get("side"), r.get("line"))
            if key not in keys:
                keys.add(key)
                have.append(r)
                added["props"] += 1
        if added["props"]:
            block = dict(block)
            block["rows"] = have
            block["status"] = "ok"
            kept["props"] = block

    for g in kept.get("games") or []:
        if not isinstance(g, dict) or str(g.get("id")) not in open_ids:
            continue
        fresh = [e for e in live[str(g.get("id"))].get("drought") or [] if isinstance(e, dict)]
        if not fresh:
            continue
        mine = g.setdefault("drought", [])
        if not isinstance(mine, list):
            continue
        index = {(str(e.get("playerId") or _plain(e.get("player"))), e.get("market")): e for e in mine if isinstance(e, dict)}
        for e in fresh:
            key = (str(e.get("playerId") or _plain(e.get("player"))), e.get("market"))
            held = index.get(key)
            if held is None:
                mine.append(e)
                index[key] = e
                added["due entries"] += 1
            elif held.get("price") in (None, "") and e.get("price") not in (None, ""):
                for k in ("price", "book", "heavyJuice"):
                    if k in e:
                        held[k] = e[k]
                added["due prices"] += 1
    return added


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
    # A series the builder already published from the lab's own captures
    # (one point per capture; EPL reads them off the price feed) is the
    # better record of the line than one point per build, so it wins for
    # that game and key. Every other key keeps the per-build series.
    captured = board.get("lineHistory") if isinstance(board.get("lineHistory"), dict) else {}
    built = {gid: {k: v for k, v in s.items() if len(v) >= 2} for gid, s in lines.items()}
    for gid, series in captured.items():
        if isinstance(series, dict):
            built.setdefault(str(gid), {}).update({k: v for k, v in series.items() if isinstance(v, list) and len(v) >= 2})
    board["lineHistory"] = {gid: s for gid, s in built.items() if s}
    dump(board_path, board)

    # 1. freeze
    fname = f"{date}_{slot}.json" if slot else f"{date}.json"
    frozen = hist / fname
    if not frozen.exists():
        dump(frozen, board)
        print(f"froze {fname}")
    else:
        kept = load(frozen, None)
        if isinstance(kept, dict):
            added = merge_late(kept, board, stamp)
            if any(added.values()):
                dump(frozen, kept)
                print(f"{fname}: added before kick-off " + ", ".join(f"{n} {k}" for k, n in added.items() if n))

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
