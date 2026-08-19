from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TeamStrength:
    attack: float
    defense: float


class PoissonGoalsModel:
    """Simple EPL goals model.

    This starter model estimates team attack/defense from recent league results.
    It is intentionally transparent and easy to adjust before becoming more advanced.
    """

    def __init__(self, max_goals: int = 7):
        self.max_goals = max_goals
        self.avg_home_goals: float | None = None
        self.avg_away_goals: float | None = None
        self.team_strengths: dict[str, TeamStrength] = {}

    def fit(self, matches: pd.DataFrame, last_n_matches_per_team: int | None = None) -> "PoissonGoalsModel":
        df = matches.dropna(subset=["home_goals", "away_goals"]).copy()
        df = df.sort_values("date")

        if last_n_matches_per_team:
            # Keep recent matches for teams by taking latest rows involving each team and de-duping.
            idx = set()
            for team in pd.concat([df["home_team"], df["away_team"]]).dropna().unique():
                team_rows = df[(df["home_team"] == team) | (df["away_team"] == team)].tail(last_n_matches_per_team)
                idx.update(team_rows.index.tolist())
            df = df.loc[sorted(idx)].copy()

        self.avg_home_goals = float(df["home_goals"].mean())
        self.avg_away_goals = float(df["away_goals"].mean())
        league_avg_goals_per_team = float((df["home_goals"].sum() + df["away_goals"].sum()) / (2 * len(df)))

        teams = sorted(set(df["home_team"]).union(set(df["away_team"])))
        strengths: dict[str, TeamStrength] = {}

        for team in teams:
            home = df[df["home_team"] == team]
            away = df[df["away_team"] == team]
            games = len(home) + len(away)
            if games == 0:
                continue

            goals_for = home["home_goals"].sum() + away["away_goals"].sum()
            goals_against = home["away_goals"].sum() + away["home_goals"].sum()

            attack = (goals_for / games) / league_avg_goals_per_team if league_avg_goals_per_team else 1.0
            defense = (goals_against / games) / league_avg_goals_per_team if league_avg_goals_per_team else 1.0
            strengths[team] = TeamStrength(attack=max(attack, 0.2), defense=max(defense, 0.2))

        self.team_strengths = strengths
        return self

    @staticmethod
    def _poisson_pmf(k: int, lam: float) -> float:
        return (math.exp(-lam) * lam**k) / math.factorial(k)

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        if self.avg_home_goals is None or self.avg_away_goals is None:
            raise RuntimeError("Model is not fit yet.")

        home = self.team_strengths.get(home_team, TeamStrength(1.0, 1.0))
        away = self.team_strengths.get(away_team, TeamStrength(1.0, 1.0))

        home_xg = self.avg_home_goals * home.attack * away.defense
        away_xg = self.avg_away_goals * away.attack * home.defense
        return round(float(home_xg), 3), round(float(away_xg), 3)

    def score_matrix(self, home_team: str, away_team: str) -> pd.DataFrame:
        home_xg, away_xg = self.expected_goals(home_team, away_team)
        rows = []
        for hg in range(self.max_goals + 1):
            for ag in range(self.max_goals + 1):
                prob = self._poisson_pmf(hg, home_xg) * self._poisson_pmf(ag, away_xg)
                rows.append({"home_goals": hg, "away_goals": ag, "prob": prob})
        return pd.DataFrame(rows)

    def match_probabilities(self, home_team: str, away_team: str) -> dict:
        mat = self.score_matrix(home_team, away_team)
        home_win = mat.loc[mat.home_goals > mat.away_goals, "prob"].sum()
        draw = mat.loc[mat.home_goals == mat.away_goals, "prob"].sum()
        away_win = mat.loc[mat.home_goals < mat.away_goals, "prob"].sum()
        over_25 = mat.loc[(mat.home_goals + mat.away_goals) > 2.5, "prob"].sum()
        under_25 = 1 - over_25
        btts_yes = mat.loc[(mat.home_goals > 0) & (mat.away_goals > 0), "prob"].sum()
        btts_no = 1 - btts_yes

        # Double chance and draw-no-bet are functions of the same three
        # outcomes, so they cost nothing to add and cannot disagree with the
        # 1X2 numbers above — they are the same numbers, combined.
        #
        # Draw-no-bet is conditional, not a sum: the draw voids the bet and the
        # stake comes back, so the fair price is P(home | not a draw). Treating
        # it as P(home) would systematically overprice both sides, which is the
        # one mistake this market invites.
        not_draw = 1.0 - draw
        if not_draw > 1e-9:
            dnb_home = home_win / not_draw
            dnb_away = away_win / not_draw
        else:
            dnb_home = dnb_away = 0.0

        home_xg, away_xg = self.expected_goals(home_team, away_team)
        top_scores = mat.sort_values("prob", ascending=False).head(5).copy()
        top_scores["score"] = top_scores["home_goals"].astype(str) + "-" + top_scores["away_goals"].astype(str)

        return {
            "home_team": home_team,
            "away_team": away_team,
            "home_xg": home_xg,
            "away_xg": away_xg,
            "home_win": round(float(home_win), 4),
            "draw": round(float(draw), 4),
            "away_win": round(float(away_win), 4),
            "over_2_5": round(float(over_25), 4),
            "under_2_5": round(float(under_25), 4),
            "btts_yes": round(float(btts_yes), 4),
            "btts_no": round(float(btts_no), 4),
            "double_chance_home_or_draw": round(float(home_win + draw), 4),
            "double_chance_draw_or_away": round(float(draw + away_win), 4),
            "double_chance_home_or_away": round(float(home_win + away_win), 4),
            "draw_no_bet_home": round(float(dnb_home), 4),
            "draw_no_bet_away": round(float(dnb_away), 4),
            "top_scores": top_scores[["score", "prob"]].assign(prob=lambda d: d["prob"].round(4)).to_dict("records"),
        }

    def project_fixtures(self, fixtures: pd.DataFrame) -> pd.DataFrame:
        records = []
        for _, row in fixtures.iterrows():
            records.append(self.match_probabilities(row["home_team"], row["away_team"]))
        return pd.DataFrame(records)
