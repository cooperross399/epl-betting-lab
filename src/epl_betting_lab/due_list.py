"""The EPL Due List: the NHL lab's Due List and the NFL lab's TD Due List, for goals and assists.

Cooper asked on 2026-10-18 for "a due goalscorer feature for the EPL like we
have our Due list for nhl and the nfl TD scorers", parameters left to Claude,
and the same morning "Add assists to that due list". Assists follow the goals
rule below with their own numbers (`ASSISTS`); see "Assists".
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
not due, by about ten points, and the interval excludes zero
(`data/outputs/due_list_backtest.md`). A long drought in this league is
usually a lost place, a new role or an injury, not variance waiting to turn.
The card prints that headline beside the list every time.

## Assists

The same machinery on ESPN's `goalAssists`, listed for 1+ assist, over 0.5.
A player with **7 or more league assists last season** is listed when his run
of appearances without an assist reaches his band's bar, set by the same
one-in-sixteen rule from 2022/23-2025/26 hit rates:

    band   players  share of apps with an assist  bar  (1 - p)^bar
    12+       7              0.31                  8      ~0.05
    9-11     28              0.26                 10      ~0.05
    7-8      52              0.20                 13      ~0.05

Assists are rarer than goals, so the bars are longer. 7 is the floor because
it gave 19-37 qualifiers a season before 2025/26; below it the bar passes
fifteen appearances. 2025/26 was a thin assist season in ESPN's record (six
players reached 7), so this season's pool is small, and the list says who is
in it rather than lowering the bar to fill it. Measured the same way as
goals, a listed player had an assist in fewer of his next appearances than
the same qualifiers did when not due (`data/outputs/due_list_backtest.md`).

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


@dataclass(frozen=True)
class Category:
    """One list: the log column it counts, who qualifies, and the bars."""

    key: str  # the board's market key (SCHEMA.md games[].drought)
    column: str  # the ESPN log column counted
    label: str  # how the bet reads on the card
    noun: str  # plural, as in "10+ Premier League goals"
    one: str  # singular, as in "without a goal"
    #: (floor of last season's total, drought that lists him), best band first.
    tiers: tuple[tuple[int, int], ...]

    @property
    def threshold(self) -> int:
        """Last league season's total needed to be considered at all: the lowest floor."""
        return self.tiers[-1][0]


GOALS = Category("goals", "goals", "Anytime goalscorer", "goals", "a goal", ((20, 4), (15, 6), (10, 8)))
ASSISTS = Category("assists", "assists", "1+ assist", "assists", "an assist", ((12, 8), (9, 10), (7, 13)))
CATEGORIES: tuple[Category, ...] = (GOALS, ASSISTS)

#: The goals list's numbers under their original names.
THRESHOLD = GOALS.threshold
TIERS = GOALS.tiers
#: Missing from this many of his club's latest league squads in a row removes him.
ABSENT_REMOVE_MATCHES = 2
MARKET = GOALS.key
LINE = 0.5
SECTION_TITLE = "Due List · goals and assists"
BACKTEST_JSON = "due_list_backtest.json"
DUE_LIST_JSON = "due_list.json"
DUE_LIST_MD = "due_list.md"


def tier_bar(prior_total: Any, category: Category = GOALS) -> int | None:
    """The drought that lists a player on last season's total; None below the qualifier."""
    if prior_total is None or pd.isna(prior_total):
        return None
    for floor, bar in category.tiers:
        if prior_total >= floor:
            return bar
    return None


def band_label(prior_total: Any, category: Category = GOALS) -> str | None:
    """The band last season's total falls in ("20+", "15-19", "10-14"); None below the qualifier."""
    if prior_total is None or pd.isna(prior_total):
        return None
    tiers = category.tiers
    for i, (floor, _) in enumerate(tiers):
        if prior_total >= floor:
            return f"{floor}+" if i == 0 else f"{floor}-{tiers[i - 1][0] - 1}"
    return None


