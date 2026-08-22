"""Per-player Poisson rates for shots, shots on target, goals, and assists.

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
is not in the data). This module deliberately prices no card props.

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

    def __init__(self) -> None:
        self.players: dict[str, PlayerRates] = {}
        self.baselines: dict[str, dict[str, float]] = {}
        self.opponent_factors: dict[str, dict[str, float]] = {}
        self.venue_factors: dict[str, dict[str, float]] = {}

    def fit(self, logs: pd.DataFrame) -> "PlayerPropsModel":
        required = {
            "player",
            "team",
            "opponent",
            "venue",
            "position",
            "minutes",
            "date",
            "match_id",
            *PROP_STATS,
        }
        missing = required - set(logs.columns)
        if missing:
            raise KeyError(
                f"Player logs are missing columns {sorted(missing)}; refusing "
                "to model from a partial dataset."
            )
        frame = logs.copy()
        frame["minutes"] = pd.to_numeric(frame["minutes"], errors="coerce")
        for stat in PROP_STATS:
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
                for stat in PROP_STATS
            }

        # Opponent concession factors: how much of each stat a team allows
        # opposing players, relative to the league, shrunk by evidence.
        self.opponent_factors = {}
        per_match = (
            frame.groupby(["opponent", "match_id"])[list(PROP_STATS)]
            .sum()
            .reset_index()
        )
        league_avg = {
            stat: float(per_match[stat].mean()) for stat in PROP_STATS
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
                for stat in PROP_STATS
            }

        # Venue factors: league-wide home/away multipliers per stat.
        self.venue_factors = {}
        per_venue = frame.groupby("venue")[list(PROP_STATS)].sum()
        minutes_by_venue = frame.groupby("venue")["minutes"].sum()
        overall_per90 = {
            stat: float(frame[stat].sum()) / float(frame["minutes"].sum()) * 90.0
            for stat in PROP_STATS
        }
        for venue in ("home", "away"):
            if venue not in per_venue.index:
                self.venue_factors[venue] = {stat: 1.0 for stat in PROP_STATS}
                continue
            venue_minutes = float(minutes_by_venue.get(venue, 0.0))
            self.venue_factors[venue] = {
                stat: (
                    (float(per_venue.loc[venue, stat]) / venue_minutes * 90.0)
                    / overall_per90[stat]
                    if venue_minutes and overall_per90[stat]
                    else 1.0
                )
                for stat in PROP_STATS
            }

        # Per-player shrunk rates and a recent-form minutes expectation.
        self.players = {}
        frame = frame.sort_values(["date", "match_id"])
        for player, rows in frame.groupby("player"):
            minutes = float(rows["minutes"].sum())
            group = str(rows["group"].iat[0])
            baseline = self.baselines.get(group) or {
                stat: 0.0 for stat in PROP_STATS
            }
            weight = minutes / (minutes + self.SHRINKAGE_MINUTES)
            per90 = {}
            for stat in PROP_STATS:
                raw = float(rows[stat].sum()) / minutes * 90.0 if minutes else 0.0
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
        if stat not in PROP_STATS:
            raise KeyError(f"Unknown prop stat {stat!r}. Known: {PROP_STATS}")
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
