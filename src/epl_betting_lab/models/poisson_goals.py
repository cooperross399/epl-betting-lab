from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TeamStrength:
    attack: float
    defense: float


@dataclass(frozen=True)
class RatingConfig:
    """How team attack and defence are estimated from past results.

    The original ratings were a team's goals per game divided by the league
    average, over its last `last_n_matches_per_team` games. Two things are
    wrong with that, and both are fixable without new data.

    **It ignores who the goals were against.** Three past Coventry counted the
    same as three past Man City, so a team with an easy run looked strong and
    was then bet at a price that already knew better. `opponent_adjusted`
    replaces the raw ratio with the standard multiplicative Poisson fit: a
    team's attack is its goals scored divided by what an average attack would
    have scored against those particular defences, solved jointly for every
    team by iteration.

    **It treats a match from four years ago as it treats last week's**, or else
    discards it entirely at an arbitrary cut-off. `half_life_days` weights each
    match by age instead, so evidence fades rather than falling off a cliff.

    `prior_matches` shrinks a team toward league average by the weight of that
    many average games. Promoted sides arrive with almost no top-flight
    history, and an unshrunk fit will happily call three games' worth of noise
    a strength.
    """

    opponent_adjusted: bool = False
    half_life_days: float | None = None
    iterations: int = 12
    prior_matches: float = 8.0
    #: What a match teaches about a team: its goals, its expected goals, or a
    #: blend. Goals record what happened; xG records the chances that were
    #: created, which is closer to what the next match will look like. A match
    #: with no xG on file always falls back to its goals.
    goal_source: str = "goals"
    xg_weight: float = 0.7

    @classmethod
    def legacy(cls) -> "RatingConfig":
        """The unadjusted ratio ratings, kept so a change can be measured."""
        return cls()


#: The ratings the live card runs on.
#:
#: Still the old goals-ratio ratings, on purpose. The opponent-adjusted xG
#: ratings are a better probability model on every threshold-free measure —
#: see docs/no_edge_out_of_sample.md — but the only bet rule the card has was
#: tuned to the old model's overconfidence, and under that rule the new model
#: bets the compression artefact: draws and long-priced away sides, 381 bets
#: and −98 units in the single-pass backtest. Switching this before the rule
#: is rebuilt and held-out-tested would be the change the doc warns against.
CARD_RATINGS = RatingConfig.legacy()


