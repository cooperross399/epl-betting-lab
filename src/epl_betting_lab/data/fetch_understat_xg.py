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


# ---------------------------------------------------------------------------
# When Understat cannot be read
#
# From 2026-11-02 every Understat request answered with something other than
# JSON. The fetch raised before writing anything, so the table kept the rows an
# earlier run had written and every match played since was rated on goals. The
# ratings the 2.5 line, BTTS and the team totals run on are 70% xG.
#
# Fantasy Premier League publishes Opta's expected goals for every appearance
# this season, keyless, and the props refresh already carries those logs from
# run to run (`fpl_match_logs.csv`, in `matchday-state`). Summed per club and
# match they are a team xG. Opta's and Understat's models are not the same
# model, so the filled rows are scaled to Understat's level on the matches both
# sources hold; with too few of those to measure, they are left unscaled.
# ---------------------------------------------------------------------------

FPL_LOGS_FILENAME = "fpl_match_logs.csv"

#: Matches both sources must hold before the scale is measured rather than 1.
MIN_OVERLAP_FOR_SCALE = 20

#: The scale is a correction between two xG models, not a free parameter.
SCALE_BOUNDS = (0.8, 1.25)

_KEY = ["date", "home_team", "away_team"]


def team_xg_from_fpl_logs(logs: pd.DataFrame) -> pd.DataFrame:
    """One row per match FPL's logs cover from both sides, in the table's columns."""
    columns = ["date", "home_team", "away_team", "home_xg", "away_xg"]
    needed = {"date", "team", "opponent", "venue", "expected_goals"}
    if logs is None or logs.empty or not needed <= set(logs.columns):
        return pd.DataFrame(columns=columns)
    frame = logs.copy()
    frame["expected_goals"] = pd.to_numeric(frame["expected_goals"], errors="coerce").fillna(0.0)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date"])
    sums = frame.groupby(["date", "team", "opponent", "venue"], as_index=False)["expected_goals"].sum()
    home = sums[sums["venue"] == "home"].rename(
        columns={"team": "home_team", "opponent": "away_team", "expected_goals": "home_xg"}
    )
    away = sums[sums["venue"] == "away"].rename(
        columns={"team": "away_team", "opponent": "home_team", "expected_goals": "away_xg"}
    )
    out = home.drop(columns="venue").merge(away.drop(columns="venue"), on=_KEY, how="inner")
    return out[columns].reset_index(drop=True)


def _scale(understat: pd.DataFrame, fpl: pd.DataFrame) -> tuple[float, int]:
    both = understat.merge(fpl, on=_KEY, suffixes=("_u", "_f"))
    if len(both) < MIN_OVERLAP_FOR_SCALE:
        return 1.0, len(both)
    opta = float(both["home_xg_f"].sum() + both["away_xg_f"].sum())
    if opta <= 0:
        return 1.0, len(both)
    ratio = float(both["home_xg_u"].sum() + both["away_xg_u"].sum()) / opta
    low, high = SCALE_BOUNDS
    return min(max(ratio, low), high), len(both)


def _read_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(columns=["date", "home_team", "away_team", "home_xg", "away_xg"])
    table = pd.read_csv(path)
    table["date"] = pd.to_datetime(table["date"], errors="coerce").dt.normalize()
    return table.dropna(subset=["date"])


def fetch_and_fill_team_xg(
    seasons: Iterable[str] = DEFAULT_UNDERSTAT_SEASONS,
    *,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    force: bool = False,
    requester: Callable[[str], object] | None = None,
    fpl_logs_path: Path | None = None,
) -> tuple[pd.DataFrame, str]:
    """Understat's table, else the table already on disk, topped up from FPL.

    Returns the table written and a sentence saying where it came from.
    Raises the Understat error only when Understat failed AND nothing could
    be added from FPL, because then the ratings really are on goals for
    every match since the last good fetch, and the run must say so.
    """
    try:
        return fetch_and_build_team_xg(
            seasons, raw_dir=raw_dir, processed_dir=processed_dir, force=force,
            requester=requester,
        ), "Team xG: Understat."
    except (UnderstatError, OSError, ValueError) as exc:
        failure = exc
    target = processed_dir / XG_FILENAME
    held = _read_table(target)
    fpl_path = fpl_logs_path or (processed_dir / FPL_LOGS_FILENAME)
    fpl_logs = pd.read_csv(fpl_path, dtype=str) if fpl_path.is_file() else pd.DataFrame()
    fpl = team_xg_from_fpl_logs(fpl_logs)
    missing = fpl.merge(held[_KEY], on=_KEY, how="left", indicator=True)
    missing = missing[missing["_merge"] == "left_only"].drop(columns="_merge")
    if missing.empty:
        raise failure
    scale, overlap = _scale(held, fpl)
    missing = missing.assign(home_xg=missing["home_xg"] * scale, away_xg=missing["away_xg"] * scale)
    table = (
        pd.concat([held, missing], ignore_index=True)
        .sort_values(_KEY)
        .reset_index(drop=True)
    )
    processed_dir.mkdir(parents=True, exist_ok=True)
    table.assign(date=table["date"].dt.strftime("%Y-%m-%d")).to_csv(target, index=False)
    noun = "match" if len(missing) == 1 else "matches"
    note = (
        f"Team xG: Understat could not be read ({failure}); kept {len(held)} match(es) "
        f"already on file and filled {len(missing)} {noun} from Fantasy Premier League's "
        f"Opta expected goals, scaled by {scale:.3f} to Understat's level "
        f"(measured on {overlap} match(es) both sources hold)."
    )
    return table, note
