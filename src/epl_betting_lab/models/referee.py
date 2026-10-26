"""Each referee's bookings against what the two sides would usually collect.

A match's expected cards are the league mean times each side's card rate
(the square root of its matches' average against the league, so the two
sides share the match). A referee's factor is the cards he gave over the cards
expected in his matches, shrunk toward 1 with REFEREE_SHRINKAGE matches'
worth of league-average evidence, so a referee with three matches says almost
nothing.

Held out on 2025/26-2026/27 (450 matches, walk-forward from 2019/20) the
factor improved every bookings forecast: Poisson log likelihood -2.1100 ->
-2.1038, over 3.5 log loss 0.6886 -> 0.6850, over 4.5 0.6641 -> 0.6557. K=5,
10, 20 and 40 all helped; 20 was chosen as the middle, not the best.
"""

from __future__ import annotations

import math
import unicodedata

import pandas as pd

#: League-average matches added to every referee's record.
REFEREE_SHRINKAGE = 20

#: League-average matches added to every side's card rate.
TEAM_SHRINKAGE = 5

#: Two seasons of league matches set the league mean and the sides' rates.
RATE_WINDOW = 760


def referee_key(name: object) -> str:
    """'Michael Oliver' and Football-Data's 'M Oliver' are one referee."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    words = text.replace(".", " ").casefold().split()
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return f"{words[0][0]} {' '.join(words[1:])}"


def _cards(frame: pd.DataFrame) -> pd.Series:
    total = pd.Series(0.0, index=frame.index)
    for column in ("HY", "AY", "HR", "AR"):
        if column in frame.columns:
            total = total + pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return total


def referee_factors(
    matches: pd.DataFrame, *, shrinkage: float = REFEREE_SHRINKAGE
) -> dict[str, float]:
    """referee_key -> card factor, from every played match with a referee."""
    needed = {"Referee", "HY", "AY", "home_team", "away_team"}
    if matches is None or matches.empty or not needed <= set(matches.columns):
        return {}
    frame = matches.dropna(subset=["Referee", "HY", "AY"]).copy()
    frame = frame[frame["Referee"].astype(str).str.strip() != ""]
    if frame.empty:
        return {}
    if "date" in frame.columns:
        frame = frame.sort_values("date")
    frame["cards"] = _cards(frame)
    recent = frame.tail(RATE_WINDOW)
    league = float(recent["cards"].mean())
    if not league > 0:
        return {}

    rates: dict[str, float] = {}
    for team in set(recent["home_team"]) | set(recent["away_team"]):
        played = recent[(recent["home_team"] == team) | (recent["away_team"] == team)]
        ratio = (played["cards"].sum() + TEAM_SHRINKAGE * league) / (
            (len(played) + TEAM_SHRINKAGE) * league
        )
        rates[team] = math.sqrt(ratio)

    frame["expected"] = [
        league * rates.get(home, 1.0) * rates.get(away, 1.0)
        for home, away in zip(frame["home_team"], frame["away_team"])
    ]
    frame["key"] = frame["Referee"].map(referee_key)
    factors: dict[str, float] = {}
    for key, group in frame.groupby("key"):
        if not key:
            continue
        factors[key] = (group["cards"].sum() + shrinkage * league) / (
            group["expected"].sum() + shrinkage * league
        )
    return factors
