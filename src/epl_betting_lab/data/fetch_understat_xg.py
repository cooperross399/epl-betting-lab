"""Per-match team expected goals from Understat, joined to Football-Data names.

Goals are a noisy measure of how well a team played: a side can dominate and
lose 1-0 to a deflection, and a rating fitted on goals learns the deflection.
Expected goals score the chances rather than the outcomes, and settle to a
team's true level in far fewer matches. The ratings can be fitted on either,
or on a blend, and the choice is measured like everything else — on log loss
against the closing market and on a price-based backtest.

Understat's league endpoint returns every match of a season with `xG.h` and
`xG.a`. Its team names differ from Football-Data's for five clubs, and those
five are mapped explicitly below; the map was derived by matching every
Understat result to the Football-Data result on the same date with the same
score, which matched all 1,920 fixtures across six seasons with none left over.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable, Mapping

import pandas as pd

from epl_betting_lab.config import PROCESSED_DIR, RAW_DIR
from epl_betting_lab.providers.understat_players import (
    UNDERSTAT_BASE_URL,
    UnderstatError,
    _default_requester,
)

#: Understat naming -> Football-Data naming. Every other club spells the same.
UNDERSTAT_TO_FOOTBALL_DATA: dict[str, str] = {
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Wolverhampton Wanderers": "Wolves",
}

#: Understat seasons are named by the year they start: "2025" is 2025/26.
DEFAULT_UNDERSTAT_SEASONS = ("2021", "2022", "2023", "2024", "2025", "2026")

XG_FILENAME = "understat_team_xg.csv"


def football_data_name(understat_name: str) -> str:
    return UNDERSTAT_TO_FOOTBALL_DATA.get(understat_name.strip(), understat_name.strip())


def raw_path(season: str, raw_dir: Path = RAW_DIR) -> Path:
    return raw_dir / f"understat_league_EPL_{season}.json"


def rows_from_payload(payload: Mapping) -> list[dict]:
    dates = payload.get("dates") if isinstance(payload, Mapping) else None
    if not isinstance(dates, list):
        raise UnderstatError("Understat league data has no match list.")
    rows = []
    for item in dates:
        if not isinstance(item, Mapping):
            continue
        rows.append({
            "match_id": str(item.get("id", "")).strip(),
            "datetime": str(item.get("datetime", "")).strip(),
            "is_result": bool(item.get("isResult")),
            "home": str((item.get("h") or {}).get("title", "")).strip(),
            "away": str((item.get("a") or {}).get("title", "")).strip(),
            "home_goals": (item.get("goals") or {}).get("h"),
            "away_goals": (item.get("goals") or {}).get("a"),
            "home_xg": (item.get("xG") or {}).get("h"),
            "away_xg": (item.get("xG") or {}).get("a"),
        })
    return rows


def fetch_season(
    season: str,
    *,
    raw_dir: Path = RAW_DIR,
    requester: Callable[[str], object] | None = None,
    base_url: str = UNDERSTAT_BASE_URL,
    force: bool = False,
) -> list[dict]:
    """One season's matches with xG, cached as JSON so reruns cost no request."""
    path = raw_path(season, raw_dir)
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    request = requester or _default_requester
    rows = rows_from_payload(request(f"{base_url}/getLeagueData/EPL/{season}"))
    raw_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def build_team_xg(rows: Iterable[Mapping]) -> pd.DataFrame:
    """Played matches only, in Football-Data naming, one row per fixture."""
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return pd.DataFrame(columns=["date", "home_team", "away_team", "home_xg", "away_xg"])
    frame = frame[frame["is_result"] == True].copy()
    frame["date"] = pd.to_datetime(frame["datetime"], errors="coerce").dt.normalize()
    frame["home_team"] = frame["home"].map(football_data_name)
    frame["away_team"] = frame["away"].map(football_data_name)
    for column in ("home_xg", "away_xg"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "home_xg", "away_xg"])
    out = frame[["date", "home_team", "away_team", "home_xg", "away_xg"]]
    return out.drop_duplicates(subset=["date", "home_team", "away_team"]).reset_index(drop=True)


def fetch_and_build_team_xg(
    seasons: Iterable[str] = DEFAULT_UNDERSTAT_SEASONS,
    *,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    force: bool = False,
    requester: Callable[[str], object] | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []
    for season in seasons:
        rows.extend(fetch_season(season, raw_dir=raw_dir, requester=requester, force=force))
    table = build_team_xg(rows)
    processed_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(processed_dir / XG_FILENAME, index=False)
    return table
