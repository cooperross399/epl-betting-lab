"""One rating scale across the four English divisions, and what it is worth.

A cup tie is two clubs from different competitions, and the card's ratings are
fitted inside one. Since #286 the model refuses a club it has never seen rather
than substituting a league-average side, so a Carabao Cup fixture cannot be
priced at all. This module exists to answer whether that can be fixed, because
promotion and relegation move clubs between divisions and those clubs are a
bridge between the pools: 60 of the 100 clubs in six seasons of E0-E3 appear in
more than one division, linking E0-E1 through 17 clubs, E1-E2 through 22 and
E2-E3 through 27.

**Two of the three things needed turn out to work.**

Pooling the divisions and fitting opponent-adjusted ratings produces a sane
scale, monotone in both directions: mean attack 1.274 / 1.021 / 0.965 / 0.840
and mean defence 0.811 / 0.946 / 1.034 / 1.134 from E0 down to E3. That is not
automatic. The card's own `CARD_RATINGS` is `RatingConfig.legacy()`, the
unadjusted ratio, and pooled it rates League Two level with the Premier League —
attack 1.035 against 1.027 — because a ratio against the league average has no
way to know the league differs. The joint fit does, through the clubs that moved.

And pooling does not disturb the Premier League ratings it is added to. Arsenal
v Chelsea prices at 62.6% pooled against 61.6% on the Premier League alone.

**The third thing does not work, and it is the one that matters.**

A rating is only useful across a division boundary if it still describes the
club on the other side. Tested out of sample on every club that changed division
between seasons — 100 changes, 3,643 matches, ratings fitted only on data before
the new season began — carrying a club's own rating across is *worse* than
throwing it away and calling the club average for its new division:

    share of the club's own rating kept        RMSE
      0.00  (average for the new division)    1.1402
      0.15                                    1.1400   <- best
      0.50                                    1.1443
      1.00  (carry it across intact)          1.1585

    full carry minus full shrink: +0.0183 RMSE,
    95% interval over 100 clubs +0.0051 to +0.0336 — excludes zero.

About 15% of a club's rating survives a division change, and 15% is inside the
noise of zero. What transfers is the *division*, not the club.

**So a cup tie can be priced, and the price carries almost no private
information.** The division gap is real and well estimated — it is what the
winning baseline uses — but a market that knows which divisions two clubs are in
knows the same thing, and prices it with the vig on its side. A model beats a
market by disagreeing with it usefully, and after a division change this model
has almost nothing left to disagree with.

That is the answer to "can the cup be added": yes, validly, and not profitably.
Recorded here so the next person to ask finds the measurement rather than
re-deriving it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from epl_betting_lab.data.fetch_football_data import processed_path_for
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig

#: The English divisions, strongest first. Order matters: the scale check below
#: asserts the fitted ratings come out monotone in this order, which is the
#: cheapest way to notice a pool that has been assembled wrongly.
DIVISIONS = ("E0", "E1", "E2", "E3")

#: Opponent-adjusted, because the unadjusted ratio cannot see a division gap.
#: Goals rather than a blend: Understat publishes no xG below the Premier
#: League, so a blend here would silently be this same goals fit wearing
#: another name.
UNIFIED_RATINGS = RatingConfig(
    opponent_adjusted=True, half_life_days=365, goal_source="goals"
)

#: How much of a club's own rating to keep when it changes division. Measured,
#: not chosen: see the sweep in the module docstring. Kept as a constant so the
#: number has one home, and so a reader meets it beside the finding that it is
#: statistically indistinguishable from keeping none of it.
CARRIED_RATING_SHARE = 0.15


def build_pool(divisions: tuple[str, ...] = DIVISIONS) -> pd.DataFrame:
    """Every division in one frame, each row carrying the division it came from.

    The per-division datasets are built separately and deliberately — the
    builder refuses to write one division's matches into another's file,
    because a rating fitted across divisions with no common scale is wrong in a
    way nothing downstream reports. This is the one place the pooling is
    intended, so the division travels on the row and the result is never
    written back over a per-division dataset.
    """
    frames = []
    for division in divisions:
        path = processed_path_for(division)
        if not path.is_file():
            raise FileNotFoundError(
                f"No dataset for {division} at `{path}`. Build it with "
                f"`scripts/fetch_data.py --divisions {division}`."
            )
        frame = pd.read_csv(path).dropna(subset=["home_goals", "away_goals"]).copy()
        frame["division"] = division
        frames.append(frame)
    pool = pd.concat(frames, ignore_index=True)
    pool["date"] = pd.to_datetime(pool["date"], errors="coerce")
    pool["season"] = pool["season"].astype(str)
    return pool.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def division_by_season(pool: pd.DataFrame) -> pd.DataFrame:
    """Which division each club played in, each season."""
    rows = [
        pool[["season", side, "division"]].rename(columns={side: "team"})
        for side in ("home_team", "away_team")
    ]
    return pd.concat(rows).drop_duplicates(["season", "team"]).reset_index(drop=True)


def division_changes(pool: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    """(club, from, to, season) for every promotion and relegation on file.

    These are the only evidence that exists for what a division is worth. No
    free source publishes a cup or European result, so no match in this project
    is ever played between two divisions.
    """
    seen = division_by_season(pool)
    seasons = sorted(pool["season"].unique())
    moves: list[tuple[str, str, str, str]] = []
    for previous, current in zip(seasons, seasons[1:]):
        before = seen[seen["season"] == previous].set_index("team")["division"]
        after = seen[seen["season"] == current].set_index("team")["division"]
        for team in before.index.intersection(after.index):
            if before[team] != after[team]:
                moves.append((team, before[team], after[team], current))
    return moves


def scale_by_division(model: PoissonGoalsModel, pool: pd.DataFrame) -> pd.DataFrame:
    """Mean fitted attack and defence for the clubs of each division.

    The cheapest check that a pool was assembled and fitted sensibly: these
    must come out monotone. Fitted with the card's own unadjusted ratio instead,
    they do not — League Two comes out level with the Premier League.
    """
    seen = division_by_season(pool).merge(
        pool[["season"]].drop_duplicates(), on="season", how="left"
    )
    latest = (
        seen.sort_values("season").groupby("team").last()[["division"]].reset_index()
    )
    strengths = pd.DataFrame(
        [
            {"team": team, "attack": s.attack, "defense": s.defense}
            for team, s in model.team_strengths.items()
        ]
    )
    joined = strengths.merge(latest, on="team", how="left").dropna(subset=["division"])
    grouped = joined.groupby("division").agg(
        clubs=("team", "size"), attack=("attack", "mean"), defense=("defense", "mean")
    )
    grouped["net"] = grouped["attack"] / grouped["defense"]
    return grouped.reindex([d for d in DIVISIONS if d in grouped.index])


@dataclass
class CarryResult:
    """What a club's own rating is worth once it changes division."""

    shares: tuple[float, ...]
    rmse: dict[float, float]
    #: Per-club mean squared error, for an interval that resamples clubs rather
    #: than matches — a club's matches share its rating and are not independent.
    per_club: dict[float, list[float]] = field(default_factory=dict)
    matches: int = 0
    clubs: int = 0

    @property
    def best_share(self) -> float:
        return min(self.rmse, key=self.rmse.get)

    def interval(self, *, draws: int = 2000, seed: int = 7) -> tuple[float, float]:
        """95% interval on (carry it all) minus (keep none of it)."""
        high, low = self.per_club.get(1.0), self.per_club.get(0.0)
        if not high or not low:
            return (float("nan"), float("nan"))
        rng = np.random.default_rng(seed)
        count = len(high)
        diffs = np.empty(draws)
        for draw in range(draws):
            picked = rng.integers(0, count, count)
            diffs[draw] = np.sqrt(np.mean([high[i] for i in picked])) - np.sqrt(
                np.mean([low[i] for i in picked])
            )
        return (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)))


