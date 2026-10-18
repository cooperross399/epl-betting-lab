"""The EPL Due List: the NHL lab's Due List and the NFL lab's TD Due List, for goalscorers.

Cooper asked on 2026-10-18 for "a due goalscorer feature for the EPL like we
have our Due list for nhl and the nfl TD scorers", parameters left to Claude.
This module is the port. The machinery is the other labs'
(`nhl_betting_lab.drought_rule`, `football_betting_lab.td_due_list`, read,
not imported: the labs never import each other); the parameters and every
number are this league's own.

## The rule

A player who scored **10 or more Premier League goals last season** is listed
for anytime goalscorer, over 0.5, when his current drought reaches the bar
for his band:

    20+ goals last season -> 4 straight appearances without a goal
    15-19                 -> 6
    10-14                 -> 8

The drought is the league matches he appeared in without scoring, carried
across the season boundary, entering the next fixture, which is how both
other labs count it. "Appeared" is ESPN's `appearances` (he got on the
pitch); a match he missed, or sat on the bench for, does not extend it. Own
goals do not count, as an anytime-goalscorer bet does not count them.

## Why these numbers

The NHL and NFL tiers put each band's bar near the drought a typical player
in it goes on about one time in sixteen. The same rule is applied here, from
each band's share of appearances with a goal the season before, measured
over 2022/23-2025/26 (ESPN league squads):

    band    player-seasons  share of apps with a goal  bar  (1 - p)^bar
    20+            8               0.52                4      ~0.05
    15-19         17               0.40                6      ~0.05
    10-14         52               0.30                8      ~0.06

10 goals is the floor because it leaves 20-26 qualifiers a season, about the
NHL list's 25-goal pool, and below it the bar passes ten appearances, more
than a quarter of a season. The bars were set from those hit rates before
any listed row was compared with an outcome.

## What the measurement says

Being due has NOT meant scoring more. Over 2022/23-2025/26 a listed player
scored in fewer of his next appearances than the same qualifiers did when
not due, by about eleven points, and the interval excludes zero
(`data/outputs/due_list_backtest.md`). A long drought in this league is
usually a lost place, a new role or an injury, not variance waiting to turn.
The card prints that headline beside the list every time.

## Who is left off

He must have been in a matchday squad for a league match this season, and
the club he is listed for is the club of his latest squad. That is how a
player who left the league, or moved clubs, is handled without a roster
feed. A qualifier who was in neither of his club's last
`ABSENT_REMOVE_MATCHES` league squads is removed and named, because a player
missing from two squads in a row is usually injured or out of the side; one
missing from the last squad only is flagged. Soccer has no league-wide
injury report a keyless source publishes, so this is the availability check
this lab can make, and the section says so.

## What it is

A LIST beside the card, like the NHL and NFL ones: no units, no edge, nothing
in the card's selections, the scoreboard, the price feed or the selection
comparison. The anytime-goalscorer price is printed only when one was staged;
the props markets are held by policy, so normally the row says "not posted",
never a price filled in. `scripts/run_due_list_backtest.py` measures what
being due has been worth in scoring rate, and the card prints that headline
beside the list.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


#: Last league season's goals needed to be considered at all.
THRESHOLD = 10
#: (floor of last season's goals, drought that lists him), best band first.
TIERS: tuple[tuple[int, int], ...] = ((20, 4), (15, 6), (10, 8))
#: Missing from this many of his club's latest league squads in a row removes him.
ABSENT_REMOVE_MATCHES = 2
MARKET = "goals"
LINE = 0.5
SECTION_TITLE = "Due List · anytime goalscorers"
BACKTEST_JSON = "due_list_backtest.json"
DUE_LIST_JSON = "due_list.json"
DUE_LIST_MD = "due_list.md"

assert TIERS[-1][0] == THRESHOLD, "the lowest tier is the base qualifier"


def tier_bar(prior_goals: Any) -> int | None:
    """The drought that lists a player on last season's goals; None below the qualifier."""
    if prior_goals is None or pd.isna(prior_goals):
        return None
    for floor, bar in TIERS:
        if prior_goals >= floor:
            return bar
    return None


def band_label(prior_goals: Any) -> str | None:
    """The band last season's total falls in ("20+", "15-19", "10-14"); None below the qualifier."""
    if prior_goals is None or pd.isna(prior_goals):
        return None
    for i, (floor, _) in enumerate(TIERS):
        if prior_goals >= floor:
            return f"{floor}+" if i == 0 else f"{floor}-{TIERS[i - 1][0] - 1}"
    return None