def rule_sentence(category: Category = GOALS) -> str:
    """The rule in one line, from the constants, so no copy of it can drift."""
    bars = ", ".join(f"{band_label(floor, category)} {category.noun} -> {bar}" for floor, bar in category.tiers)
    return (
        f"{category.threshold}+ Premier League {category.noun} last season and a run of league appearances "
        f"without {category.one} at the bar his total sets ({bars} straight games)."
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


_NEEDED = {"season", "date", "event_id", "team", "player_id", "appeared"}


def _clean_logs(logs: pd.DataFrame, category: Category = GOALS) -> pd.DataFrame:
    """The logs with `count` set to the category's column, typed and de-duplicated."""
    missing = (_NEEDED | {category.column}) - set(logs.columns)
    if missing:
        raise ValueError(f"player logs lack {sorted(missing)}")
    frame = logs.dropna(subset=["player_id", "event_id"]).copy()
    frame["player_id"] = frame["player_id"].astype(str)
    frame["event_id"] = frame["event_id"].astype(str)
    frame["season"] = pd.to_numeric(frame["season"], errors="coerce")
    frame["appeared"] = pd.to_numeric(frame["appeared"], errors="coerce")
    count = pd.to_numeric(frame[category.column], errors="coerce")
    # A missing count is not a match without one. Counting it as one would
    # extend a drought on a row that says nothing.
    frame = frame[count.notna() & frame["season"].notna() & frame["appeared"].notna()].copy()
    frame["count"] = pd.to_numeric(frame[category.column]).astype(int)
    frame["season"] = frame["season"].astype(int)
    frame["appeared"] = frame["appeared"].astype(int)
    frame["date"] = frame["date"].astype(str).str[:10]
    if "player" not in frame.columns:
        frame["player"] = ""
    return frame.drop_duplicates(subset=["player_id", "event_id"], keep="first")


def prepare_logs(logs: pd.DataFrame, category: Category = GOALS) -> pd.DataFrame:
    """Every league appearance with the drought entering it and last season's record.

    Columns added: `scored` (one or more in the category), `drought`
    (appearances without one entering this one, carried across seasons),
    `prior_total`, `prior_apps`, `prior_rate` (last season's appearances with
    one over appearances), `bar` and `listed`. The card and the backtest both
    read this, so they cannot disagree about who was due.
    """
    frame = _clean_logs(logs, category)
    frame = frame[frame["appeared"] > 0].copy()
    frame["scored"] = frame["count"] > 0
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
        .agg(prior_total=("count", "sum"), prior_apps=("scored", "size"), prior_hits=("scored", "sum"))
        .reset_index()
    )
    totals["season"] = totals["season"] + 1
    frame = frame.merge(totals, on=["player_id", "season"], how="left")
    frame["prior_rate"] = frame["prior_hits"] / frame["prior_apps"]
    frame["bar"] = frame["prior_total"].map(lambda total: tier_bar(total, category))
    frame["listed"] = frame["bar"].notna() & (frame["drought"] >= frame["bar"].fillna(10**9))
    return frame.sort_values(["date", "event_id", "player_id"]).reset_index(drop=True)


def entering(logs: pd.DataFrame, *, season: int, before: str, category: Category = GOALS) -> pd.DataFrame:
    """Each qualifier's state entering his next match of `season`, from matches before `before`.

    The same `prepare_logs`, asked about one more appearance: a sentinel row
    per qualifier dated `before`, so the drought it reports is the one
    entering that match and last season's record is read for `season`. Rows
    on or after `before` are dropped first, so a rebuilt table cannot leak a
    match into its own drought. Also carries his current club (`club`: the
    team of his latest squad this season) and `club_absent`, the number of
    his club's latest league matches in a row whose squad he was not in.
    """
    frame = _clean_logs(logs, category)
    frame = frame[frame["date"] < before]
    last = frame[(frame["season"] == season - 1) & (frame["appeared"] > 0)]
    totals = last.groupby("player_id")["count"].sum()
    qualifiers = list(totals[totals >= category.threshold].index)
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
            category.column: 0,
        }
    )
    prepared = prepare_logs(pd.concat([frame, sentinel], ignore_index=True), category)
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
    prior_total: int
    prior_apps: int
    prior_rate: float
    band: str
    bar: int
    drought: int
    one_in: int | None
    price: float | None = None
    book: str = ""
    status: str = ""
    market: str = GOALS.key

    def as_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "player_id": self.player_id,
            "team": self.team,
            "opponent": self.opponent,
            "event_id": self.event_id,
            "kickoff": self.kickoff,
            "market": self.market,
            "line": LINE,
            "prior_total": self.prior_total,
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
    category: Category = GOALS,
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
    state = entering(logs, season=season, before=before, category=category)
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
            prior_total=int(record.prior_total),
            prior_apps=int(record.prior_apps),
            prior_rate=float(record.prior_rate),
            band=band_label(record.prior_total, category) or "",
            bar=int(record.bar),
            drought=int(record.drought),
            one_in=one_in(record.prior_rate, int(record.drought)),
            price=price,
            book=book,
            status=_absence_words(absent, str(record.club)) if 0 < absent < ABSENT_REMOVE_MATCHES else "",
            market=category.key,
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


