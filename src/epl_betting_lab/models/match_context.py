"""Match context: what this fixture adds to the season ratings.

The goals model rates each club's attack and defence over a season of
matches, with one league-wide home advantage. That is the strength. This
module adds what the fixture itself says, each part a multiplier on the two
expected-goal figures and nothing else, so every market the card prices off
the score matrix (1X2, draw-no-bet, double chance, 2.5, both teams to score,
team totals) moves together and none can disagree with another:

  home edge     the club's own home advantage against the league's, over its
                last two seasons, shrunk at `HOME_EDGE_SHRINKAGE` home matches
                and clamped to `HOME_EDGE_CLAMP`
  form          each club's last `FORM_GAMES` league matches (expected goals
                where the data has them, goals where it does not, each
                divided by the league's venue mean so a run of away games
                does not read as a slump) against its own level over the fit
                window, shrunk at `FORM_SHRINKAGE` games so five games keep
                a quarter of the move, clamped to `FORM_CLAMP`
  availability  who is missing (the official fantasy game's injury and
                suspension list, which is Opta's), weighted by each player's
                share of his club's expected goal involvement (attackers) or
                minutes (defenders and goalkeepers) among the club's regulars;
                half the missing share comes off the attack, floored at
                `AVAILABILITY_FLOOR`, and half the missing defensive share
                goes onto what the club concedes, capped at
                `AVAILABILITY_CEILING`

Every constant is this lab's choice, made before any price was read, and the
walk-forward measurements do not apply the context unless asked, so every
committed measurement stands. Rest and fixture congestion are deliberately
absent: they were measured on this data and added nothing.

`PoissonGoalsModel.project_fixtures(fixtures, context=...)` applies it to the
card; `MatchContext.layers` prices the same fixture one layer at a time for
the public game page, ending exactly at the card's number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HOME_EDGE_SEASONS_MATCHES = 76
HOME_EDGE_SHRINKAGE = 40
HOME_EDGE_CLAMP = (0.9, 1.1)

FORM_GAMES = 5
FORM_WINDOW = 38
FORM_SHRINKAGE = 15
FORM_CLAMP = (0.9, 1.1)

AVAILABILITY_WEIGHT = 0.5
AVAILABILITY_FLOOR = 0.85
AVAILABILITY_CEILING = 1.15
#: A regular is a player with at least this share of his club's most-used
#: player's minutes. Squads carry thirty names; the sheet carries eleven.
REGULAR_MINUTES_SHARE = 0.4
#: A flagged player with no stated chance is read at this chance.
DOUBTFUL_DEFAULT_CHANCE = 0.5

#: The layers in the order the card applies them. `strength` is the plain
#: model; each later key is the multiplier that layer adds.
LAYER_KEYS = ("strength", "home_edge", "form", "availability")
LAYER_LABELS = {
    "strength": "Season strength",
    "home_edge": "Home edge",
    "form": "Last five",
    "availability": "Who is missing",
}

ATTACK_POSITIONS = {"MID", "FWD"}
DEFENCE_POSITIONS = {"GKP", "GK", "DEF"}


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    low, high = bounds
    if not math.isfinite(value):
        return 1.0
    return float(min(max(value, low), high))


@dataclass(frozen=True)
class TeamContext:
    """One club's multipliers. `home_edge` applies only when it plays at home."""

    home_edge: float = 1.0
    attack_form: float = 1.0
    defence_form: float = 1.0
    attack_available: float = 1.0
    defence_available: float = 1.0
    missing: tuple[str, ...] = ()
    form_games: int = 0
    home_matches: int = 0


@dataclass(frozen=True)
class Adjusted:
    home_xg: float
    away_xg: float
    home_factor: float
    away_factor: float