def rule_sentence() -> str:
    """The rule in one line, from the constants, so no copy of it can drift."""
    bars = ", ".join(f"{band_label(floor)} goals -> {bar}" for floor, bar in TIERS)
    return (
        f"{THRESHOLD}+ Premier League goals last season and a run of league appearances "
        f"without a goal at the bar his total sets ({bars} straight games)."
    )


def one_in(hit_rate: Any, drought: int) -> int | None:
    """N in "1 in N for him": round(1 / (1 - p)^drought); None when it cannot be said."""
    if hit_rate is None or pd.isna(hit_rate) or drought < 1:
        return None
    miss = 1.0 - float(hit_rate)
    if miss <= 0.0:
        return None
    rarity = miss**drought
    if rarity <= 0.0:
        return None
    return int(round(1.0 / rarity))


_NEEDED = {"season", "date", "event_id", "team", "player_id", "appeared", "goals"}


def _clean_logs(logs: pd.DataFrame) -> pd.DataFrame:
    missing = _NEEDED - set(logs.columns)
    if missing:
        raise ValueError(f"player logs lack {sorted(missing)}")
    frame = logs.dropna(subset=["player_id", "event_id"]).copy()
    frame["player_id"] = frame["player_id"].astype(str)
    frame["event_id"] = frame["event_id"].astype(str)
    frame["season"] = pd.to_numeric(frame["season"], errors="coerce")
    frame["appeared"] = pd.to_numeric(frame["appeared"], errors="coerce")
    goals = pd.to_numeric(frame["goals"], errors="coerce")
    # A missing count is not a match without a goal. Counting it as one would
    # extend a drought on a row that says nothing.
    frame = frame[goals.notna() & frame["season"].notna() & frame["appeared"].notna()].copy()
    frame["goals"] = pd.to_numeric(frame["goals"]).astype(int)
    frame["season"] = frame["season"].astype(int)
    frame["appeared"] = frame["appeared"].astype(int)
    frame["date"] = frame["date"].astype(str).str[:10]
    if "player" not in frame.columns:
        frame["player"] = ""
    return frame.drop_duplicates(subset=["player_id", "event_id"], keep="first")


def prepare_logs(logs: pd.DataFrame) -> pd.DataFrame:
    """Every league appearance with the drought entering it and last season's record.

    Columns added: `scored`, `drought` (appearances without a goal entering
    this one, carried across seasons), `prior_goals`, `prior_apps`,
    `prior_rate` (last season's appearances with a goal over appearances),
    `bar` and `listed`. The card and the backtest both read this, so they
    cannot disagree about who was due.
    """
    frame = _clean_logs(logs)
    frame = frame[frame["appeared"] > 0].copy()
    frame["scored"] = frame["goals"] > 0
    frame = frame.sort_values(["player_id", "date", "event_id"], kind="mergesort")

    # Appearances without a goal entering each row: the running count of
    # misses since his last scoring game, shifted one so this game is not
    # counted in its own drought.
    misses = (~frame["scored"]).astype(int)
    block = frame["scored"].astype(int).groupby(frame["player_id"]).cumsum()
    run = misses.groupby([frame["player_id"], block]).cumsum()
    frame["drought"] = run.groupby(frame["player_id"]).shift(1).fillna(0).astype(int)

    totals = (
        frame.groupby(["player_id", "season"])
        .agg(prior_goals=("goals", "sum"), prior_apps=("scored", "size"), prior_hits=("scored", "sum"))
        .reset_index()
    )
    totals["season"] = totals["season"] + 1
    frame = frame.merge(totals, on=["player_id", "season"], how="left")
    frame["prior_rate"] = frame["prior_hits"] / frame["prior_apps"]
    frame["bar"] = frame["prior_goals"].map(tier_bar)
    frame["listed"] = frame["bar"].notna() & (frame["drought"] >= frame["bar"].fillna(10**9))
    return frame.sort_values(["date", "event_id", "player_id"]).reset_index(drop=True)


