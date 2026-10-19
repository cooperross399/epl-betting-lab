"""Per-player Poisson rates for shots, shots on target, goals, assists, and cards.

The team models answer "how many will the match produce"; a prop asks "how
many will this player produce", and that needs player-level rates fitted on
the Understat match logs (`data/processed/player_match_logs.csv`).

The shape follows `PoissonCountModel` deliberately. A per-90 rate computed
from a handful of appearances is mostly noise, so every player's rate is
shrunk toward their position group's league baseline in proportion to the
minutes of evidence behind it — a player with 900 minutes keeps half of his
measured deviation, a player with 90 keeps a tenth. The same shrinkage is
applied to the opponent's concession factor, for the same reason.

Three honest limits, stated here because they do not show up in the numbers:

**Expected minutes are the weakest input.** They are estimated from recent
appearances, and the true driver — tonight's team sheet — is published about
75 minutes before kick-off, hours after the card is built. Books reprice on
lineup news; this model cannot. That is a structural information deficit on
every prop, and it is why prop edges must clear a higher bar than match-level
edges, not a lower one.

**Counts are treated as Poisson.** Shots are close to Poisson; goals close
enough; cards are not (they cluster, and the referee — the strongest driver —
is not in the data). Cards were left unpriced for that reason until Cooper
asked for them on 2026-10-19; they are now rated as "booked" and "sent off",
each a yes/no per match derived from the logs' yellow and red cards, and
that warning travels with every card price rather than being solved.

**Shots on target inherit the Understat definition** (Goal or SavedShot),
which is close to, not identical to, the Opta counts books settle against.
The data module carries the full caveat.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


#: Stats this model prices, each a column of the player match logs.
PROP_STATS = ("shots", "shots_on_target", "goals", "assists")

#: Card stats, derived per appearance by `add_card_columns`: booked is any
#: yellow or red (a second yellow and its red are one booking, which is how a
#: "to be booked" Yes settles), sent off is any red. Fitted only when the logs
#: carry `yellow_cards` and `red_cards`; without them the model holds no card
#: opinion rather than a baseline one.
CARD_STATS = ("booked", "sent_off")


#: Stats the Fantasy Premier League logs carry and Understat does not
#: (`providers/fpl_players`). Fitted by `PlayerPropsModel(stats=FPL_STATS)`.
FPL_STATS = ("tackles", "saves")


def add_card_columns(logs: pd.DataFrame) -> pd.DataFrame:
    """`logs` with `booked` and `sent_off`, when it carries card counts."""
    if not {"yellow_cards", "red_cards"} <= set(logs.columns):
        return logs
    frame = logs.copy()
    yellow = pd.to_numeric(frame["yellow_cards"], errors="coerce").fillna(0)
    red = pd.to_numeric(frame["red_cards"], errors="coerce").fillna(0)
    frame["booked"] = ((yellow + red) > 0).astype(int)
    frame["sent_off"] = (red > 0).astype(int)
    return frame

#: Position groups, from the first letter of Understat's position strings
#: ("FW", "MC", "DR", "GK"). Substitute appearances are grouped under the
#: player's most common starting position, resolved at fit time.
POSITION_GROUPS = ("F", "M", "D", "GK")


def _position_group(position: str) -> str:
    text = str(position).strip().upper()
    if text.startswith("GK"):
        return "GK"
    for group in ("F", "M", "D"):
        if text.startswith(group):
            return group
    return ""


@dataclass(frozen=True)
class PropCalibration:
    """A fitted correction for the model's measured miscalibration.

    Platt scaling: corrected = sigmoid(intercept + slope * logit(raw)). Two
    parameters are all the measured defect needs — the mid-range runs two to
    three points hot and the top bucket collapses, which is the signature a
    slope below one straightens out.

    The honesty rule lives at the call site, not here: fit on one window,
    apply on another, never both on the same data. `fitted_on` records the
    sample count so a correction fitted on too little announces itself.
    """

    intercept: float
    slope: float
    fitted_on: int

    #: Below this many settled outcomes a fitted curve is noise; the identity
    #: correction is the honest fallback.
    MINIMUM_SAMPLES = 200

    @classmethod
    def identity(cls, fitted_on: int = 0) -> "PropCalibration":
        return cls(intercept=0.0, slope=1.0, fitted_on=fitted_on)

    @classmethod
    def fit(cls, samples: list[tuple[float, bool]]) -> "PropCalibration":
        """Newton-fitted logistic regression of outcome on logit(probability)."""
        if len(samples) < cls.MINIMUM_SAMPLES:
            return cls.identity(fitted_on=len(samples))
        xs = [_logit(p) for p, _ in samples]
        ys = [1.0 if won else 0.0 for _, won in samples]
        a, b = 0.0, 1.0
        for _ in range(50):
            g0 = g1 = 0.0
            h00 = h01 = h11 = 0.0
            for x, y in zip(xs, ys):
                p = _sigmoid(a + b * x)
                w = max(p * (1.0 - p), 1e-9)
                g0 += p - y
                g1 += (p - y) * x
                h00 += w
                h01 += w * x
                h11 += w * x * x
            det = h00 * h11 - h01 * h01
            if abs(det) < 1e-12:
                break
            da = (h11 * g0 - h01 * g1) / det
            db = (h00 * g1 - h01 * g0) / det
            a -= da
            b -= db
            if abs(da) < 1e-10 and abs(db) < 1e-10:
                break
        return cls(intercept=a, slope=b, fitted_on=len(samples))

    def apply(self, probability: float) -> float:
        corrected = _sigmoid(self.intercept + self.slope * _logit(probability))
        return max(0.0, min(1.0, corrected))


def _logit(probability: float) -> float:
    p = min(max(probability, 1e-4), 1.0 - 1e-4)
    return math.log(p / (1.0 - p))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


@dataclass(frozen=True)
class PlayerRates:
    """One player's shrunk per-90 rates and minutes expectation."""

    player: str
    team: str
    group: str
    minutes_played: int
    expected_minutes: float
    per90: dict[str, float]


