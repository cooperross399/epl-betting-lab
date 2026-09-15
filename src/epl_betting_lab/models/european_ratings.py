"""One rating scale across eleven European leagues, and the test it passes.

Clubs never move between countries, so nothing links one country's ratings to
another's the way promotion links the English divisions. Fitted separately, each
league is normalised to its own average and a Spanish rating means nothing
against an English one — the same error that rates League Two level with the
Premier League, across borders.

European ties are the bridge. They are matches with results, played between
clubs from two different domestic pools, and openfootball publishes seven
seasons of them free. Fit them alongside the domestic seasons and every country
lands on one scale.

**It passes the out-of-sample test that the English division version failed.**

Fitting on everything before a season and predicting that season's European
ties, the club's own rating on the bridged scale beats treating the club as
average for its own league:

    joint rating (club's own, bridged scale)   RMSE 1.3750
    naive (club = average of its own league)   RMSE 1.5036

    difference -0.1286, 95% interval -0.1637 to -0.0928
    over 365 held-out ties, resampling ties rather than innings.

That is 8.6% better and the interval excludes zero. It is the opposite of the
English result, where carrying a club's rating through a promotion was *worse*
than throwing it away — and the difference makes sense: a promoted club becomes
a different thing at a higher level, while a Champions League club playing in
Europe is the same side against comparable opposition, so its domestic form
carries.

**What this is not.** It predicts goals better than a naive prior. It is not
evidence of beating a price. The Premier League model also predicts goals
respectably and carries beta = -0.023 against the closing line — the share of
its disagreement with the market that holds information is indistinguishable
from zero. Whether these ratings can beat a Champions League price is a separate
question and needs the closing-line record the price collection is accumulating.

**The bridge is partial, and the club ordering shows it.** Fitted on everything,
PSV Eindhoven comes out second by attack, with Sporting, Benfica, Fenerbahce,
Galatasaray and Celtic all above Real Madrid and Manchester City. That is not a
credible European ranking: a club that dominates a weak domestic league scores
heavily against weak opposition, and 701 ties against 18,054 domestic matches
correct it only partly — most of a club's matches are domestic, so most of its
rating is. The scale carries club-level information out of sample, which is what
the test measures, and it is not a power ranking. Anything priced on it should
expect the weak-league sides to be overrated.

**Coverage.** Eleven countries, about 70% of Champions League ties. Thirty of
the 104 clubs on file play in countries Football-Data does not publish — Ukraine,
Austria, Denmark, Switzerland, Serbia and twenty-four more. They stay unrated,
and `PoissonGoalsModel` refuses to price a club it has no rating for, so their
ties are declined rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from epl_betting_lab.config import COUNTRY_TO_LEAGUE
from epl_betting_lab.data.european_results import load_european_ties
from epl_betting_lab.data.fetch_football_data import processed_path_for
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig

#: Opponent-adjusted, because an unadjusted ratio against a league average
#: cannot see that the league changed. Goals rather than a blend: Understat
#: covers five of these eleven countries, so a blend would be a different model
#: in different countries while reporting one name.
EUROPEAN_RATINGS = RatingConfig(
    opponent_adjusted=True, half_life_days=365, goal_source="goals"
)

#: A fit needs enough history behind it to mean anything. Below this the season
#: is skipped rather than scored, because an RMSE from a thin fit is a number
#: with nothing behind it.
MIN_HISTORY = 5000


@dataclass
class EuropeanPool:
    matches: pd.DataFrame
    #: Club -> the country whose league it plays in.
    country_of: dict[str, str]
    domestic: int = 0
    ties: int = 0
    unresolved: list[tuple[str, str]] = field(default_factory=list)


def build_european_pool(
    leagues: dict[str, str] | None = None, *, ties: pd.DataFrame | None = None
) -> EuropeanPool:
    """Every domestic league, plus the European ties that link them."""
    mapping = COUNTRY_TO_LEAGUE if leagues is None else leagues
    country_of: dict[str, str] = {}
    frames: list[pd.DataFrame] = []
    columns = ["date", "home_team", "away_team", "home_goals", "away_goals", "competition"]

    first_country_for: dict[str, str] = {}
    for country, code in mapping.items():
        first_country_for.setdefault(code, country)

    for code in sorted(set(mapping.values())):
        path = processed_path_for(code)
        if not path.is_file():
            raise FileNotFoundError(
                f"No dataset for {code} at `{path}`. Build it with "
                f"`scripts/fetch_data.py --divisions {code}`."
            )
        frame = pd.read_csv(path).dropna(subset=["home_goals", "away_goals"]).copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["competition"] = code
        frame = frame.dropna(subset=["date"])
        frames.append(frame[columns])
        for club in set(frame["home_team"]) | set(frame["away_team"]):
            country_of[club] = first_country_for[code]

    domestic = pd.concat(frames, ignore_index=True)

    if ties is None:
        parsed = load_european_ties()
        ties, unresolved = parsed.matches, parsed.unresolved
    else:
        unresolved = []
    ties = ties[ties["home_team"].isin(country_of) & ties["away_team"].isin(country_of)]

    pool = pd.concat([domestic, ties[columns]], ignore_index=True)
    return EuropeanPool(
        matches=pool.sort_values("date").reset_index(drop=True),
        country_of=country_of,
        domestic=len(domestic),
        ties=len(ties),
        unresolved=unresolved,
    )


@dataclass
class BridgeResult:
    """Does a rating fitted before a season predict that season's ties?"""

    joint_rmse: float
    naive_rmse: float
    ties: int
    per_tie: np.ndarray | None = None

    @property
    def improvement(self) -> float:
        if not self.naive_rmse:
            return float("nan")
        return (1.0 - self.joint_rmse / self.naive_rmse) * 100.0

    def interval(self, *, draws: int = 4000, seed: int = 11) -> tuple[float, float]:
        """95% interval on (joint minus naive), resampling ties.

        A tie contributes two innings that share one match and one pair of
        ratings, so resampling innings would treat them as independent and
        report an interval that is too narrow.
        """
        if self.per_tie is None or not len(self.per_tie):
            return (float("nan"), float("nan"))
        rng = np.random.default_rng(seed)
        count = len(self.per_tie)
        diffs = np.empty(draws)
        for draw in range(draws):
            picked = rng.integers(0, count, count)
            diffs[draw] = np.sqrt(self.per_tie[picked, 0].mean()) - np.sqrt(
                self.per_tie[picked, 1].mean()
            )
        return (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)))