def entering(logs: pd.DataFrame, *, season: int, before: str) -> pd.DataFrame:
    """Each qualifier's state entering his next match of `season`, from matches before `before`.

    The same `prepare_logs`, asked about one more appearance: a sentinel row
    per qualifier dated `before`, so the drought it reports is the one
    entering that match and last season's record is read for `season`. Rows
    on or after `before` are dropped first, so a rebuilt table cannot leak a
    match into its own drought. Also carries his current club (`club`: the
    team of his latest squad this season) and `club_absent`, the number of
    his club's latest league matches in a row whose squad he was not in.
    """
    frame = _clean_logs(logs)
    frame = frame[frame["date"] < before]
    last = frame[(frame["season"] == season - 1) & (frame["appeared"] > 0)]
    totals = last.groupby("player_id")["goals"].sum()
    qualifiers = list(totals[totals >= THRESHOLD].index)
    current = frame[frame["season"] == season].sort_values(["date", "event_id"], kind="mergesort")
    latest_squad = current.groupby("player_id").tail(1).set_index("player_id")
    qualifiers = [pid for pid in qualifiers if pid in latest_squad.index]
    if not qualifiers:
        return pd.DataFrame()
    names = frame.sort_values("date").groupby("player_id").tail(1).set_index("player_id")["player"]
    sentinel = pd.DataFrame(
        {
            "season": season,
            "date": before,
            "event_id": [f"__next__{pid}" for pid in qualifiers],
            "team": [latest_squad.loc[pid, "team"] for pid in qualifiers],
            "player_id": qualifiers,
            "player": [names.get(pid, "") for pid in qualifiers],
            "appeared": 1,
            "goals": 0,
        }
    )
    prepared = prepare_logs(pd.concat([frame, sentinel], ignore_index=True))
    out = prepared[prepared["event_id"].str.startswith("__next__")].copy()
    out["club"] = out["team"]

    # His club's league matches this season, newest first, and whether his
    # name was on the squad sheet for each.
    club_events = (
        current[["team", "event_id", "date"]].drop_duplicates()
        .sort_values(["date", "event_id"], ascending=False, kind="mergesort")
    )
    in_squad = set(zip(current["player_id"], current["event_id"]))
    absent: list[int] = []
    for row in out.itertuples():
        count = 0
        for event_id in club_events.loc[club_events["team"] == row.club, "event_id"]:
            if (row.player_id, event_id) in in_squad:
                break
            count += 1
        absent.append(count)
    out["club_absent"] = absent
    return out.reset_index(drop=True)


@dataclass(frozen=True)
class DueRow:
    player: str
    player_id: str
    team: str
    opponent: str
    event_id: str
    kickoff: str
    prior_goals: int
    prior_apps: int
    prior_rate: float
    band: str
    bar: int
    drought: int
    one_in: int | None
    price: float | None = None
    book: str = ""
    status: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "player_id": self.player_id,
            "team": self.team,
            "opponent": self.opponent,
            "event_id": self.event_id,
            "kickoff": self.kickoff,
            "market": MARKET,
            "line": LINE,
            "prior_goals": self.prior_goals,
            "prior_apps": self.prior_apps,
            "prior_rate": round(self.prior_rate, 4),
            "band": self.band,
            "bar": self.bar,
            "drought": self.drought,
            "one_in": self.one_in,
            "price": self.price,
            "book": self.book,
            "status": self.status,
        }


def _absence_words(count: int, club: str) -> str:
    if count == 1:
        return f"not in {club}'s squad for their last league match"
    return f"not in {club}'s squad for their last {count} league matches"


def build_due_list(
    logs: pd.DataFrame,
    fixtures: list[dict[str, str]],
    *,
    season: int,
    before: str,
    prices: dict[str, tuple[float, str]] | None = None,
    removed_out: list[tuple[DueRow, str]] | None = None,
) -> list[DueRow]:
    """The listed players whose club plays one of `fixtures`.

    `fixtures` are dicts with `event_id`, `home`, `away`, `kickoff`, in the
    logs' own team spelling (ESPN display names). `before` is the date the
    droughts are read entering: the first fixture's date. A qualifier missing
    from his club's last `ABSENT_REMOVE_MATCHES` squads is not listed; when
    `removed_out` is given he is appended there with the reason, so the
    section says who was dropped rather than dropping him silently.
    `prices` maps a player id to (best American price, book) when a price
    was staged; nothing is ever filled in.
    """
    state = entering(logs, season=season, before=before)
    if state.empty:
        return []
    opponents: dict[str, dict[str, str]] = {}
    for fixture in sorted(fixtures, key=lambda f: f.get("kickoff", "")):
        for side, other in (("home", "away"), ("away", "home")):
            team = str(fixture.get(side, ""))
            # A club's FIRST fixture in the window: the drought is entering it.
            opponents.setdefault(team, {**fixture, "opponent": str(fixture.get(other, ""))})
    rows: list[DueRow] = []
    for record in state[state["listed"]].itertuples():
        fixture = opponents.get(str(record.club))
        if fixture is None:
            continue
        price, book = (prices or {}).get(str(record.player_id), (None, ""))
        absent = int(record.club_absent)
        row = DueRow(
            player=str(record.player or ""),
            player_id=str(record.player_id),
            team=str(record.club),
            opponent=fixture["opponent"],
            event_id=str(fixture.get("event_id", "")),
            kickoff=str(fixture.get("kickoff", "")),
            prior_goals=int(record.prior_goals),
            prior_apps=int(record.prior_apps),
            prior_rate=float(record.prior_rate),
            band=band_label(record.prior_goals) or "",
            bar=int(record.bar),
            drought=int(record.drought),
            one_in=one_in(record.prior_rate, int(record.drought)),
            price=price,
            book=book,
            status=_absence_words(absent, str(record.club)) if 0 < absent < ABSENT_REMOVE_MATCHES else "",
        )
        if absent >= ABSENT_REMOVE_MATCHES:
            if removed_out is not None:
                removed_out.append((row, _absence_words(absent, row.team)))
            continue
        rows.append(row)
    if removed_out is not None:
        removed_out.sort(key=lambda pair: pair[0].player)
    return sorted(rows, key=lambda r: (-(r.one_in or 0), -r.drought, r.player))


