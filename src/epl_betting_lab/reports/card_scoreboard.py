"""Score the cards that were actually issued.

The system recommends bets and then loses track of them. `bet_ledger.csv` has
a header and no rows, and settlement is preview-only, so nothing has ever
recorded how a recommendation turned out. Every claim about whether this works
rests on a backtest of seasons already in the file — in-sample, by definition.

This scores the cards themselves rather than what anyone bet. That needs no
manual entry, and it is the honest measure of the model anyway: what it said,
at the price it said it at, judged against what happened.

Three decisions bound what the number means.

**The first card to name a selection is the one scored.** A selection can
appear on Thursday and again on Saturday at a different price. Taking the
latest would score a price nobody could have acted on first; taking the first
matches the way a card is read — you see it, you take it.

**Only staked rows count.** A lean carries no stake and is not a
recommendation, so scoring it would measure something the card explicitly does
not advise.

**A fixture with no result yet is pending, not a loss.** Cards are issued days
before kick-off, so most of what is on file at any moment has not been played.

**A result only counts if it happened after the card was issued.** The same
fixture pairing recurs every season. Matching on team names alone scored a card
for 21 August 2026 against Newcastle versus Liverpool from 25 August 2025, and
returned a confident nought for five — the kind of wrong number that looks like
a finding.

**Every market the card can stake is settled here, or the count says so.**
Corners were not. `settle` knew five markets and the card stakes eight, so the
three corner markets returned None and were quietly counted as pending — 23 of
the 42 best bets across the first eight cards, 55% of everything the card had
recommended, sitting in a queue that could never resolve. The published record
therefore described a minority of the card while its "still pending" number
grew forever. Football-Data ships corner counts in the same rows as the
scorelines, so the data was on disk the whole time.

Two consequences are built in below. A selection that cannot be settled is
counted apart from one that is merely waiting for kick-off, because those are
different facts and only one of them resolves with time. And
`test_every_market_the_card_can_stake_is_settleable` reads
`market_eligibility.MARKET_SELECTIONS` directly, so a market cannot enter card
scope again without a settlement rule arriving with it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd


#: Corner markets and the line each is settled against. `corners_1x2` has no
#: line — it compares the two counts — so it is listed with None.
CORNER_MARKETS: dict[str, float | None] = {
    "corners_1x2": None,
    "corners_total_9_5": 9.5,
    "corners_total_10_5": 10.5,
}


@dataclass
class ScoredSelection:
    fixture_date: str
    home_team: str
    away_team: str
    market: str
    selection: str
    american_odds: float
    stake_units: float
    first_seen: str
    won: bool | None = None
    profit_units: float = 0.0

    @property
    def settled(self) -> bool:
        return self.won is not None


@dataclass
class Scoreboard:
    scored: list[ScoredSelection] = field(default_factory=list)
    #: Fixture not played yet. Resolves with time.
    pending: int = 0
    #: Stake returned — a draw_no_bet push. Neither win nor loss, and settled
    #: in the sense that it is over.
    void: int = 0
    #: No settlement rule, or a result missing the data the rule needs. Does
    #: NOT resolve with time, which is why it is not counted as pending: for
    #: three weeks the corner markets sat in the pending queue and the record
    #: looked like it was accumulating when it was not.
    unsettleable: int = 0

    @property
    def settled(self) -> list[ScoredSelection]:
        return [s for s in self.scored if s.settled]

    @property
    def staked_units(self) -> float:
        return sum(s.stake_units for s in self.settled)

    @property
    def profit_units(self) -> float:
        return sum(s.profit_units for s in self.settled)

    @property
    def roi(self) -> float | None:
        staked = self.staked_units
        return self.profit_units / staked if staked else None


def _key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("home_team", "")).strip().casefold(),
        str(row.get("away_team", "")).strip().casefold(),
        str(row.get("market", "")).strip().casefold(),
        str(row.get("selection", "")).strip().casefold(),
    )


def _stake(row: Mapping[str, Any]) -> float:
    try:
        return float(row.get("suggested_units") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def load_archived_cards(archive_root: Path) -> list[dict[str, Any]]:
    """Every archived card, oldest first."""
    if not archive_root.is_dir():
        return []
    cards: list[dict[str, Any]] = []
    for path in sorted(archive_root.glob("*/*/automated_card.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping):
            cards.append(dict(payload))
    return cards


def first_recommendations(cards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each staked selection at the first price a card offered it."""
    seen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for card in cards:
        if not card.get("card_generated"):
            continue
        generated = str(card.get("generated_at", ""))
        for row in card.get("best_bets") or []:
            if not isinstance(row, Mapping):
                continue
            if _stake(row) <= 0:
                # A lean carries no stake and is not a recommendation.
                continue
            key = _key(row)
            if key in seen:
                continue
            seen[key] = {**row, "first_seen": generated}
    return list(seen.values())


