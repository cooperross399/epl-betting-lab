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

**Prices are sampled at a fixed hour before kick-off, not at the close.** A
card is built at a set time and bet at that time, so a fixed lead is the honest
comparison. It is not the best price available and does not pretend to be.

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


def _event_btts(
    *,
    api_key: str,
    event_id: str,
    when: datetime,
    request: Requester,
    root: str,
    sport_key: str,
    timeout_seconds: float,
) -> dict[str, float]:
    """Best available price per BTTS selection, across books."""
    response = request(
        f"{root}/v4/historical/sports/{sport_key}/events/{event_id}/odds",
        params={
            "apiKey": api_key,
            "regions": "us",
            "markets": "btts",
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

    best: dict[str, float] = {}
    for bookmaker in data.get("bookmakers", []) or []:
        if not isinstance(bookmaker, Mapping):
            continue
        for market in bookmaker.get("markets", []) or []:
            if not isinstance(market, Mapping) or market.get("key") != "btts":
                continue
            for outcome in market.get("outcomes", []) or []:
                if not isinstance(outcome, Mapping):
                    continue
                selection = str(outcome.get("name", "")).strip().casefold()
                if selection not in {"yes", "no"}:
                    continue
                price = _american(outcome.get("price"))
                if price is None:
                    continue
                # Best price = the one that pays most for the same outcome.
                if selection not in best or price > best[selection]:
                    best[selection] = price
    return best


def harvest_btts_history(
    matchdays: Sequence[datetime],
    *,
    api_key: str,
    budget: HarvestBudget,
    hours_before: int = 3,
    requester: Requester | None = None,
    base_url: str = DEFAULT_API_BASE_URL,
    sport_key: str = "soccer_epl",
    timeout_seconds: float = 20.0,
) -> HarvestResult:
    """One row per fixture per matchday, carrying the best BTTS prices."""
    request = requester or _default_requester
    root = _validate_base_url(base_url)
    result = HarvestResult()

    for matchday in matchdays:
        when = matchday - timedelta(hours=hours_before)
        if not budget.can_afford():
            result.stopped_early = True
            break
        events = _slate_snapshot(
            api_key=api_key,
            when=when,
            request=request,
            root=root,
            sport_key=sport_key,
            timeout_seconds=timeout_seconds,
        )
        budget.charge()
        result.snapshots += 1
        result.events_seen += len(events)

        for event in events:
            event_id = str(event.get("id", "")).strip()
            if not event_id:
                continue
            if not budget.can_afford():
                result.stopped_early = True
                break
            prices = _event_btts(
                api_key=api_key,
                event_id=event_id,
                when=when,
                request=request,
                root=root,
                sport_key=sport_key,
                timeout_seconds=timeout_seconds,
            )
            budget.charge()
            if not prices:
                continue
            result.events_with_btts += 1
            result.rows.append(
                {
                    "sampled_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "commence_time": str(event.get("commence_time", "")),
                    "home_team": str(event.get("home_team", "")),
                    "away_team": str(event.get("away_team", "")),
                    "btts_yes_american": prices.get("yes"),
                    "btts_no_american": prices.get("no"),
                }
            )
        if result.stopped_early:
            break

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