def load_headline(outputs_dir: Path) -> dict[str, Any] | None:
    """The committed backtest's headline, or None when the file is absent or unreadable."""
    try:
        payload = json.loads((Path(outputs_dir) / BACKTEST_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def headline_sentence(headline: dict[str, Any] | None) -> str:
    """One line on what being due has been worth, read from the backtest; never invented."""
    if not headline:
        return "No backtest is committed yet, so nothing is said here about what being due is worth."
    hits = headline.get("hit_rate")
    if not isinstance(hits, dict) or not hits.get("listed_n"):
        return "The committed backtest has no headline, so nothing is said here."
    if hits["diff_high"] < 0:
        verdict = "**Being due has meant scoring less often, not more.** "
    elif hits["diff_low"] > 0:
        verdict = "Being due has meant scoring more often. "
    else:
        verdict = "Being due has shown no difference either way. "
    return verdict + (
        f"Seasons {hits.get('window')}: listed players scored in {hits['listed_rate']:.1%} of "
        f"{hits['listed_n']:,} next appearances, against {hits['others_rate']:.1%} for the same "
        f"qualifiers when not due (n = {hits['others_n']:,}; difference "
        f"{hits['diff']:+.1%}, 95% {hits['diff_low']:+.1%} to {hits['diff_high']:+.1%}). "
        "No price-based measurement exists: historical goalscorer prices were never bought."
    )


def _price_text(price: float | None, book: str) -> str:
    if price is None or (isinstance(price, float) and math.isnan(price)):
        return "not posted"
    return f"{price:+.0f}" + (f" ({book})" if book else "")


def render_section(
    rows: list[DueRow],
    *,
    headline: dict[str, Any] | None,
    removed: list[tuple[DueRow, str]] | None = None,
    note: str = "",
) -> str:
    """The card section. A list beside the card, never a selection."""
    out = [f"### {SECTION_TITLE}", ""]
    out.append(
        f"Anytime goalscorer, over {LINE}. Listed: {rule_sentence()} "
        "Context only: no units, nothing here is a selection, and no edge is shown."
    )
    out += ["", headline_sentence(headline), ""]
    if note:
        out += [note, ""]
    if not rows:
        out.append("Nobody playing in this round is due.")
    else:
        out.append("| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |")
        out.append("|:--|:--|:--|:--|--:|:--|--:|:--|:--|")
        for row in rows:
            rarity = f"1 in {row.one_in:,}" if row.one_in else "—"
            kickoff = row.kickoff.replace("T", " ").replace("Z", "")[:16]
            out.append(
                f"| {row.player} | {row.team} | {row.opponent} | {kickoff} | "
                f"{row.prior_goals} G, scored in {row.prior_rate:.0%} of apps | {row.drought} ({row.bar}) | "
                f"{rarity} | {row.status or '—'} | {_price_text(row.price, row.book)} |"
            )
    if removed:
        out += ["", "Removed, probably not playing (missing from recent squads):", ""]
        for row, reason in removed:
            out.append(f"- {row.player} ({row.team}): {reason}")
    return "\n".join(out) + "\n"


def payload(
    rows: list[DueRow],
    *,
    removed: list[tuple[DueRow, str]],
    season: int,
    before: str,
    generated_at: str,
    headline: dict[str, Any] | None,
    fetch_note: str = "",
) -> dict[str, Any]:
    """The JSON the board reads: the rule, the rows and who was removed."""
    return {
        "generated_at": generated_at,
        "season": season,
        "entering": before,
        "rule": rule_sentence(),
        "threshold": THRESHOLD,
        "tiers": [list(t) for t in TIERS],
        "headline": headline_sentence(headline),
        "fetch_note": fetch_note,
        "rows": [r.as_dict() for r in rows],
        "removed": [{**r.as_dict(), "reason": why} for r, why in removed],
    }