class PlayerPropsModel:
    """Poisson prop pricing from per-player match logs."""

    #: Minutes of evidence at which a player keeps half of his measured
    #: deviation from the position baseline — ten full matches.
    SHRINKAGE_MINUTES = 900

    #: Matches of evidence at which a team's concession factor keeps half its
    #: deviation, matching the team count model's reasoning.
    OPPONENT_SHRINKAGE_MATCHES = 60

    #: Appearances used for the minutes expectation. Recent form, not career.
    MINUTES_WINDOW = 6

    #: A player below this many minutes of evidence is not priced at all.
    #: League baseline would be the honest rate, but a prop priced purely on
    #: "average forward" is not a modelled opinion worth staking.
    MINIMUM_MINUTES = 270

    def __init__(self, stats: tuple[str, ...] | None = None) -> None:
        #: The stats to fit. None means the Understat set: the four volume
        #: stats, plus the card stats when the logs carry card counts. The
        #: Fantasy Premier League logs fit `FPL_STATS` instead.
        self._requested = tuple(stats) if stats else None
        self.players: dict[str, PlayerRates] = {}
        self.baselines: dict[str, dict[str, float]] = {}
        self.opponent_factors: dict[str, dict[str, float]] = {}
        self.venue_factors: dict[str, dict[str, float]] = {}
        self.stats: tuple[str, ...] = stats

    def fit(
        self, logs: pd.DataFrame, *, prior: pd.DataFrame | None = None
    ) -> "PlayerPropsModel":
        """Fit per-player rates on `logs`.

        `prior` is optional extra evidence per player — one row of minutes
        and stat totals, such as last season's — added to the player's own
        sums before shrinkage. It moves no baseline, opponent or venue
        factor and no minutes expectation, which only match rows can say.
        """
        frame = add_card_columns(logs)
        if self._requested:
            stats = self._requested
        elif set(CARD_STATS) <= set(frame.columns):
            stats = (*PROP_STATS, *CARD_STATS)
        else:
            stats = PROP_STATS
        self.stats = stats
        required = {
            "player",
            "team",
            "opponent",
            "venue",
            "position",
            "minutes",
            "date",
            "match_id",
            *stats,
        }
        missing = required - set(frame.columns)
        if missing:
            raise KeyError(
                f"Player logs are missing columns {sorted(missing)}; refusing "
                "to model from a partial dataset."
            )
        frame = frame.copy()
        frame["minutes"] = pd.to_numeric(frame["minutes"], errors="coerce")
        for stat in stats:
            frame[stat] = pd.to_numeric(frame[stat], errors="coerce").fillna(0)
        frame = frame.dropna(subset=["minutes"])
        frame = frame[frame["minutes"] > 0]
        if frame.empty:
            raise ValueError("No usable appearances to fit on.")

        frame["group"] = frame["position"].map(_position_group)
        # A substitute appearance carries position "Sub"; the player's group
        # is his most common named position across the dataset.
        named = frame[frame["group"] != ""]
        primary = (
            named.groupby("player")["group"]
            .agg(lambda s: s.mode().iat[0])
            .to_dict()
        )
        frame["group"] = frame["player"].map(primary).fillna("M")

        # League per-90 baselines per position group.
        self.baselines = {}
        for group, rows in frame.groupby("group"):
            minutes = float(rows["minutes"].sum())
            self.baselines[str(group)] = {
                stat: float(rows[stat].sum()) / minutes * 90.0 if minutes else 0.0
                for stat in stats
            }

        # Opponent concession factors: how much of each stat a team allows
        # opposing players, relative to the league, shrunk by evidence.
        self.opponent_factors = {}
        per_match = (
            frame.groupby(["opponent", "match_id"])[list(stats)]
            .sum()
            .reset_index()
        )
        league_avg = {
            stat: float(per_match[stat].mean()) for stat in stats
        }
        for team, rows in per_match.groupby("opponent"):
            played = len(rows)
            weight = played / (played + self.OPPONENT_SHRINKAGE_MATCHES)
            self.opponent_factors[str(team)] = {
                stat: 1.0
                + weight
                * (
                    (float(rows[stat].mean()) / league_avg[stat] if league_avg[stat] else 1.0)
                    - 1.0
                )
                for stat in stats
            }

        # Venue factors: league-wide home/away multipliers per stat.
        self.venue_factors = {}
        per_venue = frame.groupby("venue")[list(stats)].sum()
        minutes_by_venue = frame.groupby("venue")["minutes"].sum()
        overall_per90 = {
            stat: float(frame[stat].sum()) / float(frame["minutes"].sum()) * 90.0
            for stat in stats
        }
        for venue in ("home", "away"):
            if venue not in per_venue.index:
                self.venue_factors[venue] = {stat: 1.0 for stat in stats}
                continue
            venue_minutes = float(minutes_by_venue.get(venue, 0.0))
            self.venue_factors[venue] = {
                stat: (
                    (float(per_venue.loc[venue, stat]) / venue_minutes * 90.0)
                    / overall_per90[stat]
                    if venue_minutes and overall_per90[stat]
                    else 1.0
                )
                for stat in stats
            }

        # Per-player shrunk rates and a recent-form minutes expectation.
        prior_by_player: dict[str, dict[str, float]] = {}
        if prior is not None and not prior.empty and "player" in prior.columns:
            for _, prior_row in prior.iterrows():
                prior_by_player[str(prior_row["player"])] = {
                    column: float(pd.to_numeric(prior_row.get(column), errors="coerce") or 0.0)
                    for column in ("minutes", *stats)
                }

        self.players = {}
        frame = frame.sort_values(["date", "match_id"])
        for player, rows in frame.groupby("player"):
            extra = prior_by_player.get(str(player), {})
            minutes = float(rows["minutes"].sum()) + extra.get("minutes", 0.0)
            group = str(rows["group"].iat[0])
            baseline = self.baselines.get(group) or {
                stat: 0.0 for stat in stats
            }
            weight = minutes / (minutes + self.SHRINKAGE_MINUTES)
            per90 = {}
            for stat in stats:
                total = float(rows[stat].sum()) + extra.get(stat, 0.0)
                raw = total / minutes * 90.0 if minutes else 0.0
                per90[stat] = baseline[stat] + weight * (raw - baseline[stat])
            recent = rows.tail(self.MINUTES_WINDOW)
            self.players[str(player)] = PlayerRates(
                player=str(player),
                team=str(rows["team"].iat[-1]),
                group=group,
                minutes_played=int(minutes),
                expected_minutes=float(recent["minutes"].mean()),
                per90=per90,
            )
        return self

    def expected_count(
        self, player: str, stat: str, *, opponent: str, venue: str
    ) -> float | None:
        """The Poisson mean, or None when there is no modelled opinion."""
        if stat not in self.stats:
            if stat in CARD_STATS:
                # Logs without card counts: no opinion, never a baseline one.
                return None
            raise KeyError(f"Unknown prop stat {stat!r}. Known: {self.stats}")
        rates = self.players.get(player)
        if rates is None or rates.minutes_played < self.MINIMUM_MINUTES:
            return None
        opponent_factor = self.opponent_factors.get(opponent, {}).get(stat, 1.0)
        venue_factor = self.venue_factors.get(venue, {}).get(stat, 1.0)
        return (
            rates.per90[stat]
            * (rates.expected_minutes / 90.0)
            * opponent_factor
            * venue_factor
        )

    def over_probability(
        self, player: str, stat: str, line: float, *, opponent: str, venue: str
    ) -> float | None:
        """P(count > line), or None when there is no modelled opinion."""
        lam = self.expected_count(player, stat, opponent=opponent, venue=venue)
        if lam is None:
            return None
        threshold = math.floor(line)
        cumulative = sum(
            math.exp(-lam) * lam**k / math.factorial(k)
            for k in range(threshold + 1)
        )
        return max(0.0, min(1.0, 1.0 - cumulative))

    def anytime_scorer_probability(
        self, player: str, *, opponent: str, venue: str
    ) -> float | None:
        """P(at least one goal), or None when there is no modelled opinion."""
        return self.over_probability(
            player, "goals", 0.5, opponent=opponent, venue=venue
        )