def headline_sentence(headline: dict[str, Any] | None, category: Category = GOALS) -> str:
    """One line on what being due has been worth, read from the backtest; never invented."""
    if not headline:
        return "No backtest is committed yet, so nothing is said here about what being due is worth."
    measured = (headline.get("categories") or {}).get(category.key)
    hits = measured.get("hit_rate") if isinstance(measured, dict) else None
    if not isinstance(hits, dict) or not hits.get("listed_n"):
        return f"The committed backtest has no {category.noun} headline, so nothing is said here."
    verb = "scoring" if category is GOALS else "assisting"
    if hits["diff_high"] < 0:
        verdict = f"**Being due has meant {verb} less often, not more.** "
    elif hits["diff_low"] > 0:
        verdict = f"Being due has meant {verb} more often. "
    else:
        verdict = "Being due has shown no difference either way. "
    return verdict + (
        f"Seasons {hits.get('window')}: listed players had {category.one} in {hits['listed_rate']:.1%} of "
        f"{hits['listed_n']:,} next appearances, against {hits['others_rate']:.1%} for the same "
        f"qualifiers when not due (n = {hits['others_n']:,}; difference "
        f"{hits['diff']:+.1%}, 95% {hits['diff_low']:+.1%} to {hits['diff_high']:+.1%}). "
        "No price-based measurement exists: historical player-prop prices were never bought."
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
    """The card section, one table per category. A list beside the card, never a selection."""
    out = [f"### {SECTION_TITLE}", ""]
    out.append("Context only: no units, nothing here is a selection, and no edge is shown.")
    out.append("")
    if note:
        out += [note, ""]
    for category in CATEGORIES:
        mine = [r for r in rows if r.market == category.key]
        out += [f"**{category.label}, over {LINE}.** Listed: {rule_sentence(category)}", ""]
        out += [headline_sentence(headline, category), ""]
        if not mine:
            out += ["Nobody playing in this round is due.", ""]
            continue
        out.append("| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |")
        out.append("|:--|:--|:--|:--|--:|:--|--:|:--|:--|")
        for row in mine:
            rarity = f"1 in {row.one_in:,}" if row.one_in else "—"
            kickoff = row.kickoff.replace("T", " ").replace("Z", "")[:16]
            out.append(
                f"| {row.player} | {row.team} | {row.opponent} | {kickoff} | "
                f"{row.prior_total} {category.noun}, {row.prior_rate:.0%} of apps | {row.drought} ({row.bar}) | "
                f"{rarity} | {row.status or '—'} | {_price_text(row.price, row.book)} |"
            )
        out.append("")
    if removed:
        out += ["Removed, probably not playing (missing from recent squads):", ""]
        seen: set[str] = set()
        for row, reason in removed:
            if row.player_id not in seen:
                seen.add(row.player_id)
                out.append(f"- {row.player} ({row.team}): {reason}")
    return "\n".join(out).rstrip("\n") + "\n"


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
        "categories": {
            c.key: {
                "rule": rule_sentence(c),
                "threshold": c.threshold,
                "tiers": [list(t) for t in c.tiers],
                "headline": headline_sentence(headline, c),
            }
            for c in CATEGORIES
        },
        "fetch_note": fetch_note,
        "rows": [r.as_dict() for r in rows],
        "removed": [{**r.as_dict(), "reason": why} for r, why in removed],
    }