@dataclass
class MatchContext:
    teams: dict[str, TeamContext] = field(default_factory=dict)
    #: Which parts are switched on; a part that is off multiplies by 1.
    parts: tuple[str, ...] = ("home_edge", "form", "availability")
    #: Where the availability list came from, for the notes; "" when none.
    availability_source: str = ""
    availability_note: str = ""

    def team(self, name: str) -> TeamContext:
        return self.teams.get(name, TeamContext())

    def factors(self, home: str, away: str) -> dict[str, tuple[float, float]]:
        """{layer key: (home multiplier, away multiplier)} for one fixture."""
        h, a = self.team(home), self.team(away)
        out: dict[str, tuple[float, float]] = {}
        if "home_edge" in self.parts:
            out["home_edge"] = (h.home_edge, 1.0 / h.home_edge if h.home_edge else 1.0)
        if "form" in self.parts:
            out["form"] = (h.attack_form * a.defence_form, a.attack_form * h.defence_form)
        if "availability" in self.parts:
            out["availability"] = (h.attack_available * a.defence_available,
                                   a.attack_available * h.defence_available)
        return out

    def adjust(self, home: str, away: str, home_xg: float, away_xg: float) -> Adjusted:
        fh = fa = 1.0
        for mh, ma in self.factors(home, away).values():
            fh *= mh
            fa *= ma
        return Adjusted(home_xg * fh, away_xg * fa, fh, fa)

    def layers(self, home: str, away: str, home_xg: float, away_xg: float, price) -> list[dict]:
        """The fixture priced one layer at a time. `price(home_xg, away_xg)`
        returns the model's probabilities for a pair of expectations; each
        layer records the home win chance, the draw, the away win chance,
        the expected goals and the change in home win chance from the layer
        before. The last layer is the card's own number."""
        rows: list[dict] = []
        xh, xa = float(home_xg), float(away_xg)
        previous = None
        for key in LAYER_KEYS:
            if key != "strength":
                part = self.factors(home, away).get(key)
                if part is None:
                    continue
                xh, xa = xh * part[0], xa * part[1]
            probs = price(xh, xa)
            win = float(probs["home_win"])
            rows.append({
                "key": key, "label": LAYER_LABELS[key],
                "homeWin": round(win, 4), "draw": round(float(probs["draw"]), 4),
                "awayWin": round(float(probs["away_win"]), 4),
                "delta": None if previous is None else round(win - previous, 4),
                "homeGoals": round(xh, 2), "awayGoals": round(xa, 2),
            })
            previous = win
        return rows

    def table(self) -> list[dict]:
        """Every club's multipliers, for the ratings page."""
        return [
            {"team": team, "homeEdge": round(t.home_edge, 3), "attackForm": round(t.attack_form, 3),
             "defenceForm": round(t.defence_form, 3), "attackAvailable": round(t.attack_available, 3),
             "defenceAvailable": round(t.defence_available, 3), "missing": list(t.missing),
             "formGames": t.form_games, "homeMatches": t.home_matches}
            for team, t in sorted(self.teams.items())
        ]


# ---------- the parts ----------