def settle(
    market: str,
    selection: str,
    home_goals: int,
    away_goals: int,
    *,
    home_corners: int | None = None,
    away_corners: int | None = None,
) -> bool | None:
    """Did this selection win?

    None means "not a win and not a loss": a void stake, a market with no rule
    here, or a corner market whose result carries no corner counts. The caller
    distinguishes those cases; `settleable_markets` names the ones a rule
    exists for at all.
    """
    if market == "1x2":
        return {
            "home": home_goals > away_goals,
            "draw": home_goals == away_goals,
            "away": away_goals > home_goals,
        }.get(selection)
    if market == "btts":
        both = home_goals > 0 and away_goals > 0
        return {"yes": both, "no": not both}.get(selection)
    if market == "total_2_5":
        total = home_goals + away_goals
        return {"over": total > 2.5, "under": total < 2.5}.get(selection)
    if market == "double_chance":
        return {
            "home_or_draw": home_goals >= away_goals,
            "draw_or_away": away_goals >= home_goals,
            "home_or_away": home_goals != away_goals,
        }.get(selection)
    if market == "draw_no_bet":
        if home_goals == away_goals:
            return None  # stake returned; not a win and not a loss
        return {"home": home_goals > away_goals, "away": away_goals > home_goals}.get(
            selection
        )
    if market in CORNER_MARKETS:
        # Football-Data ships corner counts (HC/AC) beside the scoreline. A
        # result without them settles nothing rather than guessing.
        if home_corners is None or away_corners is None:
            return None
        if market == "corners_1x2":
            return {
                "home": home_corners > away_corners,
                "draw": home_corners == away_corners,
                "away": away_corners > home_corners,
            }.get(selection)
        line = CORNER_MARKETS[market]
        total = home_corners + away_corners
        # The lines are halves, so a push is impossible by construction.
        return {"over": total > line, "under": total < line}.get(selection)
    return None


def settleable_markets() -> frozenset[str]:
    """Markets `settle` has a rule for, whatever the result data turns out to be."""
    return frozenset(
        {"1x2", "btts", "total_2_5", "double_chance", "draw_no_bet"} | set(CORNER_MARKETS)
    )


def _profit(won: bool, american_odds: float, stake_units: float) -> float:
    if not won:
        return -stake_units
    if american_odds > 0:
        return stake_units * american_odds / 100.0
    return stake_units * 100.0 / abs(american_odds)