def measure_bridge(
    pool: EuropeanPool, *, skip_seasons: int = 2, min_history: int = MIN_HISTORY
) -> BridgeResult:
    """Walk forward: fit before each season, predict that season's ties.

    The comparison keeps the country gap and throws away the club — it replaces
    the club's own rating with the mean rating of its own league. Beating that
    is what shows the bridged scale carries club-level information rather than
    only a league-level one, which a market already has.
    """
    ties = pool.matches[pool.matches["competition"] == "UCL"]
    if ties.empty:
        return BridgeResult(float("nan"), float("nan"), 0)
    ties = ties.merge(
        pool.matches[["date"]].drop_duplicates(), on="date", how="left"
    ).drop_duplicates()

    seasons = sorted(ties["date"].dt.year.unique())[skip_seasons:]
    per_tie: list[tuple[float, float]] = []

    for year in seasons:
        season_ties = ties[ties["date"].dt.year == year]
        if season_ties.empty:
            continue
        start = season_ties["date"].min()
        history = pool.matches[pool.matches["date"] < start]
        if len(history) < min_history:
            continue
        model = PoissonGoalsModel().fit(history, config=EUROPEAN_RATINGS)

        by_country: dict[str, list[float]] = {}
        for club, strength in model.team_strengths.items():
            country = pool.country_of.get(club)
            if country:
                by_country.setdefault(country, []).append(strength.attack)
        league_mean = {c: float(np.mean(v)) for c, v in by_country.items()}

        for _, tie in season_ties.iterrows():
            home, away = tie["home_team"], tie["away_team"]
            if home not in model.team_strengths or away not in model.team_strengths:
                continue
            joint, naive = [], []
            for team, opponent, scored, base in (
                (home, away, tie["home_goals"], model.avg_home_goals),
                (away, home, tie["away_goals"], model.avg_away_goals),
            ):
                own = model.team_strengths[team].attack
                average = league_mean.get(pool.country_of.get(team), own)
                defence = model.team_strengths[opponent].defense
                joint.append((base * own * defence - scored) ** 2)
                naive.append((base * average * defence - scored) ** 2)
            per_tie.append((float(np.mean(joint)), float(np.mean(naive))))

    if not per_tie:
        return BridgeResult(float("nan"), float("nan"), 0)
    array = np.array(per_tie)
    return BridgeResult(
        joint_rmse=float(np.sqrt(array[:, 0].mean())),
        naive_rmse=float(np.sqrt(array[:, 1].mean())),
        ties=len(array),
        per_tie=array,
    )
