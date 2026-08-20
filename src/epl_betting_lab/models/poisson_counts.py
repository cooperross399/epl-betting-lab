"""Team-strength Poisson for any counted match event.

The goals model already works this way, and corners, cards and shots are the
same shape of problem: a count per team per match, driven by how much of it
each side generates and how much they concede. Rather than three near-copies of
`PoissonGoalsModel`, this takes the pair of columns to fit and serves all of
them.

Every one of these is fitted on data the project already downloads every week
and then discards. Football-Data ships corners (`HC`/`AC`), bookings
(`HY`/`AY`, `HR`/`AR`) and shots (`HS`/`AS`, `HST`/`AST`) in the same file as
the scorelines, so none of this needs a new source.

Two honest limits, stated here because they do not show up in the numbers:

**Cards are not Poisson.** Bookings cluster — a bad-tempered match produces
several, and referees vary more than teams do. A Poisson fit will understate
the tail. It is good enough to find a badly priced total, not good enough to
trust near the line.

**Referee identity is missing.** It is the single strongest driver of card
counts and Football-Data does not carry it. So card markets carry a real
unmodelled variable, which is why their minimum edge should be set higher than
the default rather than lower.

**Team strengths are shrunk toward the league average.** A ratio computed from
a season of matches is a noisy estimate of a team's real rate, and multiplying
two noisy ratios — one side's generating, the other's conceding — compounds the
noise. Left raw, the model produced predictions that were too spread out in
both directions: 74% where 59% happened, and 26% where 48% happened. Shrinkage
pulls each strength toward 1.0 in proportion to how little evidence stands
behind it, so a team with sixty matches keeps most of its estimate and a team
with six keeps almost none of it.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass
class TeamCountStrength:
    """How much of the counted event a team generates and concedes."""

    generates: float
    concedes: float


#: Named event types, each mapping to the Football-Data column pair.
COUNT_EVENTS: dict[str, tuple[str, str]] = {
    "corners": ("HC", "AC"),
    "cards": ("HY", "AY"),
    "shots": ("HS", "AS"),
    "shots_on_target": ("HST", "AST"),
}


class PoissonCountModel:
    """Poisson model for a counted event, fitted per team."""

    #: Matches of evidence at which a team keeps half of its measured deviation
    #: from the league average. Below it the estimate is mostly the average;
    #: above it, mostly the team. Chosen because it is roughly a season and a
    #: half, which is the point at which a corner rate stops moving much.
    SHRINKAGE_MATCHES = 60

    def __init__(
        self,
        home_column: str,
        away_column: str,
        max_count: int = 25,
        minimum_matches: int = 5,
        shrinkage_matches: int | None = None,
    ) -> None:
        self.home_column = home_column
        self.away_column = away_column
        self.max_count = max_count
        self.minimum_matches = minimum_matches
        self.shrinkage_matches = (
            self.SHRINKAGE_MATCHES if shrinkage_matches is None else shrinkage_matches
        )
        self.team_strengths: dict[str, TeamCountStrength] = {}
        self.avg_home: float | None = None
        self.avg_away: float | None = None

    @classmethod
    def for_event(cls, event: str, **kwargs: object) -> "PoissonCountModel":
        if event not in COUNT_EVENTS:
            raise KeyError(
                f"Unknown counted event {event!r}. Known: {sorted(COUNT_EVENTS)}"
            )
        home, away = COUNT_EVENTS[event]
        return cls(home, away, **kwargs)  # type: ignore[arg-type]

    def fit(self, matches: pd.DataFrame) -> "PoissonCountModel":
        for column in (self.home_column, self.away_column):
            if column not in matches.columns:
                raise KeyError(
                    f"Column {column!r} is not in the match data, so this event "
                    "cannot be modelled from it."
                )
        frame = matches.dropna(subset=[self.home_column, self.away_column]).copy()
        frame[self.home_column] = pd.to_numeric(frame[self.home_column], errors="coerce")
        frame[self.away_column] = pd.to_numeric(frame[self.away_column], errors="coerce")
        frame = frame.dropna(subset=[self.home_column, self.away_column])
        if frame.empty:
            raise ValueError("No usable rows for this counted event.")

        self.avg_home = float(frame[self.home_column].mean())
        self.avg_away = float(frame[self.away_column].mean())

        self.team_strengths = {}
        teams = set(frame["home_team"]) | set(frame["away_team"])
        for team in teams:
            at_home = frame[frame.home_team == team]
            away = frame[frame.away_team == team]
            played = len(at_home) + len(away)
            if played < self.minimum_matches:
                # Too little evidence to claim a team is unusual. League average
                # is the honest answer, not a number derived from three matches.
                self.team_strengths[team] = TeamCountStrength(1.0, 1.0)
                continue
            generated = at_home[self.home_column].sum() + away[self.away_column].sum()
            conceded = at_home[self.away_column].sum() + away[self.home_column].sum()
            expected = (self.avg_home + self.avg_away) / 2 * played
            raw_generates = float(generated / expected) if expected else 1.0
            raw_concedes = float(conceded / expected) if expected else 1.0
            # How much of the measured deviation this team has earned. A ratio
            # from a handful of matches is mostly noise, and two of them
            # multiplied together is worse; weight it by the evidence behind it.
            weight = played / (played + self.shrinkage_matches)
            self.team_strengths[team] = TeamCountStrength(
                generates=1.0 + weight * (raw_generates - 1.0),
                concedes=1.0 + weight * (raw_concedes - 1.0),
            )
        return self

    def expected_counts(self, home_team: str, away_team: str) -> tuple[float, float]:
        if self.avg_home is None or self.avg_away is None:
            raise RuntimeError("Model is not fit yet.")
        home = self.team_strengths.get(home_team, TeamCountStrength(1.0, 1.0))
        away = self.team_strengths.get(away_team, TeamCountStrength(1.0, 1.0))
        return (
            round(float(self.avg_home * home.generates * away.concedes), 3),
            round(float(self.avg_away * away.generates * home.concedes), 3),
        )

    @staticmethod
    def _pmf(k: int, lam: float) -> float:
        if lam <= 0:
            return 1.0 if k == 0 else 0.0
        return (math.exp(-lam) * lam**k) / math.factorial(k)

    def _total_distribution(self, home_team: str, away_team: str) -> list[float]:
        """Probability of each possible match total, index = total."""
        home_lambda, away_lambda = self.expected_counts(home_team, away_team)
        # The sum of two independent Poissons is Poisson with the summed mean,
        # so the match total needs no convolution.
        combined = home_lambda + away_lambda
        return [self._pmf(k, combined) for k in range(self.max_count + 1)]

    def total_over_probability(
        self, home_team: str, away_team: str, line: float
    ) -> float:
        """P(match total > line). Lines are half-numbers, so no push."""
        distribution = self._total_distribution(home_team, away_team)
        return float(sum(p for k, p in enumerate(distribution) if k > line))

    def team_total_over_probability(
        self, home_team: str, away_team: str, line: float, side: str
    ) -> float:
        """P(one team's count > line). `side` is "home" or "away"."""
        home_lambda, away_lambda = self.expected_counts(home_team, away_team)
        lam = home_lambda if side == "home" else away_lambda
        return float(
            sum(self._pmf(k, lam) for k in range(self.max_count + 1) if k > line)
        )

    def match_probabilities(self, home_team: str, away_team: str) -> dict[str, float]:
        """Three-way on the count itself, e.g. who wins the corner count."""
        home_lambda, away_lambda = self.expected_counts(home_team, away_team)
        home_win = draw = away_win = 0.0
        for h in range(self.max_count + 1):
            ph = self._pmf(h, home_lambda)
            for a in range(self.max_count + 1):
                joint = ph * self._pmf(a, away_lambda)
                if h > a:
                    home_win += joint
                elif h == a:
                    draw += joint
                else:
                    away_win += joint
        return {
            "home_expected": home_lambda,
            "away_expected": away_lambda,
            "total_expected": round(home_lambda + away_lambda, 3),
            "home": round(home_win, 4),
            "draw": round(draw, 4),
            "away": round(away_win, 4),
        }