def _scoring(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per match, what each side produced: expected goals where present, goals otherwise."""
    gh = pd.to_numeric(df["home_goals"], errors="coerce").to_numpy(dtype=float)
    ga = pd.to_numeric(df["away_goals"], errors="coerce").to_numpy(dtype=float)
    if "home_xg" in df.columns and "away_xg" in df.columns:
        xh = pd.to_numeric(df["home_xg"], errors="coerce").to_numpy(dtype=float)
        xa = pd.to_numeric(df["away_xg"], errors="coerce").to_numpy(dtype=float)
        gh = np.where(np.isnan(xh), gh, xh)
        ga = np.where(np.isnan(xa), ga, xa)
    return gh, ga


def _played(matches: pd.DataFrame) -> pd.DataFrame:
    df = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.sort_values("date", kind="stable").reset_index(drop=True)


def home_edge_factors(matches: pd.DataFrame, *, window: int = HOME_EDGE_SEASONS_MATCHES,
                      shrinkage: int = HOME_EDGE_SHRINKAGE,
                      clamp: tuple[float, float] = HOME_EDGE_CLAMP) -> dict[str, tuple[float, int]]:
    """{club: (home-edge multiplier, home matches it rests on)}.

    A club's home edge is its goal difference per game at home minus its goal
    difference per game away, halved, over its last `window` league matches;
    the league's is the mean of every club's. The deviation is shrunk toward
    zero at `shrinkage` home matches, turned into a multiplier through the
    league's goals per match (a deviation of a third of a goal on a
    2.8-goal match is about twelve percent), and clamped. The multiplier
    goes onto the club's expected goals at home and its inverse onto the
    visitor's, so the total barely moves and the split does.
    """
    df = _played(matches)
    if df.empty:
        return {}
    gh, ga = _scoring(df)
    df = df.assign(_gh=gh, _ga=ga)
    league_goals = float((df["_gh"] + df["_ga"]).mean()) or 2.6
    edges: dict[str, tuple[float, int]] = {}
    for team in sorted(set(df["home_team"]).union(df["away_team"])):
        rows = df[(df["home_team"] == team) | (df["away_team"] == team)].tail(window)
        home = rows[rows["home_team"] == team]
        away = rows[rows["away_team"] == team]
        if home.empty or away.empty:
            continue
        home_gd = float((home["_gh"] - home["_ga"]).mean())
        away_gd = float((away["_ga"] - away["_gh"]).mean())
        edges[team] = ((home_gd - away_gd) / 2.0, len(home))
    if not edges:
        return {}
    league = float(np.mean([e for e, _ in edges.values()]))
    out: dict[str, tuple[float, int]] = {}
    for team, (edge, n_home) in edges.items():
        deviation = (edge - league) * n_home / (n_home + shrinkage)
        out[team] = (_clamp(math.exp(deviation / league_goals), clamp), n_home)
    return out


def form_factors(matches: pd.DataFrame, *, games: int = FORM_GAMES, window: int = FORM_WINDOW,
                 shrinkage: int = FORM_SHRINKAGE,
                 clamp: tuple[float, float] = FORM_CLAMP) -> dict[str, tuple[float, float, int]]:
    """{club: (attack form, defence form, games the form rests on)}.

    Each club's last `games` league matches against its own last `window`:
    what it produced and what it allowed, each match's figure divided by the
    league's mean for that venue, so five away games read as five games and
    not as a slump. The ratio is shrunk toward one at `shrinkage` games and
    clamped. Attack form multiplies the club's expected goals; defence form
    multiplies what its opponent is expected to score.
    """
    df = _played(matches)
    if df.empty:
        return {}
    gh, ga = _scoring(df)
    mu_home, mu_away = float(np.nanmean(gh)) or 1.0, float(np.nanmean(ga)) or 1.0
    mu = (mu_home + mu_away) / 2.0
    df = df.assign(_gh=gh / mu_home * mu, _ga=ga / mu_away * mu)
    out: dict[str, tuple[float, float, int]] = {}
    for team in sorted(set(df["home_team"]).union(df["away_team"])):
        rows = df[(df["home_team"] == team) | (df["away_team"] == team)].tail(window)
        if len(rows) < games:
            continue
        at_home = rows["home_team"] == team
        produced = np.where(at_home, rows["_gh"], rows["_ga"]).astype(float)
        allowed = np.where(at_home, rows["_ga"], rows["_gh"]).astype(float)
        level_for, level_against = float(produced.mean()), float(allowed.mean())
        recent_for, recent_against = float(produced[-games:].mean()), float(allowed[-games:].mean())
        keep = games / (games + shrinkage)
        attack = 1.0 + (recent_for / level_for - 1.0) * keep if level_for > 0 else 1.0
        defence = 1.0 + (recent_against / level_against - 1.0) * keep if level_against > 0 else 1.0
        out[team] = (_clamp(attack, clamp), _clamp(defence, clamp), games)
    return out


def _chance(row: pd.Series) -> float:
    """How likely a player is to play, from the fantasy game's flag and stated chance."""
    status = str(row.get("status") or "").strip().lower()
    chance = row.get("chance_next_round")
    try:
        chance = None if chance is None or pd.isna(chance) else float(chance) / 100.0
    except (TypeError, ValueError):
        chance = None
    if status in ("", "a"):
        return 1.0 if chance is None else min(max(chance, 0.0), 1.0)
    if chance is not None:
        return min(max(chance, 0.0), 1.0)
    return DOUBTFUL_DEFAULT_CHANCE if status == "d" else 0.0