#: The ratings the 2.5 goals line is priced on.
#:
#: The one market where the new ratings earned a place. Fitted on 70% Understat
#: xG / 30% goals with opponent adjustment and a 365-day half-life, they score
#: 0.6719 log loss on over-2.5 against the closing market's 0.6698 — nearly on
#: it — where the old ratings score 0.6836. Held out by season the anchored
#: rule built on them sits at zero CLV with profit scattered either side; no
#: edge shown and none ruled out, which is why its stake is capped small and it
#: is tracked forward by CLV. See docs/no_edge_out_of_sample.md.
TOTALS_RATINGS = RatingConfig(
    opponent_adjusted=True, half_life_days=365, goal_source="blend", xg_weight=0.7
)


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

    def fit(
        self,
        matches: pd.DataFrame,
        last_n_matches_per_team: int | None = None,
        config: RatingConfig | None = None,
    ) -> "PoissonGoalsModel":
        config = config or RatingConfig.legacy()
        df = matches.dropna(subset=["home_goals", "away_goals"]).copy()
        df = df.sort_values("date")

        if last_n_matches_per_team:
            # Keep recent matches for teams by taking latest rows involving each team and de-duping.
            idx = set()
            for team in pd.concat([df["home_team"], df["away_team"]]).dropna().unique():
                team_rows = df[(df["home_team"] == team) | (df["away_team"] == team)].tail(last_n_matches_per_team)
                idx.update(team_rows.index.tolist())
            df = df.loc[sorted(idx)].copy()

        if config.opponent_adjusted:
            return self._fit_opponent_adjusted(df, config)

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

    def _match_weights(self, df: pd.DataFrame, half_life_days: float | None) -> np.ndarray:
        """One weight per match, halving every `half_life_days` into the past."""
        if not half_life_days:
            return np.ones(len(df), dtype=float)
        dates = pd.to_datetime(df["date"], errors="coerce")
        latest = dates.max()
        age_days = (latest - dates).dt.total_seconds().to_numpy() / 86400.0
        age_days = np.nan_to_num(age_days, nan=0.0)
        return np.power(0.5, age_days / float(half_life_days))

    @staticmethod
    def _scoring_arrays(df: pd.DataFrame, config: RatingConfig) -> tuple[np.ndarray, np.ndarray]:
        """Goals, xG, or a blend — per match, with goals as the fallback."""
        goals_h = df["home_goals"].to_numpy(dtype=float)
        goals_a = df["away_goals"].to_numpy(dtype=float)
        source = str(config.goal_source).strip().lower()
        if source == "goals" or "home_xg" not in df.columns or "away_xg" not in df.columns:
            return goals_h, goals_a
        xg_h = pd.to_numeric(df["home_xg"], errors="coerce").to_numpy(dtype=float)
        xg_a = pd.to_numeric(df["away_xg"], errors="coerce").to_numpy(dtype=float)
        weight = 1.0 if source == "xg" else float(min(max(config.xg_weight, 0.0), 1.0))
        blend_h = weight * xg_h + (1.0 - weight) * goals_h
        blend_a = weight * xg_a + (1.0 - weight) * goals_a
        return (
            np.where(np.isnan(blend_h), goals_h, blend_h),
            np.where(np.isnan(blend_a), goals_a, blend_a),
        )

    def _fit_opponent_adjusted(
        self, df: pd.DataFrame, config: RatingConfig
    ) -> "PoissonGoalsModel":
        """Solve attack and defence jointly, so the schedule cannot flatter a team.

        Each match says a team scored some goals against a particular defence.
        A team's attack is therefore its goals divided by what a league-average
        attack would have been expected to score against those same defences —
        which depends on every other team's defence, which in turn depends on
        every attack. There is no closed form, so it iterates: hold defences
        fixed and solve attacks, hold attacks fixed and solve defences, repeat.
        A dozen passes is far past the point where the numbers stop moving.

        Home and away are kept separate because home advantage is real and
        belongs in the venue term, not smeared into a team's rating.
        """
        weights = self._match_weights(df, config.half_life_days)
        teams = sorted(set(df["home_team"]).union(set(df["away_team"])))
        index = {team: i for i, team in enumerate(teams)}
        home = df["home_team"].map(index).to_numpy()
        away = df["away_team"].map(index).to_numpy()
        home_goals, away_goals = self._scoring_arrays(df, config)

        total_weight = float(weights.sum())
        if total_weight <= 0 or not teams:
            self.avg_home_goals = float(df["home_goals"].mean())
            self.avg_away_goals = float(df["away_goals"].mean())
            self.team_strengths = {t: TeamStrength(1.0, 1.0) for t in teams}
            return self

        mu_home = float((weights * home_goals).sum() / total_weight)
        mu_away = float((weights * away_goals).sum() / total_weight)

        count = len(teams)
        attack = np.ones(count, dtype=float)
        defense = np.ones(count, dtype=float)
        # Pseudo-observations of an exactly average team, in expected-goal
        # units, so `prior_matches` reads as "this many league-average games".
        prior = float(config.prior_matches) * (mu_home + mu_away) / 2.0

        for _ in range(max(1, int(config.iterations))):
            scored = np.zeros(count)
            expected = np.zeros(count)
            np.add.at(scored, home, weights * home_goals)
            np.add.at(scored, away, weights * away_goals)
            np.add.at(expected, home, weights * mu_home * defense[away])
            np.add.at(expected, away, weights * mu_away * defense[home])
            attack = (scored + prior) / np.maximum(expected + prior, 1e-9)
            attack = np.clip(attack, 0.2, 5.0)
            attack /= max(float(attack.mean()), 1e-9)

            conceded = np.zeros(count)
            expected = np.zeros(count)
            np.add.at(conceded, home, weights * away_goals)
            np.add.at(conceded, away, weights * home_goals)
            np.add.at(expected, home, weights * mu_away * attack[away])
            np.add.at(expected, away, weights * mu_home * attack[home])
            defense = (conceded + prior) / np.maximum(expected + prior, 1e-9)
            defense = np.clip(defense, 0.2, 5.0)
            defense /= max(float(defense.mean()), 1e-9)

        self.avg_home_goals = mu_home
        self.avg_away_goals = mu_away
        self.team_strengths = {
            team: TeamStrength(attack=float(attack[i]), defense=float(defense[i]))
            for team, i in index.items()
        }
        return self

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
            # Team totals come off each side's own marginal, not the joint
            # matrix, so they stay correct even where the matrix is truncated.
            "team_total_home_over_1_5": round(
                float(1.0 - sum(self._poisson_pmf(k, home_xg) for k in (0, 1))), 4
            ),
            "team_total_home_under_1_5": round(
                float(sum(self._poisson_pmf(k, home_xg) for k in (0, 1))), 4
            ),
            "team_total_away_over_1_5": round(
                float(1.0 - sum(self._poisson_pmf(k, away_xg) for k in (0, 1))), 4
            ),
            "team_total_away_under_1_5": round(
                float(sum(self._poisson_pmf(k, away_xg) for k in (0, 1))), 4
            ),
            "top_scores": top_scores[["score", "prob"]].assign(prob=lambda d: d["prob"].round(4)).to_dict("records"),
        }

    def project_fixtures(self, fixtures: pd.DataFrame) -> pd.DataFrame:
        records = []
        for _, row in fixtures.iterrows():
            records.append(self.match_probabilities(row["home_team"], row["away_team"]))
        return pd.DataFrame(records)
