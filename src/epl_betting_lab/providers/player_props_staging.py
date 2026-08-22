"""Fetch live player-prop prices into their own staging file.

Props deliberately do not travel in `current_odds_staging.csv`: the match
staging schema has no player and the odds validator rightly errors on a
market it does not know, so a prop row there would block every card. This
module keeps props in `data/staging/player_props_staging.csv`, a separate
long-form file with a `player` column and the harvest's `Over@line`
selection convention, reachable by the props tooling and invisible to the
card pipeline until the day a reviewed policy approval wires them in.

Only the four markets the model can price are fetched — shots, shots on
target, assists, anytime scorer. Cards are not fetched because the model
deliberately does not price them, and first/last scorer are not fetched
because ordering is not a rate the model measures. A price nothing can
price is quota spent on nothing.

Cost is stated before it is spent: one credit per market per event, so a
full ten-fixture slate costs about forty credits. The fetch never runs on a
schedule from here — it is dispatched deliberately, exactly like the
historical harvest.

No pick, no card, no ledger, no policy edit, no cron, and the credential is
never printed or written.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import STAGING_DIR
from epl_betting_lab.providers.team_names import normalize_team_name
from epl_betting_lab.reports.provider_market_discovery import (
    DEFAULT_API_BASE_URL,
    Requester,
    _default_requester,
)


PROPS_STAGING_FILENAME = "player_props_staging.csv"

#: The prop markets the player model prices. Fetching a market the model
#: cannot price spends quota on nothing.
PROP_EVENT_MARKETS: tuple[str, ...] = (
    "player_shots",
    "player_shots_on_target",
    "player_assists",
    "player_goal_scorer_anytime",
)

#: One credit per market per event on the live per-event endpoint.
LIVE_CREDITS_PER_EVENT = len(PROP_EVENT_MARKETS)

PROPS_COLUMNS = (
    "date",
    "commence_time",
    "home_team",
    "away_team",
    "market",
    "player",
    "selection",
    "american_odds",
    "book",
    "notes",
)

SPORT_KEY = "soccer_epl"


class PlayerPropsFetchError(RuntimeError):
    """Raised when the live fetch cannot answer safely."""


@dataclass
class PropsFetchResult:
    """What one live props fetch did and what it cost."""

    events_seen: int = 0
    events_priced: int = 0
    credits_spent: int = 0
    rows: list[dict[str, object]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _american(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_prop_rows(
    event: Mapping[str, Any],
    *,
    fetched_at: str,
) -> list[dict[str, object]]:
    """Long-form prop rows from one per-event odds payload.

    Every book's price is kept, matching the match staging file: the card
    quotes the best reachable book, so the data must hold them all.
    """
    event_id = str(event.get("id", "")).strip()
    commence = str(event.get("commence_time", "")).strip()
    home = normalize_team_name(str(event.get("home_team", "")).strip())
    away = normalize_team_name(str(event.get("away_team", "")).strip())
    rows: list[dict[str, object]] = []
    for bookmaker in event.get("bookmakers", []) or []:
        if not isinstance(bookmaker, Mapping):
            continue
        book = str(bookmaker.get("title") or bookmaker.get("key") or "").strip()
        for market in bookmaker.get("markets", []) or []:
            if not isinstance(market, Mapping):
                continue
            key = str(market.get("key", "")).strip()
            if key not in PROP_EVENT_MARKETS:
                continue
            for outcome in market.get("outcomes", []) or []:
                if not isinstance(outcome, Mapping):
                    continue
                player = str(outcome.get("description", "")).strip()
                name = str(outcome.get("name", "")).strip()
                if not player or not name:
                    continue
                point = outcome.get("point")
                selection = name if point is None else f"{name}@{point}"
                price = _american(outcome.get("price"))
                if price is None:
                    continue
                rows.append(
                    {
                        "date": commence[:10],
                        "commence_time": commence,
                        "home_team": home,
                        "away_team": away,
                        "market": key,
                        "player": player,
                        "selection": selection,
                        "american_odds": price,
                        "book": book,
                        "notes": (
                            f"the_odds_api event {event_id}; "
                            f"fetched {fetched_at}"
                        ),
                    }
                )
    return rows


def fetch_player_props(
    *,
    api_key: str,
    requester: Requester | None = None,
    base_url: str = DEFAULT_API_BASE_URL,
    markets: Sequence[str] = PROP_EVENT_MARKETS,
    max_events: int = 0,
    fetched_at: str = "",
    timeout_seconds: float = 30.0,
) -> PropsFetchResult:
    """Fetch live prop prices for the upcoming slate.

    The events list is free; each event's props cost one credit per market.
    `max_events` caps spending for probes; zero means the whole slate.
    """
    if not api_key:
        raise PlayerPropsFetchError(
            "A live props fetch requires the provider credential."
        )
    request = requester or _default_requester
    result = PropsFetchResult()

    response = request(
        f"{base_url}/v4/sports/{SPORT_KEY}/events",
        params={"apiKey": api_key},
        timeout=timeout_seconds,
    )
    if int(getattr(response, "status_code", 0) or 0) != 200:
        raise PlayerPropsFetchError(
            f"The provider answered HTTP "
            f"{getattr(response, 'status_code', 'unknown')} for the events list."
        )
    events = response.json()
    if not isinstance(events, list):
        raise PlayerPropsFetchError("The events list is not a JSON list.")
    result.events_seen = len(events)

    selected = events[:max_events] if max_events else events
    for event in selected:
        if not isinstance(event, Mapping):
            continue
        event_id = str(event.get("id", "")).strip()
        if not event_id:
            continue
        detail = request(
            f"{base_url}/v4/sports/{SPORT_KEY}/events/{event_id}/odds",
            params={
                "apiKey": api_key,
                "regions": "us",
                "markets": ",".join(markets),
                "oddsFormat": "american",
            },
            timeout=timeout_seconds,
        )
        result.credits_spent += len(markets)
        if int(getattr(detail, "status_code", 0) or 0) != 200:
            result.errors.append(
                f"Event {event_id}: HTTP {getattr(detail, 'status_code', '?')}."
            )
            continue
        payload = detail.json()
        if not isinstance(payload, Mapping):
            result.errors.append(f"Event {event_id}: malformed payload.")
            continue
        rows = extract_prop_rows(payload, fetched_at=fetched_at)
        if rows:
            result.events_priced += 1
            result.rows.extend(rows)
    return result


def write_props_staging(
    rows: list[dict[str, object]],
    *,
    staging_dir: Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Write the props staging CSV. Refuses to replace evidence by accident."""
    directory = Path(staging_dir) if staging_dir else Path(STAGING_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / PROPS_STAGING_FILENAME
    if target.exists() and not overwrite:
        raise PlayerPropsFetchError(
            f"{target} already exists. Review it first; pass overwrite only "
            "for intentional replacement."
        )
    frame = pd.DataFrame(rows, columns=list(PROPS_COLUMNS))
    frame.to_csv(target, index=False, lineterminator="\n")
    return target