def build_scoreboard(
    cards: Sequence[Mapping[str, Any]],
    results: pd.DataFrame,
    *,
    now: datetime | None = None,
) -> Scoreboard:
    """Score every staked recommendation whose fixture has been played."""
    board = Scoreboard()
    if not cards:
        return board

    # Fixture -> every result for that pairing, with its date. The pairing
    # alone is not an identity: it recurs every season.
    # Corner counts ride along with the scoreline: HC/AC are Football-Data's
    # columns and are present on every row of the processed dataset, so the
    # corner markets are settleable from exactly the same results frame.
    played: dict[tuple[str, str], list[tuple[pd.Timestamp, int, int, int | None, int | None]]] = {}
    if not results.empty:
        for _, row in results.iterrows():
            if pd.isna(row.get("home_goals")) or pd.isna(row.get("away_goals")):
                continue
            when = pd.to_datetime(row.get("date"), errors="coerce")
            if pd.isna(when):
                continue
            key = (
                str(row["home_team"]).strip().casefold(),
                str(row["away_team"]).strip().casefold(),
            )
            corners = tuple(
                None if pd.isna(row.get(column)) else int(row.get(column))
                for column in ("HC", "AC")
            )
            played.setdefault(key, []).append(
                (when, int(row["home_goals"]), int(row["away_goals"]), *corners)
            )

    for row in first_recommendations(cards):
        fixture = (
            str(row.get("home_team", "")).strip().casefold(),
            str(row.get("away_team", "")).strip().casefold(),
        )
        market = str(row.get("market", "")).strip().casefold()
        selection = str(row.get("selection", "")).strip().casefold()
        try:
            american = float(row.get("american_odds"))
        except (TypeError, ValueError):
            continue
        stake = _stake(row)
        entry = ScoredSelection(
            fixture_date="",
            home_team=str(row.get("home_team", "")),
            away_team=str(row.get("away_team", "")),
            market=market,
            selection=selection,
            american_odds=american,
            stake_units=stake,
            first_seen=str(row.get("first_seen", "")),
        )
        issued = pd.to_datetime(entry.first_seen, errors="coerce", utc=True)
        candidates = [
            item
            for item in played.get(fixture, [])
            if pd.isna(issued) or item[0].tz_localize("UTC") >= issued.normalize()
        ]
        if not candidates:
            board.pending += 1
            board.scored.append(entry)
            continue
        # The first result after the card was issued is the one it meant.
        when, home_goals, away_goals, home_corners, away_corners = min(
            candidates, key=lambda item: item[0]
        )
        entry.fixture_date = when.strftime("%Y-%m-%d")
        won = settle(
            market,
            selection,
            home_goals,
            away_goals,
            home_corners=home_corners,
            away_corners=away_corners,
        )
        if won is None:
            # Three different facts, counted apart. A push is over; a market
            # with no rule never resolves; and neither is "waiting for
            # kick-off", which is what they used to be filed as.
            if market not in settleable_markets():
                board.unsettleable += 1
            elif market in CORNER_MARKETS and (home_corners is None or away_corners is None):
                board.unsettleable += 1
            else:
                board.void += 1
            board.scored.append(entry)
            continue
        entry.won = won
        entry.profit_units = _profit(won, american, stake)
        board.scored.append(entry)
    return board


def render_scoreboard(board: Scoreboard) -> list[str]:
    """Markdown lines for the run summary and the emailed card."""
    settled = board.settled
    if not settled and not board.pending:
        return []
    lines = ["### How the recommendations have done", ""]
    if not settled:
        lines += [
            f"Nothing settled yet. {board.pending} selection(s) are waiting on "
            "results"
            + (f", and {board.unsettleable} cannot be settled" if board.unsettleable else "")
            + ".",
            "",
        ]
        return lines
    wins = sum(1 for s in settled if s.won)
    roi = board.roi
    lines += [
        f"- Settled: **{len(settled)}** selections, {wins} won",
        f"- Staked: {board.staked_units:.2f} units",
        f"- Profit: **{board.profit_units:+.2f} units**"
        + (f" ({roi:+.1%} on turnover)" if roi is not None else ""),
        f"- Still pending: {board.pending}",
        "",
    ]
    if board.void:
        lines.append(f"- Stake returned (void): {board.void}")
    if board.unsettleable:
        lines.append(
            f"- Cannot be settled: **{board.unsettleable}** — no settlement rule, "
            "or a result without the data the rule needs. These never resolve, so "
            "they are counted apart from pending rather than inflating it."
        )
    if board.void or board.unsettleable:
        lines.append("")
    lines += [
        "Each selection is scored at the first price a card offered it, and "
        "only rows the card staked are counted — a lean carries no stake and is "
        "not a recommendation.",
        "",
        "This is the only out-of-sample evidence this project has. It will take "
        "a long time to mean anything: separating a real 5% edge from zero needs "
        "roughly 1,500 settled bets.",
        "",
    ]
    return lines
