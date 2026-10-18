#!/usr/bin/env python
"""Write the Due List (anytime goalscorers) the card appends and the board shows.

    PYTHONPATH=src python scripts/build_due_list.py

Separate from the card build on purpose, like the cup section: the card must
not depend on ESPN answering a few hundred match summaries, so this writes
`data/outputs/due_list.md` and `due_list.json` and the card and the board read
them if they are there. A run where this fails loses the list and keeps the
card.

Fetches last season's and this season's league squads from ESPN (keyless),
lists the qualifiers whose clubs play in the coming round, and prices a row
only from an anytime-goalscorer price already staged at a bettable book. It
spends no provider credit, places no bet, and touches no protected file.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.due_list import (
    DUE_LIST_JSON,
    DUE_LIST_MD,
    build_due_list,
    load_headline,
    payload,
    render_section,
)
from epl_betting_lab.providers.espn_player_logs import LeagueEvent, fetch_logs


#: The round: every fixture kicking off within this many days of the first
#: one still to be played. A Premier League round runs Friday to Monday; a
#: midweek round three days later belongs to the next list.
ROUND_DAYS = 4
#: Props staging, written only when the reviewed policy approves prop markets.
PROPS_STAGING = Path("data/staging/player_props_staging.csv")
ANYTIME_MARKET = "player_goal_scorer_anytime"


def season_for(now: datetime) -> int:
    """The league season under way on `now`: 2026 is 2026/27, from July."""
    return now.year if now.month >= 7 else now.year - 1


def coming_round(events: list[LeagueEvent], now: datetime) -> list[LeagueEvent]:
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    ahead = sorted((e for e in events if not e.completed and e.kickoff > stamp), key=lambda e: e.kickoff)
    if not ahead:
        return []
    first = datetime.strptime(ahead[0].kickoff[:10], "%Y-%m-%d")
    last = (first + timedelta(days=ROUND_DAYS)).strftime("%Y-%m-%d")
    return [e for e in ahead if e.kickoff[:10] <= last]


def _fold(name: object) -> str:
    text = unicodedata.normalize("NFKD", str(name or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def staged_prices(path: Path, players: dict[str, str]) -> dict[str, tuple[float, str]]:
    """player id -> (best anytime price, book) from the props staging file, bettable books only."""
    if not path.is_file():
        return {}
    from epl_betting_lab.books import bettable_only

    try:
        frame = bettable_only(pd.read_csv(path))
    except (OSError, ValueError):
        return {}
    if frame.empty or "market" not in frame.columns:
        return {}
    frame = frame[frame["market"] == ANYTIME_MARKET]
    frame = frame[~frame["selection"].astype(str).str.lower().str.startswith(("no", "under"))]
    frame = frame.assign(odds=pd.to_numeric(frame["american_odds"], errors="coerce")).dropna(subset=["odds"])
    by_name = {_fold(name): pid for pid, name in players.items()}
    out: dict[str, tuple[float, str]] = {}
    for name, group in frame.groupby(frame["player"].map(_fold)):
        pid = by_name.get(name)
        if pid:
            best = group.sort_values("odds", ascending=False).iloc[0]
            out[pid] = (float(best["odds"]), str(best.get("book", "") or ""))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", type=Path, default=OUTPUTS_DIR)
    parser.add_argument("--now", help="ISO time to build as of (tests and replays).")
    args = parser.parse_args(argv)
    now = (
        datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    ).astimezone(timezone.utc)
    season = season_for(now)

    fetched = fetch_logs([season - 1, season])
    note = ""
    if fetched.failed:
        note = (
            f"{len(fetched.failed)} played match(es) could not be read from ESPN and are left out, "
            "so a drought crossing one is understated, never overstated."
        )
    fixtures = coming_round([e for e in fetched.events if e.season == season], now)
    args.outputs.mkdir(parents=True, exist_ok=True)
    md_path, json_path = args.outputs / DUE_LIST_MD, args.outputs / DUE_LIST_JSON
    if not fixtures:
        # No round ahead (the season is over): no list, and no stale one left behind.
        for path in (md_path, json_path):
            path.unlink(missing_ok=True)
        print("No league fixture ahead; no Due List written.")
        return 0

    logs = pd.DataFrame(fetched.rows)
    before = fixtures[0].kickoff[:10]
    names = dict(zip(logs["player_id"].astype(str), logs["player"].astype(str))) if not logs.empty else {}
    removed: list = []
    rows = build_due_list(
        logs,
        [{"event_id": e.event_id, "home": e.home, "away": e.away, "kickoff": e.kickoff} for e in fixtures],
        season=season,
        before=before,
        prices=staged_prices(PROPS_STAGING, names),
        removed_out=removed,
    ) if not logs.empty else []
    headline = load_headline(args.outputs)
    md_path.write_text(render_section(rows, headline=headline, removed=removed, note=note), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            payload(
                rows,
                removed=removed,
                season=season,
                before=before,
                generated_at=now.isoformat(timespec="seconds"),
                headline=headline,
                fetch_note=note,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Due List: {len(rows)} listed, {len(removed)} removed, round of {len(fixtures)} fixture(s) from {before}.")
    print(md_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
