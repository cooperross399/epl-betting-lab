from __future__ import annotations

import pandas as pd

PROMOTED_2026_27 = {"Coventry City", "Hull City", "Ipswich Town"}
BIG_SIXISH = {"Arsenal", "Arsenal FC", "Manchester City", "Liverpool", "Liverpool FC", "Chelsea", "Chelsea FC", "Manchester United", "Tottenham", "Tottenham Hotspur"}


def flag_promoted_team_spots(fixtures: pd.DataFrame, promoted: set[str] | None = None) -> pd.DataFrame:
    """Flag promoted-team matchup spots for manual review.

    This does not auto-bet. It tells us where to look for alternate angles:
    favorite -1, favorite win + under, promoted team under total, clean sheet, etc.
    """
    promoted = promoted or PROMOTED_2026_27
    rows = []
    for _, g in fixtures.iterrows():
        home_promoted = g.home_team in promoted
        away_promoted = g.away_team in promoted
        if not home_promoted and not away_promoted:
            continue

        promoted_team = g.home_team if home_promoted else g.away_team
        opponent = g.away_team if home_promoted else g.home_team
        spot = "promoted_home" if home_promoted else "promoted_away"
        notes = []
        if opponent in BIG_SIXISH:
            notes.append("vs elite opponent")
        if away_promoted:
            notes.append("promoted team away")
        rows.append({
            "date": g.date,
            "home_team": g.home_team,
            "away_team": g.away_team,
            "spot": spot,
            "promoted_team": promoted_team,
            "opponent": opponent,
            "review_angles": "favorite -1 / win+under / promoted team under / BTTS No",
            "notes": "; ".join(notes) if notes else "manual review",
        })
    return pd.DataFrame(rows)