def measure_carry(
    pool: pd.DataFrame,
    *,
    shares: tuple[float, ...] = (0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0),
    min_history: int = 2000,
) -> CarryResult:
    """Does a club's rating still describe it on the other side of a promotion?

    Walk-forward and out of sample: for every club that changed division, the
    ratings are fitted only on matches played before its new season began, and
    then used to predict the goals it actually scored in that season. The
    comparison is against the same model with the club's own rating replaced by
    the average of its new division — which keeps the division gap and throws
    away the club.
    """
    seen = division_by_season(pool)
    squared = {share: [] for share in shares}
    per_club = {share: [] for share in shares}
    matches = 0
    clubs = 0

    for team, _, moved_to, season in division_changes(pool):
        start = pool.loc[pool["season"] == season, "date"].min()
        history = pool[pool["date"] < start]
        if len(history) < min_history:
            continue
        model = PoissonGoalsModel().fit(history, config=UNIFIED_RATINGS)
        if team not in model.team_strengths:
            continue
        peers = [
            t
            for t in seen[(seen["season"] == season) & (seen["division"] == moved_to)]["team"]
            if t in model.team_strengths and t != team
        ]
        fixtures = pool[
            (pool["season"] == season)
            & ((pool["home_team"] == team) | (pool["away_team"] == team))
        ]
        if not peers or fixtures.empty:
            continue
        peer_attack = float(np.mean([model.team_strengths[t].attack for t in peers]))
        own_attack = model.team_strengths[team].attack
        this_club = {share: [] for share in shares}

        for _, game in fixtures.iterrows():
            at_home = game["home_team"] == team
            opponent = game["away_team"] if at_home else game["home_team"]
            if opponent not in model.team_strengths:
                continue
            scored = game["home_goals"] if at_home else game["away_goals"]
            base = model.avg_home_goals if at_home else model.avg_away_goals
            defence = model.team_strengths[opponent].defense
            for share in shares:
                attack = share * own_attack + (1.0 - share) * peer_attack
                error = (base * attack * defence - scored) ** 2
                squared[share].append(error)
                this_club[share].append(error)
            matches += 1

        if this_club[shares[0]]:
            clubs += 1
            for share in shares:
                per_club[share].append(float(np.mean(this_club[share])))

    return CarryResult(
        shares=shares,
        rmse={s: float(np.sqrt(np.mean(squared[s]))) for s in shares if squared[s]},
        per_club=per_club,
        matches=matches,
        clubs=clubs,
    )