def availability_factors(availability: pd.DataFrame, *, weight: float = AVAILABILITY_WEIGHT,
                         floor: float = AVAILABILITY_FLOOR, ceiling: float = AVAILABILITY_CEILING,
                         regular_share: float = REGULAR_MINUTES_SHARE
                         ) -> dict[str, tuple[float, float, tuple[str, ...]]]:
    """{club: (attack multiplier, conceded multiplier, who is missing)}.

    The regulars are the players with at least `regular_share` of the club's
    most-used player's minutes. An attacker (midfielder or forward) weighs
    his expected goal involvement this season, falling back to his points;
    a defender or goalkeeper weighs his minutes. The missing share is the
    weight of the regulars who will not play, pro rata for a stated chance,
    over the weight of every regular. Half of it comes off the club's attack
    and half of the defensive share goes onto what it concedes.
    """
    if availability is None or availability.empty or "team" not in availability.columns:
        return {}
    df = availability.copy()
    for col in ("minutes", "total_points", "expected_goal_involvements"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0) if col in df.columns else 0.0
    df["position"] = df["position"].astype(str).str.upper() if "position" in df.columns else ""
    out: dict[str, tuple[float, float, tuple[str, ...]]] = {}
    for team, squad in df.groupby("team"):
        team = str(team).strip()
        if not team:
            continue
        top = float(squad["minutes"].max())
        regulars = squad[squad["minutes"] >= max(top * regular_share, 1.0)] if top > 0 else squad.iloc[0:0]
        if regulars.empty:
            continue
        attack_w = defence_w = attack_out = defence_out = 0.0
        missing: list[str] = []
        for _, row in regulars.iterrows():
            chance = _chance(row)
            pos = row["position"]
            if pos in ATTACK_POSITIONS:
                w = float(row["expected_goal_involvements"]) or max(float(row["total_points"]), 0.0) or 1.0
                attack_w += w
                attack_out += w * (1.0 - chance)
            elif pos in DEFENCE_POSITIONS:
                w = max(float(row["minutes"]), 1.0)
                defence_w += w
                defence_out += w * (1.0 - chance)
            else:
                continue
            if chance < 1.0:
                missing.append(str(row.get("player") or "").strip())
        attack_share = attack_out / attack_w if attack_w > 0 else 0.0
        defence_share = defence_out / defence_w if defence_w > 0 else 0.0
        out[team] = (max(floor, 1.0 - weight * attack_share), min(ceiling, 1.0 + weight * defence_share),
                     tuple(m for m in missing if m))
    return out


# ---------- building it ----------


def build_match_context(matches: pd.DataFrame, availability: pd.DataFrame | None = None, *,
                        parts: tuple[str, ...] = ("home_edge", "form", "availability"),
                        availability_source: str = "") -> MatchContext:
    """The context for every club the matches name, from the played matches
    (expected goals joined where the data has them) and the availability
    list. A club the list does not name has nobody missing; a part asked
    for without its data multiplies by one."""
    edges = home_edge_factors(matches) if "home_edge" in parts else {}
    form = form_factors(matches) if "form" in parts else {}
    avail = availability_factors(availability) if "availability" in parts and availability is not None else {}
    teams = sorted(set(edges) | set(form) | set(avail))
    out: dict[str, TeamContext] = {}
    for team in teams:
        edge, n_home = edges.get(team, (1.0, 0))
        attack_form, defence_form, n_form = form.get(team, (1.0, 1.0, 0))
        attack_av, defence_av, missing = avail.get(team, (1.0, 1.0, ()))
        out[team] = TeamContext(home_edge=edge, attack_form=attack_form, defence_form=defence_form,
                                attack_available=attack_av, defence_available=defence_av,
                                missing=missing, form_games=n_form, home_matches=n_home)
    note = ""
    if "availability" in parts and (availability is None or availability.empty):
        note = "No availability list reached this run, so nobody is read as missing."
    return MatchContext(teams=out, parts=tuple(parts), availability_source=availability_source,
                        availability_note=note)


def load_availability(path: Path | None) -> pd.DataFrame | None:
    """The availability list on disk, or None when there is none or it cannot be read."""
    if path is None or not Path(path).is_file():
        return None
    try:
        frame = pd.read_csv(path)
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError):
        return None
    return frame if "team" in frame.columns and "player" in frame.columns else None
