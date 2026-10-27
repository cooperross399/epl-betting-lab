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
                share of his club's expected goal involvement (attackers,
                floored at `ATTACK_WEIGHT_FLOOR` so a regular with none yet
                still counts a little and never by his points, which are
                another unit) or minutes (defenders and goalkeepers) among
                the club's regulars; half the missing share comes off the
                attack, floored at `AVAILABILITY_FLOOR`, and half the missing
                defensive share goes onto what the club concedes, capped at
                `AVAILABILITY_CEILING`. The list is read for the round the
                fixtures belong to (`round_in_progress`, see
                `providers/fpl_players.AVAILABILITY_FIELDS`) and refused once
                it is older than `AVAILABILITY_MAX_AGE_HOURS`, so a stale
                flag never prices a card as today's

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
from datetime import datetime, timezone
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
#: An attacking regular's weight is his expected goal involvement, never less
#: than this (in the same unit), so a holding midfielder with 0.00 so far
#: counts as a small part of the attack rather than falling back to his
#: points, which once gave him the largest weight in the club.
ATTACK_WEIGHT_FLOOR = 0.05
#: An availability list fetched longer ago than this is refused, and the
#: card prices every club at full strength and says so. The fetch runs before
#: every card; two days covers a run whose fetch failed without letting a
#: week-old suspension price a Friday card.
AVAILABILITY_MAX_AGE_HOURS = 48
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
        """Every club's multipliers, for the ratings page. `homeEdge` is the
        club's deviation from the league's home edge (multiplier minus one),
        which is what the pages print as a signed percent."""
        return [
            {"team": team, "homeEdge": round(t.home_edge - 1.0, 3), "attackForm": round(t.attack_form, 3),
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


def _stated(value: object) -> float | None:
    try:
        return None if value is None or pd.isna(value) else float(value) / 100.0
    except (TypeError, ValueError):
        return None


def _chance(row: pd.Series, this_round: bool = False) -> float:
    """How likely a player is to play, from the fantasy game's flag and stated
    chance. With `this_round` the chance for the round in progress is read
    where the list carries one; a list written before that column existed
    falls back to the next round's figure."""
    status = str(row.get("status") or "").strip().lower()
    chance = _stated(row.get("chance_this_round")) if this_round else None
    if chance is None:
        chance = _stated(row.get("chance_next_round"))
    if status in ("", "a"):
        return 1.0 if chance is None else min(max(chance, 0.0), 1.0)
    if chance is not None:
        return min(max(chance, 0.0), 1.0)
    return DOUBTFUL_DEFAULT_CHANCE if status == "d" else 0.0


def _round_in_progress(df: pd.DataFrame) -> bool:
    """What the fetch recorded: True when the fixtures still to play belong
    to the gameweek FPL calls current, so `chance_this_round` is the one."""
    if "round_in_progress" not in df.columns or df.empty:
        return False
    value = df["round_in_progress"].iloc[0]
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    try:
        return bool(value) and not pd.isna(value)
    except (TypeError, ValueError):
        return False


def availability_factors(availability: pd.DataFrame, *, weight: float = AVAILABILITY_WEIGHT,
                         floor: float = AVAILABILITY_FLOOR, ceiling: float = AVAILABILITY_CEILING,
                         regular_share: float = REGULAR_MINUTES_SHARE
                         ) -> dict[str, tuple[float, float, tuple[str, ...]]]:
    """{club: (attack multiplier, conceded multiplier, who is missing)}.

    The regulars are the players with at least `regular_share` of the club's
    most-used player's minutes. An attacker (midfielder or forward) weighs
    his expected goal involvement this season, never less than
    `ATTACK_WEIGHT_FLOOR` (one unit for every attacker: his points were once
    the fallback, and a regular with 0.00 involvement then outweighed the
    striker five to one); a defender or goalkeeper weighs his minutes. The
    missing share is the weight of the regulars who will not play, pro rata
    for a stated chance in the round the fixtures belong to, over the weight
    of every regular. Half of it comes off the club's attack and half of the
    defensive share goes onto what it concedes.
    """
    if availability is None or availability.empty or "team" not in availability.columns:
        return {}
    df = availability.copy()
    for col in ("minutes", "total_points", "expected_goal_involvements"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0) if col in df.columns else 0.0
    df["position"] = df["position"].astype(str).str.upper() if "position" in df.columns else ""
    this_round = _round_in_progress(df)
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
            chance = _chance(row, this_round)
            pos = row["position"]
            if pos in ATTACK_POSITIONS:
                w = max(float(row["expected_goal_involvements"]), ATTACK_WEIGHT_FLOOR)
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
                        availability_source: str = "", availability_note: str = "") -> MatchContext:
    """The context for every club the matches name, from the played matches
    (expected goals joined where the data has them) and the availability
    list. A club the list does not name has nobody missing; a part asked
    for without its data multiplies by one. `availability_note` is why no
    list was read (`read_availability` supplies it); with none given and no
    list, the note says so in general terms."""
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
        note = availability_note or "No availability list reached this run, so nobody is read as missing."
    return MatchContext(teams=out, parts=tuple(parts), availability_source=availability_source,
                        availability_note=note)


NO_LIST_NOTE = "No availability list reached this run, so nobody is read as missing."


def availability_stamp(frame: pd.DataFrame | None) -> str:
    """When the list was fetched (`retrieved_at`, UTC ISO 8601), or "" for a
    list written before the stamp existed."""
    if frame is None or frame.empty or "retrieved_at" not in frame.columns:
        return ""
    value = frame["retrieved_at"].dropna()
    return str(value.iloc[0]).strip() if len(value) else ""


def _parse_stamp(stamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def read_availability(path: Path | None, *, now: datetime | None = None,
                      max_age_hours: float = AVAILABILITY_MAX_AGE_HOURS) -> tuple[pd.DataFrame | None, str]:
    """The availability list on disk and why it was not read, as `(frame, note)`.

    `(frame, "")` for a list fetched within `max_age_hours` of `now`. Otherwise
    `(None, note)`: no file, a file that cannot be read, a file without a
    fetch stamp (written before `retrieved_at` existed, so its age is
    unknown), or one older than the bound. The fetch is soft and the file is
    carried from run to run, so without this a list fetched a week ago would
    price a card as today's; the note names the age so the card can say so.
    """
    if path is None or not Path(path).is_file():
        return None, NO_LIST_NOTE
    try:
        frame = pd.read_csv(path)
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError):
        return None, "The availability list on disk could not be read, so nobody is read as missing."
    if "team" not in frame.columns or "player" not in frame.columns:
        return None, "The availability list on disk is not in the expected shape, so nobody is read as missing."
    stamp = availability_stamp(frame)
    fetched = _parse_stamp(stamp) if stamp else None
    if fetched is None:
        return None, "The availability list on disk carries no fetch time, so its age is unknown and nobody is read as missing."
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    age_hours = (moment - fetched).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        return None, (f"The availability list was fetched {age_hours:.0f} hours ago ({stamp}), past the "
                      f"{max_age_hours:.0f}-hour bound, so nobody is read as missing.")
    return frame, ""


def load_availability(path: Path | None, *, now: datetime | None = None) -> pd.DataFrame | None:
    """`read_availability` without the note: the list, or None when it is
    missing, unreadable, unstamped or older than `AVAILABILITY_MAX_AGE_HOURS`."""
    return read_availability(path, now=now)[0]
