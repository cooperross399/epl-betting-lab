"""Harvest historical BTTS prices, so the market can finally be measured.

BTTS produces most of the picks on a card and has never been backtested for
profit, because Football-Data ships historical prices for 1X2 and the 2.5 goals
line and none at all for BTTS. The provider does sell them — confirmed by
probe — but only through the per-event historical endpoint, one event at a
time.

The shape of the job follows from that. For each matchday: one slate snapshot
to learn the event ids (10 credits), then one request per event for its BTTS
prices (10 credits each). About 110 credits a matchday, 4,180 a season.

Two decisions worth stating, because they bound what the resulting measurement
can claim:

**Prices are sampled a fixed number of hours before each fixture's own
kick-off, not at a fixed hour of the day.** The first version sampled every
matchday at one time and asked for whatever was upcoming, which bought some
fixtures twice, missed the lead entirely on others, and once returned a price
timestamped after kick-off — an in-play number that would have looked like a
very good bet. Anchoring to each fixture's kick-off fixes all three and costs
less, because each fixture is bought exactly once.

A card is built at a set time and bet at that time, so a fixed lead is the
honest comparison. It is not the closing line and does not pretend to be.

**Only the best price across books is kept, per selection.** That matches how
the card is built — it quotes the best of the books it can reach — so the
backtest measures the same decision the system would have made.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from epl_betting_lab.reports.provider_market_discovery import (
    DEFAULT_API_BASE_URL,
    Requester,
    _default_requester,
    _validate_base_url,
)


HISTORICAL_CREDITS_PER_REQUEST = 10


@dataclass
class HarvestBudget:
    """Refuses to spend past a ceiling, and says what it spent."""

    limit: int
    spent: int = 0
    refused: bool = False

    def can_afford(self, cost: int = HISTORICAL_CREDITS_PER_REQUEST) -> bool:
        if self.spent + cost > self.limit:
            self.refused = True
            return False
        return True

    def charge(self, cost: int = HISTORICAL_CREDITS_PER_REQUEST) -> None:
        self.spent += cost


@dataclass
class HarvestResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    credits_spent: int = 0
    snapshots: int = 0
    events_seen: int = 0
    events_with_btts: int = 0
    already_had: int = 0
    stopped_early: bool = False
    errors: list[str] = field(default_factory=list)


def _decimal_to_american(decimal_odds: float) -> float:
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1.0) * 100.0)
    return round(-100.0 / (decimal_odds - 1.0))


def _american(price: object) -> float | None:
    """Provider prices are already American when asked for; be defensive."""
    try:
        value = float(price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value == 0:
        return None
    # A decimal price would be a small positive number; American never is.
    if 1.0 < value < 10.0:
        return _decimal_to_american(value)
    return value


def _slate_snapshot(
    *,
    api_key: str,
    when: datetime,
    request: Requester,
    root: str,
    sport_key: str,
    timeout_seconds: float,
) -> list[Mapping[str, Any]]:
    response = request(
        f"{root}/v4/historical/sports/{sport_key}/odds",
        params={
            "apiKey": api_key,
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "american",
            "date": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        timeout=timeout_seconds,
    )
    if int(getattr(response, "status_code", 0) or 0) != 200:
        return []
    payload = response.json()
    data = payload.get("data") if isinstance(payload, Mapping) else payload
    return [event for event in (data or []) if isinstance(event, Mapping)]


def _event_prices(
    *,
    api_key: str,
    event_id: str,
    when: datetime,
    markets: Sequence[str],
    request: Requester,
    root: str,
    sport_key: str,
    timeout_seconds: float,
) -> dict[str, dict[str, float]]:
    """Best price per selection, per market, across books.

    Several markets travel in one request. Historical credits are charged per
    market per region, so asking for three markets together costs the same as
    three separate calls — but it needs one round trip and, more importantly,
    prices every market at the same instant. Prices sampled minutes apart are
    not strictly comparable, and comparing markets is the whole point.
    """
    response = request(
        f"{root}/v4/historical/sports/{sport_key}/events/{event_id}/odds",
        params={
            "apiKey": api_key,
            "regions": "us",
            "markets": ",".join(markets),
            "oddsFormat": "american",
            "date": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        timeout=timeout_seconds,
    )
    if int(getattr(response, "status_code", 0) or 0) != 200:
        return {}
    payload = response.json()
    data = payload.get("data") if isinstance(payload, Mapping) else payload
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, Mapping):
        return {}

    wanted = {m.strip() for m in markets if m.strip()}
    best: dict[str, dict[tuple[str, str], float]] = {}
    for bookmaker in data.get("bookmakers", []) or []:
        if not isinstance(bookmaker, Mapping):
            continue
        for market in bookmaker.get("markets", []) or []:
            if not isinstance(market, Mapping):
                continue
            key = str(market.get("key", "")).strip()
            if key not in wanted:
                continue
            for outcome in market.get("outcomes", []) or []:
                if not isinstance(outcome, Mapping):
                    continue
                name = str(outcome.get("name", "")).strip()
                point = outcome.get("point")
                # Keep the line in the selection name, so a totals ladder does
                # not collapse every line into one column.
                selection = name if point is None else f"{name}@{point}"
                # Player-prop outcomes name the player in `description`. It is
                # part of the outcome's identity: without it every player's
                # "Over@0.5" is the same key and the ladder collapses into one
                # meaningless best price — which is exactly what the first
                # props harvest bought.
                player = str(outcome.get("description", "")).strip()
                price = _american(outcome.get("price"))
                if price is None:
                    continue
                slot = best.setdefault(key, {})
                identity = (player, selection)
                # Best price = the one that pays most for the same outcome.
                if identity not in slot or price > slot[identity]:
                    slot[identity] = price
    return best


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _fixture_key(event: Mapping[str, Any]) -> str:
    """Identity of a fixture, so it is never bought twice."""
    kickoff = _parse_time(event.get("commence_time"))
    day = kickoff.strftime("%Y-%m-%d") if kickoff else ""
    home = str(event.get("home_team", "")).strip().casefold()
    away = str(event.get("away_team", "")).strip().casefold()
    return f"{day}|{home}|{away}"


def harvest_btts_history(
    matchdays: Sequence[datetime],
    *,
    api_key: str,
    budget: HarvestBudget,
    hours_before: int = 3,
    markets: Sequence[str] = ("btts",),
    already_harvested: Sequence[str] = (),
    requester: Requester | None = None,
    base_url: str = DEFAULT_API_BASE_URL,
    sport_key: str = "soccer_epl",
    timeout_seconds: float = 20.0,
) -> HarvestResult:
    """One row per fixture per matchday, carrying the best BTTS prices."""
    request = requester or _default_requester
    root = _validate_base_url(base_url)
    result = HarvestResult()

    # Learn each fixture's kick-off first, then price it at its own lead. One
    # paid request per fixture, at the right moment, with no duplicates.
    seen: set[str] = set(already_harvested or ())
    fixtures: dict[str, Mapping[str, Any]] = {}
    for matchday in matchdays:
        if not budget.can_afford():
            result.stopped_early = True
            break
        events = _slate_snapshot(
            api_key=api_key,
            when=matchday,
            request=request,
            root=root,
            sport_key=sport_key,
            timeout_seconds=timeout_seconds,
        )
        budget.charge()
        result.snapshots += 1
        for event in events:
            event_id = str(event.get("id", "")).strip()
            if event_id and event_id not in fixtures:
                fixtures[event_id] = event

    result.events_seen = len(fixtures)

    for event_id, event in fixtures.items():
        key = _fixture_key(event)
        if key in seen:
            result.already_had += 1
            continue
        kickoff = _parse_time(event.get("commence_time"))
        if kickoff is None:
            result.errors.append(f"Event {event_id}: unreadable kick-off time.")
            continue
        when = kickoff - timedelta(hours=hours_before)
        if not budget.can_afford(HISTORICAL_CREDITS_PER_REQUEST * len(markets)):
            result.stopped_early = True
            break
        prices = _event_prices(
            api_key=api_key,
            event_id=event_id,
            when=when,
            markets=markets,
            request=request,
            root=root,
            sport_key=sport_key,
            timeout_seconds=timeout_seconds,
        )
        budget.charge(HISTORICAL_CREDITS_PER_REQUEST * len(markets))
        if not prices:
            continue
        result.events_with_btts += 1
        seen.add(key)
        base = {
            "sampled_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commence_time": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "home_team": str(event.get("home_team", "")),
            "away_team": str(event.get("away_team", "")),
        }
        # One row per market per selection. A wide table would need a column
        # per line of every ladder and would change shape whenever a book added
        # one; long rows survive that. `player` is empty for match-level
        # markets and names the player for prop markets.
        for market_key, selections in sorted(prices.items()):
            for (player, selection), price in sorted(selections.items()):
                result.rows.append(
                    {
                        **base,
                        "market": market_key,
                        "player": player,
                        "selection": selection,
                        "american": price,
                    }
                )

    result.credits_spent = budget.spent
    return result


def matchdays_between(
    start: datetime, end: datetime, *, hour: int = 15
) -> list[datetime]:
    """Every day in the range, at a fixed hour.

    Days without fixtures cost one slate snapshot and return nothing, which is
    cheaper than a separate calendar and cannot disagree with one.
    """
    # Compare on the day, not the timestamp. Setting the hour first and then
    # comparing against an end given at midnight silently dropped the last day
    # of every range.
    days: list[datetime] = []
    current = start.date()
    final = end.date()
    while current <= final:
        days.append(
            datetime(
                current.year, current.month, current.day, hour, tzinfo=timezone.utc
            )
        )
        current += timedelta(days=1)
    return days
