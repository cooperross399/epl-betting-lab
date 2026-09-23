"""One rating scale for national teams, and the venue problem it has to solve.

The European club pool works by bridging: clubs from different countries play
each other in Europe, and those ties put every country on one scale. National
teams have no such problem and no such solution — every national team already
plays every other kind of national team, so the pool is connected out of the
box. There is nothing to bridge.

What there is instead is a venue problem the club code has never had.

**A third of competitive internationals are on neutral ground.**
`PoissonGoalsModel` keeps its home advantage in two separately fitted
baselines, and using the home one for a neutral fixture hands the nominal home
side an advantage it does not have. On this archive, competitive matches since
2018:

    real venue   n=4001   home 1.693  away 1.089   advantage +0.604 goals
    neutral      n=1977   home 1.459  away 1.360   advantage +0.099 goals

So `InternationalPool` fits the team strengths once — a team's attack and
defence do not depend on where it plays — and the baselines twice, then picks
the pair that matches the fixture. `expected_goals` takes `neutral` and will
not guess.

**What this does not inherit.** Nothing from the club pools transfers. A
national team has never played any of the 97 clubs in
`data/european_clubs.py`, so there is no bridge from club ratings to these and
none can be built from results. This is a second model that shares the Poisson
code and no information.

**What it cannot be told.** Who is actually available. For a club the eleven is
largely stable week to week; a national squad is reassembled every window, with
routine withdrawals, and in friendlies teams substitute wholesale. A
results-based rating assumes the entity is the same thing each time it appears,
and for national teams that assumption is weaker than anywhere else in this
project.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from epl_betting_lab.data.international_results import (
    FRIENDLY_CODES,
    load_international_results,
)
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig, UnratedTeam

#: Five years, not the clubs' one. A club plays 38 league matches a season; a
#: national team plays about ten a year, so a 365-day window that leaves a club
#: with a full season of evidence leaves a country with ten matches.
#:
#: Measured, not assumed. Sweeping [365, 548, 730, 1095, 1460, 1825, 2555,
#: 3650, None] walk-forward on held-out competitive matches, 1825 beat the 1095
#: this module first guessed at by 0.0057 RMSE, 95% CI [-0.0079, -0.0038],
#: resampling matches — small, but it excludes zero and it is free.
#:
#: `opponent_adjusted=True` is kept, with one honest caveat: on UEFA Nations
#: League matches ALONE it buys nothing measurable (dRMSE +0.0010, 95% CI
#: [-0.0080, +0.0100] — a tight null, not an underpowered one). It earns its
#: place on the wider international population, where the gap is +0.039
#: [+0.022, +0.056]. If UNL were ever the only thing fitted, this would be
#: a setting with no evidence behind it.
INTERNATIONAL_RATINGS = RatingConfig(
    opponent_adjusted=True, half_life_days=1825, goal_source="goals"
)

#: Twelve years of history. The obvious worry was that squads turn over and an
#: old result says nothing about the side that takes the field this window.
#: Measured, that worry is wrong: a national team's rating correlates r = +0.816
#: (attack) and +0.822 (defence) across a seven-year midpoint gap, over 199
#: teams. National-team strength is more persistent than the squad is, so
#: reading further back helps rather than hurts — 12 years with the half-life
#: above beat the original 4-year/1095-day pair on held-out 1X2 log-loss,
#: 0.8709 against 0.8818, 95% CI [-0.0131, -0.0088].
DEFAULT_SINCE = "2014-01-01"

#: Below this a team is not rated at all. A national team with a handful of
#: appearances is a rating made of noise, and `expected_goals` refusing is the
#: behaviour that stopped a Premier League fit pricing Grimsby.
#:
#: Twelve is not a measured optimum and should not be described as one. What is
#: measured is that a threshold is needed at all: below six appearances the
#: model loses 0.10 log-loss of skill against a no-team-information baseline,
#: 95% CI [+0.069, +0.154]. Between six and thirty every comparison straddles
#: zero, and those nulls are underpowered — the minimum detectable effect is
#: about +0.042 against a total model skill of 0.170, so they cannot separate
#: "flat" from "this band keeps only three quarters of the skill". Twelve is the
#: conservative side of an uncertainty, chosen as a judgment. It costs nothing
#: here: all 55 UEFA Nations League teams clear it, and so do all 41 CONCACAF
#: sides.
MIN_MATCHES = 12


@dataclass
class InternationalPool:
    matches: pd.DataFrame
    #: Team -> how many matches it appears in.
    appearances: dict[str, int] = field(default_factory=dict)
    friendlies: int = 0
    competitive: int = 0

    @property
    def rateable(self) -> set[str]:
        return {t for t, n in self.appearances.items() if n >= MIN_MATCHES}


def build_international_pool(
    *,
    since: str = DEFAULT_SINCE,
    # Friendlies stay in. The expectation was that they are a different game —
    # wholesale substitutions, no motivation — and would bias the fit. Measured
    # two ways, excluding them is somewhere between no help and a measurable
    # loss (+0.0002 log-loss, 95% CI [-0.0024, +0.0028] one way; +0.0104
    # [+0.0079, +0.0130] the other, at production shrinkage). Both readings say
    # keep them, and a third of the evidence is not worth discarding on a
    # prior that measurement did not support.
    include_friendlies: bool = True,
    results=None,
) -> InternationalPool:
    """Every international result, tagged by venue and competition."""
    if results is None:
        results = load_international_results(since=since)
    frame = results.matches
    friendlies = int(frame["competition"].isin(FRIENDLY_CODES).sum())
    if not include_friendlies:
        frame = frame[~frame["competition"].isin(FRIENDLY_CODES)]

    appearances: dict[str, int] = {}
    for team in pd.concat([frame["home_team"], frame["away_team"]]):
        appearances[team] = appearances.get(team, 0) + 1

    return InternationalPool(
        matches=frame.reset_index(drop=True),
        appearances=appearances,
        friendlies=friendlies,
        competitive=int((~frame["competition"].isin(FRIENDLY_CODES)).sum()),
    )


@dataclass
class InternationalModel:
    """A fitted pool that knows the difference between a venue and a field.

    Wraps `PoissonGoalsModel` rather than changing it. The team strengths are
    the shared model's; only the baselines are chosen here, because venue is a
    property of the fixture and not of the team.
    """

    model: PoissonGoalsModel
    venue_home: float
    venue_away: float
    neutral_home: float
    neutral_away: float
    rateable: set[str]

    def expected_goals(
        self, home_team: str, away_team: str, *, neutral: bool
    ) -> tuple[float, float]:
        """Expected goals, with the baseline the venue calls for.

        `neutral` has no default on purpose. A third of these fixtures are on
        neutral ground and the wrong baseline is worth half a goal, so a caller
        that has not thought about it should not compile.
        """
        for team in (home_team, away_team):
            if team not in self.rateable:
                raise UnratedTeam(
                    f"{team!r} has fewer than {MIN_MATCHES} matches in the pool, "
                    "so it has no rating. Pricing it would invent one."
                )
        strengths = self.model.team_strengths
        base_home = self.neutral_home if neutral else self.venue_home
        base_away = self.neutral_away if neutral else self.venue_away
        home = base_home * strengths[home_team].attack * strengths[away_team].defense
        away = base_away * strengths[away_team].attack * strengths[home_team].defense
        return float(home), float(away)


def fit_international_model(
    pool: InternationalPool, *, config: RatingConfig = INTERNATIONAL_RATINGS
) -> InternationalModel:
    """Fit team strengths once, baselines twice."""
    frame = pool.matches
    if frame.empty:
        raise ValueError("The pool is empty, so there is nothing to fit.")

    model = PoissonGoalsModel()
    model.fit(frame, config=config)

    venue = frame[~frame["neutral"]]
    neutral = frame[frame["neutral"]]
    if venue.empty or neutral.empty:
        raise ValueError(
            "The pool has no matches of one venue type, so one of the two "
            "baselines would be fitted on nothing and silently equal the other."
        )
    return InternationalModel(
        model=model,
        venue_home=float(venue["home_goals"].mean()),
        venue_away=float(venue["away_goals"].mean()),
        neutral_home=float(neutral["home_goals"].mean()),
        neutral_away=float(neutral["away_goals"].mean()),
        rateable=pool.rateable,
    )
